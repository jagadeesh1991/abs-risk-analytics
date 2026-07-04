"""Reference deal + pool construction, including seeding from loan tapes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store
from ..analytics.filters import wavg
from ..models import Portfolio, Snapshot
from ..schema.canonical import ACTIVE_STATUSES
from .types import CollateralPool, DealSpec, FloatingCoupon, Tranche


def demo_pool() -> CollateralPool:
    return CollateralPool(balance=500_000_000.0, wac=0.068, wam=84,
                          servicing_fee=0.005, name="Demo Auto Pool")


def deal_for_pool(pool: CollateralPool, name: str = "ABF 2026-1",
                  oc_trigger: float = 1.03) -> DealSpec:
    """Standard 70/15/10 sequential stack over the pool; 5% initial equity
    cushion (initial OC = 100/95 ≈ 1.053 vs a 1.03 trigger)."""
    b = pool.balance
    return DealSpec(
        name=name,
        tranches=(
            Tranche("Class A", seniority=1, balance=round(b * 0.70, 2),
                    coupon=FloatingCoupon(index="SOFR", margin=0.0120)),
            Tranche("Class B", seniority=2, balance=round(b * 0.15, 2), coupon=0.0610),
            Tranche("Class C", seniority=3, balance=round(b * 0.10, 2), coupon=0.0750),
        ),
        oc_trigger=oc_trigger,
        senior_fee=0.0025,
    )


def pool_from_portfolio(session: Session, portfolio_id: int) -> CollateralPool:
    """Derive pool-level stats (balance / WAC / WAM) from the latest snapshot
    of an uploaded or generated loan tape."""
    portfolio = session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise ValueError(f"portfolio {portfolio_id} not found")
    snap = session.scalars(
        select(Snapshot).where(Snapshot.portfolio_id == portfolio_id)
        .order_by(Snapshot.as_of_date.desc())).first()
    if snap is None:
        raise ValueError(f"portfolio {portfolio.name!r} has no snapshots")

    df = store.load_snapshot(portfolio_id, snap.as_of_date)
    active = df[df["status"].isin(ACTIVE_STATUSES)]
    if active.empty:
        raise ValueError(f"portfolio {portfolio.name!r} has no active loans")

    balance = float(active["current_balance"].sum())
    wac = wavg(active["interest_rate"], active["current_balance"]) or 0.06
    wam = wavg(active["remaining_term"], active["current_balance"]) or 60.0
    return CollateralPool(balance=balance, wac=float(wac),
                          wam=max(int(round(wam)), 12),
                          servicing_fee=0.005, name=portfolio.name)
