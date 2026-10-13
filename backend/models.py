"""Every structured type the Campus Customs agent team uses."""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

TicketStatus = Literal["open", "in_progress", "waiting_approval", "resolved"]


class DelegationEvent(BaseModel):
    """One delegation from one agent to another, kept so a human can watch the team work."""

    caller: str
    callee: str
    depth: int
    request: str
    response: str | None = None
    error: str | None = None


class AgentReport(BaseModel):
    """What a specialist (inventory, accounting, facilities, customer_service) hands back."""

    agent: str
    summary: str = Field(description="Two or three sentences with the answer, citing tool values.")
    findings: list[str] = Field(default_factory=list, description="Facts from tools, one per line.")
    actions_taken: list[str] = Field(default_factory=list, description="Tool writes you made.")
    needs_human_approval: list[str] = Field(
        default_factory=list, description="Pending payment approvals, e.g. 'approval 3: $840 invoice 501'.")
    blockers: list[str] = Field(default_factory=list, description="What stops this from being finished.")


class TicketDecision(BaseModel):
    """The Boss's final decision on a ticket."""

    ticket_id: int
    status: TicketStatus
    owners: list[str] = Field(description="Agents that did work on this ticket.")
    decision: str = Field(description="The decision in plain words.")
    reasoning: str = Field(description="Why, tied to values the tools returned.")
    approval_ids: list[int] = Field(default_factory=list, description="Payment approvals requested.")
    draft_ids: list[int] = Field(default_factory=list, description="Customer drafts saved.")


AuditEvent = Literal["run_start", "agent_start", "model_response", "model_retry", "tool_result", "tool_retry",
                     "agent_end", "error", "run_end", "human_action"]


class AuditEntry(BaseModel):
    """One line of output/audit_trail.json: one step of one agent in one ticket run."""

    run_id: str = Field(description="One id per ticket run; groups every entry of that run.")
    seq: int = Field(description="Order of entries within the run, starting at 1.")
    time: str = Field(description="UTC timestamp when the entry was written.")
    ticket_id: int | None
    agent: str | None = Field(description="Which agent took this step (null for run-level entries).")
    invocation: str | None = Field(description="Which turn of that agent, e.g. 'inventory#2'.")
    depth: int = Field(description="0 = Boss, 1 = asked by Boss, 2 = asked by an agent Boss asked, ...")
    chain: list[str] = Field(description="Who was waiting on whom when this step happened, outermost first.")
    step: int | None = Field(description="Model request number inside this agent invocation.")
    event: AuditEvent
    detail: dict[str, Any]


@dataclass
class TeamDeps:
    """Shared run state passed to every agent so they can delegate to each other."""

    team: dict[str, Any]  # agent name -> Agent; filled in by backend/agent.py
    trace: list[DelegationEvent]  # shared across the whole ticket run
    audit: Any = None  # AuditLog from backend/audit.py; records every agent-loop step
    chain: tuple[str, ...] = ()  # agents currently waiting on each other, outermost first
    max_depth: int = 4

    @property
    def depth(self) -> int:
        return len(self.chain)


# ---- Types for the FastAPI routes (backend/main.py) ----

class TicketSummary(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    status: str = Field(description="The raw board status: open, in_progress, waiting_approval or resolved.")
    state: Literal["open", "resolved"] = Field(description="resolved only when status is resolved.")
    running: bool = Field(description="True while the agent team is working this ticket.")


class RunStarted(BaseModel):
    run_id: str
    ticket_id: int
    state: Literal["running"] = "running"


class RunStatus(BaseModel):
    run_id: str
    ticket_id: int
    state: Literal["running", "finished", "failed"]
    started_at: str
    finished_at: str | None = None
    decision: TicketDecision | None = None
    error: str | None = None


class EventOut(BaseModel):
    """One audit entry shaped for the board."""

    id: int = Field(description="Position in output/audit_trail.json; use it as a cursor.")
    run_id: str
    seq: int
    time: str
    ticket_id: int | None
    agent: str | None
    invocation: str | None
    depth: int
    chain: list[str]
    step: int | None
    event: str
    said: str | None = Field(description="What the agent said, when this entry has words.")
    tools: list[str] = Field(description="Names of the MCP or delegation tools this entry used or returned.")
    detail: dict[str, Any]


class EventsOut(BaseModel):
    events: list[EventOut]
    next_cursor: int = Field(description="Pass as ?after= on the next call to get only newer events.")
    total: int


class CashOut(BaseModel):
    account: str
    balance: float
    date: str
    pending_approvals_total: float
    balance_after_pending: float
    starting_balance: float | None = Field(default=None, description="The balance the most recent reset put in the account, if one is on record.")


class ApprovalOut(BaseModel):
    id: int
    kind: str
    ref_id: int
    ticket_id: int | None
    amount: float
    account: str
    reason: str | None
    requested_by: str | None
    status: str
    created_at: str
    sku: str | None = None
    qty: int | None = None
    received_at: str | None = Field(default=None, description="Set when a human confirmed a purchase order arrived.")
    received_by: str | None = None


class ApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1, description="The human who clicked approve.")


class PaymentOut(BaseModel):
    ok: bool
    approval_id: int
    kind: str
    ref_id: int
    amount: float
    paid_at: str
    approved_by: str
    balance_after: float
    continued_run_id: str | None = Field(default=None, description="Set when this human action made the team pick the ticket up again.")
    continued_ticket_id: int | None = None


class ResetOut(BaseModel):
    ok: bool
    date_today: str
    checking_balance: float
    backup: str | None = Field(default=None, description="Where the previous run was saved before the reset, if there was one.")


class DeclineRequest(BaseModel):
    declined_by: str = Field(min_length=1, description="The human who clicked decline.")


class DeclineOut(BaseModel):
    ok: bool
    approval_id: int
    status: str
    declined_by: str
    continued_run_id: str | None = Field(default=None, description="Set when this human action made the team pick the ticket up again.")
    continued_ticket_id: int | None = None


class ReceiveRequest(BaseModel):
    received_by: str = Field(min_length=1, description="The person who confirmed the delivery arrived.")
    size: str | None = Field(default=None, description="Only needed if the order is not tied to a ticket with a size.")


class ReceiveOut(BaseModel):
    ok: bool
    approval_id: int
    sku: str
    size: str
    qty_received: int
    qty_on_hand_before: int
    qty_on_hand_after: int
    received_by: str
    received_at: str
    continued_run_id: str | None = Field(default=None, description="Set when this human action made the team pick the ticket up again.")
    continued_ticket_id: int | None = None


class DecisionRequest(BaseModel):
    decided_by: str = Field(min_length=1)
    decision: str = Field(min_length=3, max_length=1000, description="What the human decided about this ticket.")


class DecisionOut(BaseModel):
    ok: bool
    ticket_id: int
    decided_by: str

    continued_run_id: str | None = Field(default=None, description="Set when this human action made the team pick the ticket up again.")
    continued_ticket_id: int | None = None