"""Validate a normalized tape before import. Errors block, warnings don't."""
import pandas as pd

from ..schema.canonical import REQUIRED_FIELDS


def validate(df: pd.DataFrame, issues: list[dict]) -> dict:
    """Return a validation report: {ok, errors, warnings, row_count, total_balance}."""
    errors: list[dict] = []
    warnings: list[dict] = [i for i in issues if i["kind"] == "warning"]
    errors += [i for i in issues if i["kind"] == "error"]

    for field in REQUIRED_FIELDS:
        if field not in df.columns or df[field].isna().all():
            errors.append({"field": field, "kind": "error",
                           "message": f"Required field '{field}' is not mapped or has no valid values",
                           "count": len(df), "sample_rows": []})
        else:
            missing = df[field].isna()
            if missing.any():
                errors.append({"field": field, "kind": "error",
                               "message": f"{int(missing.sum())} row(s) missing required '{field}'",
                               "count": int(missing.sum()),
                               "sample_rows": [int(i) + 2 for i in df.index[missing][:5]]})

    if "as_of_date" not in df.columns or df["as_of_date"].isna().all():
        errors.append({"field": "as_of_date", "kind": "error",
                       "message": "No as-of date: map a column or set one for the whole file",
                       "count": len(df), "sample_rows": []})

    if "loan_id" in df.columns:
        dupes = df["loan_id"].dropna().duplicated()
        if dupes.any():
            sample = df["loan_id"].dropna()[dupes].head(3).tolist()
            errors.append({"field": "loan_id", "kind": "error",
                           "message": f"{int(dupes.sum())} duplicate loan_id(s) within the snapshot "
                                      f"(e.g. {', '.join(map(str, sample))})",
                           "count": int(dupes.sum()), "sample_rows": []})

    # sanity warnings
    if "current_balance" in df.columns:
        neg = pd.to_numeric(df["current_balance"], errors="coerce") < 0
        if neg.any():
            warnings.append({"field": "current_balance", "kind": "warning",
                             "message": f"{int(neg.sum())} negative current balance(s)",
                             "count": int(neg.sum()),
                             "sample_rows": [int(i) + 2 for i in df.index[neg][:5]]})
    if "fico" in df.columns:
        f = pd.to_numeric(df["fico"], errors="coerce")
        odd = ((f < 300) | (f > 850)) & f.notna()
        if odd.any():
            warnings.append({"field": "fico", "kind": "warning",
                             "message": f"{int(odd.sum())} FICO value(s) outside 300-850",
                             "count": int(odd.sum()),
                             "sample_rows": [int(i) + 2 for i in df.index[odd][:5]]})

    total_balance = float(pd.to_numeric(df.get("current_balance"), errors="coerce").fillna(0).sum()) \
        if "current_balance" in df.columns else 0.0

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "row_count": int(len(df)),
        "total_balance": total_balance,
    }
