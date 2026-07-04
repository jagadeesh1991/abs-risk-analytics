"""Asset-class-specific analytics for the structuring screens.

What each desk actually watches (grounded in trustee-report and dealer
research conventions):

  ABS  — cumulative net loss vs the deal's stepped CNL triggers, annualized
         excess spread, WAL vector analysis across pricing speeds.
  CLO  — portfolio quality tests (WAS / WARF / diversity / CCC bucket /
         WA price), collateral rating & industry mix, loan price-vs-spread,
         per-tranche OC ratios, equity distributions by year.
  RMBS — refi-incentive S-curve, borrower note-rate distribution vs the
         current market rate, HPI-adjusted current LTV, WAL vector analysis.

Synthetic datasets (the CLO loan book, RMBS rate/LTV dispersions) are
seeded so results are reproducible run to run.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from .collateral import project_collateral
from .curves import DiscountCurve
from .risk import run_deal
from .types import Assumptions, CollateralCashflows, CollateralPool, DealSpec, WaterfallResult

# ---------------------------------------------------------------------------
# shared: vector analysis (WAL ladder across prepayment speeds)
# ---------------------------------------------------------------------------

def vector_analysis(deal: DealSpec, pool: CollateralPool, base: Assumptions,
                    curve: DiscountCurve, speeds: list[float]) -> dict:
    """Dealer-style vector table: per-tranche WAL under a CPR ladder."""
    runs = {}
    for cpr in speeds:
        runs[cpr] = run_deal(deal, pool,
                             Assumptions(cpr=cpr, cdr=base.cdr, severity=base.severity,
                                         recovery_lag=base.recovery_lag), curve)
    columns = [{"key": "tranche", "label": "Tranche", "format": "text"}]
    for cpr in speeds:
        columns.append({"key": f"w{int(cpr * 1000)}", "label": f"{cpr * 100:.0f}% CPR",
                        "format": "score"})
    rows = []
    for i, spec in enumerate(deal.ordered_tranches):
        row: dict = {"tranche": spec.name}
        for cpr in speeds:
            row[f"w{int(cpr * 1000)}"] = runs[cpr].tranches[i].wal_years()
        rows.append(row)
    return {"type": "table", "columns": columns, "rows": rows,
            "subtitle": f"WAL in years; CDR held at {base_cdr_label(base)}"}


def base_cdr_label(base: Assumptions) -> str:
    cdr = base.cdr if isinstance(base.cdr, float) else base.cdr[0]
    return f"{cdr * 100:.2f}%"


# ---------------------------------------------------------------------------
# ABS: cumulative net loss vs triggers, excess spread
# ---------------------------------------------------------------------------

# stepped CNL trigger schedule (month threshold -> max allowed cumulative loss)
ABS_CNL_TRIGGERS = [(12, 0.0225), (24, 0.0400), (36, 0.0525), (48, 0.0625), (10_000, 0.0700)]


def abs_extras(deal: DealSpec, pool: CollateralPool, assumptions: Assumptions,
               curve: DiscountCurve, result: WaterfallResult,
               cf: CollateralCashflows) -> dict[str, dict]:
    months = list(range(1, cf.n + 1))

    # CNL: net loss booked at charge-off (default x severity), % of original pool —
    # the non-decreasing convention used against trigger schedules
    severity = assumptions.severity
    cnl = np.cumsum(cf.defaulted_principal) * severity / pool.balance
    trigger_line = []
    for m in months:
        level = next(lvl for cap, lvl in ABS_CNL_TRIGGERS if m <= cap)
        trigger_line.append(level)
    breach = next((m for m, (v, t) in enumerate(zip(cnl, trigger_line), start=1) if v > t), None)
    cnl_chart = {
        "type": "line", "yFormat": "percent", "xLabel": "Period (months)", "x": months,
        "series": [
            {"name": "Cumulative Net Loss", "data": [round(float(v), 5) for v in cnl]},
            {"name": "CNL trigger schedule", "data": trigger_line, "ghost": True},
        ],
        "subtitle": (f"CNL breaches the trigger schedule in month {breach}"
                     if breach else "CNL inside the trigger schedule for the full life"),
    }

    # annualized excess spread: net interest less fees and tranche coupons,
    # over performing collateral
    tranche_interest = np.sum([t.interest_paid for t in result.tranches], axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        xs = (cf.net_interest - result.fees_paid - tranche_interest) * 12.0 \
            / np.maximum(cf.begin_balance, 1.0)
    alive = cf.begin_balance > pool.balance * 0.01
    excess_chart = {
        "type": "line", "yFormat": "percent", "xLabel": "Period (months)", "x": months,
        "series": [{"name": "Excess spread (annualized)",
                    "data": [round(float(v), 5) if a else None for v, a in zip(xs, alive)]}],
        "subtitle": "First-loss cushion available each month before touching enhancement",
    }

    return {
        "cnl_curve": cnl_chart,
        "excess_spread": excess_chart,
        "vector_table": vector_analysis(deal, pool, assumptions, curve,
                                        [0.04, 0.08, 0.12, 0.16, 0.20]),
    }


# ---------------------------------------------------------------------------
# CLO: synthetic BSL loan book + portfolio quality tests
# ---------------------------------------------------------------------------

_MOODYS_FACTORS = {"Ba2": 1350, "Ba3": 1766, "B1": 2220, "B2": 2720, "B3": 3490,
                   "Caa1": 4770, "Caa2": 6500, "Caa3": 8070}
_RATING_MIX = {"Ba2": 0.04, "Ba3": 0.11, "B1": 0.24, "B2": 0.31, "B3": 0.235,
               "Caa1": 0.045, "Caa2": 0.015, "Caa3": 0.005}
_RATING_SPREAD_BPS = {"Ba2": 275, "Ba3": 315, "B1": 350, "B2": 385, "B3": 430,
                      "Caa1": 560, "Caa2": 710, "Caa3": 860}
_RATING_PRICE = {"Ba2": 99.6, "Ba3": 99.3, "B1": 98.9, "B2": 98.1, "B3": 96.4,
                 "Caa1": 91.5, "Caa2": 84.0, "Caa3": 74.0}
_INDUSTRIES = ["Software & Services", "Healthcare Providers", "Business Services",
               "Hotels & Leisure", "Chemicals", "Capital Equipment", "Food & Beverage",
               "Insurance Brokerage", "Media & Entertainment", "Retail",
               "Telecommunications", "Aerospace & Defense", "Construction Materials",
               "Transportation & Logistics", "Consumer Products"]


@lru_cache(maxsize=1)
def clo_loan_book(n_loans: int = 180, seed: int = 7) -> pd.DataFrame:
    """Synthetic broadly-syndicated loan portfolio backing the CLO screen."""
    rng = np.random.default_rng(seed)
    ratings = rng.choice(list(_RATING_MIX), size=n_loans, p=list(_RATING_MIX.values()))
    size = rng.lognormal(mean=np.log(2_200_000), sigma=0.5, size=n_loans)
    spread = np.array([_RATING_SPREAD_BPS[r] for r in ratings]) + rng.normal(0, 22, n_loans)
    price = np.clip(np.array([_RATING_PRICE[r] for r in ratings])
                    + rng.normal(0, 1.1, n_loans), 55, 100.5)
    # concentration: a handful of favored industries carry more names
    weights = np.linspace(2.0, 0.6, len(_INDUSTRIES))
    industry = rng.choice(_INDUSTRIES, size=n_loans, p=weights / weights.sum())
    return pd.DataFrame({
        "obligor": [f"Obligor {i + 1:03d}" for i in range(n_loans)],
        "industry": industry, "rating": ratings,
        "par": size.round(0), "spread_bps": spread.round(0), "price": price.round(2),
    })


def clo_extras(deal: DealSpec, pool: CollateralPool, assumptions: Assumptions,
               curve: DiscountCurve, result: WaterfallResult,
               cf: CollateralCashflows) -> dict[str, dict]:
    book = clo_loan_book()
    par = book["par"].to_numpy()
    total = par.sum()
    w = par / total

    warf = float((w * book["rating"].map(_MOODYS_FACTORS)).sum())
    was = float((w * book["spread_bps"]).sum())
    wa_price = float((w * book["price"]).sum())
    ccc = float(w[book["rating"].str.startswith("Caa")].sum())
    ind_shares = book.groupby("industry")["par"].sum() / total
    diversity = float(1.0 / (ind_shares ** 2).sum())   # effective number of industries

    quality = {"type": "kpis", "items": [
        {"label": "WAS", "value": was / 10_000, "format": "percent"},
        {"label": "WARF", "value": warf, "format": "number"},
        {"label": "Diversity (eff. industries)", "value": diversity, "format": "score"},
        {"label": "Caa/CCC Bucket", "value": ccc, "format": "percent"},
        {"label": "WA Price", "value": wa_price, "format": "score"},
        {"label": "Obligors", "value": int(len(book)), "format": "number"},
    ]}

    rating_order = list(_MOODYS_FACTORS)
    by_rating = book.groupby("rating")["par"].sum().reindex(rating_order).fillna(0) / total
    ratings_chart = {"type": "bar", "yFormat": "percent", "x": rating_order,
                     "series": [{"name": "% of par", "data": [round(float(v), 4) for v in by_rating]}],
                     "subtitle": "Caa/CCC bucket above 7.5% would haircut the OC test"}

    top_ind = (book.groupby("industry")["par"].sum() / total).sort_values(ascending=False).head(10)
    industries_chart = {"type": "bar", "yFormat": "percent",
                        "x": [str(i) for i in top_ind.index],
                        "series": [{"name": "% of par", "data": [round(float(v), 4) for v in top_ind]}]}

    price_spread = {
        "type": "scatter", "xLabel": "Spread (bps)", "yLabel": "Price",
        "points": [{"x": float(r.spread_bps), "y": float(r.price),
                    "size": float(r.par), "name": f"{r.obligor} · {r.rating} · {r.industry}"}
                   for r in book.itertuples()],
        "subtitle": "Bubble = facility size. Cheap-for-rating names sit below the curve",
    }

    # per-tranche OC ratios: collateral over each attachment level
    months = list(range(1, result.n + 1))
    coll_end = cf.end_balance
    cum = np.zeros(result.n)
    oc_series = []
    for tr in result.tranches:
        cum = cum + tr.end_balance
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(cum > 1.0, coll_end / np.maximum(cum, 1.0), np.nan)
        oc_series.append({"name": f"{tr.name} OC",
                          "data": [None if not np.isfinite(v) or v > 3 else round(float(v), 4)
                                   for v in ratio]})
    oc_series.append({"name": f"Trigger ({deal.oc_trigger:.2f}x)",
                      "data": [deal.oc_trigger] * result.n, "ghost": True})
    tranche_oc = {"type": "line", "yFormat": "number", "xLabel": "Period (months)",
                  "x": months, "series": oc_series,
                  "subtitle": "Collateral over each attachment point — junior tests sit closest to the trigger"}

    # annual equity distributions
    years = (np.arange(result.n) // 12) + 1
    dist = pd.Series(result.residual_cash).groupby(years).sum()
    equity_dist = {"type": "bar", "yFormat": "currency",
                   "x": [f"Year {int(y)}" for y in dist.index],
                   "series": [{"name": "Equity distributions", "data": [round(float(v), 0) for v in dist]}]}

    return {
        "clo_quality": quality,
        "clo_ratings": ratings_chart,
        "clo_industries": industries_chart,
        "clo_price_spread": price_spread,
        "tranche_oc": tranche_oc,
        "equity_distributions": equity_dist,
        "vector_table": vector_analysis(deal, pool, assumptions, curve,
                                        [0.10, 0.15, 0.20, 0.25, 0.30]),
    }


# ---------------------------------------------------------------------------
# RMBS: S-curve, note-rate distribution, current LTV
# ---------------------------------------------------------------------------

def _model_cpr(incentive_bps: np.ndarray) -> np.ndarray:
    """Logistic S-curve: turnover floor + refi response to rate incentive."""
    return 0.05 + 0.28 / (1.0 + np.exp(-(incentive_bps - 90.0) / 40.0))


def rmbs_extras(deal: DealSpec, pool: CollateralPool, assumptions: Assumptions,
                curve: DiscountCurve, result: WaterfallResult,
                cf: CollateralCashflows) -> dict[str, dict]:
    rng = np.random.default_rng(11)

    # market mortgage rate proxy: long zero + primary/secondary spread
    market_rate = float(curve.zero(360.0)) + 0.017
    pool_incentive_bps = (pool.wac - market_rate) * 10_000

    inc = np.arange(-150, 301, 25, dtype=float)
    s_curve = {
        "type": "line", "yFormat": "percent", "xLabel": "Refi incentive (bps)",
        "x": [int(i) for i in inc],
        "series": [
            {"name": "Model CPR", "data": [round(float(v), 4) for v in _model_cpr(inc)]},
            {"name": f"This pool ({pool_incentive_bps:.0f}bp → "
                     f"{_model_cpr(np.array([pool_incentive_bps]))[0] * 100:.1f}% CPR)",
             "data": [round(float(_model_cpr(np.array([pool_incentive_bps]))[0]), 4)] * len(inc),
             "ghost": True},
        ],
        "subtitle": f"Borrower rate {pool.wac * 100:.2f}% vs current market {market_rate * 100:.2f}%",
    }

    # note-rate dispersion around WAC: who is in the money to refinance?
    rates = np.clip(rng.normal(pool.wac, 0.0055, 4000), 0.025, 0.12)
    edges = np.arange(np.floor(rates.min() * 200) / 200, rates.max() + 0.005, 0.005)
    counts, edges = np.histogram(rates, bins=edges)
    itm = float((rates > market_rate + 0.005).mean())
    note_rate_dist = {
        "type": "bar", "yFormat": "number",
        "x": [f"{e * 100:.1f}%" for e in edges[:-1]],
        "series": [{"name": "Loans", "data": [int(c) for c in counts]}],
        "subtitle": f"{itm * 100:.0f}% of the pool carries ≥50bp refi incentive at "
                    f"today's {market_rate * 100:.2f}% market rate",
    }

    # HPI-adjusted current LTV distribution
    ltv = np.clip(rng.normal(58, 13, 4000), 8, 115)
    edges = np.arange(0, 125, 10)
    counts, edges = np.histogram(ltv, bins=edges)
    current_ltv = {
        "type": "bar", "yFormat": "number",
        "x": [f"{int(edges[i])}-{int(edges[i + 1])}" for i in range(len(edges) - 1)],
        "series": [{"name": "Loans", "data": [int(c) for c in counts]}],
        "subtitle": f"Mark-to-market LTV after home-price appreciation; "
                    f"{float((ltv > 80).mean()) * 100:.1f}% of loans above 80 LTV",
    }

    return {
        "s_curve": s_curve,
        "note_rate_dist": note_rate_dist,
        "current_ltv": current_ltv,
        "vector_table": vector_analysis(deal, pool, assumptions, curve,
                                        [0.04, 0.07, 0.10, 0.15, 0.20, 0.25]),
    }


CLASS_EXTRAS = {"abs": abs_extras, "clo": clo_extras, "rmbs": rmbs_extras}
