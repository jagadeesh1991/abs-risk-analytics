import numpy as np
import pytest

from app.quant.curves import DiscountCurve
from app.quant.demo_deal import deal_for_pool, demo_pool
from app.quant.risk import price, run_deal, tranche_risk
from app.quant.types import Assumptions


def test_price_single_cashflow_hand_discounted():
    curve = DiscountCurve.flat(0.05)
    cash = np.zeros(12)
    cash[11] = 100.0                       # single payment at month 12
    expected = 100.0 * np.exp(-0.05 * 1.0)  # continuous compounding, 1 year
    assert price(cash, curve) == pytest.approx(expected, rel=1e-12)


def test_curve_shift_moves_pv_the_right_way():
    curve = DiscountCurve.demo_sofr()
    cash = np.full(60, 10.0)
    assert price(cash, curve.shifted(50)) < price(cash, curve) < price(cash, curve.shifted(-50))


def test_effective_duration_sane():
    pool = demo_pool()
    deal = deal_for_pool(pool)
    metrics = tranche_risk(deal, pool, Assumptions(cpr=0.08, cdr=0.02),
                           DiscountCurve.demo_sofr(), bump_bps=50, parallel=False)
    a, b, c = metrics["Class A"], metrics["Class B"], metrics["Class C"]
    for m in (a, b, c):
        assert m.pv > 0
        assert m.pv_down > m.pv > m.pv_up      # rates up -> PV down
        assert 0 < m.effective_duration < 10   # short amortizing paper
    # Class A floats (coupon resets soften rate risk); fixed-rate C is the
    # longest bond in the stack -> largest duration
    assert c.effective_duration > b.effective_duration
    assert a.effective_duration < b.effective_duration


def test_duration_matches_zero_bond_analytic():
    """A single flow at T under continuous compounding has D_eff ≈ T."""
    curve = DiscountCurve.flat(0.05)
    cash = np.zeros(60)
    cash[59] = 100.0                       # 5-year zero
    dy = 0.005
    pv0 = price(cash, curve)
    pv_up = price(cash, curve.shifted(50))
    pv_dn = price(cash, curve.shifted(-50))
    duration = (pv_dn - pv_up) / (2 * pv0 * dy)
    assert duration == pytest.approx(5.0, rel=1e-3)


def test_pipeline_smoke_and_pv_additivity():
    pool = demo_pool()
    deal = deal_for_pool(pool)
    curve = DiscountCurve.demo_sofr()
    result = run_deal(deal, pool, Assumptions(), curve)
    # PV of all cash legs equals PV of total collateral collections
    from app.quant.collateral import project_collateral
    cf = project_collateral(pool, Assumptions())
    lhs = price(cf.total_collections, curve)
    rhs = (price(result.fees_paid, curve) + price(result.residual_cash, curve)
           + sum(price(t.total_cash, curve) for t in result.tranches))
    assert rhs == pytest.approx(lhs, rel=1e-9)
