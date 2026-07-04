import pytest

from app.analytics import flows, performance, prepayment, stratification, summary  # noqa: F401
from app.analytics.filters import Ctx, Filters


def _ctx(session, **kw):
    return Ctx(session, Filters(**kw))


def test_kpi_summary_matches_hand_computed(session, fixture_portfolio):
    payload = summary.kpi_summary(_ctx(session))
    items = {i["label"]: i["value"] for i in payload["items"]}
    assert items["Active Loans"] == 2                       # L1 + L2 at t1
    assert items["Current Balance"] == 150.0
    assert items["60+ DPD"] == pytest.approx(50 / 150)      # L2 is DPD60
    assert items["30+ DPD"] == pytest.approx(50 / 150)
    # WAC balance-weighted: (100*0.05 + 50*0.10) / 150
    assert items["WAC"] == pytest.approx((100 * 0.05 + 50 * 0.10) / 150)


def test_kpis_respect_as_of_filter(session, fixture_portfolio):
    from datetime import date
    payload = summary.kpi_summary(_ctx(session, as_of=date(2026, 5, 31)))
    items = {i["label"]: i["value"] for i in payload["items"]}
    assert items["Active Loans"] == 3
    assert items["Current Balance"] == 200.0


def test_roll_rate_matrix_hand_computed(session, fixture_portfolio):
    payload = performance.roll_rate_matrix(_ctx(session))
    x, y = payload["xLabels"], payload["yLabels"]
    cells = {(c[0], c[1]): c[2] for c in payload["cells"]}
    cur, d30 = y.index("Current"), y.index("30-59 DPD")
    # Current (150 total): 100 stays Current, 50 (L3) vanishes -> Prepaid
    assert cells[(x.index("Current"), cur)] == pytest.approx(100 / 150, abs=1e-4)
    assert cells[(x.index("Prepaid"), cur)] == pytest.approx(50 / 150, abs=1e-4)
    # 30-59 DPD (50 total): all rolls to 60-89
    assert cells[(x.index("60-89 DPD"), d30)] == pytest.approx(1.0, abs=1e-4)


def test_strat_table_by_state(session, fixture_portfolio):
    payload = stratification.strat_table(_ctx(session), dimension="state")
    rows = {r["key"]: r for r in payload["rows"]}
    assert rows["CA"]["balance"] == 100.0        # only L1 remains active in CA at t1
    assert rows["TX"]["balance"] == 50.0
    assert rows["TX"]["dpd60_pct"] == pytest.approx(1.0)
    assert rows["Total"]["pct_pool"] == pytest.approx(1.0)


def test_row_filters_apply(session, fixture_portfolio):
    payload = summary.kpi_summary(_ctx(session, state="TX"))
    items = {i["label"]: i["value"] for i in payload["items"]}
    assert items["Active Loans"] == 1
    assert items["Current Balance"] == 50.0


def test_empty_filter_returns_message(session, fixture_portfolio):
    payload = summary.kpi_summary(_ctx(session, state="ZZ"))
    assert payload.get("empty") is True


def test_cpr_trend_hand_computed(session, fixture_portfolio):
    payload = prepayment.cpr_trend(_ctx(session))
    # t0 active balance 200; L3 (50) vanishes -> SMM = 0.25, CPR = 1 - 0.75^12
    series = {s["name"]: s["data"] for s in payload["series"]}
    assert series["CPR"][-1] == pytest.approx(1 - 0.75 ** 12, abs=1e-3)
    assert series["CDR"][-1] == 0  # no defaults in the fixture


def test_sankey_flow_links(session, fixture_portfolio):
    payload = flows.sankey_flow(_ctx(session))
    links = {(l["source"].split("· ")[1], l["target"].split("· ")[1]): l["value"]
             for l in payload["links"]}
    assert links[("Current", "Current")] == 100.0     # L1 stays current
    assert links[("Current", "Prepaid")] == 50.0      # L3 vanishes
    assert links[("30-59 DPD", "60-89 DPD")] == 50.0  # L2 rolls


def test_attrition_funnel_monotonic(session, fixture_portfolio):
    payload = flows.attrition_funnel(_ctx(session))
    values = [i["value"] for i in payload["items"]]
    assert values == sorted(values, reverse=True)
    assert values[0] == 3   # all loans ever observed
    assert values[1] == 2   # L1 + L2 still active
