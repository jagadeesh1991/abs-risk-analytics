# Developer Guide

How the codebase is organized, the extension patterns, and the conventions to
keep. Read [ARCHITECTURE.md](ARCHITECTURE.md) for the production blueprint;
this document is about working in the repo day to day.

## Repo layout

```
backend/
  app/
    main.py               FastAPI app; serves frontend/dist when it exists (production mode)
    config.py             paths; data lives under <repo>/data (gitignored)
    db.py, models.py      SQLite metadata: Portfolio, Snapshot, ColumnMapping
    store.py              parquet snapshot store, one file per (portfolio, as_of), mtime cache
    schema/
      canonical.py        THE canonical loan schema + bands + status codes
      autodetect.py       fuzzy file-column -> canonical-field matching
    ingestion/            parser (CSV/XLSX) -> normalizer (units/formats) -> validator
    analytics/
      registry.py         chart registry — extension point #1
      filters.py          Filters + Ctx (filtered access to current()/history())
      *.py                chart compute functions grouped by category
    quant/
      types.py            frozen spec dataclasses + result containers (invariants asserted)
      curves.py           DiscountCurve: zero pillars, DFs, shifts, 1m forwards
      collateral.py       CPR/CDR projection (annuity & bullet, fixed & floating)
      waterfall.py        priority-of-payments engine with OC trigger/turbo
      risk.py             PV, IRR, effective duration, parallel scenario grids
      deal_templates.py   ABS/CLO/RMBS reference deals — extension point #3
      class_analytics.py  per-asset-class desk charts + synthetic datasets
    api/                  routers: portfolios, analytics, uploads, structuring
    sample_data.py        Markov-chain loan tape simulator (5 portfolios x 24 months)
  tests/                  40 tests, all hand-computed expectations
frontend/src/
  charts/renderers.tsx    payload-type -> component registry — extension point #2
  charts/EChart.tsx       thin ECharts wrapper + palette
  components/             ChartCard (fetch+render), FilterBar, KpiCards, DataTable, Layout
  pages/                  one file per tab; Structuring.tsx hosts all 3 deal screens
  state/AppContext.tsx    portfolios, chart specs, global filters
db/schema.sql             production PostgreSQL/TimescaleDB DDL
infra/                    docker-compose + K8s manifests (blueprints)
docs/                     this documentation set
```

## The three extension points

### 1. Add a dashboard chart (backend + zero-to-one lines of frontend)

```python
# backend/app/analytics/<any module imported by analytics/__init__.py>
from .registry import register
from .filters import Ctx, empty_payload

@register("prepay_speed", "Prepayment Speed", "performance", "line",
          "Monthly CPR by snapshot", needs_history=True)
def prepay_speed(ctx: Ctx) -> dict:
    hist = ctx.history()          # all snapshots, global filters pre-applied
    if hist.empty:
        return empty_payload("No loans match the current filters")
    ...
    return {"type": "line", "yFormat": "percent", "x": [...], "series": [...]}
```

Then place `<ChartCard chartId="prepay_speed" />` on any page. `Ctx` gives you
`current()` (latest snapshot per portfolio), `history()`, `active(df)` (drops
terminal DEFAULT/PREPAID rows), and `snapshot_dates()`. Declare dropdown
params via `params={...}` in the decorator (see `strat_table`).

### 2. Add a chart payload type (frontend)

If no existing `type` fits (line/bar/pie/heatmap/table/treemap/box/waterfall/
map/sankey/funnel/radar/pyramid/scatter/kpis), add a component + a `case` in
`frontend/src/charts/renderers.tsx`. Every chart returning that type renders
automatically from then on.

### 3. Add a structured products deal template

Add a `DealTemplate` in `backend/app/quant/deal_templates.py` (pool builder,
capital-stack builder that scales to any pool balance, default assumptions,
description) and, if the class needs bespoke charts, a builder in
`class_analytics.py` registered in `CLASS_EXTRAS`. Add a route + layout entry
in `frontend/src/pages/Structuring.tsx` and a nav item in `Layout.tsx`.

## Conventions (do not break)

- **Rates are annual decimals** (0.0525), LTV/DTI are percent numbers (85.0),
  periods are monthly. The normalizer enforces this at the boundary — inside
  the app never re-guess units.
- The **canonical schema** (`schema/canonical.py`) is the only column
  vocabulary; analytics never see raw file columns.
- Quant specs are **frozen dataclasses** with validation in `__post_init__`;
  results carry numpy arrays and assert their own invariants (collateral
  balance identity, waterfall cash conservation). Keep new invariants
  *inside* the engine so tests fail loudly.
- Chart payloads are the API contract: backend computes, frontend only
  renders. No analytics math in TypeScript.
- Worker-style functions in `quant/risk.py` must stay **module-level and
  picklable** (Windows spawn + future Celery/Ray reuse the same signatures).
- Empty/edge cases return `empty_payload(message)`, never a 500.

## Testing

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

Style: every quantitative assertion is **hand-computed** (annuity payments,
SMM closed form, roll-rate cells, a 5-year zero's duration ≈ 5.0, CNL
terminal value). When you add analytics, add the tiny fixture that proves the
number, not a snapshot test. Frontend: `npx tsc -b` must stay clean;
`npm run build` before committing UI changes so production mode ships them.

## Dev gotchas

- **Vite stale watcher (Windows)**: after large file rewrites the dev server
  occasionally serves old modules — restart `npm run dev`.
- **Backend has no auto-reload** in the documented commands; restart uvicorn
  after backend edits (or run with `--reload` locally).
- **Port 8000** tends to be taken by Docker Desktop on some machines — the
  project standardizes on **8001**, and `start.ps1` probes upward from there.
- The demo-data generator **replaces** portfolios by name (IDs change);
  don't persist portfolio IDs anywhere.

## Workflow

```powershell
git pull                          # sync
# ... edit ...
cd backend; .\.venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend; npx tsc -b; npm run build
git add -A; git commit -m "..."; git push
```

`data/` and `exports/` are gitignored — commits can never leak tape data.
