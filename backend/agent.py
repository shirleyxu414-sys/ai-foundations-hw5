"""The Campus Customs agent team: Boss, Inventory, Accounting, Facilities, Customer Service.

Every agent runs on gpt-6-luna through Portkey, uses the same MCP tools (the shop database), and
can delegate to every other agent. Run one ticket:  python backend/agent.py 101
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from audit import AUDIT_PATH, SLOW_SECONDS, AuditLog, note_model_attempt, run_agent
from models import AgentReport, TeamDeps, TicketDecision
from tools import AGENT_NAMES, ROOT, add_delegation_tools, mcp_toolset

load_dotenv(ROOT / ".env")  # a .env next to this project (see .env.example)
load_dotenv(ROOT.parent / ".env")  # or the course root .env; PORTKEY_API_KEY lives in one of them

MODEL_NAME = "gpt-6-luna"
PORTKEY_URL = "https://api.portkey.ai/v1"
PROMPTS = Path(__file__).parent / "prompts"
REQUEST_LIMIT = 80  # model requests allowed per ticket, a guard against runaway delegation loops
MODEL_TIMEOUT = 30.0  # seconds one model request may take before it is retried (twice) and then fails.
# Normal requests take a median of 2.5 s and never more than about 8 s, so 30 s only ever cuts off a stalled one.


class TimedTransport(httpx.AsyncHTTPTransport):
    """Times every model request and tells the audit trail about any that stall or time out.

    Set STALL_DUMP_DIR to also save the body of a request that timed out (no key, no headers), so it can be replayed.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        started = time.monotonic()
        try:
            response = await super().handle_async_request(request)
        except Exception as exc:
            note_model_attempt(time.monotonic() - started, type(exc).__name__)
            dump_dir = os.environ.get("STALL_DUMP_DIR")
            if dump_dir:
                Path(dump_dir).mkdir(parents=True, exist_ok=True)
                (Path(dump_dir) / f"stalled_{int(time.time() * 1000)}.json").write_bytes(request.content)
            raise
        if (seconds := time.monotonic() - started) >= SLOW_SECONDS:
            note_model_attempt(seconds, None)
        return response


def make_model() -> OpenAIResponsesModel:
    http = httpx.AsyncClient(transport=TimedTransport(), timeout=httpx.Timeout(MODEL_TIMEOUT, connect=10.0))
    client = AsyncOpenAI(api_key=os.environ["PORTKEY_API_KEY"], base_url=PORTKEY_URL, timeout=MODEL_TIMEOUT,
                         max_retries=2, http_client=http)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def build_team() -> dict[str, Agent]:
    """Create the five agents. All share one model and one MCP toolset; roles differ by prompt."""
    model, toolset = make_model(), mcp_toolset()
    rules = (PROMPTS / "team.md").read_text()
    team: dict[str, Agent] = {}
    for name in AGENT_NAMES:
        team[name] = Agent(
            model,
            name=name,
            instructions=rules + "\n\n" + (PROMPTS / f"{name}.md").read_text(),
            output_type=TicketDecision if name == "boss" else AgentReport,
            deps_type=TeamDeps,
            toolsets=[toolset],
            retries=2,
        )
        add_delegation_tools(team[name], name)
    return team


async def work_ticket(ticket_id: int, team: dict[str, Agent] | None = None, audit_path: Path = AUDIT_PATH,
                      audit: AuditLog | None = None, note: str | None = None):
    """The agent loop: the Boss gets the ticket and delegates until it makes a decision.
    Every step is appended to output/audit_trail.json (never wiped between runs)."""
    team = team or build_team()
    audit = audit or AuditLog(ticket_id, audit_path)
    deps = TeamDeps(team=team, trace=[], audit=audit)
    audit.record("run_start", {"model": MODEL_NAME, "request_limit": REQUEST_LIMIT, "max_depth": deps.max_depth,
                               "agents": list(team)})
    prompt = f"Ticket {ticket_id} is on the board. Triage it, get it worked, and make the final decision."
    if note:  # a person acted on the ticket since the last run; the team carries on from there
        prompt += (f" A person has just acted on it ({note}). Read the ticket again (it shows payments, deliveries and "
                   "decisions), see what changed, and carry on from there.")
    try:
        result = await run_agent("boss", prompt, deps, usage_limits=UsageLimits(request_limit=REQUEST_LIMIT))
    except Exception as exc:
        audit.record("run_end", {"status": "failed", "error": type(exc).__name__})
        raise
    usage = result.usage
    audit.record("run_end", {"status": "finished", "decision": result.output.model_dump(),
                             "delegations": len(deps.trace),
                             "usage": {"requests": usage.requests, "input_tokens": usage.input_tokens,
                                       "output_tokens": usage.output_tokens}})
    return result.output, deps.trace


async def main(ticket_ids: list[int]) -> None:
    team = build_team()
    for tid in ticket_ids:
        decision, trace = await work_ticket(tid, team)
        print(f"\n=== Ticket {tid} ===")
        for e in trace:
            print(f"  {'  ' * (e.depth - 1)}{e.caller} -> {e.callee}: {e.request[:110]}"
                  + (f"  [{e.error}]" if e.error else ""))
        print(decision.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main([int(a) for a in sys.argv[1:]] or [101, 102, 103]))
