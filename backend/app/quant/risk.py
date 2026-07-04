"""Pricing and rate-risk sensitivities.

Effective duration/convexity are computed by full re-projection under ±bump
parallel curve shifts: floating tranche coupons re-project off each shifted
curve, then every tranche's cash flows are re-discounted. Prepayments are held
at the scenario CPR (no rate-dependent prepay model yet — that is the OAS
extension point documented in docs/ARCHITECTURE.md).

Workers are module-level functions taking picklable frozen dataclasses, so the
same signatures run under ProcessPoolExecutor today and Celery/Ray unchanged.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np

from .collateral import project_collateral
from .curves import DiscountCurve
from .types import Assumptions, CollateralPool, DealSpec, WaterfallResult
from .waterfall import WaterfallEngine


def run_deal(deal: DealSpec, pool: CollateralPool, assumptions: Assumptions,
             curve: DiscountCurve) -> WaterfallResult:
    """Full pipeline: collateral projection -> waterfall. The curve drives both
    floating collateral coupons and floating tranche coupons."""
    cf = project_collateral(pool, assumptions, curve)
    return WaterfallEngine(curve).run(deal, cf)


def price(cashflows: np.ndarray, curve: DiscountCurve) -> float:
    """PV of month-end cash flows 1..n under the curve."""
    return float((np.asarray(cashflows, dtype=float) * curve.dfs(len(cashflows))).sum())


def irr_annual(investment: float, cashflows: np.ndarray,
               lo: float = -0.95, hi: float = 5.0) -> float | None:
    """Annualized IRR of `-investment` at t=0 followed by monthly cash flows.
    Bisection on the annual rate; None when no sign change in [lo, hi]."""
    cash = np.asarray(cashflows, dtype=float)
    if investment <= 0 or cash.sum() <= 0:
        return None
    t_years = np.arange(1, len(cash) + 1) / 12.0

    def npv(rate: float) -> float:
        return float((cash / (1.0 + rate) ** t_years).sum()) - investment

    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7 * investment:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


# --------------------------------------------------------------------------
# parallel workers (module-level: picklable under Windows spawn)
# --------------------------------------------------------------------------

def _pv_by_tranche(args: tuple[DealSpec, CollateralPool, Assumptions, DiscountCurve],
                   ) -> dict[str, float]:
    deal, pool, assumptions, curve = args
    result = run_deal(deal, pool, assumptions, curve)
    pvs = {t.name: price(t.total_cash, curve) for t in result.tranches}
    pvs["__residual__"] = price(result.residual_cash, curve)
    return pvs


def _pv_scenario(args: tuple[DealSpec, CollateralPool, Assumptions, DiscountCurve, str],
                 ) -> float:
    deal, pool, assumptions, curve, target = args
    result = run_deal(deal, pool, assumptions, curve)
    if target == "__residual__":
        return price(result.residual_cash, curve)
    return price(result.tranche(target).total_cash, curve)


# --------------------------------------------------------------------------
# sensitivities
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RiskMetrics:
    pv: float
    pv_up: float                # +bump shift
    pv_down: float              # -bump shift
    effective_duration: float   # years
    convexity: float


def tranche_risk(deal: DealSpec, pool: CollateralPool, assumptions: Assumptions,
                 curve: DiscountCurve, bump_bps: float = 50.0,
                 parallel: bool = True) -> dict[str, RiskMetrics]:
    """PV and effective duration/convexity per tranche from a ±bump_bps
    parallel shift:  D_eff = (PV- − PV+) / (2 · PV0 · Δy).

    `parallel=True` fans the three revaluations across processes; the API
    path uses `parallel=False` (a single revaluation is milliseconds — the
    executor matters for scenario grids, not a 3-point bump).
    """
    curves = (curve, curve.shifted(+bump_bps), curve.shifted(-bump_bps))
    jobs = [(deal, pool, assumptions, c) for c in curves]
    if parallel:
        with ProcessPoolExecutor(max_workers=3) as ex:
            base, up, down = list(ex.map(_pv_by_tranche, jobs))
    else:
        base, up, down = (_pv_by_tranche(j) for j in jobs)

    dy = bump_bps / 10_000.0
    out: dict[str, RiskMetrics] = {}
    for name, pv0 in base.items():
        pv_u, pv_d = up[name], down[name]
        if pv0 > 1e-9:
            duration = (pv_d - pv_u) / (2.0 * pv0 * dy)
            convexity = (pv_u + pv_d - 2.0 * pv0) / (pv0 * dy * dy)
        else:
            duration, convexity = 0.0, 0.0
        out[name] = RiskMetrics(pv=pv0, pv_up=pv_u, pv_down=pv_d,
                                effective_duration=duration, convexity=convexity)
    return out


def scenario_grid(deal: DealSpec, pool: CollateralPool, base: Assumptions,
                  curve: DiscountCurve, cprs: list[float], cdrs: list[float],
                  target: str = "__residual__", parallel: bool = True) -> np.ndarray:
    """PV surface over a CPR × CDR grid for one tranche (or the residual).
    Returns a matrix shaped (len(cdrs), len(cprs)). Embarrassingly parallel —
    the unit of distribution for Celery/Ray in production."""
    jobs = [(deal, pool,
             Assumptions(cpr=cpr, cdr=cdr, severity=base.severity,
                         recovery_lag=base.recovery_lag),
             curve, target)
            for cdr in cdrs for cpr in cprs]
    if parallel:
        with ProcessPoolExecutor() as ex:
            flat = list(ex.map(_pv_scenario, jobs))
    else:
        flat = [_pv_scenario(j) for j in jobs]
    return np.array(flat).reshape(len(cdrs), len(cprs))
