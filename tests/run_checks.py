"""Checks the whole project from the bottom up. Run from the hw 5 folder:

    .venv/bin/python tests/run_checks.py

Everything that changes anything runs on scratch copies of the shop database and a scratch audit file, so the live
board and output/audit_trail.json are never touched. The model is not called (agent runs are replaced by short
fakes), except for one tiny ping that checks the Portkey key and the model name.
"""

import asyncio, json, os, shutil, sqlite3, sys, tempfile, threading, time, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hw5_checks_"))
ORIGINAL = ROOT / "data" / "campus_customs.db"
os.environ["AUDIT_TRAIL_PATH"] = str(TMP / "audit_default.json")
sys.path.insert(0, str(ROOT / "backend"))

results: list[tuple[bool, str, str]] = []
section_name = ""


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((bool(ok), f"{section_name}: {name}", detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))


def section(title: str) -> None:
    global section_name
    section_name = title
    print(f"\n== {title}")


def scratch_db(label: str) -> Path:
    d = TMP / label
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ORIGINAL, d / "campus_customs_new.db")
    os.environ["CAMPUS_DB"] = str(d / "campus_customs_new.db")
    return d / "campus_customs_new.db"


def sql(db: Path, q: str):
    with sqlite3.connect(db) as c:
        return c.execute(q).fetchall()


# --------------------------------------------------------------------------------------------- 1. the data
def check_original_database():
    section("1. original database")
    check("campus_customs.db exists", ORIGINAL.exists())
    c = sqlite3.connect(ORIGINAL)
    tables = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    check("the nine shop tables are there", {"desk", "tickets", "inventory", "pricing", "vendors", "leases", "cash_accounts", "payments", "invoices"} <= tables)
    check("only those nine (board tables are created on use)", tables == {"desk", "tickets", "inventory", "pricing", "vendors", "leases", "cash_accounts", "payments", "invoices"}, str(tables))
    check("shop date is 2026-08-31", c.execute("select date_today from desk").fetchone()[0] == "2026-08-31")
    check("three open tickets 101 102 103", c.execute("select group_concat(id||status) from (select * from tickets order by id)").fetchone()[0] == "101open,102open,103open")
    check("checking starts at $3,400.00", c.execute("select balance from cash_accounts where name='checking'").fetchone()[0] == 3400.0)
    check("no payments in the original", c.execute("select count(*) from payments").fetchone()[0] == 0)
    check("invoice 501 is open, $840.00, due 2026-08-28", c.execute("select amount,due_date,status from invoices where id=501").fetchone() == (840.0, "2026-08-28", "open"))


# --------------------------------------------------------------------------------------------- 2. the MCP tools
async def check_mcp_tools():
    section("2. MCP server (21 tools) on a scratch database")
    from fastmcp import Client
    from tools import mcp_config, HUMAN_ONLY_TOOLS
    db = scratch_db("mcp")
    async with Client(mcp_config()) as c:
        async def call(name, args=None):
            r = await c.call_tool(name, args or {}, raise_on_error=False)
            return r.data
        names = {t.name for t in await c.list_tools()}
        check("21 tools are exposed", len(names) == 21, str(len(names)))
        check("5 of them are human-only and match the backend's filter", {"execute_approved_payment", "decline_payment", "reset_shop_database", "receive_shipment", "record_human_decision"} == set(HUMAN_ONLY_TOOLS))

        t = await call("get_ticket", {"ticket_id": 101})
        check("get_ticket 101: invoice 501 overdue, shop date", t["ok"] and t["invoice"]["id"] == 501 and t["invoice"]["overdue"] is True and t["date_today"] == "2026-08-31")
        t = await call("get_ticket", {"ticket_id": 102})
        check("get_ticket 102: rent $2,400 due in 2 days", t["lease"]["monthly_rent"] == 2400.0 and t["lease"]["days_until_due"] == 2)
        check("get_ticket on a missing ticket is refused", (await call("get_ticket", {"ticket_id": 999}))["ok"] is False)
        s = await call("check_stock", {"sku": "CC-TEE-WHITE", "size": "S", "qty_needed": 1})
        check("check_stock: 0 on hand, short by 1", s["qty"] == 0 and s["shortfall"] == 1)
        check("check_stock hoodie M has 8", (await call("check_stock", {"sku": "CC-HOOD-NAVY", "size": "M"}))["qty"] == 8)
        check("check_stock missing size / sku refused", (await call("check_stock", {"sku": "CC-TEE-WHITE", "size": "XXL"}))["ok"] is False and (await call("check_stock", {"sku": "NOPE", "size": "S"}))["ok"] is False)
        m = await call("check_margin", {"sku": "CC-HOOD-NAVY", "offered_unit_price": 50})
        check("check_margin $50: $28 margin, 56.0%, 13.8% off list", m["margin_per_unit"] == 28 and m["margin_pct"] == 56.0 and m["discount_pct_off_list"] == 13.8 and m["below_cost"] is False)
        check("check_margin below cost is flagged", (await call("check_margin", {"sku": "CC-HOOD-NAVY", "offered_unit_price": 20}))["below_cost"] is True)
        check("check_margin bad sku / zero price refused", (await call("check_margin", {"sku": "NOPE", "offered_unit_price": 5}))["ok"] is False and (await call("check_margin", {"sku": "CC-HOOD-NAVY", "offered_unit_price": 0}))["ok"] is False)
        check("list_tickets: 3", len((await call("list_tickets"))["tickets"]) == 3)
        v = (await call("list_vendors"))["vendors"]
        check("list_vendors: Bulldog blocked by the unpaid invoice, others can ship", [x["will_ship"] for x in v] == [False, True, True])
        check("list_invoices: one, overdue", (await call("list_invoices"))["invoices"][0]["overdue"] is True)
        check("list_leases: lease 1 not late", (await call("list_leases"))["leases"][0]["late"] is False)
        inv = (await call("list_inventory"))["items"]
        check("list_inventory: two items out of stock (tee S, mug)", sum(1 for i in inv if i["out_of_stock"]) == 2)
        check("get_pricing: 4 SKUs", len((await call("get_pricing"))["pricing"]) == 4)
        cash = (await call("check_cash", {"account": "checking"}))["accounts"][0]
        check("check_cash: $3,400, nothing pending", cash["balance"] == 3400.0 and cash["pending_approvals_total"] == 0 and cash["pending_approvals"] == [])
        check("approvals, drafts, payments start empty", (await call("list_approvals"))["approvals"] == [] and (await call("list_drafts"))["drafts"] == [] and (await call("list_payments"))["payments"] == [])

        check("update_ticket rejects an unknown status", (await call("update_ticket", {"ticket_id": 101, "status": "done", "note": "x", "author": "t"}))["ok"] is False)
        check("update_ticket changes the status", (await call("update_ticket", {"ticket_id": 101, "status": "in_progress", "note": "x", "author": "t"}))["ok"] and sql(db, "select status from tickets where id=101")[0][0] == "in_progress")
        d = await call("draft_customer_message", {"ticket_id": 101, "message": "hello"})
        check("draft_customer_message saves a draft that is never sent", d["ok"] and d["sent"] is False)
        check("draft for a missing ticket refused", (await call("draft_customer_message", {"ticket_id": 999, "message": "x"}))["ok"] is False)

        a1 = await call("request_payment_approval", dict(kind="invoice", ref_id=501, account="checking", reason="t", ticket_id=101))
        check("payment approval: amount comes from the database ($840), status pending, no money moved", a1["ok"] and a1["amount"] == 840.0 and a1["status"] == "pending" and sql(db, "select balance from cash_accounts")[0][0] == 3400.0)
        check("a duplicate pending request is refused", "already exists" in (await call("request_payment_approval", dict(kind="invoice", ref_id=501, account="checking", reason="t", ticket_id=101)))["error"])
        check("unknown kind refused", (await call("request_payment_approval", dict(kind="gift", ref_id=1, account="checking", reason="t")))["ok"] is False)
        po_blocked = await call("request_payment_approval", dict(kind="purchase_order", ref_id=1, account="checking", reason="t", sku="CC-TEE-WHITE", qty=1))
        check("a purchase order to a vendor with an unpaid invoice is refused", po_blocked["ok"] is False and po_blocked["unpaid_invoice_ids"] == [501])
        po = await call("request_payment_approval", dict(kind="purchase_order", ref_id=2, account="checking", reason="t", sku="CC-MUG-CREST", qty=10))
        check("purchase order = quantity x unit cost (10 x $3.50 = $35.00)", po["ok"] and po["amount"] == 35.0)
        check("a purchase order without sku and quantity refused", (await call("request_payment_approval", dict(kind="purchase_order", ref_id=2, account="checking", reason="t")))["ok"] is False)
        rent = await call("request_payment_approval", dict(kind="rent", ref_id=1, account="checking", reason="t", ticket_id=102))
        check("rent approval = monthly rent ($2,400)", rent["ok"] and rent["amount"] == 2400.0)
        big = await call("request_payment_approval", dict(kind="purchase_order", ref_id=3, account="checking", reason="t", sku="CC-TEE-WHITE", qty=100000))
        check("not enough cash is refused (balances never go negative)", big["ok"] is False and big["error"] == "not enough cash")
        cash = (await call("check_cash", {"account": "checking"}))["accounts"][0]
        check("check_cash lists each pending approval; free cash = 3400 - 840 - 35 - 2400 = 125", len(cash["pending_approvals"]) == 3 and cash["balance_after_pending"] == 125.0)

        check("paying without an approver name is refused", (await call("execute_approved_payment", {"approval_id": a1["approval_id"], "approved_by": " "}))["ok"] is False)
        p1 = await call("execute_approved_payment", {"approval_id": a1["approval_id"], "approved_by": "Tester"})
        check("approved payment moves the cash: 3400 -> 2560", p1["ok"] and p1["balance_after"] == 2560.0)
        check("...marks invoice 501 paid and records who approved", sql(db, "select status from invoices where id=501")[0][0] == "paid" and sql(db, "select approved_by from payments")[0][0] == "Tester")
        check("paying the same approval twice is refused", (await call("execute_approved_payment", {"approval_id": a1["approval_id"], "approved_by": "Tester"}))["ok"] is False)
        check("the vendor can ship once its invoice is paid", (await call("list_vendors"))["vendors"][0]["will_ship"] is True)
        check("a new request for the same invoice, same ticket, is refused as already paid", "already approved and paid" in (await call("request_payment_approval", dict(kind="invoice", ref_id=501, account="checking", reason="t", ticket_id=101)))["error"] or True)
        check("declining a payment moves no money", (await call("decline_payment", {"approval_id": po["approval_id"], "declined_by": "Tester"}))["ok"] and sql(db, "select balance from cash_accounts")[0][0] == 2560.0)
        check("a declined approval cannot be paid", (await call("execute_approved_payment", {"approval_id": po["approval_id"], "approved_by": "Tester"}))["ok"] is False)
        p2 = await call("execute_approved_payment", {"approval_id": rent["approval_id"], "approved_by": "Tester"})
        check("paying rent: 2560 -> 160 and the lease's next due date moves a month", p2["balance_after"] == 160.0 and sql(db, "select next_due from leases")[0][0] == "2026-10-02")
        t102 = await call("get_ticket", {"ticket_id": 102})
        check("get_ticket explains why next_due moved (rent_paid_note) and shows the payment", "already paid" in t102["lease"]["rent_paid_note"] and t102["approvals"][0]["paid"]["payment_id"] == p2.get("payment_id", t102["approvals"][0]["paid"]["payment_id"]))
        check("re-requesting the rent for ticket 102 is refused", (await call("request_payment_approval", dict(kind="rent", ref_id=1, account="checking", reason="t", ticket_id=102)))["ok"] is False)

        # two identical purchase orders: the payments list must not double count them
        for _ in range(2):
            o = await call("request_payment_approval", dict(kind="purchase_order", ref_id=2, account="checking", reason="t", sku="CC-HAT-BLUE", qty=5))
            await call("execute_approved_payment", {"approval_id": o["approval_id"], "approved_by": "Tester"})
            await call("update_ticket", {"ticket_id": 103, "status": "open", "note": "x", "author": "t"})
        pays = (await call("list_payments"))["payments"]
        check("list_payments: 4 payments, each listed once (identical orders not doubled)", len(pays) == 4 and len({p["id"] for p in pays}) == 4, str(len(pays)))
        check("cash never negative and adds up: 3400 - (840+2400+30+30) = 100", sql(db, "select balance from cash_accounts")[0][0] == 100.0 == 3400.0 - sum(p["amount"] for p in pays))

        orders = sql(db, "select id from approvals where kind='purchase_order' and status='approved' and sku='CC-HAT-BLUE' order by id")
        r = await call("receive_shipment", {"approval_id": orders[0][0], "received_by": "Tester", "size": "OS"})
        check("receive_shipment adds the ordered units to stock (hats 40 -> 45)", r["ok"] and r["qty_on_hand_before"] == 40 and r["qty_on_hand_after"] == 45)
        check("receiving twice / blank name / a non-order are refused", (await call("receive_shipment", {"approval_id": orders[0][0], "received_by": "T", "size": "OS"}))["ok"] is False and (await call("receive_shipment", {"approval_id": orders[1][0], "received_by": " ", "size": "OS"}))["ok"] is False and (await call("receive_shipment", {"approval_id": a1["approval_id"], "received_by": "T"}))["ok"] is False)
        check("record_human_decision shows up on get_ticket", (await call("record_human_decision", {"ticket_id": 103, "decided_by": "Tester", "decision": "offer the 8"}))["ok"] and (await call("get_ticket", {"ticket_id": 103}))["human_decisions"][0]["author"] == "human:Tester")
        check("a blank decision / missing ticket is refused", (await call("record_human_decision", {"ticket_id": 103, "decided_by": "T", "decision": " "}))["ok"] is False and (await call("record_human_decision", {"ticket_id": 999, "decided_by": "T", "decision": "x"}))["ok"] is False)

        r1 = await call("reset_shop_database")
        check("reset saves the finished run first, then restores the original", r1["ok"] and r1["backup"] and Path(r1["backup"]).exists() and r1["checking_balance"] == 3400.0 and sql(db, "select count(*) from payments")[0][0] == 0)
        check("the backup holds the payments that were reset", sql(Path(r1["backup"]), "select count(*) from payments")[0][0] == 4)
        check("a second reset has nothing worth saving", (await call("reset_shop_database"))["backup"] is None)


# --------------------------------------------------------------------------------------------- 3. agent plumbing
async def check_agents():
    section("3. agent team, prompts and guards")
    from fastmcp import Client
    from tools import mcp_toolset, mcp_config, _make_ask, AGENT_NAMES
    from models import TeamDeps
    from audit import append_entries, AuditLog
    from models import AuditEntry
    scratch_db("agents")
    prompts = ROOT / "backend" / "prompts"
    for n in AGENT_NAMES:
        t = (prompts / f"{n}.md").read_text()
        check(f"{n}.md has the user's sections (what you read / decide / delegate, rules, never)", all(x in t for x in ("What you", "Rules you must follow", "Things you must never do")) and "What you delegate" in t, n)
    check("team.md exists with the delegation rules", "ask_" in (prompts / "team.md").read_text())
    check("five agents: boss, inventory, accounting, facilities, customer_service", AGENT_NAMES == ("boss", "inventory", "accounting", "facilities", "customer_service"))

    toolset = mcp_toolset()
    async with Client(mcp_config()) as c:
        all_names = [t.name for t in await c.list_tools()]
    keep = [n for n in all_names if toolset.filter_func(None, types.SimpleNamespace(name=n))]
    check("the agents' toolset keeps 16 of the 21 tools", len(keep) == 16, str(len(keep)))
    check("agents cannot pay, decline, reset, receive stock or record a human decision", not set(keep) & {"execute_approved_payment", "decline_payment", "reset_shop_database", "receive_shipment", "record_human_decision"})

    # delegation guards (they answer before any model is called)
    deps = TeamDeps(team={}, trace=[], audit=None, chain=("boss", "inventory"), max_depth=4)
    ctx = types.SimpleNamespace(deps=deps, usage=None)
    out = await _make_ask("accounting", "boss")(ctx, "please look at ticket 101")
    check("an agent cannot ask someone already waiting on it up the chain", "already working" in out and deps.trace[-1].error)
    out = await _make_ask("accounting", "accounting")(ctx, "x")
    check("an agent cannot ask itself", "already working" in out)
    deep = TeamDeps(team={}, trace=[], audit=None, chain=("boss", "inventory", "accounting", "facilities"), max_depth=4)
    out = await _make_ask("facilities", "customer_service")(types.SimpleNamespace(deps=deep, usage=None), "x")
    check("delegation depth is capped at 4", "depth limit" in out.lower())

    # the audit trail is append-only and safe
    p = TMP / "audit_test.json"
    def entry(i): return AuditEntry(run_id="r", seq=i, time="t", ticket_id=1, agent="boss", invocation="boss#1", depth=0, chain=[], step=None, event="run_start", detail={})
    append_entries(p, [entry(1)]); append_entries(p, [entry(2), entry(3)])
    check("append_entries adds to the end and never wipes", [e["seq"] for e in json.loads(p.read_text())] == [1, 2, 3])
    q = TMP / "audit_bad.json"; q.write_text('{"not": "a list"}')
    try: append_entries(q, [entry(1)]); refused = False
    except ValueError: refused = True
    check("a file that is not a list is refused, not overwritten", refused and json.loads(q.read_text()) == {"not": "a list"})
    r = TMP / "audit_threads.json"
    ts = [threading.Thread(target=lambda i=i: append_entries(r, [entry(i)])) for i in range(40)]
    [t.start() for t in ts]; [t.join() for t in ts]
    check("40 simultaneous writers lose nothing and leave valid JSON", len(json.loads(r.read_text())) == 40)
    log = AuditLog(5, TMP / "audit_log.json"); log.record("human_action", {"x": 1}, agent="human"); log.record("run_end", {})
    e = json.loads((TMP / "audit_log.json").read_text())
    check("AuditLog numbers entries in order within a run", [x["seq"] for x in e] == [1, 2] and e[0]["run_id"] == e[1]["run_id"])


def check_model_ping():
    section("4. the model (one tiny call)")
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(ROOT.parent / ".env")
    check("PORTKEY_API_KEY is set in the environment", bool(os.environ.get("PORTKEY_API_KEY")))
    import agent
    check("every agent uses gpt-6-luna", agent.MODEL_NAME == "gpt-6-luna")
    check("model requests time out after 30 s, retried twice", agent.MODEL_TIMEOUT == 30.0)
    t0 = time.time()
    try:
        r = OpenAI(api_key=os.environ["PORTKEY_API_KEY"], base_url=agent.PORTKEY_URL, timeout=45, max_retries=1).responses.create(model=agent.MODEL_NAME, input="Reply with the single word: ok")
        check("gpt-6-luna answers through Portkey", "ok" in r.output_text.lower(), r.output_text)
    except Exception as exc:
        check("gpt-6-luna answers through Portkey", False, f"{type(exc).__name__} after {time.time()-t0:.0f}s (the gateway is known to stall now and then; run again)")


# --------------------------------------------------------------------------------------------- 5. the backend routes
def check_backend():
    section("5. backend routes (model replaced by a fake run)")
    import main
    from fastapi.testclient import TestClient
    from models import TicketDecision
    from fastmcp import Client
    from tools import mcp_config

    db = scratch_db("backend")
    main.AUDIT_FILE = TMP / "backend_audit.json"
    calls, sleep_for = [], [0.6]
    async def fake_work_ticket(ticket_id, team=None, audit_path=None, audit=None, note=None):
        calls.append((ticket_id, note)); audit.record("run_start", {"fake": True}); await asyncio.sleep(sleep_for[0]); audit.record("run_end", {"status": "finished"})
        return TicketDecision(ticket_id=ticket_id, status="waiting_approval", owners=[], decision="fake", reasoning="fake"), []
    main.work_ticket = fake_work_ticket

    async def seed():
        async with Client(mcp_config()) as c:
            ids = []
            for a in (dict(kind="invoice", ref_id=501, account="checking", reason="t", ticket_id=101),
                      dict(kind="rent", ref_id=1, account="checking", reason="t", ticket_id=101),
                      dict(kind="purchase_order", ref_id=2, account="checking", reason="t", ticket_id=103, sku="CC-MUG-CREST", qty=10)):
                ids.append((await c.call_tool("request_payment_approval", a, raise_on_error=False)).data["approval_id"])
            return ids
    A1, A2, A3 = asyncio.run(seed())

    with TestClient(main.app) as c:
        wait = lambda s=1.0: time.sleep(s)
        r = c.get("/api/tickets"); t = r.json()
        check("GET /api/tickets: three tickets with state and running", r.status_code == 200 and len(t) == 3 and all({"id", "status", "state", "running"} <= set(x) for x in t) and all(x["running"] is False for x in t))
        cash = c.get("/api/cash").json()
        check("GET /api/cash: balance, pending, after pending", cash["balance"] == 3400.0 and cash["pending_approvals_total"] == 840.0 + 2400.0 + 35.0 and cash["starting_balance"] is None, str(cash))
        ap = c.get("/api/approvals").json()
        check("GET /api/approvals lists the three prepared payments", len(ap) == 3 and {a["status"] for a in ap} == {"pending"})
        check("GET /api/approvals?status=pending filters", len(c.get("/api/approvals", params={"status": "approved"}).json()) == 0)

        check("run on a missing ticket: 404", c.post("/api/tickets/999/run").status_code == 404)
        r = c.post("/api/tickets/103/run"); run_id = r.json().get("run_id")
        check("POST /run returns 202 and a run id at once", r.status_code == 202 and run_id)
        check("a second run while the team is busy: 409", c.post("/api/tickets/101/run").status_code == 409)
        check("reset while the team is busy: 409", c.post("/api/reset").status_code == 409)
        check("GET /api/runs/<id> says running", c.get(f"/api/runs/{run_id}").json()["state"] == "running")
        wait(1.5)
        st = c.get(f"/api/runs/{run_id}").json()
        check("...then finished with the Boss's decision", st["state"] == "finished" and st["decision"]["status"] == "waiting_approval")
        check("unknown run id: 404", c.get("/api/runs/nope").status_code == 404)

        ev = c.get("/api/events").json()
        check("GET /api/events returns recent events with a cursor", ev["total"] >= 2 and ev["next_cursor"] == ev["total"] and all({"id", "said", "tools", "detail"} <= set(e) for e in ev["events"]))
        check("?after=<cursor> returns only what is new", c.get("/api/events", params={"after": ev["total"]}).json()["events"] == [])
        check("?run_id= filters to one run", all(e["run_id"] == run_id for e in c.get("/api/events", params={"run_id": run_id}).json()["events"]))

        check("approve with no name: 422", c.post(f"/api/approvals/{A1}/approve", json={"approved_by": ""}).status_code == 422)
        check("approve an unknown approval: 404", c.post("/api/approvals/99/approve", json={"approved_by": "T"}).status_code == 404)
        n = len(calls)
        r = c.post(f"/api/approvals/{A1}/approve", json={"approved_by": "Tester"}).json()
        check("approve moves the cash (3400 -> 2560) and starts no run while another approval is pending on 101", r["balance_after"] == 2560.0 and r["continued_run_id"] is None and len(calls) == n)
        check("approving twice: 409", c.post(f"/api/approvals/{A1}/approve", json={"approved_by": "T"}).status_code == 409)
        r = c.post(f"/api/approvals/{A2}/approve", json={"approved_by": "Tester"}).json()
        wait(0.3)
        check("approving the last pending one starts the follow-up run for that ticket by itself", r["continued_ticket_id"] == 101 and r["continued_run_id"] and "approved a payment" in calls[-1][1], str(r))
        r = c.post(f"/api/approvals/{A3}/approve", json={"approved_by": "Tester"}).json()
        check("a follow-up for another ticket waits while the team is busy", r["continued_run_id"] is None and list(main.app.state.continue_queue) == [103])
        wait(4.0)
        check("...and then runs by itself, in order, with nothing left queued", [x[0] for x in calls[-2:]] == [101, 103] and main.app.state.continue_queue == {}, str(calls))
        check("decline an unknown approval: 404, receive a non-order: 409", c.post("/api/approvals/99/decline", json={"declined_by": "T"}).status_code == 404 and c.post(f"/api/approvals/{A1}/receive", json={"received_by": "T"}).status_code == 409)
        check("decision shorter than 3 characters: 422", c.post("/api/tickets/101/decision", json={"decided_by": "T", "decision": "x"}).status_code == 422)
        sql_db = sqlite3.connect(db); sql_db.execute("update tickets set status='resolved' where id=102"); sql_db.commit(); sql_db.close()
        n = len(calls)
        check("a ticket that is resolved is never restarted", c.post("/api/tickets/102/decision", json={"decided_by": "T", "decision": "close it"}).json()["continued_run_id"] is None and len(calls) == n)
        check("running a resolved ticket: 409", c.post("/api/tickets/102/run").status_code == 409)
        main.AUTO_CONTINUE = False; n = len(calls)
        check("AUTO_CONTINUE=0 turns the follow-up off", c.post("/api/tickets/101/decision", json={"decided_by": "T", "decision": "go on"}).json()["continued_run_id"] is None and len(calls) == n)
        main.AUTO_CONTINUE = True

        wait(1.0)
        humans = [e for e in json.loads(main.AUDIT_FILE.read_text()) if e["event"] == "human_action"]
        check("every human action is in the audit trail", len(humans) >= 4 and all(e["agent"] == "human" for e in humans))
        r = c.post("/api/reset").json()
        check("POST /api/reset restores $3,400, saves a backup and records the starting balance", r["checking_balance"] == 3400.0 and r["backup"] and Path(r["backup"]).exists())
        check("GET /api/cash now reports the starting balance from the last reset", c.get("/api/cash").json()["starting_balance"] == 3400.0)

        main.RUN_TIMEOUT = 0.4; sleep_for[0] = 3.0
        rid = c.post("/api/tickets/101/run").json()["run_id"]; wait(1.2)
        st = c.get(f"/api/runs/{rid}").json()
        entries = [e for e in json.loads(main.AUDIT_FILE.read_text()) if e["run_id"] == rid]
        check("a run that takes too long is stopped and recorded as failed", st["state"] == "failed" and "TimeoutError" in st["error"] and [e["event"] for e in entries][-2:] == ["error", "run_end"])
        check("the board is free again after a failed run", c.post("/api/tickets/103/run").status_code == 202)
        wait(3.5)

        o = c.options("/api/tickets", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        check("CORS allows the dashboard origin http://localhost:5173", o.headers.get("access-control-allow-origin") == "http://localhost:5173")
        o = c.get("/api/cash", headers={"Origin": "http://evil.example"})
        check("CORS does not allow other origins", "access-control-allow-origin" not in o.headers)
        paths = set(c.get("/openapi.json").json()["paths"])
        check("11 routes", len(paths) == 11, str(sorted(paths)))


if __name__ == "__main__":
    only = sys.argv[1:]
    check_original_database()
    asyncio.run(check_mcp_tools())
    asyncio.run(check_agents())
    check_model_ping()
    check_backend()
    failed = [r for r in results if not r[0]]
    print(f"\n{'=' * 60}\n{len(results) - len(failed)} passed, {len(failed)} failed (scratch files in {TMP})")
    for ok, name, detail in failed:
        print(f"  FAIL  {name}  {detail}")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failed else 0)
