"""Issuer / portfolio comparison charts. Most useful with the portfolio
filter set to "All portfolios"."""
import pandas as pd
from sqlalchemy import select

from ..models import Portfolio
from ..schema.canonical import STATUS_DEFAULT, STATUS_DPD30, STATUS_DPD60, STATUS_DPD90
from .filters import Ctx, empty_payload, wavg
from .registry import register


def _portfolio_names(ctx: Ctx) -> dict[int, str]:
    return {p.id: p.name for p in ctx.session.scalars(select(Portfolio))}


def _portfolio_metrics(ctx: Ctx) -> list[dict]:
    """Per-portfolio pool metrics from the current snapshot + loss from history."""
    current = ctx.current()
    if current.empty:
        return []
    hist = ctx.history()
    names = _portfolio_names(ctx)

    out = []
    for pid, grp in current.groupby("portfolio_id"):
        active = ctx.active(grp)
        if active.empty:
            continue
        bal = active["current_balance"].sum()
        d30p = active.loc[active["status"].isin(
            [STATUS_DPD30, STATUS_DPD60, STATUS_DPD90]), "current_balance"].sum()
        d60p = active.loc[active["status"].isin(
            [STATUS_DPD60, STATUS_DPD90]), "current_balance"].sum()
        h = hist[hist["portfolio_id"] == pid]
        uniq = h.drop_duplicates(subset=["loan_id"])
        orig_total = uniq["original_balance"].sum()
        cum_loss = (h.loc[h["status"] == STATUS_DEFAULT, "current_balance"].sum()
                    / orig_total) if orig_total > 0 else 0.0
        out.append({
            "portfolio_id": int(pid),
            "name": names.get(int(pid), f"Portfolio {pid}"),
            "asset_class": str(active["asset_class"].mode().iat[0]).title()
            if active["asset_class"].notna().any() else "—",
            "loans": int(len(active)),
            "balance": float(bal),
            "avg_balance": float(bal / len(active)),
            "wac": wavg(active["interest_rate"], active["current_balance"]),
            "wa_fico": wavg(active["fico"], active["current_balance"]),
            "dpd30_pct": float(d30p / bal) if bal > 0 else 0.0,
            "dpd60_pct": float(d60p / bal) if bal > 0 else 0.0,
            "cum_loss": float(cum_loss),
        })
    out.sort(key=lambda r: r["balance"], reverse=True)
    return out


@register("issuer_matrix", "Portfolio Comparison Matrix", "comparison", "table",
          "Side-by-side pool metrics for every portfolio")
def issuer_matrix(ctx: Ctx) -> dict:
    rows = _portfolio_metrics(ctx)
    if not rows:
        return empty_payload("No loans match the current filters")
    return {
        "type": "table",
        "columns": [
            {"key": "name", "label": "Portfolio", "format": "text"},
            {"key": "asset_class", "label": "Asset Class", "format": "text"},
            {"key": "loans", "label": "Loans", "format": "number"},
            {"key": "balance", "label": "Balance", "format": "currency"},
            {"key": "avg_balance", "label": "Avg Balance", "format": "currency"},
            {"key": "wac", "label": "WAC", "format": "percent"},
            {"key": "wa_fico", "label": "WA FICO", "format": "score"},
            {"key": "dpd30_pct", "label": "30+ DPD", "format": "percent"},
            {"key": "dpd60_pct", "label": "60+ DPD", "format": "percent"},
            {"key": "cum_loss", "label": "Cum Loss", "format": "percent"},
        ],
        "rows": rows,
    }


@register("issuer_radar", "Risk Profile Radar", "comparison", "radar",
          "Multi-dimensional risk comparison across portfolios (larger = more of that attribute)")
def issuer_radar(ctx: Ctx) -> dict:
    rows = _portfolio_metrics(ctx)
    if len(rows) < 2:
        return empty_payload("Needs at least 2 portfolios — set the portfolio filter to All")
    metrics = [
        ("WAC", "wac", 100),
        ("30+ DPD", "dpd30_pct", 100),
        ("60+ DPD", "dpd60_pct", 100),
        ("Cum Loss", "cum_loss", 100),
        ("WA FICO", "wa_fico", 1),
    ]
    indicators = []
    for label, key, scale in metrics:
        peak = max((r[key] or 0) * scale for r in rows)
        indicators.append({"name": label, "max": round(peak * 1.15, 4) or 1})
    series = [{"name": r["name"],
               "values": [round((r[key] or 0) * scale, 4) for _, key, scale in metrics]}
              for r in rows]
    return {"type": "radar", "indicators": indicators, "series": series}


@register("issuer_rank", "60+ DPD Ranking", "comparison", "bar",
          "Portfolios ranked by serious delinquency")
def issuer_rank(ctx: Ctx) -> dict:
    rows = _portfolio_metrics(ctx)
    if not rows:
        return empty_payload("No loans match the current filters")
    rows.sort(key=lambda r: r["dpd60_pct"], reverse=True)
    return {"type": "bar", "yFormat": "percent",
            "x": [r["name"] for r in rows],
            "series": [{"name": "60+ DPD %", "data": [round(r["dpd60_pct"], 5) for r in rows]}]}


@register("issuer_trend", "Delinquency Trend by Portfolio", "comparison", "line",
          "60+ DPD share of balance over time, one line per portfolio", needs_history=True)
def issuer_trend(ctx: Ctx) -> dict:
    hist = ctx.active(ctx.history())
    if hist.empty:
        return empty_payload("No loans match the current filters")
    hist = hist.copy()
    hist["date"] = pd.to_datetime(hist["as_of_date"]).dt.date
    names = _portfolio_names(ctx)

    dates = sorted(hist["date"].unique())
    if len(dates) < 2:
        return empty_payload("Needs at least 2 snapshots — upload more reporting periods")
    series = []
    for pid, grp in hist.groupby("portfolio_id"):
        totals = grp.groupby("date")["current_balance"].sum()
        bad = grp[grp["status"].isin([STATUS_DPD60, STATUS_DPD90])] \
            .groupby("date")["current_balance"].sum()
        pct = (bad.reindex(totals.index).fillna(0) / totals)
        aligned = pct.reindex(dates)
        series.append({"name": names.get(int(pid), f"Portfolio {pid}"),
                       "data": [None if pd.isna(v) else round(float(v), 5) for v in aligned]})
    return {"type": "line", "yFormat": "percent",
            "x": [d.isoformat() for d in dates], "series": series}
