"""Rebuild the Cash tab of output/desk_tickets.html from the live shop data.

Run from the hw 5 folder after any payment:  .venv/bin/python backend/cash_report.py
Every number comes from the MCP server (the same one the agents use). The starting balance is the one the
reset reported in the audit trail, so it is "the balance right after the reset". The ending balance is
read from cash_accounts and checked against starting balance minus the payments made.
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import Client

from audit import AUDIT_PATH
from people import display_name
from tools import ROOT, mcp_config

PAGE = ROOT / "output" / "desk_tickets.html"
TICKETS = (101, 102, 103)
usd = lambda n: f"${abs(n):,.2f}"
signed = lambda n: ("−" if n < 0 else "+") + usd(n)


def starting_balance() -> tuple[float, str]:
    """The checking balance the most recent reset reported, and when."""
    entries = json.loads(AUDIT_PATH.read_text())
    resets = [e for e in entries if e["event"] == "human_action" and e["detail"].get("action") == "reset_database"]
    if not resets:
        raise SystemExit("no reset found in the audit trail")
    last = resets[-1]
    return last["detail"]["result"]["checking_balance"], last["time"]


async def fetch() -> dict:
    async with Client(mcp_config()) as shop:
        get = lambda name, args=None: shop.call_tool(name, args or {}, raise_on_error=True)
        return {
            "cash": (await get("check_cash", {"account": "checking"})).data["accounts"][0],
            "payments": (await get("list_payments")).data["payments"],
            "approvals": (await get("list_approvals")).data["approvals"],
            "tickets": (await get("list_tickets")).data["tickets"],
            "invoices": (await get("list_invoices")).data["invoices"],
            "leases": (await get("list_leases")).data["leases"],
            "vendors": (await get("list_vendors")).data["vendors"],
        }


def what(p: dict, d: dict) -> str:
    if p["kind"] == "invoice":
        inv = next((i for i in d["invoices"] if i["id"] == p["ref_id"]), None)
        return f"Paid invoice {p['ref_id']} to {inv['vendor_name']}" + (f" ({inv['description']})" if inv else "")
    if p["kind"] == "rent":
        ls = next((l for l in d["leases"] if l["id"] == p["ref_id"]), None)
        return f"Paid rent for lease {p['ref_id']}" + (f", {ls['space_name']} to {ls['landlord']}" if ls else "")
    vendor = next((v for v in d["vendors"] if v["id"] == p["ref_id"]), None)
    return f"Purchase order to {vendor['name'] if vendor else 'vendor ' + str(p['ref_id'])}" + (f": {p['reason']}" if p.get("reason") else "")


def build(d: dict) -> str:
    start, start_time = starting_balance()
    pays = d["payments"]
    spent = sum(p["amount"] for p in pays)
    ending = d["cash"]["balance"]
    ok = abs((start - spent) - ending) < 0.005
    pending = [a for a in d["approvals"] if a["status"] == "pending"]
    ticket = {t["id"]: t for t in d["tickets"]}

    # the running balance after each payment
    bal, rows = start, []
    for n, p in enumerate(pays, 1):
        bal -= p["amount"]
        rows.append((n, p, bal))

    item_rows = [f'<tr class="hl"><td>Start</td><td>—</td><td>Checking balance right after the database reset ({escape(start_time[:19].replace("T", " "))} UTC)</td>'
                 f'<td class="num">—</td><td class="num">{usd(start)}</td></tr>']
    for n, p, after in rows:
        tid = p.get("ticket_id")
        item_rows.append(
            f'<tr><td>{n}</td><td class="mono">{"#" + str(tid) if tid else "—"}</td>'
            f'<td>{escape(what(p, d))}. Approved by {escape(display_name(p["approved_by"]))} on {escape(p["paid_at"])}.</td>'
            f'<td class="num">{signed(-p["amount"])}</td><td class="num">{usd(after)}</td></tr>')
    if not pays:
        item_rows.append('<tr><td>—</td><td>—</td><td><i>No payment has been made yet. Nothing has moved out of checking.</i></td><td class="num">$0.00</td><td class="num">' + usd(start) + '</td></tr>')
    item_rows.append(f'<tr class="hl"><td>End</td><td>—</td><td>Checking balance now, read from <span class="mono">cash_accounts</span></td><td class="num">{signed(-spent) if spent else "$0.00"}</td><td class="num"><b>{usd(ending)}</b></td></tr>')

    per_ticket = []
    for tid in TICKETS:
        t = ticket.get(tid)
        mine = [(n, p, after) for n, p, after in rows if p.get("ticket_id") == tid]
        wait = [a for a in pending if a["ticket_id"] == tid]
        status = t["status"] if t else "unknown"
        resolved = status == "resolved"
        if mine:
            lines = "".join(f'<li>{escape(what(p, d))}: <b>{signed(-p["amount"])}</b> (payment {n}, approved by {escape(display_name(p["approved_by"]))}); checking was {usd(after)} afterwards</li>' for n, p, after in mine)
            total = sum(p["amount"] for _, p, _ in mine)
            change = f'<p>Cash out for this ticket: <b>{signed(-total)}</b>.</p><ul>{lines}</ul>'
        else:
            change = '<p><b>No cash change.</b> ' + ('No payment was needed for this ticket.' if resolved else 'No payment has been made for this ticket yet.') + '</p>'
        if wait:
            change += '<ul>' + "".join(f'<li>Waiting for a human, not yet cash: approval {a["id"]}, {escape(a["kind"])} {a["ref_id"]}, <b>{usd(a["amount"])}</b>. {escape(a["reason"] or "")}</li>' for a in wait) + '</ul>'
        pill = f'<span class="pill">{escape(status)}</span>'
        note = "" if resolved else '<p class="small">Not resolved yet, so this is what has happened so far.</p>'
        per_ticket.append(f'<div class="box"><h4>Ticket {tid} · {escape(t["subject"]) if t else ""} {pill}</h4>{change}{note}</div>')

    check = (f'{usd(start)} start − {usd(spent)} paid = {usd(start - spent)}, and <span class="mono">cash_accounts</span> says {usd(ending)}. They match.'
             if ok else f'MISMATCH: {usd(start)} − {usd(spent)} = {usd(start - spent)}, but <span class="mono">cash_accounts</span> says {usd(ending)}.')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    pend_total = sum(a["amount"] for a in pending)
    return f'''<section class="panel" id="pcash" role="tabpanel" aria-labelledby="tab-cash" hidden>
    <h2>Cash · <span>checking account</span></h2>
    <p class="meta mono">money item by item · read from the working database through the MCP server at {now} UTC · cash only goes out, no revenue is modeled</p>

    <h3>The three numbers</h3>
    <div class="stats">
      <div class="stat"><div class="k">Starting balance</div><div class="v">{usd(start)}</div><div class="n">right after the reset</div></div>
      <div class="stat {"warn" if spent else ""}"><div class="k">Paid out so far</div><div class="v">{usd(spent)}</div><div class="n">{len(pays)} payment{"s" if len(pays) != 1 else ""} made</div></div>
      <div class="stat {"ok" if ok else "bad"}"><div class="k">Ending balance</div><div class="v">{usd(ending)}</div><div class="n">from <span class="mono">cash_accounts</span></div></div>
      <div class="stat warn"><div class="k">Waiting for a human</div><div class="v">{usd(pend_total)}</div><div class="n">{len(pending)} pending approval{"s" if len(pending) != 1 else ""}, not yet cash</div></div>
    </div>
    <div class="callout"><b>Check:</b> {check}</div>

    <h3>Item by item</h3>
    <table>
      <tr><th>#</th><th>Ticket</th><th>What happened to the cash</th><th class="num">Change</th><th class="num">Checking after</th></tr>
      {"".join(item_rows)}
    </table>

    <h3>Ticket by ticket: how the cash changed and why</h3>
    <div class="two">{"".join(per_ticket)}</div>
  </section>'''


def main() -> None:
    d = asyncio.run(fetch())
    html = PAGE.read_text()
    panel = build(d)
    new, n = re.subn(r'<section class="panel" id="pcash".*?</section>', lambda m: panel, html, count=1, flags=re.S)
    assert n == 1, "Cash panel not found"
    # the tab is no longer "coming later"
    new = re.sub(r'(<button class="tab" role="tab" id="tab-cash"[^>]*>\s*)<span class="lvl">[^<]*</span><span class="num">Cash</span><span class="sub">[^<]*</span>',
                 r'\1<span class="lvl">Level 4 · money</span><span class="num">Cash</span><span class="sub">start to end, item by item</span>', new, count=1)
    PAGE.write_text(new)
    start, _ = starting_balance()
    spent = sum(p["amount"] for p in d["payments"])
    print(f"start {usd(start)} | paid {usd(spent)} ({len(d['payments'])} payments) | ending {usd(d['cash']['balance'])} | match: {abs(start - spent - d['cash']['balance']) < 0.005}")


if __name__ == "__main__":
    main()
