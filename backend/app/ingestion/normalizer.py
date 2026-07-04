"""Turn a raw (all-string) DataFrame + column mapping into a canonical tape.

All unit/format quirks are absorbed here: $1,234.56 strings, percent-vs-decimal
rates, full state names, Excel serial dates, statuses in many spellings.
"""
import re
from datetime import date

import numpy as np
import pandas as pd

from ..schema.canonical import (
    FIELD_MAP,
    STATUS_CURRENT,
    STATUS_DEFAULT,
    STATUS_DPD30,
    STATUS_DPD60,
    STATUS_DPD90,
    STATUS_PREPAID,
    STATUSES,
)

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR",
}
STATE_CODES = set(US_STATES.values())

_STATUS_SYNONYMS = {
    STATUS_CURRENT: ["current", "c", "performing", "0", "ok", "active", "curr"],
    STATUS_DPD30: ["30", "30-59", "30dpd", "dpd30", "30 days", "delinquent 30", "1 month", "d30", "late30"],
    STATUS_DPD60: ["60", "60-89", "60dpd", "dpd60", "60 days", "delinquent 60", "2 months", "d60", "late60"],
    STATUS_DPD90: ["90", "90+", "90dpd", "dpd90", "90 days", "delinquent 90", "3 months", "d90",
                   "seriously delinquent", "120", "150", "late90"],
    STATUS_DEFAULT: ["default", "chargeoff", "charge-off", "charged off", "co", "loss", "defaulted",
                     "liquidated", "repossession", "repo", "foreclosure", "reo", "writeoff"],
    STATUS_PREPAID: ["prepaid", "paid off", "paidoff", "paid in full", "pif", "closed", "matured",
                     "payoff", "prepayment"],
}


def parse_number(series: pd.Series) -> pd.Series:
    """Parse numbers that may carry $, commas, %, or parentheses-negatives."""
    s = series.astype(str).str.strip()
    s = s.str.replace(r"[\$,%\s]", "", regex=True)
    s = s.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    s = s.replace({"": None, "nan": None, "None": None, "-": None, "N/A": None, "n/a": None, "NA": None})
    return pd.to_numeric(s, errors="coerce")


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse dates in common formats, including Excel serial numbers."""
    s = series.astype(str).str.strip().replace(
        {"": None, "nan": None, "None": None, "NaT": None})
    parsed = pd.to_datetime(s, errors="coerce", format="mixed")
    # Excel serial dates (e.g. "45123")
    mask = parsed.isna() & s.notna() & s.str.fullmatch(r"\d{4,6}(\.0)?").fillna(False)
    if mask.any():
        serials = pd.to_numeric(s[mask], errors="coerce")
        parsed.loc[mask] = pd.to_datetime("1899-12-30") + pd.to_timedelta(serials, unit="D")
    return parsed


def normalize_rate(series: pd.Series) -> pd.Series:
    """Store rates as decimals: 6.25 -> 0.0625, 0.0625 stays."""
    vals = parse_number(series)
    med = vals.dropna().median()
    if med is not None and not np.isnan(med) and med > 1.0:
        vals = vals / 100.0
    return vals


def normalize_ltv_dti(series: pd.Series) -> pd.Series:
    """Store LTV/DTI as percent numbers: 0.85 -> 85, 85 stays."""
    vals = parse_number(series)
    med = vals.dropna().median()
    if med is not None and not np.isnan(med) and med <= 1.5:
        vals = vals * 100.0
    return vals


def normalize_state(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    out = s.str.upper().where(s.str.upper().isin(STATE_CODES))
    lower = s.str.lower().str.replace(r"\s+", " ", regex=True)
    out = out.fillna(lower.map(US_STATES))
    return out


def normalize_status(series: pd.Series) -> pd.Series:
    lookup: dict[str, str] = {}
    for code, words in _STATUS_SYNONYMS.items():
        lookup[code.lower()] = code
        for w in words:
            lookup[w] = code
    s = series.astype(str).str.strip().str.lower()
    s = s.str.replace(r"\s+", " ", regex=True)
    out = s.map(lookup)
    # numeric strings like "45" -> bucket by value
    nums = pd.to_numeric(s, errors="coerce")
    out = out.fillna(pd.cut(nums, bins=[-1, 29, 59, 89, 100000],
                            labels=[STATUS_CURRENT, STATUS_DPD30, STATUS_DPD60, STATUS_DPD90]).astype(object))
    return out


def dpd_to_status(dpd: pd.Series) -> pd.Series:
    return pd.cut(dpd.fillna(0), bins=[-1, 29, 59, 89, 10_000_000],
                  labels=[STATUS_CURRENT, STATUS_DPD30, STATUS_DPD60, STATUS_DPD90]).astype(object)


_STATUS_MID_DPD = {STATUS_CURRENT: 0, STATUS_DPD30: 45, STATUS_DPD60: 75,
                   STATUS_DPD90: 120, STATUS_DEFAULT: 180, STATUS_PREPAID: 0}


def normalize(raw: pd.DataFrame, mapping: dict[str, str],
              default_as_of: date | None = None,
              default_asset_class: str | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Apply a {file_column: canonical_field} mapping and coerce every field.

    Returns (canonical_df, issues). Issues are dicts:
      {field, kind: "error"|"warning", message, count, sample_rows}
    Rows are NOT dropped here; the validator decides what is fatal.
    """
    issues: list[dict] = []
    df = pd.DataFrame(index=raw.index)

    def _coerce(field_name: str, series: pd.Series) -> pd.Series:
        spec = FIELD_MAP[field_name]
        if field_name == "interest_rate":
            return normalize_rate(series)
        if field_name in ("ltv", "dti"):
            return normalize_ltv_dti(series)
        if field_name == "state":
            return normalize_state(series)
        if field_name == "status":
            return normalize_status(series)
        if spec.dtype == "date":
            return parse_dates(series)
        if spec.dtype in ("float", "int"):
            return parse_number(series)
        return series.astype(str).str.strip().replace({"nan": None, "": None, "None": None})

    for file_col, field_name in mapping.items():
        if field_name not in FIELD_MAP or file_col not in raw.columns:
            continue
        before = raw[file_col]
        coerced = _coerce(field_name, before)
        df[field_name] = coerced
        # report values that were present but failed to parse
        had_value = before.notna() & (before.astype(str).str.strip() != "")
        bad = had_value & coerced.isna()
        if bad.any():
            rows = [int(i) + 2 for i in raw.index[bad][:5]]  # +2: header + 1-based
            issues.append({
                "field": field_name, "kind": "warning",
                "message": f"{int(bad.sum())} value(s) could not be parsed as {FIELD_MAP[field_name].dtype}",
                "count": int(bad.sum()), "sample_rows": rows,
            })

    if "as_of_date" not in df.columns or df["as_of_date"].isna().all():
        if default_as_of is not None:
            df["as_of_date"] = pd.to_datetime(default_as_of)
    if "asset_class" not in df.columns and default_asset_class:
        df["asset_class"] = default_asset_class

    # derive status <-> dpd
    if "status" not in df.columns or df.get("status") is None or df["status"].isna().all():
        if "dpd" in df.columns:
            df["status"] = dpd_to_status(df["dpd"])
        else:
            df["status"] = STATUS_CURRENT
            issues.append({"field": "status", "kind": "warning",
                           "message": "No status or DPD column mapped — all loans assumed Current",
                           "count": len(df), "sample_rows": []})
    else:
        unmapped = df["status"].isna()
        if "dpd" in df.columns and unmapped.any():
            df.loc[unmapped, "status"] = dpd_to_status(df.loc[unmapped, "dpd"])
        df["status"] = df["status"].fillna(STATUS_CURRENT)
    if "dpd" not in df.columns:
        df["dpd"] = df["status"].map(_STATUS_MID_DPD)
    else:
        df["dpd"] = df["dpd"].fillna(df["status"].map(_STATUS_MID_DPD))

    bad_status = ~df["status"].isin(STATUSES)
    if bad_status.any():
        df.loc[bad_status, "status"] = STATUS_CURRENT

    # int-typed fields
    for f in ("original_term", "remaining_term", "lien_position", "dpd"):
        if f in df.columns:
            df[f] = pd.to_numeric(df[f], errors="coerce").round().astype("Int64")

    return df, issues
