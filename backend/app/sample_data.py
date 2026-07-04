"""Synthetic loan tape generator.

Simulates loan pools month by month with FICO-dependent delinquency
transitions, amortization, prepayment and default, then writes 24 monthly
snapshots per portfolio — so trends, vintage curves and roll rates all look
like real seasoned collateral.

Run directly:  python -m app.sample_data
"""
from datetime import date

import numpy as np
import pandas as pd

from . import store
from .db import SessionLocal, init_db
from .models import Portfolio, Snapshot
from .schema.canonical import (
    STATUS_CURRENT, STATUS_DPD30, STATUS_DPD60, STATUS_DPD90,
    STATUS_DEFAULT, STATUS_PREPAID,
)

SEED = 42
N_SNAPSHOTS = 24

# integer state codes used inside the simulation
C, D30, D60, D90, DEF, PRE = 0, 1, 2, 3, 4, 5
STATUS_BY_CODE = [STATUS_CURRENT, STATUS_DPD30, STATUS_DPD60, STATUS_DPD90,
                  STATUS_DEFAULT, STATUS_PREPAID]

PORTFOLIOS = [
    {"name": "Auto ABS 2024-1", "asset_class": "auto", "n": 5000, "prefix": "AUT",
     "description": "Prime/near-prime auto loan securitization pool"},
    {"name": "Prime RMBS Pool", "asset_class": "mortgage", "n": 2000, "prefix": "MTG",
     "description": "First-lien prime residential mortgage pool"},
    {"name": "Consumer Lending Trust", "asset_class": "consumer", "n": 3000, "prefix": "CNS",
     "description": "Unsecured consumer installment loans"},
    # two more auto issuers at opposite ends of the credit box, so the
    # issuer-comparison dashboards have something real to compare
    {"name": "Subprime Auto Trust", "asset_class": "auto", "n": 4000, "prefix": "SUB",
     "description": "Deep-subprime auto loans from an independent finance company",
     "overrides": dict(fico_mu=605, fico_sig=55, fico_lo=460, fico_hi=740,
                       d30_base=0.028, rate_base=0.135, prepay=0.010, bal_mean=24_000,
                       ltv_mu=112, ltv_sig=16)},
    {"name": "Regional Bank Auto 2025-A", "asset_class": "auto", "n": 3000, "prefix": "RBA",
     "description": "Super-prime bank-originated auto loans",
     "overrides": dict(fico_mu=742, fico_sig=38, fico_lo=640, fico_hi=845,
                       d30_base=0.004, rate_base=0.041, prepay=0.015, bal_mean=38_000,
                       ltv_mu=86, ltv_sig=12)},
]

CLASS_CFG = {
    "auto": dict(bal_mean=32_000, bal_sig=0.35, terms=[48, 60, 72, 84], term_p=[.15, .30, .35, .20],
                 fico_mu=680, fico_sig=70, fico_lo=480, fico_hi=830,
                 rate_base=0.052, rate_slope=0.00045, d30_base=0.010, prepay=0.013,
                 ltv_mu=98, ltv_sig=14, ltv_lo=55, ltv_hi=140),
    "mortgage": dict(bal_mean=320_000, bal_sig=0.40, terms=[180, 360], term_p=[.20, .80],
                     fico_mu=725, fico_sig=50, fico_lo=580, fico_hi=830,
                     rate_base=0.044, rate_slope=0.00018, d30_base=0.004, prepay=0.007,
                     ltv_mu=76, ltv_sig=11, ltv_lo=30, ltv_hi=97),
    "consumer": dict(bal_mean=14_000, bal_sig=0.50, terms=[36, 48, 60], term_p=[.40, .35, .25],
                     fico_mu=690, fico_sig=60, fico_lo=520, fico_hi=830,
                     rate_base=0.089, rate_slope=0.0006, d30_base=0.013, prepay=0.016,
                     ltv_mu=None),
}

STATE_WEIGHTS = {
    "CA": 11.7, "TX": 9.0, "FL": 6.7, "NY": 5.8, "PA": 3.8, "IL": 3.7, "OH": 3.5,
    "GA": 3.3, "NC": 3.2, "MI": 3.0, "NJ": 2.8, "VA": 2.6, "WA": 2.4, "AZ": 2.2,
    "TN": 2.1, "MA": 2.1, "IN": 2.0, "MO": 1.8, "MD": 1.8, "WI": 1.7, "CO": 1.8,
    "MN": 1.7, "SC": 1.6, "AL": 1.5, "LA": 1.4, "KY": 1.3, "OR": 1.3, "OK": 1.2,
    "CT": 1.1, "UT": 1.0, "NV": 1.0, "IA": 0.9, "AR": 0.9, "MS": 0.9, "KS": 0.9,
    "NM": 0.6, "NE": 0.6, "ID": 0.6, "WV": 0.5, "HI": 0.4, "NH": 0.4, "ME": 0.4,
    "MT": 0.3, "RI": 0.3, "DE": 0.3, "SD": 0.3, "ND": 0.2, "AK": 0.2, "VT": 0.2, "WY": 0.2,
}

VEHICLE_TYPES = ["Sedan", "SUV", "Truck", "Crossover", "Van"]
PROPERTY_TYPES = ["SFR", "Condo", "Townhouse", "2-4 Unit", "PUD"]
LOAN_PURPOSES = ["Debt Consolidation", "Home Improvement", "Medical", "Major Purchase", "Other"]


def _month_index(y: int, m: int) -> int:
    return y * 12 + (m - 1)


def _month_end(idx: int) -> date:
    ts = pd.Timestamp(idx // 12, idx % 12 + 1, 1) + pd.offsets.MonthEnd(0)
    return ts.date()


def _annuity_payment(balance, annual_rate, term_months):
    r = annual_rate / 12.0
    return np.where(r > 0, balance * r / (1 - (1 + r) ** -term_months),
                    balance / term_months)


def _make_loans(cfg: dict, n: int, prefix: str, asset_class: str,
                first_orig: int, last_orig: int, rng: np.random.Generator) -> pd.DataFrame:
    fico = np.clip(rng.normal(cfg["fico_mu"], cfg["fico_sig"], n),
                   cfg["fico_lo"], cfg["fico_hi"]).round()
    orig_balance = (cfg["bal_mean"] * rng.lognormal(0, cfg["bal_sig"], n)).round(2)
    term = rng.choice(cfg["terms"], size=n, p=cfg["term_p"])
    rate = (cfg["rate_base"] + np.maximum(0, 740 - fico) * cfg["rate_slope"]
            + rng.normal(0, 0.004, n)).clip(0.015, 0.32).round(5)
    # loans season over the window: weight originations toward the recent past
    orig_month = rng.integers(first_orig, last_orig + 1, n)
    states = list(STATE_WEIGHTS)
    weights = np.array(list(STATE_WEIGHTS.values()))
    df = pd.DataFrame({
        "loan_id": [f"{prefix}-{i:06d}" for i in range(1, n + 1)],
        "asset_class": asset_class,
        "fico": fico,
        "original_balance": orig_balance,
        "original_term": term,
        "interest_rate": rate,
        "orig_month": orig_month,
        "orig_day": rng.integers(1, 29, n),
        "state": rng.choice(states, size=n, p=weights / weights.sum()),
        "monthly_payment": _annuity_payment(orig_balance, rate, term).round(2),
    })
    if cfg.get("ltv_mu"):
        df["ltv"] = np.clip(rng.normal(cfg["ltv_mu"], cfg["ltv_sig"], n),
                            cfg["ltv_lo"], cfg["ltv_hi"]).round(1)
    if asset_class == "mortgage":
        df["dti"] = np.clip(rng.normal(34, 8, n), 10, 55).round(1)
        df["property_type"] = rng.choice(PROPERTY_TYPES, size=n, p=[.62, .15, .12, .06, .05])
        df["lien_position"] = 1
    elif asset_class == "auto":
        df["vehicle_new_used"] = rng.choice(["New", "Used"], size=n, p=[.42, .58])
        df["vehicle_type"] = rng.choice(VEHICLE_TYPES, size=n, p=[.25, .34, .2, .15, .06])
    else:
        df["dti"] = np.clip(rng.normal(30, 9, n), 5, 55).round(1)
        df["loan_purpose"] = rng.choice(LOAN_PURPOSES, size=n, p=[.45, .2, .1, .15, .1])
    return df


def _simulate(loans: pd.DataFrame, cfg: dict, snapshot_months: list[int],
              rng: np.random.Generator) -> dict[int, pd.DataFrame]:
    """March every loan month-by-month; capture rows at snapshot months."""
    n = len(loans)
    state = np.full(n, C, dtype=int)
    balance = loans["original_balance"].to_numpy().copy()
    terminal_month = np.full(n, -1, dtype=int)  # -1 = still active
    risk = np.clip(np.exp((680 - loans["fico"].to_numpy()) / 55), 0.15, 6.0)
    p_d30 = np.clip(cfg["d30_base"] * risk, 0, 0.22)
    # refi incentive: loans priced above the pool's base rate prepay faster
    rate_gap = loans["interest_rate"].to_numpy() - cfg["rate_base"]
    p_prepay = cfg["prepay"] * np.clip(0.6 + rate_gap * 10, 0.5, 2.5)
    rate_m = loans["interest_rate"].to_numpy() / 12.0
    payment = loans["monthly_payment"].to_numpy()
    orig_month = loans["orig_month"].to_numpy()
    term = loans["original_term"].to_numpy()

    out: dict[int, pd.DataFrame] = {}
    first_month = int(orig_month.min())
    last_month = max(snapshot_months)
    snap_set = set(snapshot_months)

    for m in range(first_month, last_month + 1):
        originated = orig_month <= m
        active = originated & (state <= D90)

        # -- delinquency transitions -------------------------------------
        u = rng.random(n)
        cur = active & (state == C)
        to_d30 = cur & (u < p_d30)
        to_pre = cur & ~to_d30 & (u < p_d30 + p_prepay)
        d30 = active & (state == D30)
        d30_cure = d30 & (u < 0.32)
        d30_worse = d30 & (u >= 0.32) & (u < 0.64)
        d60 = active & (state == D60)
        d60_cure = d60 & (u < 0.10)
        d60_worse = d60 & (u >= 0.10) & (u < 0.52)
        d90 = active & (state == D90)
        d90_cure = d90 & (u < 0.05)
        d90_def = d90 & (u >= 0.05) & (u < 0.37)

        state[to_d30] = D30
        state[to_pre] = PRE
        terminal_month[to_pre] = m
        balance[to_pre] = 0.0
        state[d30_cure] = C
        state[d30_worse] = D60
        state[d60_cure] = C
        state[d60_worse] = D90
        state[d90_cure] = C
        state[d90_def] = DEF
        terminal_month[d90_def] = m  # balance kept = chargeoff amount

        # -- amortization (only current loans pay) ------------------------
        paying = originated & (state == C)
        interest = balance * rate_m
        principal = np.where(paying, payment - interest, 0.0)
        balance = np.where(paying, np.maximum(balance - principal, 0.0), balance)
        matured = paying & ((balance <= 1.0) | (m - orig_month >= term))
        state[matured] = PRE
        terminal_month[matured] = m
        balance[matured] = 0.0

        # -- snapshot ------------------------------------------------------
        if m in snap_set:
            on_tape = originated & ((terminal_month == -1) | (terminal_month == m))
            idx = np.where(on_tape)[0]
            if len(idx) == 0:
                out[m] = pd.DataFrame()
                continue
            snap = loans.iloc[idx].copy()
            st = state[idx]
            snap["status"] = [STATUS_BY_CODE[s] for s in st]
            dpd = np.zeros(len(idx), dtype=int)
            dpd[st == D30] = rng.integers(30, 60, (st == D30).sum())
            dpd[st == D60] = rng.integers(60, 90, (st == D60).sum())
            dpd[st == D90] = rng.integers(90, 160, (st == D90).sum())
            dpd[st == DEF] = 180
            snap["dpd"] = dpd
            snap["current_balance"] = balance[idx].round(2)
            snap["remaining_term"] = np.maximum(term[idx] - (m - orig_month[idx]), 0)
            snap["origination_date"] = [
                date(om // 12, om % 12 + 1, int(od))
                for om, od in zip(orig_month[idx], snap["orig_day"])
            ]
            out[m] = snap.drop(columns=["orig_month", "orig_day"])

    return out


def generate(session=None, last_snapshot: date | None = None) -> list[dict]:
    """(Re)create the three demo portfolios. Returns portfolio summaries."""
    own_session = session is None
    if own_session:
        init_db()
        session = SessionLocal()
    try:
        rng = np.random.default_rng(SEED)
        last = last_snapshot or (pd.Timestamp.today() - pd.offsets.MonthEnd(1)).date()
        last_idx = _month_index(last.year, last.month)
        snapshot_months = list(range(last_idx - N_SNAPSHOTS + 1, last_idx + 1))
        first_orig = snapshot_months[0] - 30   # up to 2.5y of seasoning
        last_orig = last_idx - 1

        results = []
        for spec in PORTFOLIOS:
            existing = session.query(Portfolio).filter_by(name=spec["name"]).first()
            if existing:
                store.delete_portfolio_data(existing.id)
                session.delete(existing)
                session.commit()

            p = Portfolio(name=spec["name"], asset_class=spec["asset_class"],
                          description=spec["description"])
            session.add(p)
            session.commit()

            cfg = {**CLASS_CFG[spec["asset_class"]], **spec.get("overrides", {})}
            loans = _make_loans(cfg, spec["n"], spec["prefix"], spec["asset_class"],
                                first_orig, last_orig, rng)
            snaps = _simulate(loans, cfg, snapshot_months, rng)

            for m, df in snaps.items():
                if df.empty:
                    continue
                as_of = _month_end(m)
                store.save_snapshot(p.id, as_of, df)
                session.add(Snapshot(
                    portfolio_id=p.id, as_of_date=as_of,
                    row_count=int(len(df)),
                    total_balance=float(df["current_balance"].sum()),
                    source_filename="generated",
                ))
            session.commit()
            results.append({"portfolio": spec["name"], "loans": spec["n"],
                            "snapshots": len(snaps)})
            print(f"  {spec['name']}: {spec['n']} loans x {len(snaps)} snapshots")
        return results
    finally:
        if own_session:
            session.close()


if __name__ == "__main__":
    print("Generating demo portfolios...")
    generate()
    print("Done.")
