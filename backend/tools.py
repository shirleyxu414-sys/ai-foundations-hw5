"""Tools for the agent team: the MCP toolset (shop database) and delegation between agents."""

import json
import os
from pathlib import Path

from fastmcp import Client
from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPToolset

from audit import run_agent
from models import DelegationEvent, TeamDeps

HUMAN_ONLY_TOOLS = ("execute_approved_payment", "decline_payment", "reset_shop_database", "receive_shipment",
                    "record_human_decision")  # same names as mcp_server/server.py
ROOT = Path(__file__).resolve().parent.parent  # hw 5/
AGENT_NAMES = ("boss", "inventory", "accounting", "facilities", "customer_service")

PEER_BLURB = {
    "boss": "triages tickets, assigns owners and makes the final decision",
    "inventory": "checks stock by SKU and size, flags shortfalls, finds the vendor to restock",
    "accounting": "cash, invoices, margins; prepares payments for human approval",
    "facilities": "the shop space: leases and rent",
    "customer_service": "drafts customer-facing messages (never sent)",
}


def mcp_config() -> dict:
    """The MCP server saved in .mcp.json, with its relative paths pinned to the project root."""
    cfg = json.loads((ROOT / ".mcp.json").read_text())
    for server in cfg["mcpServers"].values():
        server["command"] = str(ROOT / server["command"])
        server["args"] = [str(ROOT / a) for a in server.get("args", [])]
        server["env"] = {k: str(ROOT / v) for k, v in server.get("env", {}).items()}
        if os.environ.get("CAMPUS_DB"):  # tests point the whole stack at a scratch copy of the database
            server["env"]["CAMPUS_DB"] = os.environ["CAMPUS_DB"]
    return cfg


def mcp_toolset():
    toolset = MCPToolset(Client(mcp_config()))
    # Agents get every MCP tool except the ones that pay, decline or reset: those are for a human.
    return toolset.filtered(lambda ctx, tool: tool.name not in HUMAN_ONLY_TOOLS)


def add_delegation_tools(agent, name: str) -> None:
    """Give `agent` an ask_<peer> tool for every other agent (full connectivity)."""
    for peer in AGENT_NAMES:
        if peer != name:
            agent.tool(name=f"ask_{peer}", description=f"Delegate a request to {peer} ({PEER_BLURB[peer]}). "
                       "Write it so it stands alone: ticket id, SKU/size/ids, and exactly what you need back.")(
                _make_ask(name, peer))


def _make_ask(caller: str, callee: str):
    async def ask(ctx: RunContext[TeamDeps], request: str) -> str:
        deps = ctx.deps
        event = DelegationEvent(caller=caller, callee=callee, depth=deps.depth + 1, request=request)
        if callee in deps.chain or callee == caller:
            event.error = f"{callee} is already working on this request up the chain."
        elif deps.depth >= deps.max_depth:
            event.error = "Delegation depth limit reached. Answer with what your own tools show."
        if event.error:
            deps.trace.append(event)
            return event.error
        deps.trace.append(event)
        sub = TeamDeps(team=deps.team, trace=deps.trace, audit=deps.audit, chain=(*deps.chain, caller),
                       max_depth=deps.max_depth)
        result = await run_agent(callee, request, sub, usage=ctx.usage)
        event.response = result.output.model_dump_json()
        return event.response

    ask.__name__ = f"ask_{callee}"
    return ask
