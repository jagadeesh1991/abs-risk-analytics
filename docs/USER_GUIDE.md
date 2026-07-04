# User Guide

What every screen shows and how to read it. The app has three zones:
**Dashboards** (loan-tape analytics), **Advanced** (behavioral analytics),
and **Structured Products** (deal structuring & risk).

Every dashboard chart respects the global **filter bar**: portfolio, as-of
date, asset class, vintage (origination year), FICO band, and state. "Latest"
uses each portfolio's most recent snapshot; picking an earlier as-of date
rewinds the whole app to that point in time.

---

## Dashboards

### Overview
Headline pool metrics. KPI cards show the current value, a 12-month sparkline,
and a percentile rank vs the pool's own history (e.g. "P92" = higher than 92%
of past months). Composition donuts (asset class, delinquency status) and the
total balance trend.

### Surveillance
The early-warning screen.
- **60+ DPD vs Historical Range** — current serious delinquency against the
  p10–p90 corridor of its own history; outside the band = regime change.
- **Delinquency Composition / Duration Mix** — how the delinquent book splits
  by bucket and by how long loans have been 60+.
- **Roll Rate Deviation vs Baseline** — this month's transition rates minus
  the historical average. Red cells = flows accelerating (e.g. fewer cures,
  more roll-downs); the single best chart for catching deterioration early.
- **Delinquency by FICO × Seasoning** — where in the credit box and loan age
  the stress sits.

### Performance
- **Delinquency Trend** — 30/60/90+ shares of balance over time.
- **Vintage Curves** — cumulative loss by months-on-book per origination
  year; steeper young cohorts = weakening underwriting.
- **Roll Rate Matrix** — balance-weighted month-over-month transitions
  (cure / stay / roll / default / prepay).
- **Loss Surface** — observed default rate across FICO × LTV cells.

### Vintage & Cohort
- **Ghost Vintage** — every historical cohort in grey, newest highlighted:
  the instant "is the new production worse?" read.
- **Cohort Lifecycle Stack** — competing risks by months-on-book: performing
  / delinquent / prepaid / defaulted shares of original balance.
- **Loss by FICO Band & Vintage**, **Vintage Mix Pyramid** — credit-mix
  drift between cohorts.

### Stratification
Pool cuts with weighted averages (balance, % pool, WAC, WA FICO, WA LTV,
60+ %) by FICO band, LTV band, state, rate band, term band, vintage, or asset
class. Every table exports to CSV.

### Distributions & Geography
Histograms (FICO, LTV, balance), rate-by-FICO box plot, portfolio treemap,
month-over-month balance waterfall; state choropleth with a metric switcher
plus a state stratification table.

---

## Advanced

### Transitions
- **Sankey** — where last month's balance went (cures, rolls, prepays,
  defaults), state by state.
- **Transition Rates Over Time** — monthly new-delinquency, cure, and default
  rates.
- **Attrition Funnel** — originated → still active → performing →
  never-delinquent.

### Prepayment
- **CPR / CDR trend** — annualized voluntary and involuntary speeds
  (`CPR = 1-(1-SMM)^12`).
- **Prepay by Note Rate / FICO** — the empirical refi-incentive curve from
  your own tapes.

### Comparison
Cross-portfolio credit quality: metrics matrix, 60+ trend per portfolio, risk
radar, and DPD ranking. Set the portfolio filter to **All** here.

---

## Structured Products

Three screens share one engine: collateral projection (CPR/CDR vectors,
severity, recovery lag) → sequential-pay waterfall with an OC trigger →
pricing off the SOFR curve. Set assumptions in the toolbar and **Run
waterfall**; the collateral selector can swap the template pool for any
uploaded loan tape.

Common outputs: tranche results table (PV, **yield** = IRR at par,
**effective duration** from a ±50bp reprice, WAL, principal window,
writedowns, equity **MOIC**), capital structure, balance paydown, OC test
path, credit enhancement, collateral & liability cash flows, and a CPR × CDR
**equity PV sensitivity grid**.

### Auto ABS
Fixed-rate amortizing collateral, A/B/C stack, OC turbo. Class-specific:
- **Cumulative Net Loss vs Triggers** — CNL against the deal's stepped
  trigger schedule; a breach means enhancement is failing.
- **Excess Spread** — the monthly first-loss cushion.
- **Vector Analysis** — WAL per tranche across 4–20% CPR.

### CLO
Floating BSL term-loan collateral (bullet, ~1%/yr amortization) financing a
five-tranche floating stack. Class-specific (trustee-report style):
- **Portfolio Quality Tests** — WAS, WARF, diversity score, Caa/CCC bucket
  (7.5% is the typical haircut threshold), WA price, obligor count.
- **Rating & Industry mix**, **Loan Price vs Spread** scatter (bubble =
  facility size; cheap-for-rating names sit low).
- **OC Ratios by Tranche** — collateral over each attachment point; the
  junior test hugs the trigger.
- **Equity Distributions by Year** and the CPR vector table.

### RMBS
30-year prime jumbo collateral, senior/mezz stack. Class-specific:
- **Prepayment S-Curve** — model CPR vs refi incentive with this pool marked
  on the curve (out-of-the-money pool = extension risk).
- **Note Rate Distribution** — how much of the pool is refinanceable at
  today's market rate.
- **Current LTV** — HPI-adjusted equity positions.
- **Vector Analysis** — WAL per tranche across 4–25% CPR.

---

## Data in and out

### Upload wizard (Upload Tape)
1. **File** — drop CSV/XLSX; multi-sheet workbooks get a sheet picker, and a
   header-row control handles files whose headers aren't on row 1.
2. **Map columns** — file columns → canonical fields, auto-detected by fuzzy
   name matching; fix anything odd. Choose a new or existing portfolio; if no
   as-of-date column exists, set one date for the whole file.
3. **Validate** — errors (missing required fields, duplicate loan IDs,
   unparseable values with row numbers) block; warnings don't.
4. **Import** — one snapshot per distinct `as_of_date` in the file. Multi-date
   files rebuild an entire history in one upload.

Format quirks are absorbed automatically: `$1,234.56`, rates as `5.25` or
`0.0525`, LTV as `85` or `0.85`, full state names, `MM/DD/YYYY` and Excel
serial dates, statuses in many spellings (`charge-off`, `PIF`, `late30`, …).

### Exports
Upload page → download the **blank template** or any portfolio as CSV
(**latest** snapshot or **full history**). A history export re-imports
losslessly — the round trip is exact.

---

## Glossary

| Term | Meaning |
|---|---|
| CPR / SMM | Annual / monthly voluntary prepayment rate; `SMM = 1-(1-CPR)^(1/12)` |
| CDR / MDR | Annual / monthly default rate (same transform) |
| Severity | Loss given default; recovery = 1 − severity, received after the recovery lag |
| WAC / WAM / WALA | Weighted-average coupon / remaining maturity / loan age |
| DPD | Days past due; buckets 30-59, 60-89, 90+ |
| OC test | Collateral ÷ rated tranche balance vs a trigger; failing diverts residual interest to senior principal ("turbo") |
| WAL | Weighted-average life of principal repayment, years |
| Effective duration | % price change per 100bp, from ±50bp full re-projections |
| MOIC | Equity cash multiple: total distributions ÷ equity investment |
| WARF | Moody's weighted-average rating factor (B2 ≈ 2720; higher = riskier) |
| WAS | Weighted-average spread of floating collateral over its index |
| Diversity score | Effective number of independent industries in the book |
| CNL | Cumulative net loss (defaults × severity) as % of original balance |
