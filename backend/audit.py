"""Audit trail: every step of every agent loop is appended to output/audit_trail.json.

The file is one JSON list. Entries are only ever added: it is never emptied or rewritten from
scratch, and if it ever holds something that is not a JSON list we stop rather than overwrite it.
Each entry is written the moment the step happens, so a run that crashes still leaves its trail.
"""

import json
import os
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
from pydantic_core import to_jsonable_python
from pydantic_ai import Agent
from pydantic_ai.messages import RetryPromptPart, TextPart, ThinkingPart, ToolCallPart, ToolReturnPart

from models import AuditEntry, AuditEvent, TeamDeps

ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = Path(os.environ.get("AUDIT_TRAIL_PATH", ROOT / "output" / "audit_trail.json"))  # env override is for tests
SLOW_SECONDS = 15.0  # a model request slower than this is recorded even if it eventually answered
MAX_CHARS = 20000  # longest tool result or output kept in full; longer ones are cut and flagged
_write_lock = threading.Lock()
# Which agent turn is running, so the model client can say whose request was slow or timed out.
_ACTIVE: ContextVar[tuple | None] = ContextVar("audit_active_turn", default=None)


def note_model_attempt(seconds: float, error: str | None) -> None:
    """Record a model request that timed out (error set) or was slow but answered. Never raises."""
    ctx = _ACTIVE.get()
    if ctx is None:
        return
    log, name, inv, deps = ctx
    try:
        log.record("model_retry", {"seconds": round(seconds, 1), "error": error,
                                   "outcome": "no answer, the client retries" if error else "answered, but slowly"},
                   agent=name, invocation=inv, deps=deps)
    except Exception:
        pass


def _clip(value) -> tuple[object, bool]:
    value = to_jsonable_python(value)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return (text[:MAX_CHARS], True) if len(text) > MAX_CHARS else (value, False)


def append_entries(path: Path, entries: list[AuditEntry]) -> None:
    """Add entries to the end of the file, keeping everything already in it."""
    with _write_lock:
        existing = []
        if path.exists() and path.stat().st_size:
            existing = json.loads(path.read_text())
            if not isinstance(existing, list):
                raise ValueError(f"{path} is not a JSON list; refusing to overwrite it")
        existing.extend(e.model_dump(mode="json") for e in entries)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)  # the file is never half-written


class AuditLog:
    """One per ticket run. Every agent in that run writes through the same log."""

    def __init__(self, ticket_id: int | None, path: Path = AUDIT_PATH):
        self.path, self.ticket_id = path, ticket_id
        self.run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:6]}"
        self._seq, self._turns = 0, {}

    def new_invocation(self, agent: str) -> str:
        self._turns[agent] = self._turns.get(agent, 0) + 1
        return f"{agent}#{self._turns[agent]}"

    def record(self, event: AuditEvent, detail: dict, *, agent=None, invocation=None, deps: TeamDeps | None = None,
               step=None) -> None:
        self._seq += 1
        append_entries(self.path, [AuditEntry(
            run_id=self.run_id, seq=self._seq, time=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            ticket_id=self.ticket_id, agent=agent, invocation=invocation, depth=deps.depth if deps else 0,
            chain=list(deps.chain) if deps else [], step=step, event=event, detail=detail)])


async def run_agent(name: str, prompt: str, deps: TeamDeps, usage=None, usage_limits=None):
    """Run one agent of the team to its final answer, writing each loop step to the audit trail."""
    agent: Agent = deps.team[name]
    log: AuditLog = deps.audit
    inv = log.new_invocation(name)
    rec = lambda event, detail, step=None: log.record(event, detail, agent=name, invocation=inv, deps=deps, step=step)
    rec("agent_start", {"prompt": prompt, "asked_by": deps.chain[-1] if deps.chain else None})
    step = 0
    turn = _ACTIVE.set((log, name, inv, deps))
    try:
        async with agent.iter(prompt, deps=deps, usage=usage, usage_limits=usage_limits) as run:
            async for node in run:
                if Agent.is_model_request_node(node):  # carries back the results of the tools just called
                    for part in node.request.parts:
                        if isinstance(part, ToolReturnPart):
                            content, cut = _clip(part.content)
                            rec("tool_result", {"tool": part.tool_name, "call_id": part.tool_call_id,
                                                "result": content, "truncated": cut}, step)
                        elif isinstance(part, RetryPromptPart):
                            content, cut = _clip(part.content)
                            rec("tool_retry", {"tool": part.tool_name, "call_id": part.tool_call_id,
                                               "problem": content, "truncated": cut}, step)
                elif Agent.is_call_tools_node(node):  # the model's answer: text and/or tool calls
                    step += 1
                    resp = node.model_response
                    rec("model_response", {
                        "model": resp.model_name,
                        "tokens": {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens},
                        "thinking": [p.content for p in resp.parts if isinstance(p, ThinkingPart) and p.content],
                        "text": [p.content for p in resp.parts if isinstance(p, TextPart)],
                        "tool_calls": [{"tool": p.tool_name, "call_id": p.tool_call_id, "args": p.args_as_dict()}
                                       for p in resp.parts if isinstance(p, ToolCallPart)],
                    }, step)
            result = run.result
    except Exception as exc:
        rec("error", {"type": type(exc).__name__, "message": str(exc)[:2000]}, step or None)
        raise
    finally:
        _ACTIVE.reset(turn)
    output, cut = _clip(result.output.model_dump() if isinstance(result.output, BaseModel) else result.output)
    rec("agent_end", {"output": output, "truncated": cut, "model_requests": step}, step or None)
    return result
