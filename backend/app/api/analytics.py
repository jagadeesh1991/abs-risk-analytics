"""Chart discovery and computation endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..analytics.filters import Ctx, Filters
from ..analytics.registry import CHARTS, chart_list
from ..db import get_session

router = APIRouter(prefix="/api", tags=["analytics"])

_FILTER_KEYS = {"portfolio_id", "as_of", "asset_class", "vintage", "fico_band", "state"}


@router.get("/charts")
def charts():
    return chart_list()


@router.get("/charts/{chart_id}")
def compute_chart(chart_id: str, request: Request,
                  portfolio_id: int | None = None,
                  as_of: date | None = None,
                  asset_class: str | None = None,
                  vintage: int | None = None,
                  fico_band: str | None = None,
                  state: str | None = None,
                  session: Session = Depends(get_session)):
    spec = CHARTS.get(chart_id)
    if not spec:
        raise HTTPException(404, f"Unknown chart '{chart_id}'")

    filters = Filters(portfolio_id=portfolio_id, as_of=as_of, asset_class=asset_class,
                      vintage=vintage, fico_band=fico_band, state=state)
    ctx = Ctx(session, filters)

    if not ctx.snapshots():
        return {"chart_id": chart_id, "title": spec.title,
                "payload": {"empty": True,
                            "message": "No data yet — generate demo data or upload a loan tape"}}

    # chart-specific params (e.g. ?dimension=state, ?metric=balance)
    kwargs = {}
    for name in spec.params:
        value = request.query_params.get(name)
        if value is not None:
            kwargs[name] = value

    payload = spec.compute(ctx, **kwargs)
    return {"chart_id": chart_id, "title": spec.title, "payload": payload}
