"""Surveillance charts: percentile bands, delinquency composition, duration mix,
deviation heatmap, FICO×MOB delinquency heatmap."""
import pandas as pd

from ..schema.canonical import (
    ACTIVE_STATUSES,
    FICO_BANDS,
    STATUS_DPD30,
    STATUS_DPD60,
    STATUS_DPD90,
    STATUS_LABELS,
    STATUSES,
)
from .filters import Ctx, empty_payload, fico_band
from .flows import transitions
from .registry import register


def _monthly_dlq(ctx: Ctx) -> pd.DataFrame | None:
    """Per snapshot date: active balance and share in each delinquency bucket."""
    hist = ctx.active(ctx.history())
    if hist.empty:
        return None
    hist = hist.copy()
    hist["date"] = pd.to_datetime(hist["as_of_date"]).dt.date
    total = hist.groupby("date")["current_balance"].sum()
    out = pd.DataFrame({"total": total})
    for status in (STATUS_DPD30, STATUS_DPD60, STATUS_DPD90):
        bal = hist[hist["status"] == status].groupby("date")["current_balance"].sum()
        out[status] = (bal.reindex(total.index).fillna(0) / total)
    out["dpd60p"] = out[STATUS_DPD60] + out[STATUS_DPD90]
    return out.sort_index()


@register("percentile_band", "60+ DPD vs Historical Range", "surveillance", "line",
          "Monthly 60+ DPD rate against the p10–p90 corridor of its own history",
          needs_history=True)
def percentile_band(ctx: Ctx) -> dict:
    m = _monthly_dlq(ctx)
    if m is None or len(m) < 4:
        return empty_payload("Needs at least 4 snapshots to build a corridor")
    series = m["dpd60p"]
    p10, p50, p90 = series.quantile(0.10), series.quantile(0.50), series.quantile(0.90)
    x = [d.isoformat() for d in m.index]
    n = len(x)
    return {
        "type": "line", "yFormat": "percent", "x": x,
        "band": {"name": "p10–p90 history", "low": [round(float(p10), 5)] * n,
                 "high": [round(float(p90), 5)] * n},
        "series": [
            {"name": "60+ DPD", "data": [round(float(v), 5) for v in series]},
            {"name": "Median", "data": [round(float(p50), 5)] * n, "ghost": True},
        ],
    }


@register("delinq_composition", "Delinquency Composition", "surveillance", "bar",
          "Total delinquency rate decomposed into DPD buckets, month by month",
          needs_history=True)
def delinq_composition(ctx: Ctx) -> dict:
    m = _monthly_dlq(ctx)
    if m is None or len(m) < 2:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    return {
        "type": "bar", "yFormat": "percent", "stacked": True,
        "x": [d.isoformat() for d in m.index],
        "series": [
            {"name": "30-59 DPD", "data": [round(float(v), 5) for v in m[STATUS_DPD30]]},
            {"name": "60-89 DPD", "data": [round(float(v), 5) for v in m[STATUS_DPD60]]},
            {"name": "90+ DPD", "data": [round(float(v), 5) for v in m[STATUS_DPD90]]},
        ],
    }


_DURATION_BUCKETS = [(60, 90, "60-89 days"), (90, 120, "90-119 days"),
                     (120, 150, "120-149 days"), (150, 100_000, "150+ days")]


@register("duration_mix", "Delinquency Duration Mix", "surveillance", "bar",
          "How long 60+ balances have been delinquent (share of 60+ balance)",
          needs_history=True)
def duration_mix(ctx: Ctx) -> dict:
    hist = ctx.active(ctx.history())
    if hist.empty:
        return empty_payload("No loans match the current filters")
    df = hist[hist["status"].isin([STATUS_DPD60, STATUS_DPD90])].copy()
    if df.empty:
        return empty_payload("No 60+ delinquent balance in the selected data")
    df["date"] = pd.to_datetime(df["as_of_date"]).dt.date
    df["dpd_num"] = pd.to_numeric(df["dpd"], errors="coerce").fillna(75)
    total = df.groupby("date")["current_balance"].sum().sort_index()
    if len(total) < 2:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")

    series = []
    for lo, hi, label in _DURATION_BUCKETS:
        bal = df[(df["dpd_num"] >= lo) & (df["dpd_num"] < hi)] \
            .groupby("date")["current_balance"].sum()
        pct = (bal.reindex(total.index).fillna(0) / total)
        series.append({"name": label, "data": [round(float(v), 5) for v in pct]})
    return {"type": "bar", "yFormat": "percent", "stacked": True,
            "x": [d.isoformat() for d in total.index], "series": series}


@register("deviation_heatmap", "Roll Rate Deviation vs Baseline", "surveillance", "heatmap",
          "Latest month's transition rates minus the historical average — red cells are "
          "flowing faster than normal", needs_history=True)
def deviation_heatmap(ctx: Ctx) -> dict:
    tr = transitions(ctx)
    if tr.empty:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    dates = sorted(tr["date"].unique())
    if len(dates) < 3:
        return empty_payload("Needs at least 3 snapshots to build a baseline")

    def share_matrix(sub: pd.DataFrame) -> pd.DataFrame:
        pivot = sub.pivot_table(index="status_from", columns="status_to",
                                values="balance", aggfunc="sum").fillna(0)
        return pivot.div(pivot.sum(axis=1), axis=0).fillna(0)

    latest = share_matrix(tr[tr["date"] == dates[-1]])
    baseline_frames = [share_matrix(tr[tr["date"] == d]) for d in dates[:-1]]
    baseline = pd.concat(baseline_frames).groupby(level=0).mean()

    cells = []
    for yi, fs in enumerate(ACTIVE_STATUSES):
        for xi, ts in enumerate(STATUSES):
            cur = float(latest.at[fs, ts]) if fs in latest.index and ts in latest.columns else 0.0
            base = float(baseline.at[fs, ts]) if fs in baseline.index and ts in baseline.columns else 0.0
            cells.append([xi, yi, round(cur - base, 5)])

    return {"type": "heatmap", "format": "percent", "diverging": True,
            "xLabels": [STATUS_LABELS[s] for s in STATUSES],
            "yLabels": [STATUS_LABELS[s] for s in ACTIVE_STATUSES],
            "cells": cells,
            "subtitle": f"{dates[-1].isoformat()} vs average of the prior {len(dates) - 1} months "
                        "(percentage points)"}


_MOB_BUCKETS = [(0, 7, "0-6m"), (7, 13, "7-12m"), (13, 19, "13-18m"),
                (19, 25, "19-24m"), (25, 37, "25-36m"), (37, 10_000, "37m+")]


@register("dlq_fico_mob", "Delinquency by FICO × Seasoning", "surveillance", "heatmap",
          "30+ DPD share of balance across credit band and months-on-book",
          needs_history=True)
def dlq_fico_mob(ctx: Ctx) -> dict:
    hist = ctx.active(ctx.history())
    if hist.empty:
        return empty_payload("No loans match the current filters")
    df = hist.copy()
    orig = pd.to_datetime(df["origination_date"])
    asof = pd.to_datetime(df["as_of_date"])
    df["mob"] = ((asof.dt.year - orig.dt.year) * 12 + (asof.dt.month - orig.dt.month)).clip(lower=0)
    df["_fico"] = fico_band(df["fico"])
    df["_dlq"] = df["status"].isin([STATUS_DPD30, STATUS_DPD60, STATUS_DPD90])

    y_labels = [b[2] for b in FICO_BANDS]
    x_labels = [b[2] for b in _MOB_BUCKETS]
    cells = []
    for yi, fb in enumerate(y_labels):
        band_df = df[df["_fico"] == fb]
        for xi, (lo, hi, _) in enumerate(_MOB_BUCKETS):
            cell = band_df[(band_df["mob"] >= lo) & (band_df["mob"] < hi)]
            total = cell["current_balance"].sum()
            if len(cell) < 100 or total <= 0:
                continue
            rate = cell.loc[cell["_dlq"], "current_balance"].sum() / total
            cells.append([xi, yi, round(float(rate), 5)])
    if not cells:
        return empty_payload("Not enough observations per FICO × seasoning cell")
    return {"type": "heatmap", "format": "percent",
            "xLabels": x_labels, "yLabels": y_labels, "cells": cells,
            "subtitle": "Cells with fewer than 100 loan-months are hidden"}
