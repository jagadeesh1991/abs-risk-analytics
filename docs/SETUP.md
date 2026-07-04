# Setup Guide — Fresh System / VDI

Everything needed to go from `git clone` to a running app on a new machine
(personal, office desktop, or a virtual desktop). Windows commands are shown
first; Linux/macOS equivalents are at the end.

Repo: `github.com/jagadeesh1991/abs-risk-analytics`

---

## 1. Prerequisites

| Tool | Minimum | Check | No-admin install |
|---|---|---|---|
| Git | 2.30+ | `git --version` | Git for Windows "portable" build, or `winget install Git.Git` |
| Python | **3.11+** | `python --version` | python.org installer → "Install for me only" (no admin), or `winget install Python.Python.3.11` |
| Node.js | 20+ (*optional* — see §5) | `node --version` | node.org LTS installer, or `winget install OpenJS.NodeJS.LTS` |

Node is only needed to **build or develop the frontend**. A machine that just
*runs* the app can skip it entirely (§5).

Behind a corporate proxy or TLS-inspecting firewall? Do
[DEPLOYMENT.md §2](../DEPLOYMENT.md) (pip/npm proxy + certificate settings)
before continuing.

## 2. Clone

```powershell
# HTTPS (works everywhere; offices usually block SSH)
git clone https://github.com/jagadeesh1991/abs-risk-analytics.git
cd abs-risk-analytics

# or SSH if you have a key registered with GitHub
git clone git@github.com:jagadeesh1991/abs-risk-analytics.git
```

## 3. One-command start (recommended)

```powershell
.\start.ps1        # Windows
./start.sh         # Linux / macOS
```

The script:
1. finds a working Python 3.11+ (skipping the Microsoft Store `python` stub),
   creates `backend\.venv` and installs the **exact pinned versions** from
   `backend/requirements.lock` (first run only),
2. runs `npm ci` for the frontend so `package-lock.json` is honored (first run only),
3. generates the five demo portfolios if `data/` is empty (first run only),
4. **probes for free ports** — if 8001 is taken (Docker, other apps) it picks
   the next free one and points the frontend proxy at it via `BACKEND_PORT`,
5. starts both servers (two terminal windows on Windows; background jobs on
   Linux/macOS, Ctrl-C stops both).

Open **http://localhost:5173** — every dashboard is already lit up with the
demo data (17,000 loans × 24 monthly snapshots across five portfolios).

> **"running scripts is disabled on this system"** → run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
> then retry. If policy is locked by IT, use the manual steps below.

## 4. Manual start (what start.ps1 does)

```powershell
# --- backend (terminal 1) ---
cd backend
python -m venv .venv
# requirements.lock = exact pinned versions (reproducible install);
# requirements.txt  = the loose ranges they were resolved from.
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m app.sample_data          # optional: demo data via CLI
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001

# --- frontend (terminal 2) ---
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

If 8001 is occupied, pick any port and tell the frontend where the API lives:

```powershell
# terminal 1
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010
# terminal 2
$env:BACKEND_PORT = '8010'; npm run dev
```

## 5. Production mode — one server, Python only

When `frontend/dist` exists, the backend serves the whole app itself:

```powershell
cd frontend; npm install; npm run build; cd ..
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001
```

Open **http://localhost:8001** — UI and API on one port, no Node process.

**VDI / locked-down machine without Node:** build `frontend/dist` on any other
machine (`npm run build`) and copy the folder over — it is ~1.5 MB of static
files. After that the target machine only ever needs Python. To share with
colleagues on a network, add `--host 0.0.0.0` and give them
`http://<machine-name>:8001`.

## 6. Verify the install

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q     # expected: 40 passed
curl http://localhost:8001/api/health             # {"ok":true}
```

Interactive API docs: http://localhost:8001/docs

## 7. Loading data

- **Demo**: Overview page → *Generate demo data* (or `python -m app.sample_data`).
- **Your own tapes**: Upload Tape page → drop a CSV/XLSX → map columns
  (auto-detected) → validate → import. Download the **blank template** or any
  portfolio export from the same page to see the expected layout.
- Runtime data lives in `data/` (SQLite + parquet) and is **gitignored** —
  real loan tapes never enter the repo, and the app makes **zero external
  calls** at runtime.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `start.ps1` blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (once) |
| Port already in use | `start.ps1` auto-picks; manually: any `--port N` + `$env:BACKEND_PORT='N'` before `npm run dev` |
| pip SSL / proxy errors | [DEPLOYMENT.md §2](../DEPLOYMENT.md): `trusted-host`, proxy, or internal index |
| npm SSL / proxy errors | same section: `npm config set proxy/cafile/registry` |
| Charts empty, spinners forever | backend not running or wrong port — check `curl http://localhost:8001/api/health` and the browser Network tab for `/api/*` failures |
| Frontend shows stale code after `git pull` | stop and restart `npm run dev` (Vite's file watcher occasionally misses changes on Windows); hard-refresh the browser |
| `database is locked` during import | stop duplicate backend processes; only one API instance should own `data/app.sqlite` |
| Want a clean slate | stop the backend, delete the `data/` folder, restart, regenerate demo data |
| Slow `npm install` (antivirus) | prefer §5 production mode with a prebuilt `dist` |

## 9. Linux / macOS

```bash
git clone https://github.com/jagadeesh1991/abs-risk-analytics.git
cd abs-risk-analytics
./start.sh          # same first-run install + demo data + port probing as start.ps1
```

Manual equivalent:

```bash
# backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m app.sample_data
.venv/bin/python -m uvicorn app.main:app --port 8001 &

# frontend (dev)
cd ../frontend
npm ci
npm run dev                    # or: npm run build  → production mode as in §5
```

Everything else (ports, `BACKEND_PORT`, data locations, tests) is identical.

## 10. Keeping in sync across machines

```powershell
git pull                                   # get latest code
cd backend; .\.venv\Scripts\python.exe -m pip install -r requirements.lock  # if deps changed
cd ..\frontend; npm ci; npm run build                                       # if frontend changed
cd ..\backend; .\.venv\Scripts\python.exe -m pytest tests -q                # sanity check
```

Data (`data/`, `exports/`) is machine-local by design — move tapes between
machines with the CSV export/import round trip (Upload page), never through git.
