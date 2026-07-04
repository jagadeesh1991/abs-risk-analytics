"""Prepayment analytics: CPR/CDR trends and prepay speed by rate band."""
import pandas as pd

from ..schema.canonical import STATUS_DEFAULT, STATUS_PREPAID
from .filters import Ctx, empty_payload, fico_band, rate_band
from .flows import transitions
from .registry import register


def _annualize(monthly_rate: float) -> float:
    """SMM/MDR -> CPR/CDR."""
    return 1.0 - (1.0 - min(monthly_rate, 1.0)) ** 12


@register("cpr_trend", "Prepayment & Default Speed (CPR / CDR)", "prepayment", "line",
          "Annualized prepayment (CPR) and default (CDR) rates by month",
          needs_history=True)
def cpr_trend(ctx: Ctx) -> dict:
    tr = transitions(ctx)
    if tr.empty:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")

    rows = []
    for d, grp in tr.groupby("date"):
        total = grp["balance"].sum()
        if total <= 0:
            continue
        smm = grp.loc[grp["status_to"] == STATUS_PREPAID, "balance"].sum() / total
        mdr = grp.loc[grp["status_to"] == STATUS_DEFAULT, "balance"].sum() / total
        rows.append({"date": d, "cpr": _annualize(smm), "cdr": _annualize(mdr)})
    if not rows:
        return empty_payload("Not enough transition history")
    df = pd.DataFrame(rows).sort_values("date")
    return {
        "type": "line", "yFormat": "percent",
        "x": [d.isoformat() for d in df["date"]],
        "series": [
            {"name": "CPR", "data": [round(v, 5) for v in df["cpr"]]},
            {"name": "CDR", "data": [round(v, 5) for v in df["cdr"]]},
        ],
    }


@register("prepay_by_rate", "Prepay Speed by Note Rate", "prepayment", "bar",
          "Lifetime CPR by rate band — the refi-incentive curve")
def prepay_by_rate(ctx: Ctx) -> dict:
    tr = transitions(ctx)
    if tr.empty:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    tr = tr.copy()
    tr["_band"] = rate_band(tr["interest_rate"])
    data, labels = [], []
    from ..schema.canonical import RATE_BANDS
    for band in [b[2] for b in RATE_BANDS]:
        grp = tr[tr["_band"] == band]
        total = grp["balance"].sum()
        if total <= 0 or len(grp) < 50:
            continue
        smm = grp.loc[grp["status_to"] == STATUS_PREPAID, "balance"].sum() / total
        labels.append(band)
        data.append(round(_annualize(smm), 5))
    if not labels:
        return empty_payload("Not enough rate data per band")
    return {"type": "bar", "yFormat": "percent", "x": labels,
            "series": [{"name": "CPR", "data": data}]}


@register("prepay_by_fico", "Prepay Speed by FICO Band", "prepayment", "bar",
          "Lifetime CPR by credit band")
def prepay_by_fico(ctx: Ctx) -> dict:
    tr = transitions(ctx)
    if tr.empty:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    tr = tr.copy()
    tr["_band"] = fico_band(tr["fico"])
    from ..schema.canonical import FICO_BANDS
    data, labels = [], []
    for band in [b[2] for b in FICO_BANDS]:
        grp = tr[tr["_band"] == band]
        total = grp["balance"].sum()
        if total <= 0 or len(grp) < 50:
            continue
        smm = grp.loc[grp["status_to"] == STATUS_PREPAID, "balance"].sum() / total
        labels.append(band)
        data.append(round(_annualize(smm), 5))
    if not labels:
        return empty_payload("Not enough FICO data per band")
    return {"type": "bar", "yFormat": "percent", "x": labels,
            "series": [{"name": "CPR", "data": data}]}
