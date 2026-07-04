"""Risk surfaces: default rates across the FICO × LTV credit box."""
from ..schema.canonical import FICO_BANDS, LTV_BANDS, STATUS_DEFAULT
from .filters import Ctx, empty_payload, fico_band, ltv_band
from .registry import register


@register("loss_surface", "Loss Surface — FICO × LTV", "performance", "heatmap",
          "Observed default rate across the credit box (defaulted balance / original balance)",
          needs_history=True)
def loss_surface(ctx: Ctx) -> dict:
    hist = ctx.history()
    if hist.empty:
        return empty_payload("No loans match the current filters")
    if hist["ltv"].isna().all():
        return empty_payload("The selected loans have no LTV data")

    df = hist.copy()
    df["_fico"] = fico_band(df["fico"])
    df["_ltv"] = ltv_band(df["ltv"])

    uniq = df.drop_duplicates(subset=["portfolio_id", "loan_id"])
    denom = uniq.groupby(["_fico", "_ltv"])["original_balance"].sum()
    counts = uniq.groupby(["_fico", "_ltv"])["loan_id"].count()
    defaults = df[df["status"] == STATUS_DEFAULT] \
        .groupby(["_fico", "_ltv"])["current_balance"].sum()

    y_labels = [b[2] for b in FICO_BANDS]
    x_labels = [b[2] for b in LTV_BANDS]
    cells = []
    for yi, fb in enumerate(y_labels):
        for xi, lb in enumerate(x_labels):
            n = counts.get((fb, lb), 0)
            d = denom.get((fb, lb), 0.0)
            if n < 25 or d <= 0:
                continue  # too sparse to be meaningful
            loss = float(defaults.get((fb, lb), 0.0)) / float(d)
            cells.append([xi, yi, round(loss, 5)])
    if not cells:
        return empty_payload("Not enough loans per FICO × LTV cell")

    return {"type": "heatmap", "format": "percent",
            "xLabels": x_labels, "yLabels": y_labels, "cells": cells,
            "subtitle": "Cells with fewer than 25 loans are hidden"}
