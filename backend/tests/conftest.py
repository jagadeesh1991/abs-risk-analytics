"""Shared fixtures: an in-memory metadata DB and a tiny hand-computed tape."""
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import store
from app.db import Base
from app.models import Portfolio, Snapshot


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TAPES_DIR", tmp_path)
    store._cache.clear()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


def _tape(rows: list[dict], as_of: date) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(as_of)
    return df


@pytest.fixture()
def fixture_portfolio(session):
    """3-loan portfolio with two snapshots and known, hand-computed metrics.

    t0 (2026-05-31):
      L1 CURRENT bal 100, fico 750, rate 0.05, state CA
      L2 DPD30   bal  50, fico 600, rate 0.10, state TX
      L3 CURRENT bal  50, fico 700, rate 0.06, state CA
    t1 (2026-06-30):
      L1 CURRENT bal 100
      L2 DPD60   bal  50
      L3 gone (implicit prepay)
    """
    p = Portfolio(name="Fixture", asset_class="auto")
    session.add(p)
    session.commit()

    base = dict(asset_class="auto", origination_date=date(2025, 1, 15),
                original_balance=120.0, original_term=60, monthly_payment=2.0, dpd=0)
    l1 = dict(base, loan_id="L1", current_balance=100.0, fico=750, interest_rate=0.05,
              state="CA", status="CURRENT")
    l2 = dict(base, loan_id="L2", current_balance=50.0, fico=600, interest_rate=0.10,
              state="TX", status="DPD30", dpd=45)
    l3 = dict(base, loan_id="L3", current_balance=50.0, fico=700, interest_rate=0.06,
              state="CA", status="CURRENT")

    t0, t1 = date(2026, 5, 31), date(2026, 6, 30)
    df0 = _tape([l1, l2, l3], t0)
    df1 = _tape([l1, dict(l2, status="DPD60", dpd=75)], t1)

    for as_of, df in [(t0, df0), (t1, df1)]:
        store.save_snapshot(p.id, as_of, df)
        session.add(Snapshot(portfolio_id=p.id, as_of_date=as_of,
                             row_count=len(df),
                             total_balance=float(df["current_balance"].sum())))
    session.commit()
    return p
