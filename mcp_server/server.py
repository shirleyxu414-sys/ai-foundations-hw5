"""Campus Customs MCP server.

Exposes the shop database (data/campus_customs_new.db) to the agent team as MCP tools.
Every answer comes from the database; nothing is made up. The original
data/campus_customs.db is never opened here except to reset the working copy.

Run (later): python mcp_server/server.py
"""

import os
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
WORKING_DB = Path(os.environ.get("CAMPUS_DB", ROOT / "data" / "campus_customs_new.db"))

mcp = FastMCP("campus-customs")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(WORKING_DB)
    conn.row_factory = sqlite3.Row
    return conn


def not_found(what: str) -> dict:
    return {"ok": False, "error": f"{what} not found in the database"}


def has_work_to_keep() -> bool:
    """True if the working copy holds a run worth keeping: a payment, an approval, or a ticket that has moved on."""
    if not WORKING_DB.exists():
        return False
    with closing(connect()) as conn:
        kept = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] > 0
        kept = kept or conn.execute("SELECT COUNT(*) FROM tickets WHERE status != 'open'").fetchone()[0] > 0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'approvals'").fetchone():
            kept = kept or conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] > 0
    return kept


def reset_database() -> str | None:
    """Restore the working copy to the original values. Call before a full run.

    A finished run is never lost silently: if the working copy holds payments, approvals or moved-on tickets,
    it is first copied to a backups folder next to it. Returns the backup's path, or None if there was nothing to keep.
    """
    backup = None
    if has_work_to_keep():
        folder = WORKING_DB.parent / "backups"
        folder.mkdir(exist_ok=True)
        backup = folder / f"{WORKING_DB.stem}_before_reset_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db"
        shutil.copy2(WORKING_DB, backup)
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    return str(backup) if backup else None


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Read one ticket from the board, with its linked invoice (and that invoice's vendor) and
    its linked lease. Shows whether the invoice is overdue and how many days until rent is due,
    both measured against the shop's 'today' (desk.date_today), and every payment approval raised for
    this ticket with its status and, once paid, the payment that settled it."""
    with closing(connect()) as conn:
        today = conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not ticket:
            return not_found(f"ticket {ticket_id}")
        out = {"ok": True, "date_today": today, "ticket": dict(ticket),
               "invoice": None, "vendor": None, "lease": None}
        if ticket["invoice_id"] is not None:
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (ticket["invoice_id"],)).fetchone()
            if inv:
                out["invoice"] = {**dict(inv),
                                  "overdue": inv["status"] != "paid" and inv["due_date"] < today}
                vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (inv["vendor_id"],)).fetchone()
                out["vendor"] = dict(vendor) if vendor else None
        if ticket["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)).fetchone()
            if lease:
                days = (date.fromisoformat(lease["next_due"]) - date.fromisoformat(today)).days
                out["lease"] = {**dict(lease), "days_until_due": days}
        # The money history for this ticket, so nobody has to guess whether it was already paid. After rent
        # is paid, the lease's next_due moves forward a month, which can look like a mismatch with the ticket text.
        with closing(board()) as b:
            decisions = [dict(r) for r in b.execute(
                "SELECT author, note, created_at FROM ticket_log WHERE ticket_id = ? AND author LIKE 'human:%' ORDER BY id", (ticket_id,))]
            approvals = [dict(a) for a in b.execute(
                "SELECT id AS approval_id, kind, ref_id, amount, status, requested_by, sku, qty, received_at, received_by, payment_id FROM approvals "
                "WHERE ticket_id = ? ORDER BY id", (ticket_id,))]
            for a in approvals:
                pay = b.execute("SELECT id, paid_at, approved_by FROM payments WHERE id = ?",
                                (a["payment_id"],)).fetchone() if a["payment_id"] else None
                a["paid"] = {"payment_id": pay["id"], "paid_at": pay["paid_at"], "approved_by": pay["approved_by"]} if pay else None
        out["approvals"] = approvals
        out["human_decisions"] = decisions
        if out["lease"]:
            paid_rent = next((a for a in approvals if a["kind"] == "rent" and a["ref_id"] == ticket["lease_id"] and a["paid"]), None)
            if paid_rent:
                out["lease"]["rent_paid_note"] = (
                    f"Rent for this lease was already paid for this ticket on {paid_rent['paid']['paid_at']} "
                    f"(payment {paid_rent['paid']['payment_id']}, ${paid_rent['amount']:,.2f}, approval {paid_rent['approval_id']}). "
                    f"Paying rent moves next_due forward one month, so next_due is now {out['lease']['next_due']}; "
                    "that is why it no longer matches the ticket text. Nothing further is owed for this ticket.")
        return out


@mcp.tool
def check_stock(sku: str, size: str, qty_needed: int | None = None) -> dict:
    """Check how many units of a SKU in one size are on hand (inventory table). If qty_needed is
    given, also report how many units short we are. Reports a SKU or size that does not exist."""
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT * FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
        if not row:
            known = [r["size"] for r in conn.execute(
                "SELECT size FROM inventory WHERE sku = ? ORDER BY size", (sku,))]
            return {**not_found(f"sku {sku} size {size}"), "sizes_on_file_for_sku": known}
        out = {"ok": True, **dict(row)}
        if qty_needed is not None:
            out["qty_needed"] = qty_needed
            out["shortfall"] = max(0, qty_needed - row["qty"])
        return out


@mcp.tool
def check_margin(sku: str, offered_unit_price: float) -> dict:
    """Check a proposed selling price for a SKU against its unit cost and list price (pricing
    table): margin per unit, margin percent of the offered price, and discount off list price.
    The offered price is supplied by the caller; cost and list price come from the database."""
    if offered_unit_price <= 0:
        return {"ok": False, "error": "offered_unit_price must be greater than zero"}
    with closing(connect()) as conn:
        p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if not p:
            return not_found(f"pricing for sku {sku}")
        margin = offered_unit_price - p["unit_cost"]
        return {
            "ok": True, "sku": sku,
            "unit_cost": p["unit_cost"], "list_price": p["list_price"],
            "offered_unit_price": offered_unit_price,
            "margin_per_unit": round(margin, 2),
            "margin_pct": round(100 * margin / offered_unit_price, 1),
            "discount_pct_off_list": round(100 * (1 - offered_unit_price / p["list_price"]), 1),
            "below_cost": margin < 0,
        }


# ---------------------------------------------------------------------------
# Problem 5 tools. These tables are created on first use in the working copy;
# reset_database() wipes them with everything else, so a reset also clears the board.
# ---------------------------------------------------------------------------

TICKET_STATUSES = ("open", "in_progress", "waiting_approval", "resolved")

BOARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, ref_id INTEGER NOT NULL,
    ticket_id INTEGER, amount REAL NOT NULL, account TEXT NOT NULL, reason TEXT,
    requested_by TEXT, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
    sku TEXT, qty INTEGER, received_at TEXT, received_by TEXT, payment_id INTEGER);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL, audience TEXT NOT NULL,
    message TEXT NOT NULL, author TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ticket_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL, author TEXT NOT NULL,
    note TEXT NOT NULL, created_at TEXT NOT NULL);
"""


def board() -> sqlite3.Connection:
    conn = connect()
    conn.executescript(BOARD_SCHEMA)
    have = {r["name"] for r in conn.execute("PRAGMA table_info(approvals)")}
    for col, kind in (("sku", "TEXT"), ("qty", "INTEGER"), ("received_at", "TEXT"), ("received_by", "TEXT"),
                      ("payment_id", "INTEGER")):
        if col not in have:  # a board created before purchase orders could be received
            conn.execute(f"ALTER TABLE approvals ADD COLUMN {col} {kind}")
            if col == "qty":  # old purchase orders only said "(purchase order: 1 x CC-TEE-WHITE)" in their reason
                for row in conn.execute("SELECT id, reason FROM approvals WHERE kind = 'purchase_order' AND qty IS NULL").fetchall():
                    m = re.search(r"purchase order: (\d+) x (\S+?)\)", row["reason"] or "")
                    if m:
                        conn.execute("UPDATE approvals SET qty = ?, sku = ? WHERE id = ?", (int(m.group(1)), m.group(2), row["id"]))
            conn.commit()
    # Link older approved approvals to the payment that settled them (same kind and id, oldest unlinked first).
    for a in conn.execute("SELECT id, kind, ref_id, amount FROM approvals WHERE status = 'approved' AND payment_id IS NULL ORDER BY id").fetchall():
        pay = conn.execute("SELECT id FROM payments WHERE kind = ? AND ref_id = ? AND amount = ? AND id NOT IN "
                           "(SELECT payment_id FROM approvals WHERE payment_id IS NOT NULL) ORDER BY id", (a["kind"], a["ref_id"], a["amount"])).fetchone()
        if pay:
            conn.execute("UPDATE approvals SET payment_id = ? WHERE id = ?", (pay["id"], a["id"]))
    conn.commit()
    return conn


def shop_now(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]


@mcp.tool
def list_tickets(status: str | None = None) -> dict:
    """List the tickets on the board (optionally only one status, e.g. 'open'), oldest first,
    with today's date (desk.date_today). Use get_ticket for the linked invoice and lease."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM tickets" + (" WHERE status = ?" if status else "") + " ORDER BY created_at, id",
            (status,) if status else ()).fetchall()
        return {"ok": True, "date_today": shop_now(conn), "tickets": [dict(r) for r in rows]}


@mcp.tool
def list_leases() -> dict:
    """List every lease (leases table) with its landlord, monthly rent and next due date, plus the
    days until it is due and whether it is late, both measured against desk.date_today."""
    with closing(connect()) as conn:
        today = shop_now(conn)
        out = []
        for lease in conn.execute("SELECT * FROM leases ORDER BY id"):
            days = (date.fromisoformat(lease["next_due"]) - date.fromisoformat(today)).days
            out.append({**dict(lease), "days_until_due": days, "late": days < 0})
        return {"ok": True, "date_today": today, "leases": out}


@mcp.tool
def list_payments() -> dict:
    """List every payment that has actually been made (payments table), oldest first, with the
    approval it came from and the ticket it was for. Empty until a human approves something."""
    with closing(board()) as conn:
        rows = conn.execute(
            "SELECT p.*, a.id AS approval_id, a.ticket_id, a.reason FROM payments p LEFT JOIN approvals a "
            "ON a.payment_id = p.id ORDER BY p.id").fetchall()
        return {"ok": True, "payments": [dict(r) for r in rows]}


@mcp.tool
def list_vendors() -> dict:
    """List every vendor with its specialty and lead time in days, and whether the vendor will
    ship new product right now (a vendor will not ship while an invoice to them is unpaid)."""
    with closing(connect()) as conn:
        out = []
        for v in conn.execute("SELECT * FROM vendors ORDER BY id"):
            unpaid = conn.execute(
                "SELECT id, amount, due_date FROM invoices WHERE vendor_id = ? AND status != 'paid'",
                (v["id"],)).fetchall()
            out.append({**dict(v), "unpaid_invoices": [dict(i) for i in unpaid],
                        "will_ship": not unpaid})
        return {"ok": True, "date_today": shop_now(conn), "vendors": out}


@mcp.tool
def list_invoices(status: str | None = None) -> dict:
    """List invoices owed to vendors (optionally only one status, e.g. 'open' or 'paid'), each
    with the vendor name and whether it is overdue against desk.date_today."""
    with closing(connect()) as conn:
        today = shop_now(conn)
        sql = ("SELECT i.*, v.name AS vendor_name FROM invoices i "
               "JOIN vendors v ON v.id = i.vendor_id")
        rows = conn.execute(sql + (" WHERE i.status = ?" if status else "") + " ORDER BY i.id",
                            (status,) if status else ()).fetchall()
        return {"ok": True, "date_today": today,
                "invoices": [{**dict(r), "overdue": r["status"] != "paid" and r["due_date"] < today}
                             for r in rows]}


@mcp.tool
def check_cash(account: str | None = None) -> dict:
    """Read cash balances (cash_accounts table), plus the pending payment approvals already requested
    against each account (listed one by one, with the invoice or lease each one pays) and the free
    cash left after them: balance_after_pending = balance - pending_approvals_total. An invoice or
    rent that already has a pending approval is already covered by it; do not count it again."""
    with closing(board()) as conn:
        rows = conn.execute("SELECT * FROM cash_accounts" + (" WHERE name = ?" if account else ""),
                            (account,) if account else ()).fetchall()
        if not rows:
            return not_found(f"cash account {account}")
        accounts = []
        for r in rows:
            pending = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM approvals WHERE account = ? AND status = 'pending'",
                (r["name"],)).fetchone()[0]
            committed = [dict(a) for a in conn.execute(
                "SELECT id, kind, ref_id, ticket_id, amount FROM approvals "
                "WHERE account = ? AND status = 'pending' ORDER BY id", (r["name"],))]
            accounts.append({**dict(r), "pending_approvals_total": pending,
                             "pending_approvals": committed,  # what is already committed, so it is not counted twice
                             "balance_after_pending": r["balance"] - pending})
        return {"ok": True, "accounts": accounts}


@mcp.tool
def request_payment_approval(kind: str, ref_id: int, account: str, reason: str,
                             ticket_id: int | None = None, requested_by: str = "accounting",
                             sku: str | None = None, qty: int | None = None) -> dict:
    """Prepare a payment for HUMAN approval. kind is 'invoice' (ref_id = invoices.id), 'rent'
    (ref_id = leases.id) or 'purchase_order' (ref_id = vendors.id, plus sku and qty; the amount is
    qty x pricing.unit_cost). The amount is always computed from the database, never supplied by
    the caller. This does NOT move money. It refuses if the invoice is already paid, if a
    purchase order goes to a vendor with an unpaid invoice (it will not ship), if the account lacks
    the cash (balances never go negative), or if an identical request is already pending."""
    if kind not in ("invoice", "rent", "purchase_order"):
        return {"ok": False, "error": "kind must be 'invoice', 'rent' or 'purchase_order'"}
    with closing(board()) as conn:
        acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if not acct:
            return not_found(f"cash account {account}")
        if kind == "invoice":
            row = conn.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if not row:
                return not_found(f"invoice {ref_id}")
            if row["status"] == "paid":
                return {"ok": False, "error": f"invoice {ref_id} is already paid"}
            amount = row["amount"]
        elif kind == "purchase_order":
            if not sku or not qty or qty <= 0:
                return {"ok": False, "error": "a purchase_order needs sku and a qty above zero"}
            if not conn.execute("SELECT 1 FROM vendors WHERE id = ?", (ref_id,)).fetchone():
                return not_found(f"vendor {ref_id}")
            price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
            if not price:
                return not_found(f"pricing for sku {sku}")
            unpaid = conn.execute("SELECT id FROM invoices WHERE vendor_id = ? AND status != 'paid'",
                                  (ref_id,)).fetchall()
            if unpaid:
                return {"ok": False, "error": "vendor will not ship while an invoice to them is unpaid",
                        "unpaid_invoice_ids": [u["id"] for u in unpaid]}
            amount = round(qty * price["unit_cost"], 2)
            reason = f"{reason} (purchase order: {qty} x {sku})"
        else:
            row = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if not row:
                return not_found(f"lease {ref_id}")
            amount = row["monthly_rent"]
        if conn.execute("SELECT 1 FROM approvals WHERE kind = ? AND ref_id = ? AND status = 'pending'",
                        (kind, ref_id)).fetchone():
            return {"ok": False, "error": f"a pending approval for {kind} {ref_id} already exists"}
        if ticket_id is not None:
            done = conn.execute("SELECT id FROM approvals WHERE kind = ? AND ref_id = ? AND ticket_id = ? AND status = 'approved'",
                                (kind, ref_id, ticket_id)).fetchone()
            if done:  # without this, every rerun of a ticket would buy the same thing again
                return {"ok": False, "error": f"approval {done['id']} for this {kind} {ref_id} on ticket {ticket_id} "
                                              "was already approved and paid; do not request it again"}
        pending = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM approvals WHERE account = ? AND status = 'pending'",
            (account,)).fetchone()[0]
        if amount > acct["balance"] - pending:
            return {"ok": False, "error": "not enough cash", "amount": amount,
                    "balance": acct["balance"], "pending_approvals_total": pending}
        cur = conn.execute(
            "INSERT INTO approvals (kind, ref_id, ticket_id, amount, account, reason, requested_by, created_at, sku, qty)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, ref_id, ticket_id, amount, account, reason, requested_by, shop_now(conn),
             sku if kind == "purchase_order" else None, qty if kind == "purchase_order" else None))
        conn.commit()
        return {"ok": True, "approval_id": cur.lastrowid, "status": "pending", "kind": kind,
                "ref_id": ref_id, "amount": amount, "account": account,
                "note": "Waiting for a human. No money has moved."}


@mcp.tool
def draft_customer_message(ticket_id: int, message: str, author: str = "customer_service") -> dict:
    """Save a draft message for the ticket's requester on the board. Drafts are never sent:
    nothing is emailed and no vendor or customer is contacted."""
    with closing(board()) as conn:
        if not conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone():
            return not_found(f"ticket {ticket_id}")
        cur = conn.execute(
            "INSERT INTO drafts (ticket_id, audience, message, author, created_at) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, "requester", message, author, shop_now(conn)))
        conn.commit()
        return {"ok": True, "draft_id": cur.lastrowid, "sent": False}


@mcp.tool
def update_ticket(ticket_id: int, status: str, note: str, author: str) -> dict:
    """Set a ticket's status ('open', 'in_progress', 'waiting_approval' or 'resolved') and add a
    note to the ticket log saying who did what and why."""
    if status not in TICKET_STATUSES:
        return {"ok": False, "error": f"status must be one of {list(TICKET_STATUSES)}"}
    with closing(board()) as conn:
        if not conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone():
            return not_found(f"ticket {ticket_id}")
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.execute("INSERT INTO ticket_log (ticket_id, author, note, created_at) VALUES (?, ?, ?, ?)",
                     (ticket_id, author, note, shop_now(conn)))
        conn.commit()
        return {"ok": True, "ticket_id": ticket_id, "status": status}


LOW_STOCK_AT = 3  # units on hand at or below this count as "low"


@mcp.tool
def list_inventory(sku: str | None = None) -> dict:
    """List stock on hand (inventory table), optionally for one SKU, with every size. Each row is
    flagged out_of_stock (0 units) or low_stock (3 units or fewer) so Inventory can see what needs
    restocking without guessing."""
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM inventory" + (" WHERE sku = ?" if sku else "")
                            + " ORDER BY sku, size", (sku,) if sku else ()).fetchall()
        if sku and not rows:
            return not_found(f"sku {sku}")
        return {"ok": True, "low_stock_at": LOW_STOCK_AT,
                "items": [{**dict(r), "out_of_stock": r["qty"] == 0, "low_stock": r["qty"] <= LOW_STOCK_AT}
                          for r in rows]}


@mcp.tool
def get_pricing(sku: str | None = None) -> dict:
    """List unit cost and list price (pricing table), optionally for one SKU, with the margin per
    unit at list price. Use check_margin to test a different price."""
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM pricing" + (" WHERE sku = ?" if sku else "")
                            + " ORDER BY sku", (sku,) if sku else ()).fetchall()
        if sku and not rows:
            return not_found(f"pricing for sku {sku}")
        return {"ok": True, "pricing": [{**dict(r), "margin_at_list": round(r["list_price"] - r["unit_cost"], 2)}
                                        for r in rows]}


@mcp.tool
def list_approvals(status: str | None = None, ticket_id: int | None = None) -> dict:
    """List payment approval requests on the board (approvals table), optionally filtered by status
    ('pending', 'approved' or 'declined') or ticket. Shows what is still waiting for a human."""
    with closing(board()) as conn:
        sql, args = "SELECT * FROM approvals WHERE 1=1", []
        if status:
            sql, args = sql + " AND status = ?", args + [status]
        if ticket_id is not None:
            sql, args = sql + " AND ticket_id = ?", args + [ticket_id]
        return {"ok": True, "approvals": [dict(r) for r in conn.execute(sql + " ORDER BY id", args)]}


@mcp.tool
def list_drafts(ticket_id: int | None = None) -> dict:
    """List the customer message drafts saved on the board (drafts table), optionally for one
    ticket. Drafts are never sent."""
    with closing(board()) as conn:
        rows = conn.execute("SELECT * FROM drafts" + (" WHERE ticket_id = ?" if ticket_id is not None else "")
                            + " ORDER BY id", (ticket_id,) if ticket_id is not None else ()).fetchall()
        return {"ok": True, "drafts": [dict(r) for r in rows]}


def _next_month(day: str) -> str:
    d = date.fromisoformat(day)
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    last = (date(y + (m == 12), m % 12 + 1, 1) - date(y, m, 1)).days
    return date(y, m, min(d.day, last)).isoformat()


# HUMAN-ONLY: the backend removes these five from the agents' toolset (backend/tools.py), so only the
# dashboard, acting for a human, can call them. They are still MCP tools on this same server.
HUMAN_ONLY_TOOLS = ("execute_approved_payment", "decline_payment", "reset_shop_database", "receive_shipment",
                    "record_human_decision")


@mcp.tool
def execute_approved_payment(approval_id: int, approved_by: str) -> dict:
    """HUMAN ONLY. Make the payment for a pending approval after a person approved it. Refuses if
    approved_by is empty, the approval is not pending, or the account lacks the cash (balances never
    go negative). On success, in one transaction: adds a row to payments, lowers cash_accounts, and
    marks the invoice paid (or moves the lease's next_due forward one month for rent)."""
    if not approved_by.strip():
        return {"ok": False, "error": "approved_by must name the human who approved this payment"}
    with closing(board()) as conn:
        a = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if not a:
            return not_found(f"approval {approval_id}")
        if a["status"] != "pending":
            return {"ok": False, "error": f"approval {approval_id} is already {a['status']}"}
        acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (a["account"],)).fetchone()
        if a["amount"] > acct["balance"]:
            return {"ok": False, "error": "not enough cash", "amount": a["amount"], "balance": acct["balance"]}
        if a["kind"] == "invoice":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (a["ref_id"],)).fetchone()
            if not inv or inv["status"] == "paid":
                return {"ok": False, "error": f"invoice {a['ref_id']} is missing or already paid"}
        today = shop_now(conn)
        with conn:
            cur = conn.execute("INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                               "VALUES (?, ?, ?, ?, ?, ?)",
                               (a["kind"], a["ref_id"], a["amount"], a["account"], today, approved_by))
            conn.execute("UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
                         (a["amount"], today, a["account"]))
            if a["kind"] == "invoice":
                conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (a["ref_id"],))
            elif a["kind"] == "rent":
                lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (a["ref_id"],)).fetchone()
                conn.execute("UPDATE leases SET next_due = ? WHERE id = ?",
                             (_next_month(lease["next_due"]), a["ref_id"]))
            conn.execute("UPDATE approvals SET status = 'approved', payment_id = ? WHERE id = ?", (cur.lastrowid, approval_id))
        balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (a["account"],)).fetchone()[0]
        return {"ok": True, "approval_id": approval_id, "kind": a["kind"], "ref_id": a["ref_id"],
                "amount": a["amount"], "paid_at": today, "approved_by": approved_by,
                "balance_after": balance}


@mcp.tool
def decline_payment(approval_id: int, declined_by: str) -> dict:
    """HUMAN ONLY. Decline a pending payment approval. No money moves."""
    with closing(board()) as conn:
        a = conn.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if not a:
            return not_found(f"approval {approval_id}")
        if a["status"] != "pending":
            return {"ok": False, "error": f"approval {approval_id} is already {a['status']}"}
        conn.execute("UPDATE approvals SET status = 'declined' WHERE id = ?", (approval_id,))
        conn.commit()
        return {"ok": True, "approval_id": approval_id, "status": "declined", "declined_by": declined_by}


@mcp.tool
def reset_shop_database() -> dict:
    """HUMAN ONLY. Put the working database back to the original values (copies
    data/campus_customs.db over data/campus_customs_new.db). This also clears the board tables
    (approvals, drafts, ticket_log). Do it before a fresh run. If the working copy holds a finished or
    partly finished run, it is saved to data/backups/ first and the path is returned as `backup`."""
    backup = reset_database()
    with closing(connect()) as conn:
        balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()[0]
        return {"ok": True, "date_today": shop_now(conn), "checking_balance": balance, "backup": backup}


@mcp.tool
def receive_shipment(approval_id: int, received_by: str, size: str | None = None) -> dict:
    """HUMAN ONLY. A person confirms that a paid purchase order has arrived. Adds the ordered quantity to
    inventory (the size comes from the ticket the order was for, or from `size`), and records who received it
    and when. Refuses an order that is not a paid purchase order, one already received, or an empty name."""
    if not received_by.strip():
        return {"ok": False, "error": "received_by must name the person who confirmed the delivery"}
    with closing(board()) as conn:
        a = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if not a:
            return not_found(f"approval {approval_id}")
        if a["kind"] != "purchase_order" or a["status"] != "approved":
            return {"ok": False, "error": f"approval {approval_id} is not a paid purchase order"}
        if a["received_at"]:
            return {"ok": False, "error": f"approval {approval_id} was already received on {a['received_at']}"}
        if not a["sku"] or not a["qty"]:
            return {"ok": False, "error": f"approval {approval_id} has no sku and quantity on record"}
        if size is None and a["ticket_id"] is not None:
            t = conn.execute("SELECT size FROM tickets WHERE id = ?", (a["ticket_id"],)).fetchone()
            size = t["size"] if t else None
        if not size:
            return {"ok": False, "error": "no size on record for this order; pass size"}
        row = conn.execute("SELECT qty FROM inventory WHERE sku = ? AND size = ?", (a["sku"], size)).fetchone()
        if not row:
            return not_found(f"sku {a['sku']} size {size}")
        today = shop_now(conn)
        with conn:
            conn.execute("UPDATE inventory SET qty = qty + ? WHERE sku = ? AND size = ?", (a["qty"], a["sku"], size))
            conn.execute("UPDATE approvals SET received_at = ?, received_by = ? WHERE id = ?", (today, received_by, approval_id))
            if a["ticket_id"] is not None:
                conn.execute("INSERT INTO ticket_log (ticket_id, author, note, created_at) VALUES (?, ?, ?, ?)",
                             (a["ticket_id"], f"human:{received_by}",
                              f"Received purchase order {approval_id}: {a['qty']} x {a['sku']} size {size}.", today))
        return {"ok": True, "approval_id": approval_id, "sku": a["sku"], "size": size, "qty_received": a["qty"],
                "qty_on_hand_before": row["qty"], "qty_on_hand_after": row["qty"] + a["qty"],
                "received_by": received_by, "received_at": today}


@mcp.tool
def record_human_decision(ticket_id: int, decided_by: str, decision: str) -> dict:
    """HUMAN ONLY. A person records a decision about a ticket (for example how it should end). Saved in the
    ticket log as 'human:<name>' and shown to the agents as `human_decisions` when they read the ticket."""
    if not decided_by.strip() or not decision.strip():
        return {"ok": False, "error": "decided_by and decision must both be filled in"}
    with closing(board()) as conn:
        if not conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone():
            return not_found(f"ticket {ticket_id}")
        conn.execute("INSERT INTO ticket_log (ticket_id, author, note, created_at) VALUES (?, ?, ?, ?)",
                     (ticket_id, f"human:{decided_by}", decision.strip(), shop_now(conn)))
        conn.commit()
        return {"ok": True, "ticket_id": ticket_id, "decided_by": decided_by}


if __name__ == "__main__":
    mcp.run()
