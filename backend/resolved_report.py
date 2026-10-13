"""Write output/resolved_tickets.json and output/resolved_board.html from the live run.

  .venv/bin/python backend/resolved_report.py            (writes into output/)
  .venv/bin/python backend/resolved_report.py --out DIR  (writes somewhere else, e.g. to test)

Shop facts (tickets, approvals, payments, cash) come from the MCP server. What each agent did comes from
output/audit_trail.json. Board screenshots come from `node frontend/scripts/shot.mjs <ticket>` and are
embedded in the page, so the page works when double-clicked. Nothing here is invented: a ticket that is not
resolved is written with its real status and the page says so.
"""

import argparse
import asyncio
import base64
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import Client

from audit import AUDIT_PATH
from people import display_name
from tools import ROOT, mcp_config

TICKETS = (101, 102, 103)
usd = lambda n: f"${n:,.2f}"


async def fetch() -> dict:
    async with Client(mcp_config()) as shop:
        get = lambda name, args=None: shop.call_tool(name, args or {}, raise_on_error=True)
        return {
            "cash": (await get("check_cash", {"account": "checking"})).data["accounts"][0],
            "payments": (await get("list_payments")).data["payments"],
            "approvals": (await get("list_approvals")).data["approvals"],
            "tickets": (await get("list_tickets")).data["tickets"],
        }


def since_last_reset(entries: list[dict]) -> list[dict]:
    """The audit entries from the most recent reset on: the run this record describes (earlier runs stay in the trail)."""
    last = max((i for i, e in enumerate(entries) if e["event"] == "human_action" and e["detail"].get("action") == "reset_database"), default=None)
    if last is None:
        raise SystemExit("no reset found in the audit trail")
    return entries[last:]


def starting_balance(entries: list[dict]) -> float:
    resets = [e for e in entries if e["event"] == "human_action" and e["detail"].get("action") == "reset_database"]
    if not resets:
        raise SystemExit("no reset found in the audit trail")
    return resets[-1]["detail"]["result"]["checking_balance"]


def short(text: str, limit: int = 300) -> str:
    """The first sentences of a text, at most `limit` characters."""
    out = ""
    for sentence in text.replace("\n", " ").split(". "):
        piece = sentence if sentence.endswith(".") else sentence + "."
        if len(out) + len(piece) > limit and out:
            break
        out = (out + " " + piece).strip()
    return out if len(out) <= limit else out[: limit - 1] + "…"


def agent_contributions(entries: list[dict], run_ids: list[str]) -> dict:
    """For each agent: what it reported in each run of the ticket, and the tools it called."""
    tools: dict[str, list[str]] = {}
    for e in entries:
        if e["run_id"] in run_ids and e["event"] == "model_response":
            for c in e["detail"]["tool_calls"]:
                if c["tool"] != "final_result":
                    tools.setdefault(e["invocation"], []).append(c["tool"])
    out: dict[str, list] = {}
    for e in entries:
        if e["run_id"] in run_ids and e["event"] == "agent_end":
            o = e["detail"]["output"]
            used = tools.get(e["invocation"], [])
            out.setdefault(e["agent"], []).append({
                "run_id": e["run_id"],
                "turn": e["invocation"],
                "contribution": short(o.get("summary") or o.get("decision") or "", 400),
                "did": [short(x, 160) for x in o.get("actions_taken", [])],
                "tools_called": [f"{t} x{used.count(t)}" if used.count(t) > 1 else t for t in dict.fromkeys(used)],
            })
    return out


def build(d: dict, entries: list[dict]) -> dict:
    start = starting_balance(entries)
    ending = d["cash"]["balance"]
    pays = d["payments"]
    paid = sum(p["amount"] for p in pays)
    human = {e["detail"]["approval_id"]: e["time"] for e in entries
             if e["event"] == "human_action" and e["detail"].get("action") == "approve_payment"}
    tickets = {t["id"]: t for t in d["tickets"]}
    after_payment, bal = {}, start  # the checking balance right after each payment, in the order the money moved
    for p in pays:
        bal -= p["amount"]
        after_payment[p["id"]] = round(bal, 2)
    out_tickets = []
    for tid in TICKETS:
        t = tickets[tid]
        runs = []
        for e in entries:
            if e["event"] == "run_start" and e["ticket_id"] == tid:
                end = next((x for x in entries if x["run_id"] == e["run_id"] and x["event"] == "run_end"), None)
                u = (end["detail"].get("usage") or {}) if end else {}
                runs.append({"run_id": e["run_id"], "started_at": e["time"], "ended_at": end["time"] if end else None,
                             "result": (end["detail"].get("decision") or {}).get("status") if end else "unfinished",
                             "finished": bool(end and end["detail"]["status"] == "finished"),
                             "model_requests": u.get("requests", 0), "tokens": u.get("input_tokens", 0) + u.get("output_tokens", 0)})
        last_end = next((x for x in reversed(entries) if x["event"] == "run_end" and x["ticket_id"] == tid
                         and x["detail"].get("decision")), None)
        approvals = []
        for a in d["approvals"]:
            if a["ticket_id"] != tid:
                continue
            pay = next((p for p in pays if p["id"] == a.get("payment_id")), None)
            approvals.append({
                "approval_id": a["id"], "kind": a["kind"], "ref_id": a["ref_id"], "amount": a["amount"],
                "prepared_by": a["requested_by"], "status": a["status"],
                "approved_by": display_name(pay["approved_by"]) if pay else None, "paid_at": pay["paid_at"] if pay else None,
                "approved_at_utc": human.get(a["id"]), "reason": a["reason"]})
        decisions = [{"decided_by": display_name(e["detail"]["decided_by"]), "decision": e["detail"]["decision"], "at_utc": e["time"]}
                     for e in entries if e["event"] == "human_action" and e["detail"].get("action") == "record_decision" and e["ticket_id"] == tid]
        deliveries = [{"approval_id": a["id"], "item": f'{a["qty"]} x {a["sku"]}', "confirmed_by": display_name(a["received_by"]), "received_at": a["received_at"]}
                      for a in d["approvals"] if a["ticket_id"] == tid and a.get("received_at")]
        mine = [p for p in pays if p.get("ticket_id") == tid]
        spent = sum(p["amount"] for p in mine)
        out_tickets.append({
            "id": tid, "subject": t["subject"], "requester": t["requester"],
            "final_status": t["status"], "resolved": t["status"] == "resolved",
            "outcome": short(last_end["detail"]["decision"]["decision"]) if last_end else "No run yet.",
            "runs": runs,
            "usage": {"runs": len(runs), "failed_runs": sum(1 for r in runs if not r["finished"]),
                      "model_requests": sum(r["model_requests"] for r in runs), "tokens": sum(r["tokens"] for r in runs)},
            "agents": agent_contributions(entries, [r["run_id"] for r in runs]),
            "human_approvals": approvals,
            "human_decisions": decisions,
            "deliveries_confirmed_by_a_human": deliveries,
            "cash_change": {"payments": [{"payment_id": p["id"], "kind": p["kind"], "ref_id": p["ref_id"], "amount": -p["amount"],
                                          "approved_by": display_name(p["approved_by"]), "checking_after_this_payment": after_payment[p["id"]]} for p in mine],
                            "total": -spent}})
    untied = [p for p in pays if p.get("ticket_id") not in TICKETS]
    ok = abs((start - paid) - ending) < 0.005 and abs(sum(t["cash_change"]["total"] for t in out_tickets) + paid) < 0.005 and not untied
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "MCP server on data/campus_customs_new.db, and output/audit_trail.json",
        "all_resolved": all(t["resolved"] for t in out_tickets),
        "cash": {"account": "checking", "starting_balance": start, "total_paid": paid, "ending_balance": ending,
                 "pending_approvals_total": d["cash"]["pending_approvals_total"],
                 "arithmetic": f"{usd(start)} - {usd(paid)} = {usd(start - paid)}; cash_accounts says {usd(ending)}",
                 "matches_cash_accounts": ok},
        "usage": {"runs": sum(t["usage"]["runs"] for t in out_tickets), "failed_runs": sum(t["usage"]["failed_runs"] for t in out_tickets),
                  "model_requests": sum(t["usage"]["model_requests"] for t in out_tickets), "tokens": sum(t["usage"]["tokens"] for t in out_tickets),
                  "note": "requests and tokens are counted for finished runs only; a failed run records none"},
        "tickets": out_tickets,
    }


CSS = """
:root{--desk:#ece0c8;--card:#fff;--soft:#fbf7ee;--line:#e5dac4;--line2:#d3c4a6;--ink:#2a2118;--brown:#6b5843;--stamp:#a3262a;--open:#2b5fa8;--wait:#8a5a00;--waitbg:#fbf1d9;--waitline:#e2b857;--done:#2b6b46;--donebg:#e6f3ea;--bad:#b3261e;--badbg:#fbeceb;--serif:Georgia,'Iowan Old Style','Palatino Linotype',Palatino,serif;--shadow:0 1px 2px rgba(80,55,20,.06),0 4px 14px rgba(80,55,20,.05)}
*{box-sizing:border-box}body{margin:0;background:var(--desk) linear-gradient(180deg,#f3eadb,var(--desk));color:var(--ink);font:15px/1.55 -apple-system,'SF Pro Text','Helvetica Neue',Arial,sans-serif}
main{max-width:1240px;margin:0 auto;padding:34px 28px 60px}h1,h2,h3{font-family:var(--serif);font-weight:600;margin:0}
.eyebrow{color:var(--stamp);letter-spacing:.2em;font-size:12px;text-transform:uppercase;font-weight:600}h1{font-size:36px;margin:6px 0 8px}h1 em{color:var(--stamp)}
.lede{color:var(--brown);max-width:820px;margin:0 0 20px}.mono{font-family:'SF Mono',Menlo,Consolas,monospace}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:22px 24px;margin-top:22px}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:14px;border:1px solid var(--line);border-radius:8px;overflow:hidden}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}th{background:var(--soft);color:var(--brown);font-size:12px;letter-spacing:.08em;text-transform:uppercase}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 10px;border-radius:99px;font-weight:700;font-size:12px;border:1px solid #bcd0ee;background:#e8f0fb;color:var(--open)}.pill.resolved{background:var(--donebg);border-color:#b5d8c3;color:var(--done)}.pill.waiting_approval,.pill.in_progress{background:var(--waitbg);border-color:var(--waitline);color:var(--wait)}
.callout{border:1px solid var(--waitline);border-left:4px solid var(--waitline);background:var(--waitbg);border-radius:6px;padding:10px 14px;margin:12px 0}.callout.ok{border-color:#b5d8c3;border-left-color:var(--done);background:var(--donebg)}.callout.bad{border-color:#e9b9b5;border-left-color:var(--bad);background:var(--badbg)}
h3{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--brown);margin:20px 0 8px}.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
.box{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:2px 16px 12px}.box h4{font-family:var(--serif);margin:12px 0 4px}.box p,.box ul{margin:4px 0}.box ul{padding-left:18px}.small{font-size:13px;color:var(--brown)}
figure{margin:12px 0 0}figure img{width:100%;border:1px solid var(--line2);border-radius:10px;box-shadow:var(--shadow)}figcaption{font-size:12px;color:var(--brown);margin-top:6px}
.tool{font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px;background:#f3ebda;border:1px solid var(--line);padding:0 6px;border-radius:4px;margin-right:4px;white-space:nowrap}
"""


def page(report: dict, shots: Path) -> str:
    c = report["cash"]
    rows, cards = [], []
    for t in report["tickets"]:
        status = t["final_status"]
        approvers = ", ".join(f'{escape(a["approved_by"])} (approval {a["approval_id"]})' for a in t["human_approvals"] if a["approved_by"]) or "—"
        rows.append(f'<tr><td class="mono">#{t["id"]}</td><td>{escape(t["subject"])}</td><td><span class="pill {escape(status)}">{escape(status)}</span></td>'
                    f'<td class="num">{("−" + usd(-t["cash_change"]["total"])) if t["cash_change"]["total"] else "$0.00"}</td><td>{approvers}</td></tr>')
        png = shots / f"ticket_{t['id']}.png"
        meta = shots / f"ticket_{t['id']}.json"
        if png.exists():
            m = json.loads(meta.read_text()) if meta.exists() else {}
            fig = (f'<figure><img alt="React board for ticket {t["id"]}" src="data:image/png;base64,{base64.b64encode(png.read_bytes()).decode()}">'
                   f'<figcaption>The React board with ticket {t["id"]} selected. Taken {escape(m.get("taken_at", "")[:19].replace("T", " "))} UTC; '
                   f'the board showed “{escape(m.get("banner") or "")}” and a checking balance of {escape(m.get("balance_shown") or "")}.</figcaption></figure>')
        else:
            fig = '<div class="callout bad">No screenshot saved yet for this ticket (run <span class="mono">node frontend/scripts/shot.mjs ' + str(t["id"]) + '</span>).</div>'
        agents = "".join(
            f'<div class="box"><h4>{escape(name.replace("_", " ").title())}</h4>' + "".join(
                f'<p>{escape(x["contribution"])}</p>' + (f'<p class="small">{"".join(f"<span class=tool>{escape(tl)}</span>" for tl in x["tools_called"])}</p>' if x["tools_called"] else "")
                for x in items) + '</div>' for name, items in t["agents"].items())
        appr = "".join(
            f'<li>Approval {a["approval_id"]}: {escape(a["kind"])} {a["ref_id"]}, <b>{usd(a["amount"])}</b>, {escape(a["status"])}'
            + (f', approved by <b>{escape(a["approved_by"])}</b> on {escape(a["paid_at"])}' if a["approved_by"] else ", waiting for a human") + '</li>'
            for a in t["human_approvals"]) or "<li>No payment needed human approval for this ticket.</li>"
        cc = t["cash_change"]
        cash_line = (f'Cash out for this ticket: <b>−{usd(-cc["total"])}</b>.<ul>' + "".join(
            f'<li>Payment {p["payment_id"]}: {escape(p["kind"].replace("_", " "))} {p["ref_id"]}, <b>−{usd(-p["amount"])}</b>; checking was {usd(p["checking_after_this_payment"])} afterwards</li>'
            for p in cc["payments"]) + '</ul>' if cc["total"] else "No cash changed for this ticket.")
        extra = ""
        if t["human_decisions"]:
            extra += "<h4>Human decision</h4><ul>" + "".join(f'<li>{escape(x["decided_by"])}: {escape(x["decision"])}</li>' for x in t["human_decisions"]) + "</ul>"
        if t["deliveries_confirmed_by_a_human"]:
            extra += "<h4>Deliveries a human confirmed</h4><ul>" + "".join(f'<li>Order {x["approval_id"]}: {escape(x["item"])}, confirmed by {escape(x["confirmed_by"])} on {escape(x["received_at"])}</li>' for x in t["deliveries_confirmed_by_a_human"]) + "</ul>"
        note = "" if t["resolved"] else f'<div class="callout bad"><b>Not resolved.</b> The board status is {escape(status)}.</div>'
        cards.append(f'''<section class="card" id="t{t["id"]}">
  <h2>Ticket <span class="mono" style="color:var(--stamp)">{t["id"]}</span> · {escape(t["subject"])} <span class="pill {escape(status)}">{escape(status)}</span></h2>
  <p class="small">{escape(t["requester"])} · {len(t["runs"])} run{"s" if len(t["runs"]) != 1 else ""}</p>
  {note}<p><b>Outcome:</b> {escape(t["outcome"])}</p>
  <div class="two"><div class="box"><h4>Human approvals</h4><ul>{appr}</ul>{extra}</div><div class="box"><h4>Cash</h4><p>{cash_line}</p></div></div>
  <h3>What each agent contributed</h3><div class="two">{agents}</div>
  <h3>The board</h3>{fig}
</section>''')
    verdict = ('<div class="callout ok"><b>Cash math checks out:</b> ' if c["matches_cash_accounts"] else '<div class="callout bad"><b>Cash math does NOT match:</b> ') + escape(c["arithmetic"]) + '.</div>'
    done = "all three tickets are resolved" if report["all_resolved"] else "not every ticket is resolved yet"
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Campus Customs · Resolved board</title><style>{CSS}</style></head>
<body><main>
<div class="eyebrow">Campus Customs · Agent Desk · Problem 9</div>
<h1>The <em>resolved</em> board</h1>
<p class="lede">A screenshot of the React board for each ticket, what each agent contributed, and the money. Right now {done}. Generated {escape(report["generated_at"])} UTC from the live shop data.</p>
<section class="card"><h2>Summary</h2>
<table><tr><th>Ticket</th><th>Subject</th><th>Final status</th><th class="num">Cash change</th><th>Approved by</th></tr>{"".join(rows)}</table>
<h3>Checking account</h3>
<table><tr><th>Starting balance (right after the reset)</th><th class="num">Paid out</th><th class="num">Ending balance (cash_accounts)</th></tr><tr><td>{usd(c["starting_balance"])}</td><td class="num">−{usd(c["total_paid"])}</td><td class="num"><b>{usd(c["ending_balance"])}</b></td></tr></table>
{verdict}</section>
{"".join(cards)}
</main></body></html>
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "output")
    ap.add_argument("--shots", type=Path, default=ROOT / "output" / "screenshots")
    args = ap.parse_args()
    entries = json.loads(AUDIT_PATH.read_text())
    report = build(asyncio.run(fetch()), since_last_reset(entries))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "resolved_tickets.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (args.out / "resolved_board.html").write_text(page(report, args.shots))
    print("statuses:", {t["id"]: t["final_status"] for t in report["tickets"]}, "| all resolved:", report["all_resolved"])
    print("cash:", report["cash"]["arithmetic"], "| matches:", report["cash"]["matches_cash_accounts"])


if __name__ == "__main__":
    main()
