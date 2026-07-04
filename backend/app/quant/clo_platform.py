"""Multi-deal CLO platform: the manager's surveillance universe.

What an institutional CLO desk (BlackRock / Invesco / PIMCO style) works from
every morning, modeled on trustee reports and manager surveillance systems:

  Platform  — shelf-wide deal board: every deal's coverage-test cushions,
              quality metrics and lifecycle stage on one screen, plus
              aggregated industry / rating exposure across all deals.
  Per deal  — compliance report (OC / IC coverage, collateral quality
              covenants, concentration limits) with trigger / actual /
              cushion / status per test, quality trends, top obligors,
              trustee payment-date history and equity analytics, and a
              forward projection off the waterfall engine.

The shelf is synthetic but engineered to be realistic: vintages carry their
era's AAA spreads and SOFR path, seasoned deals show credit migration
(higher WARF / CCC, thinner OC cushions), and one stressed 2021 vintage
fails its junior OC test so the compliance workflow is visible end to end.
All randomness is seeded per deal — results are reproducible run to run.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd

from . import class_analytics as ca
from .curves import DiscountCurve
from .risk import run_deal
from .types import Assumptions, CollateralPool, DealSpec, FloatingCoupon, Tranche

# ---------------------------------------------------------------------------
# deal shelf
# ---------------------------------------------------------------------------

# capital stack proportions shared across the shelf (% of target par)
STACK = (("A (AAA)", 0.63), ("B (AA)", 0.10), ("C (A)", 0.07),
         ("D (BBB)", 0.06), ("E (BB)", 0.05))
EQUITY_PCT = 0.09

# margin over the AAA spread for each junior class (bps)
CLASS_MARGIN_OVER_AAA = {"B (AA)": 50, "C (A)": 120, "D (BBB)": 245, "E (BB)": 560}

# OC / IC triggers by class (coverage tests; OC = par over cum debt through class)
OC_TRIGGERS = {"B (AA)": 1.255, "C (A)": 1.160, "D (BBB)": 1.085, "E (BB)": 1.045}
IC_TRIGGERS = {"B (AA)": 1.20, "C (A)": 1.10, "D (BBB)": 1.05}

MGMT_SENIOR_FEE = 0.0015     # paid top of waterfall
MGMT_SUB_FEE = 0.0025        # paid if coverage tests pass
CCC_LIMIT = 0.075            # excess above this carried at market value in OC


@dataclass(frozen=True)
class CloShelfDeal:
    deal_id: str          # "2021-1"
    closing: date
    reinvest_end: date
    noncall_end: date
    maturity: date
    target_par: float
    aaa_spread_bps: int   # priced at close — vintage-era economics
    seed: int
    # credit-migration dials (seasoned / stressed vintages)
    ccc_target: float     # engineered par-weighted Caa share
    default_frac: float   # defaulted par as % of target par
    caa_mark_mult: float  # distressed-market multiplier on Caa prices
    warf_covenant: float
    was_covenant_bps: float

    @property
    def name(self) -> str:
        return f"STRATA CLO {self.deal_id}"


SHELF: tuple[CloShelfDeal, ...] = (
    # seasoned, on watch: CCC just over the 7.5% haircut threshold
    CloShelfDeal("2021-1", date(2021, 4, 15), date(2026, 4, 15), date(2023, 4, 15),
                 date(2034, 4, 15), 400e6, 117, 21, 0.082, 0.016, 1.0, 3100, 340),
    # the stressed vintage: heavy CCC at distressed marks + defaults
    # -> junior OC test failing, sub fees / equity shut off
    CloShelfDeal("2021-2", date(2021, 10, 20), date(2026, 10, 20), date(2023, 10, 20),
                 date(2034, 10, 20), 350e6, 121, 27, 0.150, 0.055, 0.72, 3100, 340),
    CloShelfDeal("2022-1", date(2022, 5, 18), date(2027, 5, 18), date(2024, 5, 18),
                 date(2035, 5, 18), 450e6, 148, 31, 0.068, 0.009, 1.0, 3000, 350),
    CloShelfDeal("2023-1", date(2023, 3, 22), date(2028, 3, 22), date(2025, 3, 22),
                 date(2036, 3, 22), 400e6, 178, 37, 0.054, 0.005, 1.0, 2950, 360),
    CloShelfDeal("2023-2", date(2023, 9, 14), date(2028, 9, 14), date(2025, 9, 14),
                 date(2036, 9, 14), 380e6, 169, 41, 0.061, 0.004, 1.0, 2950, 360),
    CloShelfDeal("2024-1", date(2024, 6, 12), date(2029, 6, 12), date(2026, 6, 12),
                 date(2037, 6, 12), 500e6, 151, 47, 0.048, 0.002, 1.0, 2900, 350),
    CloShelfDeal("2025-1", date(2025, 2, 19), date(2030, 2, 19), date(2027, 2, 19),
                 date(2038, 2, 19), 425e6, 139, 53, 0.038, 0.001, 1.0, 2900, 345),
    CloShelfDeal("2026-1", date(2026, 5, 15), date(2031, 5, 15), date(2028, 5, 15),
                 date(2039, 5, 15), 400e6, 141, 59, 0.030, 0.0, 1.0, 2900, 345),
)


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _balances_at(deal: CloShelfDeal, factor: float) -> dict[str, float]:
    """Debt stack after sequential amortization: paydown hits the AAA first."""
    balances = {name: deal.target_par * pct for name, pct in STACK}
    paydown = deal.target_par * (1.0 - factor)
    for name, _ in STACK:
        take = min(balances[name], paydown)
        balances[name] -= take
        paydown -= take
    return balances


def sofr_history(d: date) -> float:
    """Approximate SOFR path over the shelf's life (annual decimal)."""
    if d < date(2022, 3, 1):
        return 0.0005
    if d < date(2023, 1, 1):        # 2022 hiking cycle ramp
        return 0.0005 + 0.043 * (_months_between(date(2022, 3, 1), d) / 10)
    if d < date(2024, 9, 1):
        return 0.0525
    if d < date(2025, 6, 1):
        return 0.0475
    return 0.0430


# ---------------------------------------------------------------------------
# per-deal state (loan book + current metrics), seeded and cached
# ---------------------------------------------------------------------------

@dataclass
class DealState:
    deal: CloShelfDeal
    as_of: date
    status: str                # Ramp-Up | Reinvestment | Amortization
    factor: float              # current collateral par / target par
    par: float                 # current performing par
    defaulted_par: float
    book: pd.DataFrame         # obligor-level: par scaled to current portfolio
    tranche_balances: dict[str, float]
    warf: float
    was_bps: float
    wa_price: float
    ccc: float
    diversity: float
    oc: dict[str, float]       # actual OC ratio per test class
    ic: dict[str, float]
    equity_nav: float


def _build_book(deal: CloShelfDeal) -> pd.DataFrame:
    """Per-deal loan book: base synthetic BSL book, obligor-cap trimming, and
    credit migration steered to the deal's engineered Caa share."""
    rng = np.random.default_rng(deal.seed)
    n = int(rng.integers(150, 210))
    book = ca.clo_loan_book(n, deal.seed).copy()

    # concentration management: no single obligor above ~1.9% of par
    cap = book["par"].sum() * 0.019
    book["par"] = book["par"].clip(upper=cap)

    # migrate names between the B and Caa buckets until the par-weighted Caa
    # share sits at the deal's target (seasoned deals drift up, new deals
    # are ramped clean)
    def caa_share() -> float:
        w = book["par"] / book["par"].sum()
        return float(w[book["rating"].str.startswith("Caa")].sum())

    order = book.index.to_numpy().copy()
    rng.shuffle(order)
    if caa_share() < deal.ccc_target:
        for i in order:
            if caa_share() >= deal.ccc_target:
                break
            if book.loc[i, "rating"] in ("B2", "B3"):
                book.loc[i, "rating"] = str(rng.choice(["Caa1", "Caa1", "Caa2"]))
                book.loc[i, "price"] = float(np.clip(
                    ca._RATING_PRICE[book.loc[i, "rating"]] + rng.normal(0, 2.0), 55, 97))
    else:
        for i in order:
            if caa_share() <= deal.ccc_target:
                break
            if book.loc[i, "rating"].startswith("Caa"):
                book.loc[i, "rating"] = "B3"
                book.loc[i, "price"] = float(np.clip(
                    ca._RATING_PRICE["B3"] + rng.normal(0, 1.1), 55, 100.5))

    # distressed vintages carry their Caa bucket at stressed marks
    if deal.caa_mark_mult < 1.0:
        caa = book["rating"].str.startswith("Caa")
        book.loc[caa, "price"] = (book.loc[caa, "price"] * deal.caa_mark_mult).round(2)
    return book


@lru_cache(maxsize=32)
def deal_state(deal_id: str, as_of: date) -> DealState:
    deal = next(d for d in SHELF if d.deal_id == deal_id)
    book = _build_book(deal)

    age_m = max(_months_between(deal.closing, as_of), 0)
    if age_m < 6:
        status = "Ramp-Up"
    elif as_of <= deal.reinvest_end:
        status = "Reinvestment"
    else:
        status = "Amortization"

    # post-reinvestment deleveraging: ~2.2%/month of par pays down class A
    months_amort = max(_months_between(deal.reinvest_end, as_of), 0)
    factor = max(1.0 - 0.022 * months_amort, 0.35)

    defaulted_par = deal.target_par * factor * deal.default_frac
    par = deal.target_par * factor - defaulted_par
    book = book.assign(par=book["par"] / book["par"].sum() * par)

    balances = _balances_at(deal, factor)

    w = (book["par"] / book["par"].sum()).to_numpy()
    warf = float((w * book["rating"].map(ca._MOODYS_FACTORS)).sum())
    was_bps = float((w * book["spread_bps"]).sum())
    wa_price = float((w * book["price"]).sum())
    ccc_mask = book["rating"].str.startswith("Caa")
    ccc = float(w[ccc_mask].sum())
    ind = book.groupby("industry")["par"].sum() / par
    diversity = float(1.0 / (ind ** 2).sum())

    # OC numerator per the indenture: performing par, excess CCC at market
    # value, defaulted assets at an assumed 45% recovery
    ccc_excess = max(ccc - CCC_LIMIT, 0.0) * par
    ccc_price = float((book.loc[ccc_mask, "par"] * book.loc[ccc_mask, "price"]).sum()
                      / max(book.loc[ccc_mask, "par"].sum(), 1.0)) / 100.0 if ccc_mask.any() else 1.0
    oc_numerator = par - ccc_excess * (1.0 - ccc_price) + defaulted_par * 0.45

    oc, cum = {}, 0.0
    for name, _ in STACK:
        cum += balances[name]
        if name in OC_TRIGGERS:
            oc[name] = oc_numerator / cum if cum > 0 else float("inf")

    # IC: quarterly interest collections over cumulative class coupon due
    sofr = sofr_history(as_of)
    collections = par * (sofr + was_bps / 10_000) / 4 - deal.target_par * factor * MGMT_SENIOR_FEE / 4
    ic, cum_int = {}, 0.0
    margins = {"A (AAA)": deal.aaa_spread_bps} | {
        k: deal.aaa_spread_bps + v for k, v in CLASS_MARGIN_OVER_AAA.items()}
    for name, _ in STACK:
        cum_int += balances[name] * (sofr + margins[name] / 10_000) / 4
        if name in IC_TRIGGERS:
            ic[name] = collections / cum_int if cum_int > 0 else float("inf")

    # equity NAV: collateral at market minus debt outstanding
    mv = float((book["par"] * book["price"]).sum()) / 100.0 + defaulted_par * 0.45
    equity_nav = max(mv - sum(balances.values()), 0.0)

    return DealState(deal=deal, as_of=as_of, status=status, factor=factor, par=par,
                     defaulted_par=defaulted_par, book=book, tranche_balances=balances,
                     warf=warf, was_bps=was_bps, wa_price=wa_price, ccc=ccc,
                     diversity=diversity, oc=oc, ic=ic, equity_nav=equity_nav)


def shelf_states(as_of: date) -> list[DealState]:
    return [deal_state(d.deal_id, as_of) for d in SHELF]


# ---------------------------------------------------------------------------
# compliance evaluation
# ---------------------------------------------------------------------------

def compliance_rows(s: DealState) -> list[dict]:
    """Trigger / actual / cushion / status for every test in the indenture."""
    d = s.deal
    rows: list[dict] = []

    def add(group: str, test: str, threshold: str, actual: str,
            cushion: float | None, ok: bool) -> None:
        rows.append({"group": group, "test": test, "threshold": threshold,
                     "actual": actual, "cushion": cushion,
                     "status": "PASS" if ok else "FAIL"})

    for name, trig in OC_TRIGGERS.items():
        val = s.oc[name]
        add("Coverage", f"OC — Class {name}", f"≥ {trig:.3f}x", f"{val:.3f}x",
            (val - trig) / trig, val >= trig)
    for name, trig in IC_TRIGGERS.items():
        val = s.ic[name]
        add("Coverage", f"IC — Class {name}", f"≥ {trig:.2f}x", f"{val:.2f}x",
            (val - trig) / trig, val >= trig)

    add("Quality", "Max WARF", f"≤ {d.warf_covenant:.0f}", f"{s.warf:.0f}",
        (d.warf_covenant - s.warf) / d.warf_covenant, s.warf <= d.warf_covenant)
    add("Quality", "Min WAS", f"≥ {d.was_covenant_bps / 100:.2f}%",
        f"{s.was_bps / 100:.2f}%", (s.was_bps - d.was_covenant_bps) / d.was_covenant_bps,
        s.was_bps >= d.was_covenant_bps)
    add("Quality", "Min Diversity (eff. industries)", "≥ 9.0", f"{s.diversity:.1f}",
        (s.diversity - 9.0) / 9.0, s.diversity >= 9.0)
    add("Quality", "Max Caa/CCC bucket", "≤ 7.50%", f"{s.ccc * 100:.2f}%",
        (CCC_LIMIT - s.ccc) / CCC_LIMIT, s.ccc <= CCC_LIMIT)

    w = s.book["par"] / s.book["par"].sum()
    top_obligor = float(w.max())
    top_industry = float((s.book.groupby("industry")["par"].sum() / s.book["par"].sum()).max())
    defaulted = s.defaulted_par / max(s.par + s.defaulted_par, 1.0)
    add("Concentration", "Max single obligor", "≤ 2.00%", f"{top_obligor * 100:.2f}%",
        (0.02 - top_obligor) / 0.02, top_obligor <= 0.02)
    add("Concentration", "Max single industry", "≤ 15.00%", f"{top_industry * 100:.2f}%",
        (0.15 - top_industry) / 0.15, top_industry <= 0.15)
    add("Concentration", "Max defaulted obligations", "≤ 2.50%", f"{defaulted * 100:.2f}%",
        (0.025 - defaulted) / 0.025, defaulted <= 0.025)
    return rows


def failing_tests(s: DealState) -> int:
    return sum(1 for r in compliance_rows(s) if r["status"] == "FAIL")


# ---------------------------------------------------------------------------
# quarterly history (trends + trustee payment reports)
# ---------------------------------------------------------------------------

def _payment_dates(s: DealState, max_n: int = 12) -> list[date]:
    """Quarterly payment dates from first payment to the last one before as-of."""
    dates, d = [], s.deal.closing
    while True:
        m, y = d.month + 3, d.year
        if m > 12:
            m, y = m - 12, y + 1
        d = date(y, m, min(s.deal.closing.day, 28))
        if d > s.as_of:
            break
        dates.append(d)
    return dates[-max_n:]


def quality_history(s: DealState, quarters: int = 12) -> pd.DataFrame:
    """Backfilled quarterly WARF / WAS / CCC / junior-OC path ending at today's
    metrics: seasoned books walked back to cleaner starting points."""
    rng = np.random.default_rng(s.deal.seed + 101)
    dates = _payment_dates(s, quarters)
    n = len(dates)
    if n == 0:   # ramping deal with no payment date yet
        return pd.DataFrame(columns=["date", "warf", "was_bps", "ccc", "jr_oc"])
    k = np.arange(n - 1, -1, -1)   # quarters before now
    jr_oc = s.oc["E (BB)"]
    df = pd.DataFrame({
        "date": [d.isoformat() for d in dates],
        "warf": s.warf - k * 16 + rng.normal(0, 12, n),
        "was_bps": s.was_bps + k * 1.6 + rng.normal(0, 2.5, n),
        "ccc": np.clip(s.ccc - k * 0.0018 + rng.normal(0, 0.0012, n), 0, None),
        "jr_oc": jr_oc + k * 0.0022 + rng.normal(0, 0.0012, n),
    })
    # pin the last row to the exact current state
    df.loc[df.index[-1], ["warf", "was_bps", "ccc", "jr_oc"]] = (
        s.warf, s.was_bps, s.ccc, jr_oc)
    return df


def payment_history(s: DealState, max_n: int = 8) -> list[dict]:
    """Trustee report per payment date: proceeds, fees, debt service, equity."""
    rng = np.random.default_rng(s.deal.seed + 202)
    d = s.deal
    rows = []
    margins = {"A (AAA)": d.aaa_spread_bps} | {
        k: d.aaa_spread_bps + v for k, v in CLASS_MARGIN_OVER_AAA.items()}
    equity_notional = d.target_par * EQUITY_PCT
    for pay_date in _payment_dates(s, max_n):
        sofr = sofr_history(pay_date)
        # par factor on that date (approximate: today's amortization schedule)
        months_amort = max(_months_between(d.reinvest_end, pay_date), 0)
        factor = max(1.0 - 0.022 * months_amort, 0.35)
        par = d.target_par * factor
        int_proceeds = par * (sofr + s.was_bps / 10_000) / 4 * float(rng.normal(1, 0.015))
        prin_proceeds = par * 0.066 * float(rng.normal(1, 0.1)) if months_amort > 0 \
            else par * 0.004 * float(rng.normal(1, 0.3))
        senior_fee = par * MGMT_SENIOR_FEE / 4
        sub_fee = par * MGMT_SUB_FEE / 4
        balances = _balances_at(d, factor)
        debt_interest = sum(bal * (sofr + margins[name] / 10_000) / 4
                            for name, bal in balances.items())
        equity = max(int_proceeds - senior_fee - sub_fee - debt_interest, 0.0)
        rows.append({
            "date": pay_date.isoformat(),
            "int_proceeds": int_proceeds,
            "prin_proceeds": prin_proceeds,
            "senior_fee": senior_fee, "sub_fee": sub_fee,
            "debt_interest": debt_interest,
            "equity_dist": equity,
            "equity_annualized": equity * 4 / equity_notional,
        })
    return rows


# ---------------------------------------------------------------------------
# forward projection off the waterfall engine
# ---------------------------------------------------------------------------

def forward_projection(s: DealState) -> tuple:
    """Run today's stack through the engine: paydown + projected equity."""
    d = s.deal
    was = s.was_bps / 10_000
    wam = min(max(_months_between(s.as_of, d.maturity), 24), 96)
    pool = CollateralPool(balance=max(s.par, 1e6), wac=0.043 + was, wam=wam,
                          servicing_fee=MGMT_SENIOR_FEE + MGMT_SUB_FEE,
                          spread=was, amort_style="bullet", name=d.name)
    margins = {"A (AAA)": d.aaa_spread_bps} | {
        k: d.aaa_spread_bps + v for k, v in CLASS_MARGIN_OVER_AAA.items()}
    tranches = tuple(
        Tranche(name, i + 1, round(s.tranche_balances[name], 2),
                FloatingCoupon("SOFR", margins[name] / 10_000))
        for i, (name, _) in enumerate(STACK) if s.tranche_balances[name] > 0)
    spec = DealSpec(name=d.name, tranches=tranches,
                    oc_trigger=OC_TRIGGERS["E (BB)"], senior_fee=MGMT_SENIOR_FEE)
    assumptions = Assumptions(cpr=0.20, cdr=0.02 + s.ccc * 0.15, severity=0.35,
                              recovery_lag=3)
    result = run_deal(spec, pool, assumptions, DiscountCurve.demo_sofr())
    return spec, result
