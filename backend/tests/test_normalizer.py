from datetime import date

import pandas as pd

from app.ingestion.normalizer import (
    normalize,
    normalize_rate,
    normalize_state,
    parse_dates,
    parse_number,
)
from app.ingestion.validator import validate
from app.schema.autodetect import suggest_mapping


def test_parse_number_handles_currency_strings():
    s = pd.Series(["$1,234.56", "(100)", " 42 ", "", "N/A"])
    out = parse_number(s)
    assert out.tolist()[:3] == [1234.56, -100.0, 42.0]
    assert out[3:].isna().all()


def test_rates_normalized_to_decimals():
    assert normalize_rate(pd.Series(["5.25", "6.75"])).tolist() == [0.0525, 0.0675]
    assert normalize_rate(pd.Series(["0.0525", "0.0675"])).tolist() == [0.0525, 0.0675]


def test_state_names_become_codes():
    out = normalize_state(pd.Series(["Texas", "ca", "NY", "new york", "Atlantis"]))
    assert out.tolist()[:4] == ["TX", "CA", "NY", "NY"]
    assert pd.isna(out.iloc[4])


def test_dates_parse_mixed_and_excel_serials():
    out = parse_dates(pd.Series(["03/15/2024", "2024-06-01", "45123"]))
    assert out.dt.date.tolist() == [date(2024, 3, 15), date(2024, 6, 1), date(2023, 7, 16)]


def test_autodetect_maps_messy_headers():
    cols = ["Loan Number", "Orig Dt", "Curr UPB", "Note Rate (%)", "Credit Score",
            "Days Delinquent", "Borrower State", "Original Amount"]
    m = suggest_mapping(cols)
    assert m["Loan Number"] == "loan_id"
    assert m["Orig Dt"] == "origination_date"
    assert m["Curr UPB"] == "current_balance"
    assert m["Note Rate (%)"] == "interest_rate"
    assert m["Credit Score"] == "fico"
    assert m["Days Delinquent"] == "dpd"
    assert m["Borrower State"] == "state"
    assert m["Original Amount"] == "original_balance"


def _raw_tape():
    return pd.DataFrame({
        "id": ["A1", "A2"],
        "orig": ["01/10/2024", "02/20/2024"],
        "orig_amt": ["$10,000", "$20,000"],
        "bal": ["$9,000", "$18,000"],
        "days_late": ["0", "65"],
    })


_MAPPING = {"id": "loan_id", "orig": "origination_date", "orig_amt": "original_balance",
            "bal": "current_balance", "days_late": "dpd"}


def test_normalize_derives_status_from_dpd():
    df, issues = normalize(_raw_tape(), _MAPPING, default_as_of=date(2026, 6, 30),
                           default_asset_class="auto")
    assert df["status"].tolist() == ["CURRENT", "DPD60"]
    report = validate(df, issues)
    assert report["ok"], report["errors"]
    assert report["row_count"] == 2
    assert report["total_balance"] == 27000.0


def test_validator_catches_duplicates_and_missing_required():
    raw = _raw_tape()
    raw.loc[1, "id"] = "A1"  # duplicate loan id
    df, issues = normalize(raw, _MAPPING, default_as_of=date(2026, 6, 30))
    report = validate(df, issues)
    assert not report["ok"]
    assert any("duplicate" in e["message"].lower() for e in report["errors"])

    df2, issues2 = normalize(_raw_tape(), {k: v for k, v in _MAPPING.items() if v != "loan_id"},
                             default_as_of=date(2026, 6, 30))
    report2 = validate(df2, issues2)
    assert not report2["ok"]
    assert any(e["field"] == "loan_id" for e in report2["errors"])
