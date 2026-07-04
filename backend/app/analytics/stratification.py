"""Stratification tables: pool cuts by credit/collateral dimensions."""
import pandas as pd

from ..schema.canonical import STATUS_DPD60, STATUS_DPD90
from .filters import Ctx, empty_payload, fico_band, ltv_band, rate_band, term_band, wavg
from .registry import register

_DIMENSIONS = {
    "fico_band": ("FICO Band", lambda df: fico_band(df["fico"])),
    "ltv_band": ("LTV Band", lambda df: ltv_band(df["ltv"])),
    "state": ("State", lambda df: df["state"].fillna("Unknown")),
    "rate_band": ("Rate Band", lambda df: rate_band(df["interest_rate"])),
    "term_band": ("Term Band", lambda df: term_band(df["original_term"])),
    "vintage": ("Vintage", lambda df: pd.to_datetime(df["origination_date"]).dt.year.astype("Int64").astype(str)),
    "asset_class": ("Asset Class", lambda df: df["asset_class"].str.title()),
}

_BAND_ORDERS = {
    "fico_band": ["<580", "580-619", "620-659", "660-699", "700-739", "740+", "Unknown"],
    "ltv_band": ["≤70", "70-80", "80-90", "90-100", ">100", "Unknown"],
    "rate_band": ["<4%", "4-6%", "6-8%", "8-12%", "12%+", "Unknown"],
    "term_band": ["≤36m", "37-60m", "61-84m", "85-180m", ">180m", "Unknown"],
}


@register("strat_table", "Stratification Table", "stratification", "table",
          "Pool cut with weighted averages by the chosen dimension",
          params={"dimension": {
              "label": "Dimension",
              "default": "fico_band",
              "options": [{"value": k, "label": v[0]} for k, v in _DIMENSIONS.items()],
          }})
def strat_table(ctx: Ctx, dimension: str = "fico_band") -> dict:
    if dimension not in _DIMENSIONS:
        dimension = "fico_band"
    label, key_fn = _DIMENSIONS[dimension]
    active = ctx.active(ctx.current())
    if active.empty:
        return empty_payload("No loans match the current filters")

    df = active.copy()
    df["_key"] = key_fn(df)
    total_balance = df["current_balance"].sum()

    rows = []
    for key, grp in df.groupby("_key", dropna=False):
        bal = float(grp["current_balance"].sum())
        d60 = float(grp.loc[grp["status"].isin([STATUS_DPD60, STATUS_DPD90]),
                            "current_balance"].sum())
        rows.append({
            "key": str(key),
            "count": int(len(grp)),
            "balance": bal,
            "pct_pool": bal / total_balance if total_balance > 0 else 0,
            "avg_balance": bal / len(grp) if len(grp) else 0,
            "wac": wavg(grp["interest_rate"], grp["current_balance"]),
            "wa_fico": wavg(grp["fico"], grp["current_balance"]),
            "wa_ltv": wavg(grp["ltv"], grp["current_balance"]),
            "dpd60_pct": d60 / bal if bal > 0 else 0,
        })

    order = _BAND_ORDERS.get(dimension)
    if order:
        rows.sort(key=lambda r: order.index(r["key"]) if r["key"] in order else 99)
    else:
        rows.sort(key=lambda r: r["balance"], reverse=True)

    # totals row
    rows.append({
        "key": "Total",
        "count": int(len(df)),
        "balance": float(total_balance),
        "pct_pool": 1.0,
        "avg_balance": float(total_balance / len(df)) if len(df) else 0,
        "wac": wavg(df["interest_rate"], df["current_balance"]),
        "wa_fico": wavg(df["fico"], df["current_balance"]),
        "wa_ltv": wavg(df["ltv"], df["current_balance"]),
        "dpd60_pct": float(df.loc[df["status"].isin([STATUS_DPD60, STATUS_DPD90]),
                                  "current_balance"].sum() / total_balance) if total_balance > 0 else 0,
    })

    return {
        "type": "table",
        "columns": [
            {"key": "key", "label": label, "format": "text"},
            {"key": "count", "label": "Loans", "format": "number"},
            {"key": "balance", "label": "Balance", "format": "currency"},
            {"key": "pct_pool", "label": "% of Pool", "format": "percent"},
            {"key": "avg_balance", "label": "Avg Balance", "format": "currency"},
            {"key": "wac", "label": "WAC", "format": "percent"},
            {"key": "wa_fico", "label": "WA FICO", "format": "score"},
            {"key": "wa_ltv", "label": "WA LTV", "format": "score"},
            {"key": "dpd60_pct", "label": "60+ DPD %", "format": "percent"},
        ],
        "rows": rows,
    }
