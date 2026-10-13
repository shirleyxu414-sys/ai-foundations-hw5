"""FastAPI backend for the Campus Customs dashboard.

Run from the hw 5 folder:  .venv/bin/uvicorn backend.main:app --port 8000

Every shop fact (tickets, cash, approvals) and every change to the shop (paying, resetting) goes
through the MCP server, the same one the agents use. This file has no database code of its own.
The agent team only prepares payments; the approve route below is the only way cash moves.
"""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the backend files import each other by name

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client

from agent import build_team, work_ticket
from audit import AUDIT_PATH, AuditLog
from models import (ApprovalOut, ApproveRequest, CashOut, DeclineOut, DeclineRequest, DecisionOut, DecisionRequest, EventOut, EventsOut, PaymentOut, ReceiveOut, ReceiveRequest, ResetOut, RunStarted,
                    RunStatus, TicketSummary)
from tools import mcp_config

AUDIT_FILE = AUDIT_PATH  # where agent events are read from (tests point this somewhere else)
CASH_ACCOUNT = "checking"
AUTO_CONTINUE = os.environ.get("AUTO_CONTINUE", "1") != "0"  # set AUTO_CONTINUE=0 to make people press Run again
RUN_TIMEOUT = float(os.environ.get("RUN_TIMEOUT_SECONDS", 300))  # a whole ticket run may not take longer than this
DASHBOARD_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000",
                     "http://127.0.0.1:3000"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.team = build_team()  # the five agents, built once and reused for every ticket
    app.state.runs = {}  # run_id -> RunStatus, newest last
    app.state.tasks = set()  # keeps background runs alive until they finish
    app.state.continue_queue = {}  # ticket id -> what the person did; follow-ups waiting for the current run to end
    # The human's own connection to the MCP server. Unlike the agents' toolset it is not filtered,
    # so it can call the human-only tools (execute_approved_payment, reset_shop_database).
    async with Client(mcp_config()) as shop:
        app.state.shop = shop
        yield


app = FastAPI(title="Campus Customs backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=DASHBOARD_ORIGINS, allow_methods=["*"], allow_headers=["*"])


async def shop_call(name: str, args: dict | None = None) -> dict:
    """Call one MCP tool and return its result dict."""
    result = await app.state.shop.call_tool(name, args or {}, raise_on_error=False)
    if result.is_error or not isinstance(result.data, dict):
        raise HTTPException(502, f"MCP tool {name} failed")
    return result.data


def active_run() -> RunStatus | None:
    return next((r for r in app.state.runs.values() if r.state == "running"), None)


def audit_human(action: str, ticket_id: int | None, detail: dict) -> None:
    """Moving money or resetting the shop is written to the audit trail like an agent step."""
    AuditLog(ticket_id, AUDIT_FILE).record("human_action", {"action": action, **detail}, agent="human")


# ---------------------------------------------------------------- tickets

@app.get("/api/tickets", response_model=list[TicketSummary])
async def tickets():
    """The tickets on the board and whether each is open or resolved."""
    data = await shop_call("list_tickets")
    running = {r.ticket_id for r in app.state.runs.values() if r.state == "running"}
    return [TicketSummary(**{k: t[k] for k in ("id", "type", "requester", "subject", "status")},
                          state="resolved" if t["status"] == "resolved" else "open", running=t["id"] in running)
            for t in data["tickets"]]


@app.post("/api/tickets/{ticket_id}/run", response_model=RunStarted, status_code=202)
async def run_ticket(ticket_id: int):
    """Start the agent team on one ticket. Returns at once with a run id; poll /api/runs/{run_id}
    for the outcome and /api/events to watch the agents work."""
    ticket = await shop_call("get_ticket", {"ticket_id": ticket_id})
    if not ticket["ok"]:
        raise HTTPException(404, f"ticket {ticket_id} not found")
    if ticket["ticket"]["status"] == "resolved":
        raise HTTPException(409, f"ticket {ticket_id} is already resolved; reset the database to run it again")
    if (busy := active_run()) is not None:  # one ticket at a time keeps cash and token use predictable
        raise HTTPException(409, f"the team is already working ticket {busy.ticket_id} (run {busy.run_id})")

    return RunStarted(run_id=launch_run(ticket_id).run_id, ticket_id=ticket_id)


def launch_run(ticket_id: int, note: str | None = None) -> RunStatus:
    """Start the agent team on a ticket in the background and return its status record at once."""
    audit = AuditLog(ticket_id, AUDIT_FILE)
    status = RunStatus(run_id=audit.run_id, ticket_id=ticket_id, state="running", started_at=now())
    app.state.runs[status.run_id] = status

    async def work() -> None:
        try:
            decision, _ = await asyncio.wait_for(work_ticket(ticket_id, app.state.team, audit=audit, note=note), RUN_TIMEOUT)
            status.decision, status.state = decision, "finished"
        except TimeoutError:  # wait_for cancelled the run, so write its ending to the audit trail here
            message = f"the run took longer than {RUN_TIMEOUT:.0f} seconds and was stopped"
            audit.record("error", {"type": "TimeoutError", "message": message})
            audit.record("run_end", {"status": "failed", "error": "TimeoutError"})
            status.error, status.state = f"TimeoutError: {message}", "failed"
        except Exception as exc:  # the audit trail already has the error entry
            status.error, status.state = f"{type(exc).__name__}: {str(exc)[:300]}", "failed"
        status.finished_at = now()
        await start_queued_follow_up()

    task = asyncio.create_task(work())
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)
    return status


async def maybe_continue(ticket_id: int | None, what: str) -> tuple[str, int] | None:
    """After a person acts on a ticket, make the team pick it up again, unless there is a reason not to.

    No run if automatic continuing is switched off, the ticket is resolved, or something on this ticket is still
    waiting for a person (running now would stop at the same place). If another ticket is running, the follow-up
    waits for it. Only human actions call this, so a run can never start another run on its own.
    Returns (run id, ticket id) when a run was started now.
    """
    if not AUTO_CONTINUE or ticket_id is None:
        return None
    ticket = await shop_call("get_ticket", {"ticket_id": ticket_id})
    if not ticket["ok"] or ticket["ticket"]["status"] == "resolved":
        return None
    if (await shop_call("list_approvals", {"status": "pending", "ticket_id": ticket_id}))["approvals"]:
        return None
    if active_run() is not None:
        app.state.continue_queue.setdefault(ticket_id, what)  # one follow-up per ticket, in the order people acted
        return None
    status = launch_run(ticket_id, note=what)
    return status.run_id, ticket_id


async def start_queued_follow_up() -> None:
    """When a run ends, start the follow-up that was waiting for it, if any."""
    while app.state.continue_queue and active_run() is None:
        ticket_id, what = next(iter(app.state.continue_queue.items()))
        del app.state.continue_queue[ticket_id]
        if await maybe_continue(ticket_id, what):
            return


async def approval_ticket(approval_id: int) -> int | None:
    """Which ticket an approval was prepared for."""
    approvals = (await shop_call("list_approvals", {}))["approvals"]
    return next((a["ticket_id"] for a in approvals if a["id"] == approval_id), None)


@app.get("/api/runs/{run_id}", response_model=RunStatus)
async def run_status(run_id: str):
    """Whether a run is still going, and the Boss's final decision when it has finished."""
    if run_id not in app.state.runs:
        raise HTTPException(404, f"run {run_id} not found")
    return app.state.runs[run_id]


# ---------------------------------------------------------------- events

def event_out(idx: int, e: dict) -> EventOut:
    d = e["detail"]
    said = None
    if e["event"] == "model_response":
        said = " ".join(d.get("text", [])) or None
    elif e["event"] == "agent_end":
        said = d["output"].get("summary") or d["output"].get("decision") if isinstance(d.get("output"), dict) else None
    elif e["event"] == "error":
        said = d.get("message")
    elif e["event"] == "human_action":
        said = d.get("summary")
    tools = [c["tool"] for c in d.get("tool_calls", [])] if e["event"] == "model_response" else (
        [d["tool"]] if e["event"] in ("tool_result", "tool_retry") else [])
    return EventOut(id=idx, said=said, tools=tools, **{k: e[k] for k in (
        "run_id", "seq", "time", "ticket_id", "agent", "invocation", "depth", "chain", "step", "event", "detail")})


@app.get("/api/events", response_model=EventsOut)
async def events(after: int | None = Query(None, ge=0, description="Cursor from the previous call"),
                 limit: int = Query(100, ge=1, le=500), ticket_id: int | None = None, run_id: str | None = None):
    """Recent agent events: what each agent said and which tools it used, read from the audit trail.
    Without `after` you get the latest `limit` events. Pass the returned `next_cursor` as `after`
    on the next call to get only what is new."""
    path = Path(AUDIT_FILE)
    entries = json.loads(path.read_text()) if path.exists() and path.stat().st_size else []
    total = len(entries)
    wanted = [(i, e) for i, e in enumerate(entries)
              if (ticket_id is None or e["ticket_id"] == ticket_id) and (run_id is None or e["run_id"] == run_id)]
    if after is None:
        page = wanted[-limit:]
        nxt = total
    else:
        newer = [(i, e) for i, e in wanted if i >= after]
        page = newer[:limit]
        nxt = page[-1][0] + 1 if len(newer) > limit else total
    return EventsOut(events=[event_out(i, e) for i, e in page], next_cursor=nxt, total=total)


# ---------------------------------------------------------------- approvals and cash

@app.get("/api/approvals", response_model=list[ApprovalOut])
async def approvals(status: str | None = None, ticket_id: int | None = None):
    """Payment requests the agents have prepared, so the board can show which are waiting for a human."""
    args = {k: v for k, v in (("status", status), ("ticket_id", ticket_id)) if v is not None}
    return (await shop_call("list_approvals", args))["approvals"]


@app.post("/api/approvals/{approval_id}/approve", response_model=PaymentOut)
async def approve(approval_id: int, body: ApproveRequest):
    """A human clicked approve. This is the only route that moves cash: it makes the payment for an
    approval the agents prepared (an invoice, rent, or a purchase order). The MCP tool refuses if
    the account lacks the cash, so the balance never goes negative."""
    result = await shop_call("execute_approved_payment", {"approval_id": approval_id, "approved_by": body.approved_by})
    if not result["ok"]:
        error = result["error"]
        raise HTTPException(404 if "not found" in error else 409, error)
    audit_human("approve_payment", None, {
        "approval_id": approval_id, "approved_by": body.approved_by, "result": result,
        "summary": f"{body.approved_by} approved {result['kind'].replace('_', ' ')} {result['ref_id']}: ${result['amount']:,.2f}"})
    follow = await maybe_continue(await approval_ticket(approval_id), f"{body.approved_by} approved a payment")
    return {**result, "continued_run_id": follow[0] if follow else None, "continued_ticket_id": follow[1] if follow else None}


@app.post("/api/approvals/{approval_id}/decline", response_model=DeclineOut)
async def decline(approval_id: int, body: DeclineRequest):
    """A human said no to a payment the agents prepared. No money moves."""
    result = await shop_call("decline_payment", {"approval_id": approval_id, "declined_by": body.declined_by})
    if not result["ok"]:
        error = result["error"]
        raise HTTPException(404 if "not found" in error else 409, error)
    audit_human("decline_payment", None, {"approval_id": approval_id, "declined_by": body.declined_by,
                                          "summary": f"{body.declined_by} declined approval {approval_id}"})
    follow = await maybe_continue(await approval_ticket(approval_id), f"{body.declined_by} declined a payment")
    return {**result, "continued_run_id": follow[0] if follow else None, "continued_ticket_id": follow[1] if follow else None}


@app.post("/api/approvals/{approval_id}/receive", response_model=ReceiveOut)
async def receive(approval_id: int, body: ReceiveRequest):
    """A human confirms a paid purchase order has arrived. The ordered quantity is added to inventory."""
    args = {"approval_id": approval_id, "received_by": body.received_by}
    if body.size:
        args["size"] = body.size
    result = await shop_call("receive_shipment", args)
    if not result["ok"]:
        error = result["error"]
        raise HTTPException(404 if "not found" in error else 409, error)
    audit_human("receive_shipment", None, {"approval_id": approval_id, "received_by": body.received_by, "result": result,
                                           "summary": f"{body.received_by} confirmed purchase order {approval_id} arrived: "
                                                      f"{result['qty_received']} x {result['sku']} size {result['size']} "
                                                      f"(on hand {result['qty_on_hand_before']} → {result['qty_on_hand_after']})"})
    follow = await maybe_continue(await approval_ticket(approval_id), f"{body.received_by} confirmed a delivery arrived")
    return {**result, "continued_run_id": follow[0] if follow else None, "continued_ticket_id": follow[1] if follow else None}


@app.post("/api/tickets/{ticket_id}/decision", response_model=DecisionOut)
async def decision(ticket_id: int, body: DecisionRequest):
    """A human records a decision about a ticket. The agents see it as `human_decisions` when they read the ticket."""
    result = await shop_call("record_human_decision", {"ticket_id": ticket_id, "decided_by": body.decided_by,
                                                      "decision": body.decision})
    if not result["ok"]:
        raise HTTPException(404 if "not found" in result["error"] else 409, result["error"])
    audit_human("record_decision", ticket_id, {"decided_by": body.decided_by, "decision": body.decision,
                                              "summary": f"{body.decided_by} decided on ticket {ticket_id}: {body.decision}"})
    follow = await maybe_continue(ticket_id, f"{body.decided_by} recorded a decision")
    return {**result, "continued_run_id": follow[0] if follow else None, "continued_ticket_id": follow[1] if follow else None}


_reset_cache: dict = {"key": None, "value": None}


def last_reset_balance() -> float | None:
    """The checking balance the most recent database reset reported, read from the audit trail."""
    path = Path(AUDIT_FILE)
    if not path.exists():
        return None
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    if _reset_cache["key"] != key:  # the file only changes when something is recorded, so parse it only then
        resets = [e for e in json.loads(path.read_text() or "[]")
                  if e["event"] == "human_action" and e["detail"].get("action") == "reset_database"]
        _reset_cache.update(key=key, value=resets[-1]["detail"]["result"]["checking_balance"] if resets else None)
    return _reset_cache["value"]


@app.get("/api/cash", response_model=CashOut)
async def cash():
    """The current checking balance (cash_accounts), and what is already spoken for by pending approvals."""
    data = await shop_call("check_cash", {"account": CASH_ACCOUNT})
    if not data["ok"]:
        raise HTTPException(404, f"cash account {CASH_ACCOUNT} not found")
    a = data["accounts"][0]
    return CashOut(account=a["name"], balance=a["balance"], date=a["date"],
                   pending_approvals_total=a["pending_approvals_total"], balance_after_pending=a["balance_after_pending"],
                   starting_balance=last_reset_balance())


# ---------------------------------------------------------------- reset

@app.post("/api/reset", response_model=ResetOut)
async def reset():
    """Put the database back to its original values for a fresh run. The audit trail is not touched."""
    if (busy := active_run()) is not None:
        raise HTTPException(409, f"the team is working ticket {busy.ticket_id}; wait for it to finish")
    result = await shop_call("reset_shop_database")
    audit_human("reset_database", None, {"summary": "database reset to the original values", "result": result})
    return result
