# STRATA — Structured Risk & Tranche Analytics

Enterprise-style structured credit analytics across **ABS, CLO and RMBS**: upload
loan tapes (CSV/Excel), normalize them to a canonical schema, monitor credit through
13 dashboard tabs (delinquency trends, vintage curves, roll rates, surveillance
corridors, geography), and structure deals with a real cash-flow waterfall engine
(OC triggers, tranche PV / yield / duration / WAL, equity MOIC, scenario grids).

## Quick start (fresh machine)

```powershell
git clone https://github.com/jagadeesh1991/abs-risk-analytics.git
cd abs-risk-analytics
.\start.ps1        # Windows — first run: installs everything + demo data, then opens both servers
./start.sh         # Linux/macOS equivalent
```

Open http://localhost:5173 and explore — demo data is generated automatically on
the first run. Python dependencies are pinned in `backend/requirements.lock` and
the frontend installs with `npm ci`, so every machine gets identical versions.
Prerequisites are
just Git + Python 3.11+ (+ Node 20+ for frontend development). Full step-by-step
instructions for a new system or VDI — including manual setup, a Python-only
production mode, Linux/macOS commands and a troubleshooting table — are in
**[docs/SETUP.md](docs/SETUP.md)**.

## Documentation

| Document | What's in it |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Get running post-clone on any system/VDI: prerequisites, one-command & manual start, production mode, verification, troubleshooting |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Every screen explained: dashboards, structuring screens, upload wizard, exports, glossary |
| [docs/API.md](docs/API.md) | REST endpoint reference with request/response shapes |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Repo layout, the three extension points, conventions, testing, dev gotchas |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Production blueprint: ingestion pipeline, waterfall & risk engine design, Kafka/Redis/TimescaleDB topology |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Corporate-environment specifics: proxies, TLS interception, no-admin installs, multi-user path |
| [db/schema.sql](db/schema.sql) · [infra/](infra/) | PostgreSQL/TimescaleDB DDL and docker-compose/K8s manifests |

## Stack

- **Backend** — Python 3.11, FastAPI, pandas/NumPy. Tapes stored as parquet (one file
  per portfolio + as-of date), metadata in SQLite. No database server needed; zero
  external calls at runtime.
- **Frontend** — React 19 + TypeScript + Vite, Apache ECharts.
- **Quant core** — pure NumPy: CPR/CDR collateral projection (fixed/floating,
  annuity/bullet), OC-trigger waterfall with cash conservation asserted every period,
  PV / IRR / effective duration, parallel scenario grids.

## Demo data

**Generate demo data** (UI button, or `python -m app.sample_data` from `backend/`)
creates five portfolios — prime auto, subprime auto, super-prime bank auto, mortgage
and consumer — each with 24 monthly snapshots simulated via FICO-dependent Markov
delinquency transitions and rate-dependent prepayment. The CLO screen additionally
uses a synthetic 180-name BSL loan book (rating-linked spreads/prices, 15 industries).

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

The suite covers ingestion normalization (currency strings, percent-vs-decimal rates,
state names, Excel serial dates, status↔DPD derivation), column auto-detection,
validation (duplicates, missing required fields) and analytics against a
hand-computed fixture tape (KPIs, roll rates, stratification, filters).

## Project layout

```
backend/app/
  schema/canonical.py    canonical loan schema — the single source of truth
  schema/autodetect.py   fuzzy column-name matching for uploads
  ingestion/             parser (CSV/XLSX) -> normalizer -> validator
  analytics/registry.py  chart registry — THE extension point
  analytics/*.py         chart compute functions (pandas)
  api/                   REST endpoints (/api/portfolios, /api/charts, /api/uploads)
  sample_data.py         Markov-chain synthetic tape generator
  store.py               parquet snapshot store with mtime cache
frontend/src/
  charts/renderers.tsx   chart-type -> ECharts component registry
  components/ChartCard   generic fetch-and-render container
  pages/                 Overview, Performance, Stratification, Distributions,
                         Geography, Transitions, Prepayment, Comparison, Upload wizard
data/                    runtime data (sqlite, parquet, uploads) — gitignored
```

## Adding a new chart (the whole point of the architecture)

1. **Backend** — write a compute function anywhere under `app/analytics/` and decorate it:

   ```python
   @register("prepay_speed", "Prepayment Speed", "performance", "line",
             "Monthly CPR by snapshot", needs_history=True)
   def prepay_speed(ctx: Ctx) -> dict:
       hist = ctx.history()
       ...
       return {"type": "line", "yFormat": "percent", "x": [...], "series": [...]}
   ```

   `ctx` gives you filtered data: `ctx.current()` (latest snapshot), `ctx.history()`
   (all snapshots), `ctx.active(df)` (drop terminal loans). Charts can declare
   dropdown params (see `strat_table` / `geo_states`).

2. **Frontend** — drop `<ChartCard chartId="prepay_speed" />` on any page. If the
   payload uses an existing `type` (line, bar, pie, heatmap, table, treemap, box,
   waterfall, map, kpis), no other frontend work is needed. New payload types get a
   renderer in `src/charts/renderers.tsx`.

## Canonical schema

Required: `loan_id`, `origination_date`, `original_balance`, `current_balance`.
As-of date and asset class can come from a column or be set once for the whole file.
Everything else is optional and charts degrade gracefully: `interest_rate`,
`fico`, `dpd`/`status` (either derives the other), `state`, `ltv`, `dti`, terms,
payment, plus asset-class extras (vehicle, property, purpose).

The normalizer absorbs format quirks automatically: `$1,234.56`, rates as `5.25` vs
`0.0525`, LTV as `0.85` vs `85`, full state names, `MM/DD/YYYY` and Excel serial
dates, statuses in many spellings (`charge-off`, `PIF`, `late30`, …).

## Dashboards

| Tab | Charts |
|---|---|
| Overview | KPI scorecard (sparklines + percentile vs history), asset-class & status donuts, balance trend |
| Surveillance | Scorecard, 60+ DPD vs p10–p90 historical corridor, stacked delinquency composition, duration mix, roll-rate deviation heatmap, FICO×seasoning heatmap |
| Performance | Delinquency trend, vintage curves, roll-rate matrix, FICO×LTV loss surface |
| Vintage & Cohort | Ghost vintage (latest vs history), cohort lifecycle stack (competing risks), loss by FICO band × vintage, vintage mix pyramid |
| Stratification | Switchable pool-cut tables with weighted averages + CSV export |
| Distributions | FICO/LTV/balance histograms, rate box plot, treemap, balance waterfall |
| Geography | US choropleth with metric switcher + state strat table |
| Transitions | Delinquency Sankey flow, transition-rate trend, attrition funnel |
| Prepayment | CPR/CDR trend, prepay speed by note rate and FICO band |
| Comparison | Issuer matrix, delinquency trend per portfolio, risk radar, DPD ranking |
| Structured Products | Three class-specific screens sharing the waterfall core (tranche PV/yield/duration/WAL/MOIC, capital stack, paydown, OC, credit enhancement, cash flows, CPR×CDR equity grid) plus desk analytics per class — **Auto ABS**: cumulative net loss vs stepped trigger schedule, excess spread trend, WAL vector analysis; **CLO**: portfolio quality tests (WAS/WARF/diversity/CCC bucket/WA price) over a 180-name synthetic BSL loan book, rating & industry mix, price-vs-spread scatter, per-tranche OC ratios, annual equity distributions; **RMBS**: refi-incentive S-curve, borrower note-rate distribution vs market rate, HPI-adjusted current LTV, WAL vector analysis |

## Getting data in and out

- **Template**: `GET /api/uploads/template` (or the button on the Upload page) — canonical
  headers with one example row per asset class.
- **Export**: `GET /api/portfolios/{id}/export?scope=latest|history` — any portfolio as
  CSV. `latest` is one row per loan; `history` stacks every as-of date, and re-uploading
  it recreates all snapshots (the importer splits on the `as_of_date` column).
- Pre-generated exports of the demo portfolios live in `exports/`.

## Structured products risk engine

`backend/app/quant/` is a typed, tested quantitative core: CPR/CDR vector collateral
projection, a stateful priority-of-payments waterfall with OC trigger and turbo
diversion, and PV / effective-duration / scenario-grid risk (process-parallel,
Celery-signature-compatible). The production blueprint — ingestion (Intex/Bloomberg
adapters, Kafka topics), compute topology (Celery/Ray workers, Redis,
TimescaleDB), and deployment — is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
with PostgreSQL DDL in [db/schema.sql](db/schema.sql) and deployable manifests in
[infra/](infra/).

## Roadmap ideas

- Quadrant bubbles / bump-rank charts for issuer positioning
- Calendar heatmaps, percentile-band (fan) charts
- Loan-level drill-down table with search
- Auth + multi-user, PostgreSQL/DuckDB storage swap
