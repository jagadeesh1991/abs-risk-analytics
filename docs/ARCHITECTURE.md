# Structured Products Risk Analytics Engine — Architecture Blueprint

Multi-asset (ABS / CLO / MBS) risk platform: loan-level ingestion → deal modeling →
cash-flow simulation → risk analytics. This document is the production blueprint; the
`backend/app/quant` package is the reference implementation of the compute core, and
`infra/` holds the deployable manifests.

```
                  ┌────────────────────────── CONTROL PLANE ─────────────────────────┐
                  │  FastAPI (REST)  ·  auth  ·  run orchestration  ·  result serving │
                  └───────┬───────────────────────────────────────────────┬──────────┘
   SOURCES                │ publish                                       │ query
┌──────────────┐   ┌──────▼──────────┐    ┌──────────────────┐    ┌───────▼──────────┐
│ Intex CDI    │   │  Kafka           │    │  Worker pool      │    │ PostgreSQL /     │
│ Bloomberg    ├──►│  lld.raw         ├───►│  (Celery|Ray)     ├───►│ TimescaleDB      │
│ Trustee CSV  │   │  lld.normalized  │    │  collateral proj  │    │ deals/tranches   │
│ REMIC factors│   │  pool.factors    │    │  waterfall        │    │ loan_level_perf  │
└──────────────┘   │  deal.events     │    │  MC scenario paths│    │ tranche_cashflows│
                   │  risk.results    │    └───────┬───────────┘    └──────────────────┘
                   └──────────────────┘            │ hot cache: curves, deal specs,
                                                   ▼ dedup keys, scenario partials
                                              ┌─────────┐
                                              │  Redis  │
                                              └─────────┘
```

---

## 1. Data Ingestion Pipeline

### 1.1 Source adapters
Every upstream feed implements one interface and emits rows in the **canonical loan
schema** (single source of truth: `backend/app/schema/canonical.py`):

```python
class SourceAdapter(Protocol):
    def discover(self) -> Iterable[FileRef]            # poll SFTP/API/inbox
    def parse(self, ref: FileRef) -> pd.DataFrame       # vendor format -> raw frame
    def column_hints(self) -> dict[str, str]            # vendor field -> canonical field
```

- **Intex**: wrap the CDI/API SDK; deal structure (tranches, triggers, fee schedule)
  lands in `deals`/`tranches`; collateral snapshots flow as LLD.
- **Bloomberg**: B-PIPE/DL for pool factors, index fixings (SOFR curve pillars),
  tranche prices for calibration.
- **Trustee / servicer tapes**: CSV/XLSX through the existing normalizer
  (`backend/app/ingestion/normalizer.py`) — the fuzzy column auto-mapper
  (`schema/autodetect.py`) is seeded by `column_hints()`.

### 1.2 Kafka topic map

| Topic | Key | Payload | Semantics |
|---|---|---|---|
| `lld.raw` | `(source, file_id)` | raw file pointer + metadata | at-least-once |
| `lld.normalized` | `(pool_id, as_of_date)` | canonical LLD batch pointer | **idempotent**: snapshot key upserts |
| `pool.factors` | `(pool_id, factor_date)` | REMIC/MBS factor, 1m CPR/CDR realized | idempotent upsert |
| `deal.events` | `deal_id` | trigger flips, ratings, amendments | ordered per deal |
| `risk.results` | `run_id` | scenario partials from workers | consumed by aggregator |

Exactly-once *effect* is achieved without transactions: every write is keyed on a
natural idempotency key (`pool_id + as_of_date`, `run_id + path_id`) and upserted —
replays are harmless. This mirrors how the local parquet store already works (one file
per `(portfolio, as_of)`, overwrite-on-reimport).

### 1.3 REMIC / MBS pool factor updates
Monthly factor drops do not carry LLD. The pipeline maintains a **factor ladder** per
pool (`pool_factors` table): balance projection = orig balance × factor; realized
1m CPR/CDR are backed out from consecutive factors and stored alongside, feeding
prepay-model calibration. When LLD later arrives for the same period, it supersedes
the factor-implied aggregates (same idempotency key, higher-fidelity source wins via
`source_rank`).

---

## 2. Cash-Flow Waterfall Engine

Reference implementation: `backend/app/quant/waterfall.py`.

### 2.1 Deal specs are data, not code
A deal is a declarative `DealSpec` (tranches with seniority ranks, coupon legs
fixed/float, OC trigger level, fee schedule). The engine interprets the spec each
period; supporting a new structure means extending the spec vocabulary (IC triggers,
pro-rata locks, reserve accounts), never writing per-deal code. Specs serialize to
JSONB (`deals.structure`) so the DB is the deal library.

### 2.2 Period state machine
Each period the engine holds: tranche balances, cumulative interest shortfalls,
trigger states, reserve balances. Priority of payments (sequential structure):

```
collections(t) = net_interest(t) + sched_prin(t) + prepaid_prin(t) + recoveries(t)
 1. senior fees        (accrued on performing collateral)
 2. interest waterfall (seniority order; unpaid accrues as shortfall)
 3. principal waterfall (collections, sequential retirement)
 4. OC test @ determination date:  performing_collateral(t) / rated_balance(t)
      FAIL -> divert ALL residual interest as turbo principal, senior-most first
 5. residual -> equity
terminal: unpaid rated balance written down (reverse-seniority by construction)
invariant (asserted): cash_in == fees + Σ interest_paid + Σ principal_paid + residual
```

Floating coupons re-project every run from the curve's implied 1-month forwards
(`DiscountCurve.forward_1m`), so rate scenarios propagate into coupon legs.

### 2.3 Extension vocabulary (roadmap, same engine loop)
IC test (interest coverage), pro-rata → sequential toggles, step-down dates, reserve
account draw/replenish, available-funds cap, deferrable (PIK) mezz interest, call
options (clean-up call at ≤10% factor).

---

## 3. Analytics & Risk Engine

Reference implementation: `backend/app/quant/{collateral,curves,risk}.py`.

### 3.1 Behavioral models
- **Prepayment**: CPR vectors → SMM `1-(1-CPR)^(1/12)`; vector ramps supported
  (PSA-style). Calibration inputs: realized SMM from `pool_factors` + tape
  transitions (the loan-tape app already computes CPR/CDR empirically per pool).
- **Default**: CDR vectors → MDR (same transform); roll-rate–based hazard curves are
  the calibration path (transition matrices already computed by
  `analytics/flows.py`).
- **Severity/LGD**: scalar or vector severity, recovery lag in months; collateral
  engine books recoveries `lag` months after default at `(1-severity)`.

### 3.2 Curve service and OAS
`DiscountCurve`: zero pillars, log-linear DF interpolation, parallel `shift(bps)`;
key-rate shifts are pillar-local bumps (same interface). **OAS extension point**: OAS
is computed by root-solving the spread `s` such that
`PV_market = Σ CF_i(path) · DF(t_i) · e^(-s·t_i)` averaged over rate paths from a
short-rate lattice/HW simulation — plug QuantLib (or an internal HW1F) behind the
`DiscountCurve` interface; the waterfall re-runs per path (rate-dependent CPR model
hooks into `Assumptions.cpr` as a callable of the path).

### 3.3 Sensitivities and VaR
- **Effective duration/convexity**: full re-projection under ±50bp parallel shifts
  (coupon legs re-project, then re-discount): `D_eff = (PV₋ − PV₊)/(2·PV₀·Δy)`.
- **Scenario/Monte Carlo**: unit of distribution is `run_scenario(deal_id, path_id,
  assumptions)` — pure function of picklable specs, identical signature under
  `ProcessPoolExecutor` (today) and Celery/Ray (`infra/`). Grid and MC results
  stream to `risk.results`; the aggregator persists `simulation_runs` and computes
  **VaR/ES as quantiles of the scenario PV distribution**.
- **Caching**: Redis keys `curve:{date}:{ccy}`, `dealspec:{deal_id}:{version}`,
  `run:{run_id}:partial:{path_id}` (idempotent worker restarts).

### 3.4 Compute sizing
One 84-month waterfall run ≈ 1 ms (pure NumPy loop). A 10k-path MC on a 50-deal
book ≈ 500k runs ≈ 10 CPU-minutes — a 32-core worker pool clears it in <1 minute;
HPA on queue depth (`infra/k8s/worker.yaml`).

---

## 4. Deployment Topology

- **api**: FastAPI, stateless, 2+ replicas behind the ingress.
- **worker**: Celery pool (`-c` = cores), HPA on queue depth / CPU.
- **kafka / redis / timescaledb**: managed services in production; StatefulSets or
  compose services for dev (`infra/docker-compose.yml`).
- Local-first parity: with no broker configured the same code paths execute
  in-process (`parallel=False`) — the office laptop runs the full stack minus the
  distribution layer.

Schemas: `db/schema.sql` (PostgreSQL + TimescaleDB hypertable for
`loan_level_performance`).
