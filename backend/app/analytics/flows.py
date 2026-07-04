"""Transition-flow charts: Sankey, attrition funnel, transition-rate trend."""
import pandas as pd

from ..schema.canonical import (
    ACTIVE_STATUSES,
    STATUS_CURRENT,
    STATUS_DEFAULT,
    STATUS_DPD30,
    STATUS_LABELS,
    STATUS_PREPAID,
)
from .filters import Ctx, empty_payload
from .registry import register


def month_pairs(ctx: Ctx) -> list[tuple]:
    """Consecutive (from_date, to_date) snapshot pairs, oldest first."""
    dates = ctx.snapshot_dates()
    return list(zip(dates[:-1], dates[1:]))


def transitions(ctx: Ctx) -> pd.DataFrame:
    """Loan-level month-over-month transitions across the whole history.

    Columns: date (the 'to' date), status_from, status_to, balance (at 'from'),
    plus interest_rate / fico / asset_class carried from the 'from' row.
    Loans that vanish without a terminal row count as prepaid.
    """
    hist = ctx.history()
    if hist.empty:
        return pd.DataFrame()
    hist = hist.copy()
    hist["date"] = pd.to_datetime(hist["as_of_date"]).dt.date
    frames = []
    for d0, d1 in month_pairs(ctx):
        t0 = hist[(hist["date"] == d0) & hist["status"].isin(ACTIVE_STATUSES)]
        t1 = hist[hist["date"] == d1][["portfolio_id", "loan_id", "status"]]
        if t0.empty:
            continue
        m = t0[["portfolio_id", "loan_id", "status", "current_balance",
                "interest_rate", "fico", "asset_class"]].merge(
            t1, on=["portfolio_id", "loan_id"], how="left", suffixes=("_from", "_to"))
        m["status_to"] = m["status_to"].fillna(STATUS_PREPAID)
        m["date"] = d1
        frames.append(m.rename(columns={"status_from": "status_from",
                                        "current_balance": "balance"}))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


@register("sankey_flow", "Delinquency Flow (Sankey)", "flow", "sankey",
          "Where last month's balance went: cures, rolls, prepays and defaults",
          needs_history=True)
def sankey_flow(ctx: Ctx) -> dict:
    pairs = month_pairs(ctx)
    if not pairs:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    d0, d1 = pairs[-1]

    hist = ctx.history().copy()
    hist["date"] = pd.to_datetime(hist["as_of_date"]).dt.date
    t0 = hist[(hist["date"] == d0) & hist["status"].isin(ACTIVE_STATUSES)]
    t1 = hist[hist["date"] == d1][["portfolio_id", "loan_id", "status"]]
    if t0.empty:
        return empty_payload("No active loans in the prior snapshot")
    m = t0[["portfolio_id", "loan_id", "status", "current_balance"]].merge(
        t1, on=["portfolio_id", "loan_id"], how="left", suffixes=("_from", "_to"))
    m["status_to"] = m["status_to"].fillna(STATUS_PREPAID)

    flows = m.groupby(["status_from", "status_to"])["current_balance"].sum().reset_index()
    flows = flows[flows["current_balance"] > 0]

    left = f"{d0.strftime('%b %Y')} · "
    right = f"{d1.strftime('%b %Y')} · "
    nodes, links = [], []
    seen: set[str] = set()
    for _, row in flows.iterrows():
        src = left + STATUS_LABELS[row["status_from"]]
        dst = right + STATUS_LABELS[row["status_to"]]
        for name in (src, dst):
            if name not in seen:
                seen.add(name)
                nodes.append({"name": name})
        links.append({"source": src, "target": dst,
                      "value": round(float(row["current_balance"]), 2)})

    return {"type": "sankey", "format": "currency", "nodes": nodes, "links": links,
            "subtitle": f"Balance flow {d0.isoformat()} → {d1.isoformat()}"}


@register("attrition_funnel", "Cohort Attrition Funnel", "flow", "funnel",
          "From everything ever originated down to loans that have never missed a payment",
          needs_history=True)
def attrition_funnel(ctx: Ctx) -> dict:
    hist = ctx.history()
    if hist.empty:
        return empty_payload("No loans match the current filters")
    current = ctx.current()
    key = ["portfolio_id", "loan_id"]

    originated = hist.drop_duplicates(subset=key)
    active_now = ctx.active(current)
    performing = active_now[active_now["status"] == STATUS_CURRENT]
    # never observed outside CURRENT across the whole history, and still active
    ever_bad = hist.loc[hist["status"] != STATUS_CURRENT, key].drop_duplicates()
    merged = active_now[key].merge(ever_bad, on=key, how="left", indicator=True)
    never_delinq = int((merged["_merge"] == "left_only").sum())

    items = [
        {"name": "Ever Originated (observed)", "value": int(len(originated))},
        {"name": "Still Active", "value": int(len(active_now))},
        {"name": "Currently Performing", "value": int(len(performing))},
        {"name": "Never Delinquent", "value": never_delinq},
    ]
    return {"type": "funnel", "format": "number", "items": items}


@register("transition_trend", "Transition Rates Over Time", "flow", "line",
          "Monthly new-delinquency, cure and default rates (share of prior-month balance)",
          needs_history=True)
def transition_trend(ctx: Ctx) -> dict:
    tr = transitions(ctx)
    if tr.empty:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")

    rows = []
    for d, grp in tr.groupby("date"):
        total = grp["balance"].sum()
        if total <= 0:
            continue
        cur = grp[grp["status_from"] == STATUS_CURRENT]
        dlq = grp[grp["status_from"] != STATUS_CURRENT]
        new_dlq = cur.loc[cur["status_to"] == STATUS_DPD30, "balance"].sum()
        cures = dlq.loc[dlq["status_to"] == STATUS_CURRENT, "balance"].sum()
        defaults = grp.loc[grp["status_to"] == STATUS_DEFAULT, "balance"].sum()
        rows.append({
            "date": d,
            "new_dlq": new_dlq / max(cur["balance"].sum(), 1e-9),
            "cure": cures / max(dlq["balance"].sum(), 1e-9) if len(dlq) else 0.0,
            "default": defaults / total,
        })
    if not rows:
        return empty_payload("Not enough transition history")
    df = pd.DataFrame(rows).sort_values("date")
    return {
        "type": "line", "yFormat": "percent",
        "x": [d.isoformat() for d in df["date"]],
        "series": [
            {"name": "New delinquency (C→30)", "data": [round(v, 5) for v in df["new_dlq"]]},
            {"name": "Cure rate (DLQ→C)", "data": [round(v, 5) for v in df["cure"]]},
            {"name": "Default rate", "data": [round(v, 5) for v in df["default"]]},
        ],
    }
