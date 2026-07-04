"""Geographic analysis: state-level choropleth metrics."""
from ..schema.canonical import STATUS_DPD60, STATUS_DPD90
from .filters import Ctx, empty_payload, wavg
from .registry import register

_METRICS = {
    "balance": ("Active Balance", "currency"),
    "count": ("Loan Count", "number"),
    "dpd60_pct": ("60+ DPD %", "percent"),
    "wa_fico": ("WA FICO", "score"),
}


@register("geo_states", "Geographic Distribution", "geography", "map",
          "State-level pool metrics",
          params={"metric": {
              "label": "Metric",
              "default": "balance",
              "options": [{"value": k, "label": v[0]} for k, v in _METRICS.items()],
          }})
def geo_states(ctx: Ctx, metric: str = "balance") -> dict:
    if metric not in _METRICS:
        metric = "balance"
    label, fmt = _METRICS[metric]
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")
    df = active[active["state"].notna()]
    if df.empty:
        return empty_payload("The selected loans have no state data")

    data = []
    for state, grp in df.groupby("state"):
        bal = float(grp["current_balance"].sum())
        if metric == "balance":
            value = bal
        elif metric == "count":
            value = int(len(grp))
        elif metric == "dpd60_pct":
            d60 = float(grp.loc[grp["status"].isin([STATUS_DPD60, STATUS_DPD90]),
                                "current_balance"].sum())
            value = d60 / bal if bal > 0 else 0
        else:  # wa_fico
            value = wavg(grp["fico"], grp["current_balance"]) or 0
        data.append({"name": str(state), "value": round(float(value), 6)})

    return {"type": "map", "format": fmt, "metricLabel": label, "data": data}
