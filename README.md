# Campus Customs: a team of agents that runs a small shop (HW 5)

A PydanticAI team (Boss, Inventory, Accounting, Facilities, Customer Service, all on `gpt-6-luna` through Portkey) works three open tickets using an MCP server over SQLite. Agents can only *request* payments; a person approves them in a React dashboard. Every agent step is appended to `output/audit_trail.json`.

- `mcp_server/` the FastMCP server (21 tools) over `data/campus_customs_new.db`
- `backend/` the agent team, prompts (`backend/prompts/`) and the FastAPI routes
- `frontend/` the React + Vite + TypeScript dashboard
- `data/campus_customs.db` the original database, kept for resets; `data/campus_customs_new.db` the working copy (this is the finished run: three tickets resolved, checking at $152.00); `data/backups/` earlier runs
- `output/` the plan and results (`desk_tickets.html`, `resolved_board.html`, `resolved_tickets.json`), the run log, `harness.md` (agents, tools, safety) and `design.md`
- `AI_prompts.md` the prompts used to build it

## Run it

Everything below is run from the project folder (the one holding this README) unless it says otherwise. You need Python 3.11+ and Node 18+.

### 1. Set up once

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your own PORTKEY_API_KEY in .env (never commit it)
cd frontend && npm install && cd ..
```

### 2. Copy the original database to the working copy (a clean start)

`data/campus_customs.db` is the original and is never changed. The app works on `data/campus_customs_new.db`. To start from a clean shop (three open tickets, checking at $3,400.00, no approvals, payments or drafts), copy the original over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

The cloned repo's working copy is the finished run ($152.00, three tickets resolved), so do this, or the reset in step 6, before running the tickets again.

### 3. Start the MCP server

```bash
.venv/bin/python mcp_server/server.py
```

It talks over stdio, so it waits silently for a client. You do not have to start it for the app: the backend launches its own copy and the agents reach all shop data through it. Run it by hand only to try the tools from an MCP client (`.mcp.json` already points a client such as Claude Code at it). To use a different database file, set `CAMPUS_DB=path/to/file.db` first.

### 4. Start the FastAPI backend (port 8000)

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

Leave it running. The API docs are at http://localhost:8000/docs.

### 5. Start the React board (port 5173)

In a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The board shows the checking balance, the three tickets, the agent team, the live feed and the approvals. It talks to the backend at http://localhost:8000 (set `VITE_API_URL` in `frontend/.env` to change that).

### 6. Reset the database before a full three-ticket run

Use the **Reset database** button on the board (it asks you to click a second time to confirm), or, with the backend running:

```bash
curl -X POST http://localhost:8000/api/reset
```

It restores the original data, first saving any finished or partly finished run to `data/backups/`, and records the starting balance ($3,400.00) in `output/audit_trail.json`. The board's "Started at" line reads that record. It refuses while a run is in progress. Prefer this over the plain `cp` in step 2 when you use the board, because `cp` leaves no backup and no reset entry, so the board would show an older starting balance. (`output/audit_trail.json` is append-only and is never wiped.)

Then run all three tickets: select each ticket (101, 102, 103) and click **Run the team on #…**. Agents only prepare payments. When a ticket reaches "waiting for approval", approve it in the **Approvals** panel with your name (the agents cannot pay). After an approval the team continues on that ticket by itself. If a ticket needs a delivery confirmed ("Mark received") or a decision, the board offers those too. Each ticket should end resolved and the checking balance should equal $3,400.00 minus the payments you approved.

Running the agents calls the model, so it needs `PORTKEY_API_KEY`. To rebuild the Cash tab and the two resolved files from a finished run: `.venv/bin/python backend/refresh_reports.py` (add `--shots` to retake the board screenshots, which needs the board running).

Viewing the saved results needs no key and no server: open `output/desk_tickets.html` or `output/resolved_board.html` in a browser.

To check the code without calling the model: `.venv/bin/python tests/run_checks.py` (one tiny model ping needs the key; everything else uses scratch copies of the database).
