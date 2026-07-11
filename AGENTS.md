# AGENTS.md

## Cursor Cloud specific instructions

STRATA is a local-only structured-credit analytics app with two dev services (no DB server, no external calls):

- **Backend** — FastAPI/uvicorn (Python 3.11+), venv at `backend/.venv`, serves `/api/*` on port **8001** (`/docs`, `/api/health`). Run from `backend/`: `./.venv/bin/python -m uvicorn app.main:app --port 8001`.
- **Frontend** — React + Vite (port **5173**), proxies `/api` to the backend using the `BACKEND_PORT` env var. Run from `frontend/`: `BACKEND_PORT=8001 npm run dev`.

`./start.sh` launches both together (and bootstraps on first run). Standard commands are documented in `README.md` / `docs/SETUP.md`; testing details in `docs/DEVELOPMENT.md`.

Common commands:
- Backend tests: from `backend/`, `./.venv/bin/python -m pytest tests -q`.
- Frontend lint: from `frontend/`, `npm run lint` (oxlint; emits a few `only-export-components` warnings that are expected). Build/typecheck: `npm run build`.

Non-obvious caveats:
- **Demo data is required for the UI to show anything** and is generated separately from dependency install. Generate it from `backend/` with `./.venv/bin/python -m app.sample_data` (~5s, creates 5 portfolios). `data/` is gitignored and fully regenerable.
- **`data/app.sqlite` may exist as a stale git-LFS pointer** (ASCII text, ~130 bytes) rather than a real SQLite DB. `start.sh` only generates demo data when `data/app.sqlite` is *missing*, so a stale pointer silently blocks generation. If the app has no data, `rm -rf data` then regenerate with `sample_data`.
- **The frontend has no `package-lock.json`**, so `npm ci` fails — use `npm install` (that is why `start.sh` uses `npm ci || npm install`).
- Creating the venv requires the `python3-venv` system package (already present in the VM snapshot).
