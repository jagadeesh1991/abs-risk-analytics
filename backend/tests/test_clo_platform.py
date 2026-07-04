"""CLO platform shelf: deal states, compliance evaluation, trustee reports."""
from datetime import date

import pytest

from app.quant.clo_platform import (
    OC_TRIGGERS, SHELF, compliance_rows, deal_state, failing_tests,
    forward_projection, payment_history, quality_history, shelf_states,
)

AS_OF = date(2026, 7, 4)


def test_shelf_states_cover_every_deal():
    states = shelf_states(AS_OF)
    assert [s.deal.deal_id for s in states] == [d.deal_id for d in SHELF]
    for s in states:
        assert s.par > 0
        assert 0.35 <= s.factor <= 1.0
        assert set(s.oc) == set(OC_TRIGGERS)


def test_lifecycle_stages():
    by_id = {s.deal.deal_id: s for s in shelf_states(AS_OF)}
    assert by_id["2021-1"].status == "Amortization"     # reinvest ended 2026-04
    assert by_id["2023-1"].status == "Reinvestment"
    assert by_id["2026-1"].status == "Ramp-Up"          # closed 2026-05


def test_oc_ratios_decrease_down_the_stack():
    s = deal_state("2023-1", AS_OF)
    ocs = [s.oc[name] for name in ("B (AA)", "C (A)", "D (BBB)", "E (BB)")]
    assert ocs == sorted(ocs, reverse=True), "senior OC must exceed junior OC"


def test_stressed_deal_fails_junior_oc_and_clean_deal_passes():
    stressed = deal_state("2021-2", AS_OF)
    assert stressed.oc["E (BB)"] < OC_TRIGGERS["E (BB)"]
    assert failing_tests(stressed) >= 3

    clean = deal_state("2023-1", AS_OF)
    assert failing_tests(clean) == 0


def test_compliance_rows_cover_all_groups():
    rows = compliance_rows(deal_state("2022-1", AS_OF))
    groups = {r["group"] for r in rows}
    assert groups == {"Coverage", "Quality", "Concentration"}
    assert all(r["status"] in ("PASS", "FAIL") for r in rows)


def test_ccc_share_matches_engineered_target():
    for deal_id, target in [("2021-2", 0.150), ("2026-1", 0.030)]:
        s = deal_state(deal_id, AS_OF)
        assert s.ccc == pytest.approx(target, abs=0.012)


def test_payment_history_cash_identities():
    rows = payment_history(deal_state("2022-1", AS_OF))
    assert rows, "seasoned deal must have payment dates"
    for r in rows:
        assert r["equity_dist"] >= 0
        # equity is the residual of the interest waterfall
        residual = (r["int_proceeds"] - r["senior_fee"] - r["sub_fee"]
                    - r["debt_interest"])
        assert r["equity_dist"] == pytest.approx(max(residual, 0.0), abs=1e-6)


def test_quality_history_pins_current_state():
    s = deal_state("2021-1", AS_OF)
    hist = quality_history(s)
    assert len(hist) > 0
    last = hist.iloc[-1]
    assert last["warf"] == pytest.approx(s.warf)
    assert last["ccc"] == pytest.approx(s.ccc)


def test_ramping_deal_has_empty_history_but_valid_columns():
    s = deal_state("2026-1", AS_OF)
    hist = quality_history(s)
    assert len(hist) == 0
    assert list(hist.columns) == ["date", "warf", "was_bps", "ccc", "jr_oc"]


def test_forward_projection_runs_the_engine():
    spec, result = forward_projection(deal_state("2021-1", AS_OF))
    # amortizing deal: AAA already partially paid down at projection start
    assert result.n > 0
    total_prin = sum(float(t.principal_paid.sum()) for t in result.tranches)
    assert total_prin > 0


def test_deterministic_across_calls():
    a = deal_state("2024-1", AS_OF)
    b = deal_state("2024-1", AS_OF)
    assert a.warf == b.warf and a.ccc == b.ccc
    assert payment_history(a) == payment_history(b)
