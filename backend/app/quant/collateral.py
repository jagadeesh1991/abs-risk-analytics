"""Collateral cash-flow projection under CPR/CDR vector assumptions.

Monthly convention throughout. Event order within a month:
    1. defaults are removed from the beginning balance (MDR applied first),
    2. the performing balance pays interest and its level-pay scheduled principal
       (payment re-derived each month from the surviving balance and remaining
       term — the standard 'current-balance annuity' treatment),
    3. voluntary prepayments (SMM) come out of the remaining performing balance,
    4. recoveries on defaulted principal arrive `recovery_lag` months later at
       (1 - severity).

Balance identity, asserted by CollateralCashflows itself:
    begin - defaulted - scheduled - prepaid == end
"""
from __future__ import annotations

import numpy as np

from .types import Assumptions, CollateralCashflows, CollateralPool

_EPS = 1e-9


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


def project_collateral(pool: CollateralPool, assumptions: Assumptions) -> CollateralCashflows:
    wam = pool.wam
    lag = assumptions.recovery_lag
    n = wam + lag

    cpr = _to_vector(assumptions.cpr, wam, "cpr")
    cdr = _to_vector(assumptions.cdr, wam, "cdr")
    smm = annual_to_monthly(cpr)
    mdr = annual_to_monthly(cdr)

    begin = np.zeros(n)
    sched = np.zeros(n)
    prepaid = np.zeros(n)
    defaulted = np.zeros(n)
    recoveries = np.zeros(n)
    gross_int = np.zeros(n)
    net_int = np.zeros(n)
    end = np.zeros(n)

    r = pool.wac / 12.0
    svc = pool.servicing_fee / 12.0
    balance = pool.balance

    for m in range(wam):
        if balance <= _EPS:
            break
        begin[m] = balance

        d = balance * mdr[m]
        performing = balance - d

        remaining_term = wam - m
        if r > 0:
            payment = performing * r / (1.0 - (1.0 + r) ** -remaining_term)
        else:
            payment = performing / remaining_term
        interest = performing * r
        s = min(max(payment - interest, 0.0), performing)

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
