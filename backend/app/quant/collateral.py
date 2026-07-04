"""Collateral cash-flow projection under CPR/CDR vector assumptions.

Monthly convention throughout. Event order within a month:
    1. defaults are removed from the beginning balance (MDR applied first),
    2. the performing balance pays interest and scheduled principal —
       level-pay annuity re-derived monthly for amortizing pools, or ~1%/yr
       mandatory amortization with a balloon at WAM for bullet (CLO) pools,
    3. voluntary prepayments (SMM) come out of the remaining performing balance,
    4. recoveries on defaulted principal arrive `recovery_lag` months later at
       (1 - severity).

Floating-rate pools (pool.spread set) accrue interest at the curve's implied
1-month forward + spread, so rate scenarios flow through collateral interest.

Balance identity, asserted by CollateralCashflows itself:
    begin - defaulted - scheduled - prepaid == end
"""
from __future__ import annotations

import numpy as np

from .curves import DiscountCurve
from .types import Assumptions, CollateralCashflows, CollateralPool

_EPS = 1e-9
_BULLET_ANNUAL_AMORT = 0.01     # mandatory amortization on term-loan collateral


def annual_to_monthly(rate: np.ndarray | float) -> np.ndarray | float:
    """CPR->SMM / CDR->MDR: 1 - (1 - annual)^(1/12)."""
    return 1.0 - (1.0 - np.asarray(rate, dtype=float)) ** (1.0 / 12.0)


def _to_vector(value: float | tuple[float, ...], n: int, name: str) -> np.ndarray:
    arr = np.atleast_1d(np.asarray(value, dtype=float))
    if arr.size == 1:
        arr = np.full(n, float(arr[0]))
    elif arr.size < n:
        arr = np.concatenate([arr, np.full(n - arr.size, arr[-1])])  # hold last value
    else:
        arr = arr[:n]
    if np.any((arr < 0) | (arr >= 1)):
        raise ValueError(f"{name} values must be annual decimals in [0, 1)")
    return arr


def project_collateral(pool: CollateralPool, assumptions: Assumptions,
                       curve: DiscountCurve | None = None) -> CollateralCashflows:
    wam = pool.wam
    lag = assumptions.recovery_lag
    n = wam + lag

    cpr = _to_vector(assumptions.cpr, wam, "cpr")
    cdr = _to_vector(assumptions.cdr, wam, "cdr")
    smm = annual_to_monthly(cpr)
    mdr = annual_to_monthly(cdr)

    # per-month annual coupon path: fixed WAC, or index forward + spread
    if pool.spread is not None:
        if curve is None:
            raise ValueError("floating-rate pool requires a discount curve")
        coupon_path = curve.forward_1m(wam) + pool.spread
    else:
        coupon_path = np.full(wam, pool.wac)

    begin = np.zeros(n)
    sched = np.zeros(n)
    prepaid = np.zeros(n)
    defaulted = np.zeros(n)
    recoveries = np.zeros(n)
    gross_int = np.zeros(n)
    net_int = np.zeros(n)
    end = np.zeros(n)

    svc = pool.servicing_fee / 12.0
    balance = pool.balance

    for m in range(wam):
        if balance <= _EPS:
            break
        begin[m] = balance

        d = balance * mdr[m]
        performing = balance - d

        r = coupon_path[m] / 12.0
        interest = performing * r
        remaining_term = wam - m
        if pool.amort_style == "bullet":
            if remaining_term == 1:
                s = performing                       # balloon at maturity
            else:
                s = performing * _BULLET_ANNUAL_AMORT / 12.0
        elif r > 0:
            payment = performing * r / (1.0 - (1.0 + r) ** -remaining_term)
            s = min(max(payment - interest, 0.0), performing)
        else:
            s = performing / remaining_term

        p = (performing - s) * smm[m]

        defaulted[m] = d
        sched[m] = s
        prepaid[m] = p
        gross_int[m] = interest
        net_int[m] = max(interest - performing * svc, 0.0)
        if lag > 0:
            recoveries[m + lag] = d * (1.0 - assumptions.severity)
        else:
            recoveries[m] = d * (1.0 - assumptions.severity)

        balance = performing - s - p
        end[m] = balance

    # months after the pool amortizes only carry lagged recoveries; balances flat at 0
    return CollateralCashflows(
        n=n, begin_balance=begin, scheduled_principal=sched,
        prepaid_principal=prepaid, defaulted_principal=defaulted,
        recoveries=recoveries, gross_interest=gross_int,
        net_interest=net_int, end_balance=end,
    )
