"""Stateful cash-flow waterfall with an overcollateralization (OC) trigger.

Priority of payments, each period:
    1. Senior fees (accrued on performing collateral, paid from interest).
    2. Tranche interest, sequential by seniority; unpaid interest is carried
       as a non-compounding shortfall into the next period's amount due.
    3. Principal collections (scheduled + prepaid + recoveries) applied
       sequentially by seniority.
    4. OC test on the determination date: end-of-period performing collateral
       / end-of-period rated balance (consistent timing on both legs). On
       failure, ALL residual interest is diverted to principal ("turbo") and
       applied sequentially starting with the senior-most outstanding tranche.
    5. Whatever survives flows to the residual/equity holder.

At final maturity any tranche balance left unpaid is written down (losses
realize reverse-seniority by construction: junior bonds are the last to
receive principal). Cash is conserved to the cent every period and the
engine asserts it.
"""
from __future__ import annotations

import numpy as np

from .curves import DiscountCurve
from .types import (
    CollateralCashflows,
    DealSpec,
    FloatingCoupon,
    TrancheResult,
    WaterfallResult,
)

_ATOL = 1e-6


class WaterfallEngine:
    def __init__(self, curve: DiscountCurve):
        self.curve = curve

    # -- coupon projection ---------------------------------------------------
    def _coupon_paths(self, deal: DealSpec, n: int) -> dict[str, np.ndarray]:
        fwd = self.curve.forward_1m(n)
        paths: dict[str, np.ndarray] = {}
        for t in deal.ordered_tranches:
            if isinstance(t.coupon, FloatingCoupon):
                rate = fwd + t.coupon.margin
                rate = np.maximum(rate, t.coupon.floor)
                if t.coupon.cap is not None:
                    rate = np.minimum(rate, t.coupon.cap)
            else:
                rate = np.full(n, float(t.coupon))
            paths[t.name] = rate
        return paths

    # -- main loop -------------------------------------------------------------
    def run(self, deal: DealSpec, cf: CollateralCashflows) -> WaterfallResult:
        n = cf.n
        order = deal.ordered_tranches
        k = len(order)
        coupons = self._coupon_paths(deal, n)

        balance = np.array([t.balance for t in order], dtype=float)
        shortfall = np.zeros(k)

        res = {t.name: TrancheResult(
            name=t.name,
            begin_balance=np.zeros(n), coupon_rate=coupons[t.name].copy(),
            interest_due=np.zeros(n), interest_paid=np.zeros(n),
            interest_shortfall=np.zeros(n), principal_paid=np.zeros(n),
            turbo_principal=np.zeros(n), writedown=np.zeros(n),
            end_balance=np.zeros(n),
        ) for t in order}

        fees_paid = np.zeros(n)
        oc_ratio = np.zeros(n)
        oc_pass = np.ones(n, dtype=bool)
        residual = np.zeros(n)

        for m in range(n):
            interest_avail = float(cf.net_interest[m])
            principal_avail = float(cf.principal_collected[m])
            cash_in = interest_avail + principal_avail
            begin_snapshot = balance.copy()

            # 1) senior fees
            fees_due = float(cf.begin_balance[m]) * deal.senior_fee / 12.0
            fee = min(interest_avail, fees_due)
            fees_paid[m] = fee
            interest_avail -= fee

            # 2) sequential interest
            for i, t in enumerate(order):
                rate_m = coupons[t.name][m] / 12.0
                due = balance[i] * rate_m + shortfall[i]
                paid = min(due, interest_avail)
                interest_avail -= paid
                shortfall[i] = due - paid
                r = res[t.name]
                r.interest_due[m] = due
                r.interest_paid[m] = paid
                r.interest_shortfall[m] = shortfall[i]

            # 3) sequential principal from collections
            principal_paid = np.zeros(k)
            remaining = principal_avail
            for i in range(k):
                pay = min(balance[i], remaining)
                balance[i] -= pay
                principal_paid[i] += pay
                remaining -= pay

            # 4) OC test on end-of-period balances (consistent determination date)
            rated = float(balance.sum())
            if rated > _ATOL:
                oc_ratio[m] = float(cf.end_balance[m]) / rated
                oc_pass[m] = oc_ratio[m] >= deal.oc_trigger
            else:
                oc_ratio[m] = np.inf
                oc_pass[m] = True

            turbo_paid = np.zeros(k)
            if not oc_pass[m] and interest_avail > _ATOL:
                divert = interest_avail
                for i in range(k):                      # senior-most first
                    pay = min(balance[i], divert)
                    balance[i] -= pay
                    turbo_paid[i] += pay
                    divert -= pay
                    if divert <= _ATOL:
                        break
                interest_avail = divert                 # only if stack fully repaid

            # 5) residual
            residual[m] = interest_avail + remaining

            # 6) terminal writedown: no cash left after the final period
            is_last = m == n - 1
            for i, t in enumerate(order):
                r = res[t.name]
                r.begin_balance[m] = begin_snapshot[i]
                r.turbo_principal[m] = turbo_paid[i]
                r.principal_paid[m] = principal_paid[i] + turbo_paid[i]
                if is_last and balance[i] > _ATOL:
                    r.writedown[m] = balance[i]
                    balance[i] = 0.0
                r.end_balance[m] = balance[i]

            cash_out = (fee
                        + sum(res[t.name].interest_paid[m] for t in order)
                        + sum(res[t.name].principal_paid[m] for t in order)
                        + residual[m])
            if not np.isclose(cash_in, cash_out, atol=_ATOL):
                raise AssertionError(
                    f"waterfall leaked cash in period {m + 1}: "
                    f"in={cash_in:.6f} out={cash_out:.6f}")

        return WaterfallResult(
            deal_name=deal.name, n=n,
            tranches=[res[t.name] for t in order],
            fees_paid=fees_paid, oc_ratio=oc_ratio, oc_pass=oc_pass,
            residual_cash=residual,
        )
