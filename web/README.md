# RuleStorm web UI

React + Vite + Tailwind. Plan and design rules: `design/FRONTEND_PLAN.md`.

- Install once: `npm install` (in `web/`)
- Develop: start the API (`python -m uvicorn rulestorm.api:app --port 8000` from the repo root), then `npm run dev` here; Vite forwards `/api` to port 8000.
- Build: `npm run build` writes `web/dist`, which is committed and served by FastAPI at `/` (see the end of `rulestorm/api.py`). No Node on the server.

Layout: `src/ui` (primitives) · `src/sim` (map, agents, clock, time ruler, director) · `src/domain` (RuleStorm pieces) · `src/screens` · `src/lib` (API client, router, template words).
