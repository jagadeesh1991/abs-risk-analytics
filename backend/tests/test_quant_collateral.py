import numpy as np
import pytest

from app.quant.collateral import annual_to_monthly, project_collateral
from app.quant.types import Assumptions, CollateralPool


POOL = CollateralPool(balance=1_000_000.0, wac=0.06, wam=36, servicing_fee=0.0)


def test_smm_closed_form():
    # 6% CPR -> SMM = 1 - 0.94^(1/12)
    assert annual_to_monthly(0.06) == pytest.approx(1 - 0.94 ** (1 / 12))
    assert annual_to_monthly(0.0) == 0.0


def test_zero_cpr_cdr_reduces_to_annuity():
    cf = project_collateral(POOL, Assumptions(cpr=0.0, cdr=0.0, recovery_lag=0))
    r = 0.06 / 12
    pmt = 1_000_000 * r / (1 - (1 + r) ** -36)
    total_paid = cf.scheduled_principal + cf.gross_interest
    # every month pays exactly the level annuity payment
    assert np.allclose(total_paid[:36], pmt, atol=1e-6)
    assert cf.prepaid_principal.sum() == 0
    assert cf.defaulted_principal.sum() == 0
    assert cf.end_balance[35] == pytest.approx(0.0, abs=1e-6)


def test_balance_conservation_under_stress():
    cf = project_collateral(POOL, Assumptions(cpr=0.25, cdr=0.10, severity=0.5))
    resid = (cf.begin_balance - cf.scheduled_principal - cf.prepaid_principal
             - cf.defaulted_principal - cf.end_balance)
    assert np.allclose(resid, 0, atol=1e-6)
    # principal fully accounted for: everything either collected or defaulted
    assert (cf.scheduled_principal.sum() + cf.prepaid_principal.sum()
            + cf.defaulted_principal.sum()) == pytest.approx(1_000_000, abs=1e-3)


def test_recovery_lag_and_severity():
    a = Assumptions(cpr=0.0, cdr=0.12, severity=0.4, recovery_lag=6)
    cf = project_collateral(POOL, a)
    # recoveries are (1 - severity) of defaults, shifted 6 months
    assert cf.recoveries[:6].sum() == 0
    assert cf.recoveries.sum() == pytest.approx(cf.defaulted_principal.sum() * 0.6, rel=1e-9)
    # first-month default is exactly MDR on the opening balance
    mdr = annual_to_monthly(0.12)
    assert cf.defaulted_principal[0] == pytest.approx(1_000_000 * mdr, rel=1e-9)


def test_cpr_vector_is_honored():
    ramp = tuple(np.linspace(0.0, 0.30, 36))
    cf = project_collateral(POOL, Assumptions(cpr=ramp, cdr=0.0, recovery_lag=0))
    assert cf.prepaid_principal[0] == 0.0
    assert cf.prepaid_principal[12] > 0.0


def test_bullet_pool_balloons_at_maturity():
    from app.quant.curves import DiscountCurve
    pool = CollateralPool(balance=1_000_000.0, wac=0.078, wam=60,
                          spread=0.035, amort_style="bullet", servicing_fee=0.0)
    cf = project_collateral(pool, Assumptions(cpr=0.0, cdr=0.0, recovery_lag=0),
                            curve=DiscountCurve.flat(0.043))
    # ~1%/yr mandatory amortization, then the balloon repays everything at WAM
    assert cf.scheduled_principal[0] == pytest.approx(1_000_000 * 0.01 / 12, rel=1e-6)
    assert cf.scheduled_principal[59] == pytest.approx(cf.begin_balance[59], rel=1e-9)
    assert cf.end_balance[59] == pytest.approx(0.0, abs=1e-6)


def test_floating_pool_interest_tracks_curve():
    from app.quant.curves import DiscountCurve
    pool = CollateralPool(balance=1_000_000.0, wac=0.078, wam=24,
                          spread=0.035, amort_style="bullet", servicing_fee=0.0)
    a = Assumptions(cpr=0.0, cdr=0.0, recovery_lag=0)
    low = project_collateral(pool, a, curve=DiscountCurve.flat(0.03))
    high = project_collateral(pool, a, curve=DiscountCurve.flat(0.05))
    assert high.gross_interest.sum() > low.gross_interest.sum()
    with pytest.raises(ValueError):
        project_collateral(pool, a)   # floating pool without a curve
