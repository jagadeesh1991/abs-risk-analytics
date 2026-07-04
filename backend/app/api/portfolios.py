"""Portfolio CRUD, filter options, and demo-data generation."""
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import sample_data, store
from ..db import get_session
from ..models import Portfolio, Snapshot
from ..schema.canonical import ALL_FIELD_NAMES, ASSET_CLASSES, FICO_BANDS

router = APIRouter(prefix="/api", tags=["portfolios"])


def _portfolio_json(p: Portfolio) -> dict:
    snaps = sorted(p.snapshots, key=lambda s: s.as_of_date)
    return {
        "id": p.id,
        "name": p.name,
        "asset_class": p.asset_class,
        "description": p.description,
        "snapshot_count": len(snaps),
        "snapshots": [
            {"as_of_date": s.as_of_date.isoformat(), "row_count": s.row_count,
             "total_balance": s.total_balance, "source": s.source_filename}
            for s in snaps
        ],
        "latest_as_of": snaps[-1].as_of_date.isoformat() if snaps else None,
        "latest_balance": snaps[-1].total_balance if snaps else 0,
    }


@router.get("/portfolios")
def list_portfolios(session: Session = Depends(get_session)):
    portfolios = session.scalars(select(Portfolio).order_by(Portfolio.name)).all()
    return [_portfolio_json(p) for p in portfolios]


class PortfolioCreate(BaseModel):
    name: str
    asset_class: str
    description: str = ""


@router.post("/portfolios")
def create_portfolio(body: PortfolioCreate, session: Session = Depends(get_session)):
    if body.asset_class not in ASSET_CLASSES + ["mixed"]:
        raise HTTPException(400, f"asset_class must be one of {ASSET_CLASSES + ['mixed']}")
    if session.query(Portfolio).filter_by(name=body.name).first():
        raise HTTPException(409, f"Portfolio '{body.name}' already exists")
    p = Portfolio(name=body.name, asset_class=body.asset_class, description=body.description)
    session.add(p)
    session.commit()
    return _portfolio_json(p)


@router.delete("/portfolios/{portfolio_id}")
def delete_portfolio(portfolio_id: int, session: Session = Depends(get_session)):
    p = session.get(Portfolio, portfolio_id)
    if not p:
        raise HTTPException(404, "Portfolio not found")
    store.delete_portfolio_data(portfolio_id)
    session.delete(p)
    session.commit()
    return {"ok": True}


@router.post("/sample-data")
def generate_sample_data(session: Session = Depends(get_session)):
    results = sample_data.generate(session)
    return {"ok": True, "portfolios": results}


@router.get("/portfolios/{portfolio_id}/export")
def export_portfolio(portfolio_id: int, scope: str = "latest",
                     session: Session = Depends(get_session)):
    """Download a portfolio as CSV in the canonical column layout.

    scope=latest  -> most recent snapshot only (one row per loan)
    scope=history -> every snapshot stacked (one row per loan per as-of date)
    """
    p = session.get(Portfolio, portfolio_id)
    if not p:
        raise HTTPException(404, "Portfolio not found")
    snaps = sorted(p.snapshots, key=lambda s: s.as_of_date)
    if not snaps:
        raise HTTPException(404, "Portfolio has no snapshots to export")
    selected = snaps if scope == "history" else [snaps[-1]]

    frames = [store.load_snapshot(portfolio_id, s.as_of_date) for s in selected]
    df = pd.concat(frames, ignore_index=True)[ALL_FIELD_NAMES]
    df = df.copy()
    for col in ("as_of_date", "origination_date"):
        df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d")

    filename = f"{p.name}_{selected[-1].as_of_date.isoformat()}_{scope}.csv".replace(" ", "_")
    return Response(
        df.to_csv(index=False),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/filters/options")
def filter_options(portfolio_id: int | None = None,
                   session: Session = Depends(get_session)):
    """Distinct values the FilterBar can offer, given the portfolio scope."""
    q = select(Snapshot).order_by(Snapshot.as_of_date)
    snaps = list(session.scalars(q))
    if portfolio_id is not None:
        snaps = [s for s in snaps if s.portfolio_id == portfolio_id]
    dates = sorted({s.as_of_date for s in snaps})
    if not dates:
        return {"as_of_dates": [], "asset_classes": [], "vintages": [],
                "fico_bands": [b[2] for b in FICO_BANDS], "states": []}

    # use each portfolio's latest snapshot to enumerate row-level options
    latest: dict[int, Snapshot] = {}
    for s in snaps:
        cur = latest.get(s.portfolio_id)
        if cur is None or s.as_of_date > cur.as_of_date:
            latest[s.portfolio_id] = s
    frames = [store.load_snapshot(s.portfolio_id, s.as_of_date) for s in latest.values()]
    df = pd.concat(frames, ignore_index=True)

    vintages = sorted(pd.to_datetime(df["origination_date"]).dt.year.dropna().unique().tolist())
    states = sorted(df["state"].dropna().unique().tolist())
    classes = sorted(df["asset_class"].dropna().unique().tolist())
    return {
        "as_of_dates": [d.isoformat() for d in dates],
        "asset_classes": classes,
        "vintages": [int(v) for v in vintages],
        "fico_bands": [b[2] for b in FICO_BANDS],
        "states": states,
    }
