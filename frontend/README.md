# Campus Customs dashboard

React + Vite + TypeScript. It calls the FastAPI backend (`backend/main.py`) and nothing else.

## Run it

1. Backend, from the `backend/` folder: `../.venv/bin/uvicorn main:app --reload --port 8000`
2. Dashboard, from this folder: `npm install` (first time), then `npm run dev`
3. Open http://localhost:5173

The backend address is `http://localhost:8000`. To point somewhere else, set `VITE_API_URL` before `npm run dev`.

## Files

- `src/api.ts` typed calls to the backend routes; `src/types.ts` their shapes
- `src/hooks.ts` polling, and the cursor-based event stream
- `src/derive.ts` turns the agent events into agent status, feed lines and summaries
- `src/components/` Header (balance, reset), TicketList, RunBanner, AgentBoard (agent cards and summaries), Feed, Approvals
