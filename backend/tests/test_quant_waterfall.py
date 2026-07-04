import numpy as np
import pytest

from app.quant.collateral import project_collateral
from app.quant.curves import DiscountCurve
from app.quant.demo_deal import deal_for_pool, demo_pool
from app.quant.types import Assumptions
from app.quant.waterfall import WaterfallEngine

CURVE = DiscountCurve.demo_sofr()


def _run(cpr=0.08, cdr=0.02, severity=0.40, oc_trigger=1.03):
    pool = demo_pool()
    deal = deal_for_pool(pool, oc_trigger=oc_trigger)
    cf = project_collateral(pool, Assumptions(cpr=cpr, cdr=cdr, severity=severity))
    return deal, cf, WaterfallEngine(CURVE).run(deal, cf)


def test_cash_conservation_deal_level():
    _, cf, result = _run()
    cash_in = cf.total_collections.sum()
    cash_out = (result.fees_paid.sum() + result.residual_cash.sum()
                + sum(t.total_cash.sum() for t in result.tranches))
    assert cash_out == pytest.approx(cash_in, abs=1e-3)


def test_sequential_priority():
    _, _, result = _run()
    a, b, c = result.tranches
    months = np.arange(len(a.principal_paid))
    # B receives no principal before A is (nearly) retired
    first_b = months[b.principal_paid > 0.01]
    assert len(first_b) > 0
    assert a.end_balance[first_b[0]] == pytest.approx(0.0, abs=1.0)
    # senior WAL strictly shortest
    assert a.wal_years() < b.wal_years() < c.wal_years()


def test_oc_stays_healthy_in_base_case():
    _, _, result = _run(cdr=0.02)
    # base case: no OC breach while meaningful rated balance is outstanding
    rated_alive = np.array([t.begin_balance for t in result.tranches]).sum(axis=0) > 1000
    assert result.oc_pass[rated_alive].all()


def test_oc_breach_diverts_interest_to_senior_principal():
    _, _, stressed = _run(cdr=0.12)
    _, _, base = _run(cdr=0.02)
    assert (~stressed.oc_pass).any(), "12% CDR should breach a 1.03 OC trigger"
    a_stressed = stressed.tranche("Class A")
    assert a_stressed.turbo_principal.sum() > 0
    # turbo de-levers the senior bond faster than in the base case
    m = 36
    assert a_stressed.end_balance[m] < base.tranche("Class A").end_balance[m]
    # residual is squeezed while the trigger is failing
    failing = ~stressed.oc_pass
    assert stressed.residual_cash[failing].sum() == pytest.approx(0.0, abs=1e-3)


def test_terminal_writedown_hits_junior_first():
    _, _, result = _run(cdr=0.15, severity=0.6)
    a, b, c = result.tranches
    assert c.writedown.sum() > 0, "deep stress should write down the junior bond"
    if b.writedown.sum() > 0:      # losses must exhaust C before touching B
        assert c.writedown.sum() == pytest.approx(c.begin_balance[0] - c.principal_paid.sum(), rel=1e-6)
    assert a.writedown.sum() == pytest.approx(0.0, abs=1.0)


def test_zero_rated_balance_oc_passes():
    # 100%-ish CPR retires the stack almost immediately; no div-by-zero
    _, _, result = _run(cpr=0.99, cdr=0.0)
    assert result.oc_pass.all() or result.oc_ratio[~result.oc_pass].min() > 0
