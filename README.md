# Campus Customs: a team of agents that runs a small shop (HW 5)

A PydanticAI team (Boss, Inventory, Accounting, Facilities, Customer Service, all on `gpt-6-luna` through Portkey) works three open tickets using an MCP server over SQLite. Agents can only *request* payments; a person approves them in a React dashboard. Every agent step is appended to `output/audit_trail.json`.

- `mcp_server/` the FastMCP server (21 tools) over `data/campus_customs_new.db`
- `backend/` the agent team, prompts (`backend/prompts/`) and the FastAPI routes
- `frontend/` the React + Vite + TypeScript dashboard
- `data/campus_customs.db` the original database, kept for resets; `data/campus_customs_new.db` the working copy (this is the finished run: three tickets resolved, checking at $152.00); `data/backups/` earlier runs
- `output/` the plan and results (`desk_tickets.html`, `resolved_board.html`, `resolved_tickets.json`), the run log, `harness.md` (agents, tools, safety) and `design.md`
- `AI_prompts.md` the prompts used to build it

## Run it

You need Python 3.11+ and Node 18+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then put your PORTKEY_API_KEY in .env
```

Backend (from `backend/`):

```bash
cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000
```

Dashboard (from `frontend/`, opens on http://localhost:5173):

```bash
cd frontend && npm install && npm run dev
```

Viewing the results needs no key and no server: open `output/desk_tickets.html` or `output/resolved_board.html` in a browser. The "Reset database" button restores the original data (and saves the current run to `data/backups/` first). Running the agents calls the model, so it needs `PORTKEY_API_KEY`.

To check the code without calling the model: `.venv/bin/python tests/run_checks.py` (one tiny model ping needs the key; everything else uses scratch copies of the database).
