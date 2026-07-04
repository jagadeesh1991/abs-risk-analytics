"""Per-asset-class deal templates: representative institutional structures.

Each template ships a reference pool, a capital-stack builder that scales to
any pool balance (so uploaded loan tapes can be dropped in as collateral),
default scenario assumptions, and desk-note copy for the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .types import CollateralPool, DealSpec, FloatingCoupon, Tranche


@dataclass(frozen=True)
class DealTemplate:
    key: str
    label: str
    description: str
    build_pool: Callable[[], CollateralPool]
    build_deal: Callable[[CollateralPool], DealSpec]
    defaults: dict            # default Assumptions + oc_trigger for the UI


# ---------------------------------------------------------------------------
# Auto ABS — fixed-rate amortizing collateral, 3-tranche sequential + OC turbo
# ---------------------------------------------------------------------------

def _abs_pool() -> CollateralPool:
    # near-prime WAC leaves real excess spread over the stack — the ABS arb
    return CollateralPool(balance=500_000_000.0, wac=0.089, wam=84,
                          servicing_fee=0.0050, name="Near-Prime Auto Loan Pool")


def _abs_deal(pool: CollateralPool) -> DealSpec:
    b = pool.balance
    return DealSpec(
        name="STRATA AUTO 2026-1",
        tranches=(
            Tranche("Class A", 1, round(b * 0.70, 2), FloatingCoupon("SOFR", 0.0120)),
            Tranche("Class B", 2, round(b * 0.15, 2), 0.0610),
            Tranche("Class C", 3, round(b * 0.10, 2), 0.0750),
        ),
        oc_trigger=1.03, senior_fee=0.0025,
    )


# ---------------------------------------------------------------------------
# CLO — floating BSL term-loan collateral (bullet), 5-tranche floating stack
# ---------------------------------------------------------------------------

def _clo_pool() -> CollateralPool:
    return CollateralPool(balance=400_000_000.0, wac=0.0825, wam=72,
                          servicing_fee=0.0040,           # manager senior fee proxy
                          spread=0.0385, amort_style="bullet",
                          name="BSL Term Loan Portfolio")


def _clo_deal(pool: CollateralPool) -> DealSpec:
    b = pool.balance
    return DealSpec(
        name="STRATA CLO 2026-1",
        tranches=(
            Tranche("A (AAA)", 1, round(b * 0.63, 2), FloatingCoupon("SOFR", 0.0140)),
            Tranche("B (AA)", 2, round(b * 0.10, 2), FloatingCoupon("SOFR", 0.0190)),
            Tranche("C (A)", 3, round(b * 0.07, 2), FloatingCoupon("SOFR", 0.0260)),
            Tranche("D (BBB)", 4, round(b * 0.06, 2), FloatingCoupon("SOFR", 0.0385)),
            Tranche("E (BB)", 5, round(b * 0.05, 2), FloatingCoupon("SOFR", 0.0700)),
        ),
        oc_trigger=1.04, senior_fee=0.0040,
    )


# ---------------------------------------------------------------------------
# RMBS — 30yr fixed-rate mortgage collateral, senior/mezz sequential stack
# ---------------------------------------------------------------------------

def _rmbs_pool() -> CollateralPool:
    return CollateralPool(balance=750_000_000.0, wac=0.062, wam=336,
                          servicing_fee=0.0025, name="Prime Jumbo Mortgage Pool")


def _rmbs_deal(pool: CollateralPool) -> DealSpec:
    b = pool.balance
    return DealSpec(
        name="STRATA RMBS 2026-1",
        tranches=(
            Tranche("A-1 (AAA)", 1, round(b * 0.88, 2), 0.0500),
            Tranche("M-1 (AA)", 2, round(b * 0.05, 2), 0.0560),
            Tranche("M-2 (A)", 3, round(b * 0.03, 2), 0.0620),
            Tranche("B (BBB)", 4, round(b * 0.02, 2), 0.0700),
        ),
        oc_trigger=1.005, senior_fee=0.0015,
    )


TEMPLATES: dict[str, DealTemplate] = {
    "abs": DealTemplate(
        key="abs", label="Auto ABS",
        description=("Fixed-rate amortizing consumer collateral. Sequential A/B/C "
                     "stack with a 1.03x OC trigger diverting excess spread to "
                     "senior principal (turbo) on breach."),
        build_pool=_abs_pool, build_deal=_abs_deal,
        defaults={"cpr": 0.08, "cdr": 0.02, "severity": 0.40,
                  "recovery_lag": 6, "curve_shift_bps": 0, "oc_trigger": 1.03},
    ),
    "clo": DealTemplate(
        key="clo", label="CLO",
        description=("Broadly-syndicated floating-rate term loans (SOFR + 350bp, "
                     "~1%/yr amortization, balloon at maturity) financing a "
                     "five-tranche floating stack AAA→BB over a 9% equity slice. "
                     "Matched floating assets/liabilities keep debt duration near "
                     "zero; a 1.04x OC test protects the seniors."),
        build_pool=_clo_pool, build_deal=_clo_deal,
        defaults={"cpr": 0.20, "cdr": 0.02, "severity": 0.35,
                  "recovery_lag": 3, "curve_shift_bps": 0, "oc_trigger": 1.04},
    ),
    "rmbs": DealTemplate(
        key="rmbs", label="RMBS",
        description=("Prime jumbo 30-year fixed collateral in a senior/mezzanine "
                     "sequential structure — 88% AAA with 12% subordination, "
                     "12-month foreclosure-to-liquidation recovery lag, 35% severity."),
        build_pool=_rmbs_pool, build_deal=_rmbs_deal,
        defaults={"cpr": 0.07, "cdr": 0.0015, "severity": 0.25,
                  "recovery_lag": 12, "curve_shift_bps": 0, "oc_trigger": 1.005},
    ),
}
