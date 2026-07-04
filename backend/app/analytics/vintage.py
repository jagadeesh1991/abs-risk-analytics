"""Vintage & cohort analysis: ghost vintage, lifecycle stack, loss comparisons."""
import numpy as np
import pandas as pd

from ..schema.canonical import (
    FICO_BANDS,
    STATUS_CURRENT,
    STATUS_DEFAULT,
    STATUS_PREPAID,
)
from .filters import Ctx, empty_payload, fico_band
from .performance import vintage_curves
from .registry import register


@register("ghost_vintage", "Ghost Vintage — Latest vs History", "vintage", "line",
          "Every historical cohort faded to grey; the newest cohort highlighted",
          needs_history=True)
def ghost_vintage(ctx: Ctx) -> dict:
    payload = vintage_curves(ctx)
    if payload.get("empty"):
        return payload
    series = payload["series"]
    if len(series) < 2:
        return empty_payload("Needs at least 2 cohorts to compare")
    latest = max(s["name"] for s in series)
    for s in series:
        s["ghost"] = s["name"] != latest
    payload["series"] = sorted(series, key=lambda s: s["ghost"], reverse=True)
    payload["subtitle"] = f"Cohort {latest} highlighted against all prior vintages"
    return payload


@register("cohort_lifecycle", "Cohort Lifecycle Stack", "vintage", "line",
          "Competing risks by months-on-book: performing, delinquent, prepaid, defaulted "
          "(share of original balance, loans originated inside the observation window)",
          needs_history=True)
def cohort_lifecycle(ctx: Ctx) -> dict:
    hist = ctx.history()
    if hist.empty:
        return empty_payload("No loans match the current filters")
    df = hist.copy()
    df["orig"] = pd.to_datetime(df["origination_date"])
    df["asof"] = pd.to_datetime(df["as_of_date"])
    df["mob"] = ((df["asof"].dt.year - df["orig"].dt.year) * 12
                 + (df["asof"].dt.month - df["orig"].dt.month)).clip(lower=0)

    # loans we observe from (near) birth, so early lifecycle isn't censored
    df["_key"] = df["portfolio_id"].astype(str) + "|" + df["loan_id"].astype(str)
    first_mob = df.groupby("_key")["mob"].transform("min")
    df = df[first_mob <= 1]
    if df.empty:
        return empty_payload("No loans originated inside the observed window")

    keys, key_idx = np.unique(df["_key"].to_numpy(), return_inverse=True)
    n = len(keys)
    max_mob = int(df["mob"].max())

    w = np.zeros(n)
    w[key_idx] = df["original_balance"].to_numpy()  # last write wins; static per loan

    # status matrix: -1 unobserved, 0 performing, 1 delinquent
    status_mat = np.full((n, max_mob + 1), -1, dtype=np.int8)
    mob_arr = df["mob"].to_numpy()
    is_current = (df["status"] == STATUS_CURRENT).to_numpy()
    active_mask = ~df["status"].isin([STATUS_DEFAULT, STATUS_PREPAID]).to_numpy()
    status_mat[key_idx[active_mask], mob_arr[active_mask]] = \
        np.where(is_current[active_mask], 0, 1)

    term_mob = np.full(n, np.iinfo(np.int32).max, dtype=np.int64)
    term_default = np.zeros(n, dtype=bool)
    for status, flag in [(STATUS_DEFAULT, True), (STATUS_PREPAID, False)]:
        rows = df[df["status"] == status]
        if rows.empty:
            continue
        idx = key_idx[df["status"].to_numpy() == status]
        term_mob[idx] = rows["mob"].to_numpy()
        term_default[idx] = flag

    x, cur_s, dlq_s, pre_s, def_s = [], [], [], [], []
    total_w = w.sum()
    for m in range(max_mob + 1):
        terminated = term_mob <= m
        defaulted = (terminated & term_default)
        prepaid = (terminated & ~term_default)
        observed = status_mat[:, m] >= 0
        cur = observed & (status_mat[:, m] == 0)
        dlq = observed & (status_mat[:, m] == 1)
        denom = w[cur].sum() + w[dlq].sum() + w[defaulted].sum() + w[prepaid].sum()
        if denom < total_w * 0.05:  # too few loans this deep in — stop the tail
            break
        x.append(m)
        cur_s.append(round(float(w[cur].sum() / denom), 5))
        dlq_s.append(round(float(w[dlq].sum() / denom), 5))
        pre_s.append(round(float(w[prepaid].sum() / denom), 5))
        def_s.append(round(float(w[defaulted].sum() / denom), 5))

    if len(x) < 3:
        return empty_payload("Not enough post-origination history yet")
    return {
        "type": "line", "yFormat": "percent", "xLabel": "Months on book",
        "stacked": True, "area": True, "x": x,
        "series": [
            {"name": "Performing", "data": cur_s},
            {"name": "Delinquent", "data": dlq_s},
            {"name": "Prepaid", "data": pre_s},
            {"name": "Defaulted", "data": def_s},
        ],
    }


def _cohort_loss_by_band(ctx: Ctx) -> pd.DataFrame | None:
    """cohort year × FICO band -> cumulative loss rate."""
    hist = ctx.history()
    if hist.empty:
        return None
    df = hist.copy()
    df["cohort"] = pd.to_datetime(df["origination_date"]).dt.year
    df["_band"] = fico_band(df["fico"])
    uniq = df.drop_duplicates(subset=["portfolio_id", "loan_id"])
    denom = uniq.groupby(["cohort", "_band"])["original_balance"].sum()
    counts = uniq.groupby(["cohort", "_band"])["loan_id"].count()
    defaults = df[df["status"] == STATUS_DEFAULT] \
        .groupby(["cohort", "_band"])["current_balance"].sum()
    out = pd.DataFrame({"denom": denom, "count": counts,
                        "defaults": defaults}).fillna(0.0)
    out["loss"] = np.where(out["denom"] > 0, out["defaults"] / out["denom"], 0.0)
    return out


@register("grouped_loss_by_fico", "Cumulative Loss by FICO Band & Vintage", "vintage", "bar",
          "Observed loss rates across credit bands, one bar group per cohort year",
          needs_history=True)
def grouped_loss_by_fico(ctx: Ctx) -> dict:
    stats = _cohort_loss_by_band(ctx)
    if stats is None or stats.empty:
        return empty_payload("No loans match the current filters")
    bands = [b[2] for b in FICO_BANDS]
    cohorts = sorted(stats.index.get_level_values(0).unique())[-4:]  # last 4 vintages
    series = []
    for cohort in cohorts:
        data = []
        for band in bands:
            row = stats.loc[(cohort, band)] if (cohort, band) in stats.index else None
            data.append(round(float(row["loss"]), 5)
                        if row is not None and row["count"] >= 25 else None)
        if any(v is not None for v in data):
            series.append({"name": str(cohort), "data": data})
    if not series:
        return empty_payload("Not enough loans per FICO band and cohort")
    return {"type": "bar", "yFormat": "percent", "x": bands, "series": series}


@register("distribution_pyramid", "Vintage Mix Pyramid", "vintage", "pyramid",
          "FICO composition of the two most recent cohorts, back to back",
          needs_history=True)
def distribution_pyramid(ctx: Ctx) -> dict:
    hist = ctx.history()
    if hist.empty:
        return empty_payload("No loans match the current filters")
    uniq = hist.drop_duplicates(subset=["portfolio_id", "loan_id"]).copy()
    uniq["cohort"] = pd.to_datetime(uniq["origination_date"]).dt.year
    uniq["_band"] = fico_band(uniq["fico"])
    sizes = uniq.groupby("cohort")["loan_id"].count()
    cohorts = sorted(sizes[sizes >= 100].index)
    if len(cohorts) < 2:
        return empty_payload("Needs two cohorts with at least 100 loans each")
    a, b = cohorts[-2], cohorts[-1]

    bands = [x[2] for x in FICO_BANDS]
    def shares(cohort):
        grp = uniq[uniq["cohort"] == cohort]
        counts = grp.groupby("_band")["loan_id"].count()
        total = counts.sum()
        return [round(float(counts.get(band, 0)) / total, 5) for band in bands]

    return {"type": "pyramid", "format": "percent", "categories": bands,
            "left": {"name": str(a), "data": shares(a)},
            "right": {"name": str(b), "data": shares(b)}}
