import numpy as np
import pytest

from app.quant.class_analytics import (
    _model_cpr,
    abs_extras,
    clo_extras,
    clo_loan_book,
    rmbs_extras,
    vector_analysis,
)
from app.quant.collateral import project_collateral
from app.quant.curves import DiscountCurve
from app.quant.deal_templates import TEMPLATES
from app.quant.risk import run_deal
from app.quant.types import Assumptions

CURVE = DiscountCurve.demo_sofr()


def _setup(key: str):
    tpl = TEMPLATES[key]
    pool = tpl.build_pool()
    deal = tpl.build_deal(pool)
    d = tpl.defaults
    assumptions = Assumptions(cpr=d["cpr"], cdr=d["cdr"], severity=d["severity"],
                              recovery_lag=d["recovery_lag"])
    result = run_deal(deal, pool, assumptions, CURVE)
    cf = project_collateral(pool, assumptions, CURVE)
    return deal, pool, assumptions, result, cf


def test_abs_cnl_monotonic_and_bounded():
    deal, pool, a, result, cf = _setup("abs")
    charts = abs_extras(deal, pool, a, CURVE, result, cf)
    cnl = charts["cnl_curve"]["series"][0]["data"]
    assert all(b >= a2 - 1e-9 for a2, b in zip(cnl, cnl[1:])), "CNL must be non-decreasing"
    # terminal CNL equals severity share of total defaults
    assert cnl[-1] == pytest.approx(cf.defaulted_principal.sum() * a.severity / pool.balance,
                                    rel=1e-4)
    assert "vector_table" in charts and "excess_spread" in charts


def test_clo_quality_metrics_in_institutional_ranges():
    book = clo_loan_book()
    deal, pool, a, result, cf = _setup("clo")
    charts = clo_extras(deal, pool, a, CURVE, result, cf)
    kpis = {i["label"]: i["value"] for i in charts["clo_quality"]["items"]}
    assert 2000 < kpis["WARF"] < 3500            # single-B centered book
    assert 0.030 < kpis["WAS"] < 0.050           # 300-500bp weighted spread
    assert 0 < kpis["Caa/CCC Bucket"] < 0.10     # inside the 7.5%-ish limit zone
    assert 5 < kpis["Diversity (eff. industries)"] < 15
    assert kpis["Obligors"] == len(book)
    # ratings bar sums to ~100% of par
    assert sum(charts["clo_ratings"]["series"][0]["data"]) == pytest.approx(1.0, abs=1e-6)
    assert len(charts["clo_price_spread"]["points"]) == len(book)


def test_vector_analysis_wal_shortens_with_speed():
    tpl = TEMPLATES["rmbs"]
    pool = tpl.build_pool()
    deal = tpl.build_deal(pool)
    a = Assumptions(cpr=0.07, cdr=0.0015, severity=0.25, recovery_lag=12)
    table = vector_analysis(deal, pool, a, CURVE, [0.04, 0.10, 0.20])
    senior = table["rows"][0]
    assert senior["w40"] > senior["w100"] > senior["w200"]


def test_rmbs_s_curve_monotonic():
    deal, pool, a, result, cf = _setup("rmbs")
    charts = rmbs_extras(deal, pool, a, CURVE, result, cf)
    s = charts["s_curve"]["series"][0]["data"]
    assert all(b >= a2 for a2, b in zip(s, s[1:])), "CPR must rise with incentive"
    inc = np.array([-150.0, 300.0])
    lo, hi = _model_cpr(inc)
    assert 0.04 < lo < 0.08 and 0.25 < hi < 0.35   # turnover floor to refi ceiling
    assert "note_rate_dist" in charts and "current_ltv" in charts