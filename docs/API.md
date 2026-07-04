# API Reference

Base URL: `http://localhost:8001` (or whatever port the backend runs on).
Interactive OpenAPI docs with schemas and try-it-out: **`/docs`**.

All responses are JSON. Chart-producing endpoints return **standard chart
payloads** — a `type` field plus type-specific data — rendered generically by
the frontend (`frontend/src/charts/renderers.tsx`). Payload types:
`kpis · line · bar · pie · heatmap · table · treemap · box · waterfall · map ·
sankey · funnel · radar · pyramid · scatter`.

---

## Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness: `{"ok": true}` |

## Portfolios

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/portfolios` | all portfolios with snapshot inventories |
| POST | `/api/portfolios` | create: `{name, asset_class, description?}` |
| DELETE | `/api/portfolios/{id}` | delete portfolio + its tape data |
| POST | `/api/sample-data` | (re)generate the 5 demo portfolios |
| GET | `/api/portfolios/{id}/export?scope=latest\|history` | CSV download — `latest` = one row per loan; `history` = every snapshot stacked (re-import recreates them all) |
| GET | `/api/filters/options?portfolio_id=` | distinct values for the filter bar |

## Charts (loan-tape analytics)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/charts` | registry listing: id, title, category, chart_type, params |
| GET | `/api/charts/{chart_id}` | compute one chart |

Filter query params on every chart: `portfolio_id, as_of, asset_class,
vintage, fico_band, state`. Chart-specific params are declared in the
registry listing (e.g. `strat_table?dimension=state`,
`geo_states?metric=dpd60_pct`).

```bash
curl "http://localhost:8001/api/charts/delinquency_trend?asset_class=auto&fico_band=620-659"
```

Empty results return `{"empty": true, "message": "..."}` instead of erroring.

## Uploads

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/uploads/schema` | canonical field list (for mapping UIs) |
| GET | `/api/uploads/template` | blank CSV template with example rows |
| POST | `/api/uploads` | multipart file → `{upload_id, columns, rows, sheets, suggested_mapping}` |
| POST | `/api/uploads/{id}/preview` | re-parse with `{sheet, header_row}` |
| POST | `/api/uploads/{id}/validate` | dry run → `{ok, errors[], warnings[], row_count, total_balance}` |
| POST | `/api/uploads/{id}/import` | persist snapshots (see body below) |
| GET | `/api/uploads/mappings/{portfolio_id}` | last saved column mapping |

Validate/import body:

```json
{
  "mapping": {"Loan Number": "loan_id", "Curr UPB": "current_balance"},
  "sheet": null, "header_row": 0,
  "as_of_date": "2026-06-30",
  "asset_class": "auto",
  "portfolio_id": 7,
  "new_portfolio_name": null, "new_portfolio_asset_class": null
}
```

## Structuring (structured products engine)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/structuring/templates` | ABS / CLO / RMBS deal templates: pool, stack, default assumptions |
| POST | `/api/structuring/run` | full run: waterfall + risk + all chart payloads |

Run body — **unset fields fall back to the template defaults**, so
`{"deal_type": "clo"}` alone is a valid base-case run:

```json
{
  "deal_type": "abs | clo | rmbs",
  "cpr": 0.08, "cdr": 0.02, "severity": 0.40, "recovery_lag": 6,
  "curve_shift_bps": 0, "oc_trigger": 1.03,
  "portfolio_id": null
}
```

`portfolio_id` swaps the template pool for an uploaded tape (balance / WAC /
WAM derived from its latest snapshot); the capital stack re-scales to the pool.

Response shape:

```json
{
  "pool": {"name": "...", "balance": 5e8, "wac": 0.089, "wam": 84, "floating": false},
  "deal": {"name": "...", "oc_trigger": 1.03, "tranches": [...], "equity": 2.5e7},
  "oc_breached": false,
  "charts": {
    "tranche_table": {...}, "capital_stack": {...}, "paydown": {...},
    "oc": {...}, "credit_enhancement": {...}, "collateral": {...},
    "debt_service": {...}, "equity_grid": {...},
    "…plus class-specific charts": "cnl_curve/excess_spread/vector_table (abs), clo_quality/clo_ratings/clo_industries/clo_price_spread/tranche_oc/equity_distributions (clo), s_curve/note_rate_dist/current_ltv (rmbs)"
  }
}
```

Conventions everywhere: **rates are annual decimals** (`0.0525` = 5.25%),
periods are monthly, money is USD.
