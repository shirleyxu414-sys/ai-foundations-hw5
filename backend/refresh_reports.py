"""Rebuild every generated record from the live shop data in one command.

  .venv/bin/python backend/refresh_reports.py            rebuild the Cash tab and resolved_tickets.json / resolved_board.html
  .venv/bin/python backend/refresh_reports.py --shots    also retake the three board screenshots first
                                                         (needs the dashboard running on http://localhost:5173)
  --force                                                rebuild even if the tickets are not all resolved (it refuses by default,
                                                         so a reset database cannot overwrite the record of a finished run)

Run it after a rerun, once the tickets have reached the state you want recorded.
"""

import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import Client

from tools import mcp_config

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


async def tickets_resolved() -> bool:
    async with Client(mcp_config()) as shop:
        tickets = (await shop.call_tool("list_tickets", {})).data["tickets"]
    return all(t["status"] == "resolved" for t in tickets)


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


if __name__ == "__main__":
    # These files are the record of a finished run. Rebuilding them from a database that has been reset (or is
    # mid-run) would replace that record with an unfinished one, so it needs --force.
    if "--force" not in sys.argv and not asyncio.run(tickets_resolved()):
        sys.exit("Not all three tickets are resolved in the working database, so nothing was rebuilt.\n"
                 "That would overwrite the record of the finished run with an unfinished one.\n"
                 "Finish the run first, or pass --force if you really want it.")
    if "--shots" in sys.argv:
        for ticket in (101, 102, 103):
            run(["node", "scripts/shot.mjs", str(ticket)], ROOT / "frontend")
    run([PY, "backend/cash_report.py"])
    run([PY, "backend/resolved_report.py"])
