"""Deal structuring & waterfall simulation endpoints.

Responses embed standard chart payloads (table / line / bar) so the existing
frontend renderers display them without new components.
"""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_session
from ..quant.collateral import project_collateral
from ..quant.curves import DiscountCurve
from ..quant.demo_deal import deal_for_pool, demo_pool, pool_from_portfolio
from ..quant.risk import run_deal, tranche_risk
from ..quant.types import Assumptions, DealSpec, FloatingCoupon

router = APIRouter(prefix="/api/structuring", tags=["structuring"])


class RunRequest(BaseModel):
    cpr: float = Field(0.08, ge=0, lt=1, description="annual CPR, decimal")
    cdr: float = Field(0.02, ge=0, lt=1, description="annual CDR, decimal")
    severity: float = Field(0.40, ge=0, le=1)
    recovery_lag: int = Field(6, ge=0, le=36)
    curve_shift_bps: float = Field(0, ge=-500, le=500)
    oc_trigger: float = Field(1.03, ge=1.0, le=1.5)
    portfolio_id: int | None = None    # None -> demo pool


def _coupon_label(coupon: float | FloatingCoupon) -> str:
    if isinstance(coupon, FloatingCoupon):
        return f"{coupon.index} + {coupon.margin * 10_000:.0f}bp"
    return f"{coupon * 100:.2f}% fixed"


def _deal_json(deal: DealSpec) -> dict:
    return {
        "name": deal.name,
        "oc_trigger": deal.oc_trigger,
        "senior_fee": deal.senior_fee,
        "tranches": [
            {"name": t.name, "seniority": t.seniority, "balance": t.balance,
             "coupon": _coupon_label(t.coupon)}
            for t in deal.ordered_tranches
        ],
    }


@router.get("/demo")
def demo(session: Session = Depends(get_session)):
    pool = demo_pool()
    return {
        "pool": {"name": pool.name, "balance": pool.balance, "wac": pool.wac,
                 "wam": pool.wam},
        "deal": _deal_json(deal_for_pool(pool)),
        "default_assumptions": {"cpr": 0.08, "cdr": 0.02, "severity": 0.40,
                                "recovery_lag": 6, "curve_shift_bps": 0,
                                "oc_trigger": 1.03},
    }


@router.post("/run")
def run(body: RunRequest, session: Session = Depends(get_session)):
    if body.portfolio_id is not None:
        try:
            pool = pool_from_portfolio(session, body.portfolio_id)
        except ValueError as e:
            raise HTTPException(404, str(e))
    else:
        pool = demo_pool()

    deal = deal_for_pool(pool, name=f"{pool.name} — Structured",
                         oc_trigger=body.oc_trigger)
    assumptions = Assumptions(cpr=body.cpr, cdr=body.cdr,
                              severity=body.severity,
                              recovery_lag=body.recovery_lag)
    curve = DiscountCurve.demo_sofr().shifted(body.curve_shift_bps)

    result = run_deal(deal, pool, assumptions, curve)
    # single 3-point revaluation is milliseconds — no process pool in-request
    risk = tranche_risk(deal, pool, assumptions, curve, bump_bps=50, parallel=False)
    cf = project_collateral(pool, assumptions)

    months = list(range(1, result.n + 1))

    # -- tranche results table ------------------------------------------------
    rows = []
    for spec, tr in zip(deal.ordered_tranches, result.tranches):
        m = risk[tr.name]
        window = tr.principal_window()
        rows.append({
            "tranche": tr.name,
            "coupon": _coupon_label(spec.coupon),
            "balance": spec.balance,
            "pv": m.pv,
            "duration": m.effective_duration,
            "wal": tr.wal_years(),
            "window": f"{window[0]}–{window[1]}m" if window else "—",
            "shortfall": float(tr.interest_shortfall[-1]),
            "writedown": float(tr.writedown.sum()),
        })
    residual = risk["__residual__"]
    rows.append({
        "tranche": "Residual / Equity", "coupon": "excess spread",
        "balance": max(pool.balance - deal.rated_balance, 0.0),
        "pv": residual.pv, "duration": residual.effective_duration,
        "wal": None, "window": "—", "shortfall": 0.0, "writedown": 0.0,
    })
    tranche_table = {
        "type": "table",
        "columns": [
            {"key": "tranche", "label": "Tranche", "format": "text"},
            {"key": "coupon", "label": "Coupon", "format": "text"},
            {"key": "balance", "label": "Balance", "format": "currency"},
            {"key": "pv", "label": "PV", "format": "currency"},
            {"key": "duration", "label": "Eff. Duration", "format": "score"},
            {"key": "wal", "label": "WAL (yrs)", "format": "score"},
            {"key": "window", "label": "Prin. Window", "format": "text"},
            {"key": "shortfall", "label": "Int. Shortfall", "format": "currency"},
            {"key": "writedown", "label": "Writedown", "format": "currency"},
        ],
        "rows": rows,
    }

    # -- tranche balance paydown (stacked area) --------------------------------
    paydown = {
        "type": "line", "yFormat": "currency", "stacked": True, "area": True,
        "xLabel": "Period (months)", "x": months,
        "series": [{"name": t.name,
                    "data": [round(float(v), 2) for v in t.end_balance]}
                   for t in result.tranches],
    }

    # -- OC ratio vs trigger ----------------------------------------------------
    oc_vals = [None if not np.isfinite(v) or v > 5 else round(float(v), 4)
               for v in result.oc_ratio]
    oc_chart = {
        "type": "line", "yFormat": "number", "xLabel": "Period (months)",
        "x": months,
        "series": [
            {"name": "OC ratio", "data": oc_vals},
            {"name": f"Trigger ({deal.oc_trigger:.2f}x)",
             "data": [deal.oc_trigger] * result.n, "ghost": True},
        ],
        "subtitle": ("OC test FAILED in "
                     f"{int((~result.oc_pass).sum())} of {result.n} periods — "
                     "residual interest diverted to senior principal (turbo)"
                     if (~result.oc_pass).any() else
                     "OC test passing in every period"),
    }

    # -- collateral cash decomposition (stacked bars) ---------------------------
    collateral_chart = {
        "type": "bar", "yFormat": "currency", "stacked": True, "x": months,
        "series": [
            {"name": "Net interest", "data": [round(float(v), 2) for v in cf.net_interest]},
            {"name": "Scheduled principal", "data": [round(float(v), 2) for v in cf.scheduled_principal]},
            {"name": "Prepayments", "data": [round(float(v), 2) for v in cf.prepaid_principal]},
            {"name": "Recoveries", "data": [round(float(v), 2) for v in cf.recoveries]},
        ],
    }

    return {
        "pool": {"name": pool.name, "balance": pool.balance, "wac": pool.wac,
                 "wam": pool.wam},
        "deal": _deal_json(deal),
        "oc_breached": bool((~result.oc_pass).any()),
        "charts": {
            "tranche_table": tranche_table,
            "paydown": paydown,
            "oc": oc_chart,
            "collateral": collateral_chart,
        },
    }
