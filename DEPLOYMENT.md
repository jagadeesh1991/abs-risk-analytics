# Porting to the Office System

Step-by-step guide for getting this project running on a corporate Windows machine.

## 0. What travels and what doesn't

- **Code travels via GitHub** (`github.com/jagadeesh1991/abs-risk-analytics`). The repo
  contains only source — no loan data.
- **`data/` and `exports/` are gitignored.** Demo data is regenerated on the office
  machine in seconds (`python -m app.sample_data`), and real loan tapes should never
  be committed. Everything the app does runs 100% locally — there are no external API
  calls at runtime, so real tape data never leaves the machine.

## 1. Prerequisites on the office machine

| Tool | Version | No-admin install option |
|---|---|---|
| Git | any recent | Git for Windows portable, or `winget install Git.Git` |
| Python | 3.11+ | python.org installer with "install for me only", or `winget install Python.Python.3.11` |
| Node.js | 20+ | Only needed to *build* the frontend once — see §4 if Node is blocked |

## 2. Corporate proxy / SSL setup (skip if not behind a proxy)

```powershell
# pip through a proxy / TLS-inspecting firewall
pip config set global.proxy http://proxy.company.com:8080
pip config set global.trusted-host "pypi.org files.pythonhosted.org"
# or point at the internal mirror: pip config set global.index-url https://artifactory.company.com/api/pypi/pypi/simple

# npm through the same
npm config set proxy http://proxy.company.com:8080
npm config set https-proxy http://proxy.company.com:8080
# corporate root CA (if TLS is intercepted):
npm config set cafile C:\path\to\company-root-ca.pem
# or internal registry: npm config set registry https://artifactory.company.com/api/npm/npm/
```

## 3. Clone and run (development mode — two servers)

Office networks usually block SSH; clone over HTTPS:

```powershell
git clone https://github.com/jagadeesh1991/abs-risk-analytics.git
cd abs-risk-analytics
.\start.ps1        # creates venv, installs deps, picks free ports, opens both servers
```

Then open http://localhost:5173, click **Generate demo data**, or upload a tape.
`start.ps1` automatically avoids occupied ports (Docker, other apps).

## 4. Production mode — one server, Python only

The backend serves the built frontend automatically when `frontend/dist` exists:

```powershell
cd frontend; npm install; npm run build; cd ..
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001
```

Open **http://localhost:8001** — the whole app on one port, no Node process running.

**If Node cannot be installed at the office:** run `npm run build` on your personal
machine and copy the `frontend/dist` folder over (it's plain static files, ~1.5 MB).
After that the office machine only ever needs Python.

## 5. Verify the install

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q   # 16 tests should pass
```

## 6. Loading real data at the office

1. Upload Tape page → download the **blank template** or a demo **export** to see the layout.
2. Map your tape's columns in the wizard (auto-detect handles most common header names).
3. Multi-period files work: include an `as_of_date` column and the importer creates one
   snapshot per date — that unlocks all trend/vintage/roll-rate/CPR charts.

## 7. Later: sharing with the team

When this needs to be multi-user, the path is:
1. Deploy on an internal Windows/Linux server (`uvicorn --host 0.0.0.0 --port 8001` in
   production mode) so colleagues hit `http://<server>:8001`.
2. Add authentication (the API layer is centralized, so an auth dependency on the
   routers covers everything) — check with IT whether SSO/AD integration is required.
3. If data volume grows past a few million rows, swap the parquet+pandas store for
   DuckDB or PostgreSQL behind the same analytics API.

## Known office pitfalls

- **PowerShell execution policy** blocks `start.ps1` → run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or start the two servers
  manually (commands in README).
- **Port conflicts** with corporate software → `start.ps1` auto-probes; in production
  mode pass any `--port`.
- **Antivirus slowing `npm install`** → prefer the production-mode approach (§4) with
  a prebuilt `dist` copied over.
- **Self-signed cert errors during pip/npm** → §2 trusted-host / cafile settings.
