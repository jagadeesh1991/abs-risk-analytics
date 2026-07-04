"""CLO platform management endpoints — the manager's surveillance screens.

GET /api/clo/platform          -> shelf-wide deal board, KPIs, exposure charts
GET /api/clo/deals/{deal_id}   -> per-deal compliance / trends / trustee reports

Responses embed standard chart payloads (kpis / table / line / bar / scatter)
so the existing frontend renderers display them without new components.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from ..quant.clo_platform import (
    CLASS_MARGIN_OVER_AAA, EQUITY_PCT, OC_TRIGGERS, SHELF, STACK, DealState,
    compliance_rows, deal_state, failing_tests, forward_projection,
    payment_history, quality_history, shelf_states,
)

router = APIRouter(prefix="/api/clo", tags=["clo-platform"])


# ---------------------------------------------------------------------------
# platform screen
# ---------------------------------------------------------------------------

@router.get("/platform")
def platform():
    as_of = date.today()
    states = shelf_states(as_of)
    total_par = sum(s.par for s in states)
    w = np.array([s.par for s in states]) / total_par
    fails = {s.deal.deal_id: failing_tests(s) for s in states}

    kpis = {"type": "kpis", "items": [
        {"label": "CLO AUM (par)", "value": total_par, "format": "currency"},
        {"label": "Deals", "value": len(states), "format": "number"},
        {"label": "In Reinvestment", "format": "number",
         "value": sum(1 for s in states if s.status == "Reinvestment")},
        {"label": "Deals Failing Tests", "format": "number",
         "value": sum(1 for v in fails.values() if v > 0)},
        {"label": "Platform WARF", "value": float(np.dot(w, [s.warf for s in states])),
         "format": "number"},
        {"label": "Platform WAS", "format": "percent",
         "value": float(np.dot(w, [s.was_bps for s in states])) / 10_000},
        {"label": "Caa/CCC Exposure", "format": "percent",
         "value": float(np.dot(w, [s.ccc for s in states]))},
        {"label": "Equity NAV", "value": sum(s.equity_nav for s in states),
         "format": "currency"},
    ]}

    board_rows = []
    for s in states:
        d = s.deal
        n_fail = fails[d.deal_id]
        board_rows.append({
            "deal": d.name, "deal_id": d.deal_id, "status": s.status,
            "closing": d.closing.isoformat(),
            "reinvest_end": d.reinvest_end.isoformat(),
            "par": s.par, "factor": s.factor,
            "aaa": f"S+{d.aaa_spread_bps}",
            "warf": s.warf, "was": s.was_bps / 10_000, "ccc": s.ccc,
            "diversity": s.diversity,
            "jr_oc_cushion": (s.oc["E (BB)"] - 1.045) / 1.045,
            "equity_nav": s.equity_nav,
            "tests": "PASS" if n_fail == 0 else f"{n_fail} FAIL",
        })
    deal_board = {
        "type": "table",
        "columns": [
            {"key": "deal", "label": "Deal", "format": "text"},
            {"key": "status", "label": "Stage", "format": "text"},
            {"key": "closing", "label": "Closed", "format": "text"},
            {"key": "reinvest_end", "label": "Reinvest End", "format": "text"},
            {"key": "par", "label": "Collateral Par", "format": "currency"},
            {"key": "aaa", "label": "AAA Coupon", "format": "text"},
            {"key": "warf", "label": "WARF", "format": "number"},
            {"key": "was", "label": "WAS", "format": "percent"},
            {"key": "ccc", "label": "CCC %", "format": "percent"},
            {"key": "jr_oc_cushion", "label": "Jr OC Cushion", "format": "percent"},
            {"key": "equity_nav", "label": "Equity NAV", "format": "currency"},
            {"key": "tests", "label": "Compliance", "format": "status"},
        ],
        "rows": board_rows,
    }

    names = [s.deal.deal_id for s in states]
    cushion_chart = {
        "type": "bar", "yFormat": "percent", "x": names,
        "series": [{"name": "Jr OC cushion",
                    "data": [round((s.oc["E (BB)"] - 1.045) / 1.045, 5) for s in states]}],
        "subtitle": "Junior-most OC test headroom — the first coverage test to bind",
    }
    warf_was = {
        "type": "scatter", "xLabel": "WARF", "yLabel": "WAS (bps)",
        "points": [{"x": round(s.warf), "y": round(s.was_bps),
                    "size": s.par, "name": f"{s.deal.name} · {s.status}"}
                   for s in states],
        "subtitle": "Bubble = collateral par. Up-and-left = better carry per unit of risk",
    }

    # aggregated exposure across every deal's book
    books = pd.concat([s.book.assign(deal=s.deal.deal_id) for s in states])
    total_book = books["par"].sum()
    top_ind = (books.groupby("industry")["par"].sum() / total_book).sort_values(ascending=False)
    industry_chart = {
        "type": "bar", "yFormat": "percent",
        "x": [str(i) for i in top_ind.head(10).index],
        "series": [{"name": "% of platform par",
                    "data": [round(float(v), 4) for v in top_ind.head(10)]}],
    }
    rating_order = ["Ba2", "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3"]
    by_rating = books.groupby("rating")["par"].sum().reindex(rating_order).fillna(0) / total_book
    rating_chart = {
        "type": "bar", "yFormat": "percent", "x": rating_order,
        "series": [{"name": "% of platform par",
                    "data": [round(float(v), 4) for v in by_rating]}],
    }

    # cross-deal obligor overlap: names held in 3+ deals
    overlap = (books.groupby("obligor").agg(deals=("deal", "nunique"), par=("par", "sum"))
               .query("deals >= 3").sort_values("par", ascending=False).head(12))
    overlap_table = {
        "type": "table",
        "columns": [
            {"key": "obligor", "label": "Obligor", "format": "text"},
            {"key": "deals", "label": "Held in # Deals", "format": "number"},
            {"key": "par", "label": "Aggregate Par", "format": "currency"},
            {"key": "pct", "label": "% of Platform", "format": "percent"},
        ],
        "rows": [{"obligor": ob, "deals": int(r.deals), "par": float(r.par),
                  "pct": float(r.par / total_book)}
                 for ob, r in overlap.iterrows()],
        "subtitle": "Single-name risk compounding across the shelf",
    }

    equity_ltm = {
        "type": "bar", "yFormat": "percent", "x": names,
        "series": [{"name": "LTM equity cash-on-cash", "data": [
            round(float(np.mean([r["equity_annualized"] for r in payment_history(s, 4)]))
                  if payment_history(s, 4) else 0.0, 4)
            for s in states]}],
        "subtitle": "Trailing-year annualized equity distributions on original equity notional",
    }

    return {
        "as_of": as_of.isoformat(),
        "deals": [{"deal_id": s.deal.deal_id, "name": s.deal.name, "status": s.status}
                  for s in states],
        "charts": {
            "kpis": kpis, "deal_board": deal_board,
            "oc_cushion": cushion_chart, "warf_was": warf_was,
            "industry": industry_chart, "rating": rating_chart,
            "overlap": overlap_table, "equity_ltm": equity_ltm,
        },
    }


# ---------------------------------------------------------------------------
# per-deal screen
# ---------------------------------------------------------------------------

@router.get("/deals/{deal_id}")
def deal_detail(deal_id: str):
    if not any(d.deal_id == deal_id for d in SHELF):
        raise HTTPException(404, f"no deal {deal_id!r} on the shelf")
    as_of = date.today()
    s: DealState = deal_state(deal_id, as_of)
    d = s.deal

    kpis = {"type": "kpis", "items": [
        {"label": "Collateral Par", "value": s.par, "format": "currency"},
        {"label": "Factor", "value": s.factor, "format": "percent"},
        {"label": "WARF", "value": s.warf, "format": "number"},
        {"label": "WAS", "value": s.was_bps / 10_000, "format": "percent"},
        {"label": "Caa/CCC", "value": s.ccc, "format": "percent"},
        {"label": "WA Price", "value": s.wa_price, "format": "score"},
        {"label": "Defaulted Par", "value": s.defaulted_par, "format": "currency"},
        {"label": "Equity NAV", "value": s.equity_nav, "format": "currency"},
    ]}

    comp_rows = compliance_rows(s)
    compliance = {
        "type": "table",
        "columns": [
            {"key": "group", "label": "Group", "format": "text"},
            {"key": "test", "label": "Test", "format": "text"},
            {"key": "threshold", "label": "Requirement", "format": "text"},
            {"key": "actual", "label": "Actual", "format": "text"},
            {"key": "cushion", "label": "Cushion", "format": "percent"},
            {"key": "status", "label": "Status", "format": "status"},
        ],
        "rows": comp_rows,
        "subtitle": "Indenture tests as of the latest determination date",
    }

    hist = quality_history(s)
    trend = lambda col, scale=1.0: [round(float(v) * scale, 5) for v in hist[col]]  # noqa: E731
    x = [str(v)[:7] for v in hist["date"]] if len(hist) else []
    warf_trend = {"type": "line", "yFormat": "number", "x": x,
                  "series": [{"name": "WARF", "data": trend("warf")},
                             {"name": f"Covenant ({d.warf_covenant:.0f})", "ghost": True,
                              "data": [d.warf_covenant] * len(hist)}]}
    ccc_trend = {"type": "line", "yFormat": "percent", "x": x,
                 "series": [{"name": "Caa/CCC bucket", "data": trend("ccc")},
                            {"name": "7.5% haircut threshold", "ghost": True,
                             "data": [0.075] * len(hist)}]}
    oc_trend = {"type": "line", "yFormat": "number", "x": x,
                "series": [{"name": "Class E OC", "data": trend("jr_oc")},
                           {"name": "Trigger (1.045x)", "ghost": True,
                            "data": [1.045] * len(hist)}]}

    book = s.book
    total = book["par"].sum()
    top10 = book.nlargest(10, "par")
    obligors = {
        "type": "table",
        "columns": [
            {"key": "obligor", "label": "Obligor", "format": "text"},
            {"key": "industry", "label": "Industry", "format": "text"},
            {"key": "rating", "label": "Rating", "format": "text"},
            {"key": "par", "label": "Par", "format": "currency"},
            {"key": "pct", "label": "% of Pool", "format": "percent"},
            {"key": "spread", "label": "Spread", "format": "text"},
            {"key": "price", "label": "Price", "format": "score"},
        ],
        "rows": [{"obligor": r.obligor, "industry": r.industry, "rating": r.rating,
                  "par": float(r.par), "pct": float(r.par / total),
                  "spread": f"S+{r.spread_bps:.0f}", "price": float(r.price)}
                 for r in top10.itertuples()],
    }
    top_ind = (book.groupby("industry")["par"].sum() / total).sort_values(ascending=False).head(10)
    industry_chart = {
        "type": "bar", "yFormat": "percent",
        "x": [str(i) for i in top_ind.index],
        "series": [{"name": "% of par", "data": [round(float(v), 4) for v in top_ind]}],
    }

    pay_rows = payment_history(s)
    payments = {
        "type": "table",
        "columns": [
            {"key": "date", "label": "Payment Date", "format": "text"},
            {"key": "int_proceeds", "label": "Interest Proceeds", "format": "currency"},
            {"key": "prin_proceeds", "label": "Principal Proceeds", "format": "currency"},
            {"key": "senior_fee", "label": "Senior Mgmt Fee", "format": "currency"},
            {"key": "sub_fee", "label": "Sub Mgmt Fee", "format": "currency"},
            {"key": "debt_interest", "label": "Debt Interest", "format": "currency"},
            {"key": "equity_dist", "label": "Equity Distribution", "format": "currency"},
            {"key": "equity_annualized", "label": "Ann. Equity Yield", "format": "percent"},
        ],
        "rows": pay_rows,
        "subtitle": "Trustee payment-date reports, most recent quarters",
    }
    equity_cum = {
        "type": "line", "yFormat": "currency", "area": True,
        "x": [r["date"][:7] for r in pay_rows],
        "series": [{"name": "Cumulative equity distributions",
                    "data": [round(v, 0) for v in
                             np.cumsum([r["equity_dist"] for r in pay_rows])]}],
    }

    spec, result = forward_projection(s)
    months = list(range(1, result.n + 1))
    paydown = {
        "type": "line", "yFormat": "currency", "stacked": True, "area": True,
        "xLabel": "Months forward", "x": months,
        "series": [{"name": t.name, "data": [round(float(v), 2) for v in t.end_balance]}
                   for t in result.tranches],
        "subtitle": "Engine projection from today's balances at 20 CPR / stressed CDR",
    }
    years = (np.arange(result.n) // 12) + 1
    dist = pd.Series(result.residual_cash).groupby(years).sum()
    equity_fwd = {
        "type": "bar", "yFormat": "currency",
        "x": [f"Year {int(y)}" for y in dist.index],
        "series": [{"name": "Projected equity distributions",
                    "data": [round(float(v), 0) for v in dist]}],
        "subtitle": f"Waterfall projection · equity notional "
                    f"${d.target_par * EQUITY_PCT / 1e6:.0f}M",
    }

    orig = dict((name, d.target_par * pct) for name, pct in STACK)
    margins = {"A (AAA)": d.aaa_spread_bps} | {
        k: d.aaa_spread_bps + v for k, v in CLASS_MARGIN_OVER_AAA.items()}
    stack = {
        "type": "table",
        "columns": [
            {"key": "tranche", "label": "Tranche", "format": "text"},
            {"key": "coupon", "label": "Coupon", "format": "text"},
            {"key": "orig", "label": "Original", "format": "currency"},
            {"key": "current", "label": "Current", "format": "currency"},
            {"key": "factor", "label": "Factor", "format": "percent"},
            {"key": "oc", "label": "OC Actual", "format": "text"},
            {"key": "oc_trig", "label": "OC Trigger", "format": "text"},
            {"key": "status", "label": "Test", "format": "status"},
        ],
        "rows": [{
            "tranche": name,
            "coupon": f"SOFR + {margins[name]}bp",
            "orig": orig[name], "current": bal,
            "factor": bal / orig[name] if orig[name] else None,
            "oc": f"{s.oc[name]:.3f}x" if name in s.oc else "—",
            "oc_trig": f"{OC_TRIGGERS[name]:.3f}x" if name in OC_TRIGGERS else "—",
            "status": ("PASS" if s.oc[name] >= OC_TRIGGERS[name] else "FAIL")
                      if name in OC_TRIGGERS else "—",
        } for name, bal in s.tranche_balances.items()],
    }

    return {
        "as_of": as_of.isoformat(),
        "deal": {"deal_id": d.deal_id, "name": d.name, "status": s.status,
                 "closing": d.closing.isoformat(),
                 "reinvest_end": d.reinvest_end.isoformat(),
                 "noncall_end": d.noncall_end.isoformat(),
                 "maturity": d.maturity.isoformat(),
                 "failing": failing_tests(s)},
        "charts": {
            "kpis": kpis, "stack": stack, "compliance": compliance,
            "warf_trend": warf_trend, "ccc_trend": ccc_trend, "oc_trend": oc_trend,
            "obligors": obligors, "industry": industry_chart,
            "payments": payments, "equity_cum": equity_cum,
            "paydown": paydown, "equity_fwd": equity_fwd,
        },
    }
