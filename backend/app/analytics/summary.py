"""Overview charts: KPI cards, composition donut, balance trend."""
import pandas as pd

from ..schema.canonical import STATUS_DEFAULT, STATUS_DPD30, STATUS_DPD60, STATUS_DPD90
from .filters import Ctx, empty_payload, wavg
from .registry import register


def _dpd_pct(active: pd.DataFrame, statuses: list[str]) -> float | None:
    total = active["current_balance"].sum()
    if total <= 0:
        return None
    return float(active.loc[active["status"].isin(statuses), "current_balance"].sum() / total)


def _spark_and_pctile(series: "pd.Series", current) -> dict:
    """Trailing sparkline data + percentile rank of the current value in history."""
    vals = series.dropna()
    if len(vals) < 3 or current is None:
        return {}
    return {
        "spark": [round(float(v), 6) for v in vals.tail(12)],
        "pctile": round(float((vals <= current).mean()), 2),
    }


@register("kpi_summary", "Portfolio KPIs", "overview", "kpis",
          "Headline pool metrics with 12-month sparklines and percentile vs own history")
def kpi_summary(ctx: Ctx) -> dict:
    cur = ctx.current()
    if cur.empty:
        return empty_payload("No loans match the current filters")
    active = ctx.active(cur)
    hist = ctx.history()

    # cumulative loss: all defaulted balance observed / original balance of unique loans
    defaults = hist[hist["status"] == STATUS_DEFAULT]
    uniq = hist.drop_duplicates(subset=["portfolio_id", "loan_id"])
    orig_total = uniq["original_balance"].sum()
    cum_loss = float(defaults["current_balance"].sum() / orig_total) if orig_total > 0 else None

    # per-snapshot history of each metric, for sparklines + percentile ranks
    h = ctx.active(hist).copy()
    h["date"] = pd.to_datetime(h["as_of_date"]).dt.date
    monthly = {}
    if not h.empty:
        g = h.groupby("date")
        total = g["current_balance"].sum()
        monthly["balance"] = total
        monthly["count"] = g["loan_id"].count().astype(float)
        for key, statuses in [("dpd30", [STATUS_DPD30, STATUS_DPD60, STATUS_DPD90]),
                              ("dpd60", [STATUS_DPD60, STATUS_DPD90]),
                              ("dpd90", [STATUS_DPD90])]:
            bal = h[h["status"].isin(statuses)].groupby("date")["current_balance"].sum()
            monthly[key] = (bal.reindex(total.index).fillna(0) / total)
        monthly["wac"] = g.apply(lambda x: wavg(x["interest_rate"], x["current_balance"]),
                                 include_groups=False)
        monthly["fico"] = g.apply(lambda x: wavg(x["fico"], x["current_balance"]),
                                  include_groups=False)

    def item(label, value, fmt, spark_key=None):
        d = {"label": label, "value": value, "format": fmt}
        if spark_key and spark_key in monthly:
            d.update(_spark_and_pctile(monthly[spark_key], value))
        return d

    items = [
        item("Active Loans", int(len(active)), "number", "count"),
        item("Current Balance", float(active["current_balance"].sum()), "currency", "balance"),
        item("WAC", wavg(active["interest_rate"], active["current_balance"]), "percent", "wac"),
        item("WA FICO", wavg(active["fico"], active["current_balance"]), "score", "fico"),
        item("30+ DPD", _dpd_pct(active, [STATUS_DPD30, STATUS_DPD60, STATUS_DPD90]),
             "percent", "dpd30"),
        item("60+ DPD", _dpd_pct(active, [STATUS_DPD60, STATUS_DPD90]), "percent", "dpd60"),
        item("90+ DPD", _dpd_pct(active, [STATUS_DPD90]), "percent", "dpd90"),
        item("Cumulative Loss", cum_loss, "percent"),
    ]
    return {"type": "kpis", "items": items}


@register("balance_by_asset_class", "Balance by Asset Class", "overview", "pie",
          "Active balance composition across asset classes")
def balance_by_asset_class(ctx: Ctx) -> dict:
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")
    g = active.groupby("asset_class")["current_balance"].sum().sort_values(ascending=False)
    return {"type": "pie", "format": "currency",
            "items": [{"name": str(k).title(), "value": float(v)} for k, v in g.items()]}


@register("status_composition", "Balance by Delinquency Status", "overview", "pie",
          "Active balance split by delinquency bucket")
def status_composition(ctx: Ctx) -> dict:
    from ..schema.canonical import STATUS_LABELS
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")
    g = active.groupby("status")["current_balance"].sum()
    order = [s for s in STATUS_LABELS if s in g.index]
    return {"type": "pie", "format": "currency",
            "items": [{"name": STATUS_LABELS[s], "value": float(g[s])} for s in order]}


@register("balance_trend", "Portfolio Balance Trend", "overview", "line",
          "Total active balance across reporting periods", needs_history=True)
def balance_trend(ctx: Ctx) -> dict:
    hist = ctx.active(ctx.history())
    if hist.empty:
        return empty_payload("No loans match the current filters")
    g = hist.groupby(pd.to_datetime(hist["as_of_date"]).dt.date)["current_balance"].sum().sort_index()
    if len(g) < 2:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    return {"type": "line", "yFormat": "currency",
            "x": [d.isoformat() for d in g.index],
            "series": [{"name": "Active Balance", "data": [float(v) for v in g.values]}]}
