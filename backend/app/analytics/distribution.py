"""Distribution & composition charts: histograms, treemap, box plot, waterfall."""
import numpy as np
import pandas as pd

from ..schema.canonical import (
    ACTIVE_STATUSES,
    FICO_BANDS,
    STATUS_DEFAULT,
    STATUS_PREPAID,
)
from .filters import Ctx, empty_payload, fico_band
from .registry import register


def _histogram(values: pd.Series, bin_width: float, fmt: str, unit: str = "") -> dict:
    v = pd.to_numeric(values, errors="coerce").dropna()
    if v.empty:
        return empty_payload("No data for this field in the selected loans")
    lo = np.floor(v.min() / bin_width) * bin_width
    hi = np.ceil(v.max() / bin_width) * bin_width + bin_width
    edges = np.arange(lo, hi, bin_width)
    counts, edges = np.histogram(v, bins=edges)
    labels = [f"{int(edges[i])}{unit}" for i in range(len(edges) - 1)]
    return {"type": "bar", "yFormat": "number",
            "x": labels, "series": [{"name": "Loans", "data": [int(c) for c in counts]}]}


@register("hist_fico", "FICO Distribution", "distribution", "bar",
          "Active loan count by credit score")
def hist_fico(ctx: Ctx) -> dict:
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")
    return _histogram(active["fico"], 20, "number")


@register("hist_ltv", "LTV Distribution", "distribution", "bar",
          "Active loan count by loan-to-value")
def hist_ltv(ctx: Ctx) -> dict:
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")
    if active["ltv"].isna().all():
        return empty_payload("The selected loans have no LTV data")
    return _histogram(active["ltv"], 5, "number")


@register("hist_balance", "Balance Distribution", "distribution", "bar",
          "Active loan count by current balance")
def hist_balance(ctx: Ctx) -> dict:
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")
    v = pd.to_numeric(active["current_balance"], errors="coerce").dropna()
    if v.empty:
        return empty_payload("No balance data")
    # ~20 round-number bins
    raw_width = max(float(v.max()) / 20, 1)
    magnitude = 10 ** np.floor(np.log10(raw_width))
    bin_width = float(np.ceil(raw_width / magnitude) * magnitude)
    counts, edges = np.histogram(v, bins=np.arange(0, v.max() + bin_width, bin_width))
    labels = [f"${edges[i]/1000:.0f}k" for i in range(len(edges) - 1)]
    return {"type": "bar", "yFormat": "number", "x": labels,
            "series": [{"name": "Loans", "data": [int(c) for c in counts]}]}


@register("composition_treemap", "Portfolio Composition", "distribution", "treemap",
          "Active balance by asset class and FICO band")
def composition_treemap(ctx: Ctx) -> dict:
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")
    df = active.copy()
    df["_band"] = fico_band(df["fico"])
    children = []
    for ac, grp in df.groupby("asset_class"):
        bands = grp.groupby("_band")["current_balance"].sum().sort_values(ascending=False)
        children.append({
            "name": str(ac).title(),
            "value": float(grp["current_balance"].sum()),
            "children": [{"name": str(b), "value": float(v)} for b, v in bands.items() if v > 0],
        })
    children.sort(key=lambda c: c["value"], reverse=True)
    return {"type": "treemap", "format": "currency", "children": children}


@register("rate_by_fico_box", "Rate by FICO Band", "distribution", "box",
          "Interest-rate quartiles within each credit band")
def rate_by_fico_box(ctx: Ctx) -> dict:
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")
    df = active.copy()
    df["_band"] = fico_band(df["fico"])
    order = [b[2] for b in FICO_BANDS]
    cats, data = [], []
    for band in order:
        rates = pd.to_numeric(df.loc[df["_band"] == band, "interest_rate"], errors="coerce").dropna()
        if len(rates) < 5:
            continue
        q = rates.quantile([0, 0.25, 0.5, 0.75, 1.0])
        cats.append(band)
        data.append([round(float(x), 5) for x in q.values])
    if not cats:
        return empty_payload("Not enough rate data per band")
    return {"type": "box", "format": "percent", "categories": cats, "data": data}


@register("balance_waterfall", "Balance Walk", "distribution", "waterfall",
          "What moved the pool balance between the last two snapshots", needs_history=True)
def balance_waterfall(ctx: Ctx) -> dict:
    dates = ctx.snapshot_dates()
    if len(dates) < 2:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    d0, d1 = dates[-2], dates[-1]
    hist = ctx.history().copy()
    hist["date"] = pd.to_datetime(hist["as_of_date"]).dt.date
    t0 = hist[(hist["date"] == d0) & hist["status"].isin(ACTIVE_STATUSES)]
    t1 = hist[hist["date"] == d1]
    t1_active = t1[t1["status"].isin(ACTIVE_STATUSES)]

    start = float(t0["current_balance"].sum())
    end = float(t1_active["current_balance"].sum())

    keys0 = set(zip(t0["portfolio_id"], t0["loan_id"]))
    is_new = [k not in keys0 for k in zip(t1_active["portfolio_id"], t1_active["loan_id"])]
    new_orig = float(t1_active.loc[is_new, "current_balance"].sum())

    m = t0[["portfolio_id", "loan_id", "current_balance"]].merge(
        t1[["portfolio_id", "loan_id", "status", "current_balance"]],
        on=["portfolio_id", "loan_id"], how="left", suffixes=("_0", "_1"))
    m["status"] = m["status"].fillna(STATUS_PREPAID)
    defaults = float(m.loc[m["status"] == STATUS_DEFAULT, "current_balance_0"].sum())
    prepays = float(m.loc[(m["status"] == STATUS_PREPAID) | m["current_balance_1"].isna(),
                          "current_balance_0"].sum())
    surviving = m[m["status"].isin(ACTIVE_STATUSES) & m["current_balance_1"].notna()]
    amort = float((surviving["current_balance_0"] - surviving["current_balance_1"]).sum())

    items = [
        {"name": f"Balance {d0.isoformat()}", "value": start, "kind": "start"},
        {"name": "New Originations", "value": new_orig, "kind": "delta"},
        {"name": "Amortization", "value": -amort, "kind": "delta"},
        {"name": "Prepayments", "value": -prepays, "kind": "delta"},
        {"name": "Defaults", "value": -defaults, "kind": "delta"},
        {"name": f"Balance {d1.isoformat()}", "value": end, "kind": "end"},
    ]
    return {"type": "waterfall", "format": "currency", "items": items}
