"""Deal structuring & waterfall simulation endpoints, per asset class.

GET  /api/structuring/templates      -> ABS / CLO / RMBS deal templates
POST /api/structuring/run            -> full run: waterfall, risk, chart payloads

Responses embed standard chart payloads (table / line / bar / heatmap) so the
existing frontend renderers display them without new components.
"""
from __future__ import annotations

import dataclasses

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_session
from ..quant.collateral import project_collateral
from ..quant.curves import DiscountCurve
from ..quant.deal_templates import TEMPLATES
from ..quant.demo_deal import pool_from_portfolio
from ..quant.risk import irr_annual, price, run_deal, tranche_risk
from ..quant.types import Assumptions, CollateralPool, DealSpec, FloatingCoupon

router = APIRouter(prefix="/api/structuring", tags=["structuring"])


class RunRequest(BaseModel):
    """Unset assumption fields fall back to the deal template's defaults."""
    deal_type: str = Field("abs", pattern="^(abs|clo|rmbs)$")
    cpr: float | None = Field(None, ge=0, lt=1)
    cdr: float | None = Field(None, ge=0, lt=1)
    severity: float | None = Field(None, ge=0, le=1)
    recovery_lag: int | None = Field(None, ge=0, le=36)
    curve_shift_bps: float = Field(0, ge=-500, le=500)
    oc_trigger: float | None = Field(None, ge=1.0, le=1.5)
    portfolio_id: int | None = None    # None -> template pool


def _coupon_label(coupon: float | FloatingCoupon) -> str:
    if isinstance(coupon, FloatingCoupon):
        return f"{coupon.index} + {coupon.margin * 10_000:.0f}bp"
    return f"{coupon * 100:.2f}% fixed"


def _deal_json(deal: DealSpec, pool: CollateralPool) -> dict:
    return {
        "name": deal.name,
        "oc_trigger": deal.oc_trigger,
        "senior_fee": deal.senior_fee,
        "equity": max(pool.balance - deal.rated_balance, 0.0),
        "tranches": [
            {"name": t.name, "seniority": t.seniority, "balance": t.balance,
             "pct": t.balance / pool.balance, "coupon": _coupon_label(t.coupon)}
            for t in deal.ordered_tranches
        ],
    }


def _pool_json(pool: CollateralPool) -> dict:
    return {"name": pool.name, "balance": pool.balance, "wac": pool.wac,
            "wam": pool.wam, "floating": pool.spread is not None,
            "amort_style": pool.amort_style}


@router.get("/templates")
def templates():
    out = {}
    for key, tpl in TEMPLATES.items():
        pool = tpl.build_pool()
        out[key] = {
            "label": tpl.label,
            "description": tpl.description,
            "defaults": tpl.defaults,
            "pool": _pool_json(pool),
            "deal": _deal_json(tpl.build_deal(pool), pool),
        }
    return out


@router.post("/run")
def run(body: RunRequest, session: Session = Depends(get_session)):
    tpl = TEMPLATES[body.deal_type]
    if body.portfolio_id is not None:
        try:
            pool = pool_from_portfolio(session, body.portfolio_id)
        except ValueError as e:
            raise HTTPException(404, str(e))
    else:
        pool = tpl.build_pool()

    d = tpl.defaults
    cpr = body.cpr if body.cpr is not None else d["cpr"]
    cdr = body.cdr if body.cdr is not None else d["cdr"]
    severity = body.severity if body.severity is not None else d["severity"]
    recovery_lag = body.recovery_lag if body.recovery_lag is not None else d["recovery_lag"]
    oc_trigger = body.oc_trigger if body.oc_trigger is not None else d["oc_trigger"]

    deal = dataclasses.replace(tpl.build_deal(pool), oc_trigger=oc_trigger)
    assumptions = Assumptions(cpr=cpr, cdr=cdr, severity=severity,
                              recovery_lag=recovery_lag)
    curve = DiscountCurve.demo_sofr().shifted(body.curve_shift_bps)

    result = run_deal(deal, pool, assumptions, curve)
    risk = tranche_risk(deal, pool, assumptions, curve, bump_bps=50, parallel=False)
    cf = project_collateral(pool, assumptions, curve)
    months = list(range(1, result.n + 1))
    equity_investment = max(pool.balance - deal.rated_balance, 0.0)

    # -- tranche results table -------------------------------------------------
    rows = []
    for spec, tr in zip(deal.ordered_tranches, result.tranches):
        m = risk[tr.name]
        window = tr.principal_window()
        rows.append({
            "tranche": tr.name,
            "coupon": _coupon_label(spec.coupon),
            "balance": spec.balance,
            "pct": spec.balance / pool.balance,
            "pv": m.pv,
            "yield": irr_annual(spec.balance, tr.total_cash),
            "duration": m.effective_duration,
            "wal": tr.wal_years(),
            "window": f"{window[0]}–{window[1]}m" if window else "—",
            "writedown": float(tr.writedown.sum()),
            "moic": None,
        })
    residual = risk["__residual__"]
    total_residual = float(result.residual_cash.sum())
    rows.append({
        "tranche": "Equity", "coupon": "excess spread",
        "balance": equity_investment,
        "pct": equity_investment / pool.balance,
        "pv": residual.pv,
        "yield": irr_annual(equity_investment, result.residual_cash),
        "duration": residual.effective_duration,
        "wal": None, "window": "—", "writedown": 0.0,
        "moic": total_residual / equity_investment if equity_investment > 0 else None,
    })
    tranche_table = {
        "type": "table",
        "columns": [
            {"key": "tranche", "label": "Tranche", "format": "text"},
            {"key": "coupon", "label": "Coupon", "format": "text"},
            {"key": "balance", "label": "Balance", "format": "currency"},
            {"key": "pct", "label": "% Deal", "format": "percent"},
            {"key": "pv", "label": "PV", "format": "currency"},
            {"key": "yield", "label": "Yield (IRR)", "format": "percent"},
            {"key": "duration", "label": "Eff. Dur", "format": "score"},
            {"key": "wal", "label": "WAL (yrs)", "format": "score"},
            {"key": "window", "label": "Prin. Window", "format": "text"},
            {"key": "writedown", "label": "Writedown", "format": "currency"},
            {"key": "moic", "label": "MOIC", "format": "score"},
        ],
        "rows": rows,
    }

    # -- capital structure (single stacked column) -------------------------------
    capital_stack = {
        "type": "bar", "yFormat": "currency", "stacked": True,
        "x": ["Capital Structure"],
        "series": ([{"name": t.name, "data": [t.balance]} for t in deal.ordered_tranches]
                   + [{"name": "Equity", "data": [equity_investment]}]),
    }

    # -- tranche balance paydown --------------------------------------------------
    paydown = {
        "type": "line", "yFormat": "currency", "stacked": True, "area": True,
        "xLabel": "Period (months)", "x": months,
        "series": [{"name": t.name,
                    "data": [round(float(v), 2) for v in t.end_balance]}
                   for t in result.tranches],
    }

    # -- OC ratio vs trigger --------------------------------------------------------
    oc_vals = [None if not np.isfinite(v) or v > 5 else round(float(v), 4)
               for v in result.oc_ratio]
    oc_chart = {
        "type": "line", "yFormat": "number", "xLabel": "Period (months)", "x": months,
        "series": [
            {"name": "OC ratio", "data": oc_vals},
            {"name": f"Trigger ({deal.oc_trigger:.2f}x)",
             "data": [deal.oc_trigger] * result.n, "ghost": True},
        ],
        "subtitle": (f"OC test FAILED in {int((~result.oc_pass).sum())} of {result.n} "
                     "periods — residual interest diverted to senior principal"
                     if (~result.oc_pass).any() else "OC test passing in every period"),
    }

    # -- credit enhancement paths ---------------------------------------------------
    coll_end = cf.end_balance
    alive = coll_end > pool.balance * 0.005
    ce_series = []
    senior_stack = np.zeros(result.n)
    for tr in result.tranches:
        senior_stack = senior_stack + tr.end_balance
        ce = np.where(coll_end > 0, 1.0 - senior_stack / np.maximum(coll_end, 1e-9), 0.0)
        ce_series.append({
            "name": tr.name,
            "data": [round(float(c), 4) if a else None for c, a in zip(ce, alive)],
        })
    credit_enhancement = {
        "type": "line", "yFormat": "percent", "xLabel": "Period (months)", "x": months,
        "series": ce_series,
        "subtitle": "Subordination below each tranche as % of collateral; rising lines = de-levering",
    }

    # -- debt service decomposition ----------------------------------------------------
    total_interest = np.sum([t.interest_paid for t in result.tranches], axis=0)
    total_principal = np.sum([t.principal_paid for t in result.tranches], axis=0)
    debt_service = {
        "type": "bar", "yFormat": "currency", "stacked": True, "x": months,
        "series": [
            {"name": "Fees", "data": [round(float(v), 2) for v in result.fees_paid]},
            {"name": "Tranche interest", "data": [round(float(v), 2) for v in total_interest]},
            {"name": "Tranche principal", "data": [round(float(v), 2) for v in total_principal]},
            {"name": "Residual distributions", "data": [round(float(v), 2) for v in result.residual_cash]},
        ],
    }

    # -- equity PV sensitivity grid (CPR × CDR) ------------------------------------------
    cpr_mults, cdr_mults = (0.5, 0.75, 1.0, 1.25, 1.5), (0.5, 1.0, 1.5, 2.0, 3.0)
    base_cpr = max(cpr, 0.005)
    base_cdr = max(cdr, 0.001)
    cprs = [min(base_cpr * k, 0.95) for k in cpr_mults]
    cdrs = [min(base_cdr * k, 0.95) for k in cdr_mults]
    cells = []
    for yi, grid_cdr in enumerate(cdrs):
        for xi, grid_cpr in enumerate(cprs):
            r = run_deal(deal, pool,
                         Assumptions(cpr=grid_cpr, cdr=grid_cdr, severity=severity,
                                     recovery_lag=recovery_lag), curve)
            cells.append([xi, yi, round(price(r.residual_cash, curve), 0)])
    equity_grid = {
        "type": "heatmap", "format": "currency",
        "xLabels": [f"{c * 100:.1f}%" for c in cprs],
        "yLabels": [f"{c * 100:.2f}%" for c in cdrs],
        "cells": cells,
        "subtitle": "Equity PV across prepayment (x) and default (y) scenarios",
    }

    return {
        "pool": _pool_json(pool),
        "deal": _deal_json(deal, pool),
        "oc_breached": bool((~result.oc_pass).any()),
        "charts": {
            "tranche_table": tranche_table,
            "capital_stack": capital_stack,
            "paydown": paydown,
            "oc": oc_chart,
            "credit_enhancement": credit_enhancement,
            "collateral": {
                "type": "bar", "yFormat": "currency", "stacked": True, "x": months,
                "series": [
                    {"name": "Net interest", "data": [round(float(v), 2) for v in cf.net_interest]},
                    {"name": "Scheduled principal", "data": [round(float(v), 2) for v in cf.scheduled_principal]},
                    {"name": "Prepayments", "data": [round(float(v), 2) for v in cf.prepaid_principal]},
                    {"name": "Recoveries", "data": [round(float(v), 2) for v in cf.recoveries]},
                ],
            },
            "debt_service": debt_service,
            "equity_grid": equity_grid,
        },
    }
