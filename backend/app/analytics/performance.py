"""Performance charts: delinquency trend, vintage curves, roll-rate matrix."""
import pandas as pd

from ..schema.canonical import (
    ACTIVE_STATUSES,
    STATUS_DEFAULT,
    STATUS_DPD30,
    STATUS_DPD60,
    STATUS_DPD90,
    STATUS_LABELS,
    STATUS_PREPAID,
    STATUSES,
)
from .filters import Ctx, empty_payload
from .registry import register


@register("delinquency_trend", "Delinquency Trend", "performance", "line",
          "Share of active balance in each delinquency bucket over time", needs_history=True)
def delinquency_trend(ctx: Ctx) -> dict:
    hist = ctx.active(ctx.history())
    if hist.empty:
        return empty_payload("No loans match the current filters")
    hist = hist.copy()
    hist["date"] = pd.to_datetime(hist["as_of_date"]).dt.date
    totals = hist.groupby("date")["current_balance"].sum()
    if len(totals) < 2:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")

    series = []
    for status, label in [(STATUS_DPD30, "30-59 DPD"), (STATUS_DPD60, "60-89 DPD"),
                          (STATUS_DPD90, "90+ DPD")]:
        bal = hist[hist["status"] == status].groupby("date")["current_balance"].sum()
        pct = (bal.reindex(totals.index).fillna(0) / totals).fillna(0)
        series.append({"name": label, "data": [float(v) for v in pct.values]})
    # 60+ aggregate line
    bal60 = hist[hist["status"].isin([STATUS_DPD60, STATUS_DPD90])].groupby("date")["current_balance"].sum()
    pct60 = (bal60.reindex(totals.index).fillna(0) / totals).fillna(0)
    series.append({"name": "60+ DPD", "data": [float(v) for v in pct60.values]})

    return {"type": "line", "yFormat": "percent",
            "x": [d.isoformat() for d in totals.index], "series": series}


@register("vintage_curves", "Vintage Curves — Cumulative Loss", "performance", "line",
          "Cumulative default rate by months-on-book, one curve per origination year",
          needs_history=True)
def vintage_curves(ctx: Ctx) -> dict:
    hist = ctx.history()
    if hist.empty:
        return empty_payload("No loans match the current filters")
    df = hist.copy()
    df["orig"] = pd.to_datetime(df["origination_date"])
    df["asof"] = pd.to_datetime(df["as_of_date"])
    df["cohort"] = df["orig"].dt.year
    df["mob"] = ((df["asof"].dt.year - df["orig"].dt.year) * 12
                 + (df["asof"].dt.month - df["orig"].dt.month)).clip(lower=0)

    # cohort denominators: original balance of unique loans ever observed
    uniq = df.drop_duplicates(subset=["portfolio_id", "loan_id"])
    denom = uniq.groupby("cohort")["original_balance"].sum()
    counts = uniq.groupby("cohort")["loan_id"].count()

    defaults = df[df["status"] == STATUS_DEFAULT]
    if defaults.empty:
        return empty_payload("No defaults observed yet in the selected data")

    loss = defaults.groupby(["cohort", "mob"])["current_balance"].sum()
    max_mob = int(df["mob"].max())
    series = []
    for cohort in sorted(denom.index):
        if counts.get(cohort, 0) < 25 or denom[cohort] <= 0:
            continue  # skip tiny cohorts — their curves are noise
        # cohort is only observable up to the MOB its youngest data reaches
        observed_mob = int(df.loc[df["cohort"] == cohort, "mob"].max())
        cohort_loss = loss.loc[cohort] if cohort in loss.index.get_level_values(0) else pd.Series(dtype=float)
        cum = cohort_loss.reindex(range(observed_mob + 1)).fillna(0).cumsum() / denom[cohort]
        series.append({"name": str(cohort), "data": [round(float(v), 6) for v in cum.values]})
    if not series:
        return empty_payload("Not enough loans per cohort to draw vintage curves")

    return {"type": "line", "yFormat": "percent", "xLabel": "Months on book",
            "x": list(range(max_mob + 1)), "series": series}


@register("roll_rate_matrix", "Roll Rate Matrix", "performance", "heatmap",
          "Balance-weighted month-over-month transitions between delinquency states",
          needs_history=True)
def roll_rate_matrix(ctx: Ctx) -> dict:
    dates = ctx.snapshot_dates()
    if len(dates) < 2:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    d_from, d_to = dates[-2], dates[-1]

    hist = ctx.history()
    hist = hist.copy()
    hist["date"] = pd.to_datetime(hist["as_of_date"]).dt.date
    t0 = hist[hist["date"] == d_from]
    t1 = hist[hist["date"] == d_to]
    t0 = t0[t0["status"].isin(ACTIVE_STATUSES)][["portfolio_id", "loan_id", "status", "current_balance"]]
    t1 = t1[["portfolio_id", "loan_id", "status"]]
    if t0.empty:
        return empty_payload("No active loans in the prior snapshot")

    m = t0.merge(t1, on=["portfolio_id", "loan_id"], how="left", suffixes=("_from", "_to"))
    # loans that vanish without a terminal row are treated as paid off
    m["status_to"] = m["status_to"].fillna(STATUS_PREPAID)

    from_states = ACTIVE_STATUSES
    to_states = STATUSES
    pivot = m.pivot_table(index="status_from", columns="status_to",
                          values="current_balance", aggfunc="sum").fillna(0)
    cells = []
    for yi, fs in enumerate(from_states):
        row_total = float(pivot.loc[fs].sum()) if fs in pivot.index else 0.0
        for xi, ts in enumerate(to_states):
            v = float(pivot.at[fs, ts]) if fs in pivot.index and ts in pivot.columns else 0.0
            pct = v / row_total if row_total > 0 else 0.0
            cells.append([xi, yi, round(pct, 5)])

    return {"type": "heatmap", "format": "percent",
            "xLabels": [STATUS_LABELS[s] for s in to_states],
            "yLabels": [STATUS_LABELS[s] for s in from_states],
            "cells": cells,
            "meta": {"from": d_from.isoformat(), "to": d_to.isoformat()},
            "subtitle": f"{d_from.isoformat()} → {d_to.isoformat()}, % of prior-month balance"}
