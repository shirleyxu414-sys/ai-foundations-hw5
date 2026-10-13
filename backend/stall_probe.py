"""Find out whether model requests stall, how often, and whether the same request stalls again.

  CAMPUS_DB=<scratch db> AUDIT_TRAIL_PATH=<scratch json> STALL_DUMP_DIR=<dir> \\
      .venv/bin/python backend/stall_probe.py runs 12        # run the Customer Service agent 12 times per prompt
  .venv/bin/python backend/stall_probe.py replay <dir> 10    # send each saved stalled request again, 10 times

Always point it at scratch copies: the agent writes drafts. The prompts are the Customer Service requests from the
two real runs that stalled (ticket 101 pass 1 and ticket 103 pass 2), read from output/audit_trail.json.
"""

import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from agent import MODEL_NAME, PORTKEY_URL, build_team
from audit import AUDIT_PATH, AuditLog, run_agent
from models import TeamDeps
from tools import ROOT

REAL_AUDIT = ROOT / "output" / "audit_trail.json"


def stalled_prompts() -> list[tuple[str, str]]:
    entries = json.loads(REAL_AUDIT.read_text())
    out = []
    for run_suffix, label in (("832c1d", "ticket 101 pass 1"), ("4fb6a8", "ticket 103 pass 2")):
        start = next(e for e in entries if e["run_id"].endswith(run_suffix) and e["event"] == "agent_start"
                     and e["agent"] == "customer_service")
        out.append((label, start["detail"]["prompt"]))
    return out


async def probe_runs(n: int) -> None:
    assert os.environ.get("CAMPUS_DB") and os.environ.get("AUDIT_TRAIL_PATH"), "use scratch copies, see the docstring"
    team = build_team()
    results = []
    for label, prompt in stalled_prompts():
        for i in range(n):
            audit = AuditLog(None, AUDIT_PATH)
            deps = TeamDeps(team=team, trace=[], audit=audit)
            t0 = time.monotonic()
            try:
                await asyncio.wait_for(run_agent("customer_service", prompt, deps), 240)
                status = "ok"
            except Exception as exc:
                status = type(exc).__name__
            results.append((label, i, time.monotonic() - t0, status))
            print(f"{label} run {i + 1}/{n}: {results[-1][2]:5.1f}s {status}", flush=True)
    entries = [e for e in json.loads(AUDIT_PATH.read_text()) if e["run_id"].startswith(datetime.now().strftime("%Y"))]
    mr = [e for e in entries if e["event"] == "model_response"]
    retries = [e for e in entries if e["event"] == "model_retry"]
    # latency of every model request = gap from the entry before it
    gaps = []
    for a, b in zip(entries, entries[1:]):
        if b["event"] == "model_response" and a["run_id"] == b["run_id"]:
            gaps.append((datetime.fromisoformat(b["time"]) - datetime.fromisoformat(a["time"])).total_seconds())
    print(f"\nmodel requests answered: {len(mr)} | median gap {statistics.median(gaps):.1f}s | max {max(gaps):.1f}s")
    print(f"slow or timed-out attempts recorded (model_retry): {len(retries)}")
    for r in retries:
        d = r["detail"]
        print(f"   {r['invocation']} step after {d['seconds']}s error={d['error']} -> {d['outcome']}")


async def replay(folder: Path, n: int) -> None:
    key = os.environ["PORTKEY_API_KEY"]
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as c:
        for f in sorted(folder.glob("stalled_*.json")):
            body = f.read_bytes()
            print(f"\n{f.name} ({len(body):,} bytes), replayed {n} times:")
            times = []
            for _ in range(n):
                t0 = time.monotonic()
                try:
                    r = await c.post(PORTKEY_URL + "/responses", content=body,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                    times.append((time.monotonic() - t0, f"HTTP {r.status_code}"))
                except Exception as exc:
                    times.append((time.monotonic() - t0, type(exc).__name__))
            print("   ", [f"{t:.1f}s {s}" for t, s in times])
            print(f"    stalled again: {sum(1 for _, s in times if 'Timeout' in s)} of {n}")


if __name__ == "__main__":
    if sys.argv[1] == "runs":
        asyncio.run(probe_runs(int(sys.argv[2])))
    else:
        asyncio.run(replay(Path(sys.argv[2]), int(sys.argv[3])))
