"""Canonical loan schema — single source of truth for every field the app understands.

Every tape (uploaded or generated) is normalized to these columns before it is
stored. Analytics only ever see canonical columns.
"""
from dataclasses import dataclass, field


ASSET_CLASSES = ["auto", "mortgage", "consumer"]

# Delinquency status codes, ordered from best to worst. DEFAULT / PREPAID are
# terminal: a loan appears with that status in its final snapshot, then drops
# off the tape.
STATUS_CURRENT = "CURRENT"
STATUS_DPD30 = "DPD30"
STATUS_DPD60 = "DPD60"
STATUS_DPD90 = "DPD90"
STATUS_DEFAULT = "DEFAULT"
STATUS_PREPAID = "PREPAID"
STATUSES = [STATUS_CURRENT, STATUS_DPD30, STATUS_DPD60, STATUS_DPD90, STATUS_DEFAULT, STATUS_PREPAID]
STATUS_LABELS = {
    STATUS_CURRENT: "Current",
    STATUS_DPD30: "30-59 DPD",
    STATUS_DPD60: "60-89 DPD",
    STATUS_DPD90: "90+ DPD",
    STATUS_DEFAULT: "Default",
    STATUS_PREPAID: "Prepaid",
}
ACTIVE_STATUSES = [STATUS_CURRENT, STATUS_DPD30, STATUS_DPD60, STATUS_DPD90]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    dtype: str  # "str" | "float" | "int" | "date"
    required: bool = False
    label: str = ""
    description: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    asset_classes: tuple[str, ...] = ()  # empty = applies to all


FIELDS: list[FieldSpec] = [
    FieldSpec("loan_id", "str", True, "Loan ID", "Unique loan identifier within a snapshot",
              ("loanid", "loan_number", "loan_no", "account_id", "account_number", "acct_id", "id", "loan")),
    FieldSpec("as_of_date", "date", False, "As-of Date",
              "Snapshot/reporting date; may instead be supplied once for the whole file",
              ("asof", "as_of", "report_date", "reporting_date", "cutoff_date", "snapshot_date", "period")),
    FieldSpec("asset_class", "str", False, "Asset Class",
              "auto / mortgage / consumer; may instead be supplied once for the whole file",
              ("asset_type", "product", "product_type", "loan_type", "collateral_class")),
    FieldSpec("origination_date", "date", True, "Origination Date", "Date the loan was originated",
              ("orig_date", "origination", "orig_dt", "funding_date", "note_date", "issue_date", "open_date")),
    FieldSpec("original_balance", "float", True, "Original Balance", "Balance at origination",
              ("orig_balance", "orig_bal", "original_amount", "orig_amount", "loan_amount", "original_upb",
               "orig_upb", "funded_amount", "note_amount")),
    FieldSpec("current_balance", "float", True, "Current Balance", "Outstanding principal balance as of the snapshot",
              ("curr_balance", "current_bal", "curr_bal", "balance", "upb", "current_upb", "outstanding_balance",
               "principal_balance", "unpaid_balance")),
    FieldSpec("interest_rate", "float", False, "Interest Rate", "Note rate (stored as a decimal, e.g. 0.0625)",
              ("rate", "int_rate", "note_rate", "coupon", "apr", "wac")),
    FieldSpec("original_term", "int", False, "Original Term", "Original term in months",
              ("term", "orig_term", "loan_term", "term_months", "original_term_months")),
    FieldSpec("remaining_term", "int", False, "Remaining Term", "Remaining term in months",
              ("rem_term", "remaining_months", "months_remaining", "rmg_term")),
    FieldSpec("fico", "float", False, "FICO", "Borrower credit score",
              ("fico_score", "credit_score", "score", "cscore", "borrower_fico", "orig_fico")),
    FieldSpec("dpd", "int", False, "Days Past Due", "Days past due as of the snapshot; derived from status if absent",
              ("days_past_due", "days_delinquent", "dlq_days", "delinquency_days", "past_due_days")),
    FieldSpec("status", "str", False, "Status",
              "Delinquency status (current / 30 / 60 / 90+ / default / prepaid); derived from DPD if absent",
              ("loan_status", "delinquency_status", "dlq_status", "payment_status", "account_status", "state_code")),
    FieldSpec("state", "str", False, "State", "US state (2-letter code or full name)",
              ("borrower_state", "property_state", "st", "geo_state", "obligor_state", "state_name")),
    FieldSpec("monthly_payment", "float", False, "Monthly Payment", "Scheduled monthly payment",
              ("payment", "pmt", "scheduled_payment", "monthly_pmt", "installment")),
    # Asset-class specific
    FieldSpec("ltv", "float", False, "LTV", "Loan-to-value ratio in percent (e.g. 85)",
              ("loan_to_value", "ltv_ratio", "orig_ltv", "cltv", "original_ltv"),
              ("auto", "mortgage")),
    FieldSpec("dti", "float", False, "DTI", "Debt-to-income ratio in percent",
              ("debt_to_income", "dti_ratio", "orig_dti"),
              ("mortgage", "consumer")),
    FieldSpec("property_type", "str", False, "Property Type", "Property type (SFR, condo, ...)",
              ("prop_type", "property"), ("mortgage",)),
    FieldSpec("lien_position", "int", False, "Lien Position", "1 = first lien",
              ("lien", "lien_pos"), ("mortgage",)),
    FieldSpec("vehicle_new_used", "str", False, "New/Used", "Whether the vehicle was new or used",
              ("new_used", "vehicle_condition", "new_or_used"), ("auto",)),
    FieldSpec("vehicle_type", "str", False, "Vehicle Type", "Car, SUV, truck, ...",
              ("veh_type", "collateral_type"), ("auto",)),
    FieldSpec("loan_purpose", "str", False, "Loan Purpose", "Purpose of the loan",
              ("purpose",), ("consumer",)),
]

FIELD_MAP = {f.name: f for f in FIELDS}
REQUIRED_FIELDS = [f.name for f in FIELDS if f.required]
ALL_FIELD_NAMES = [f.name for f in FIELDS]

# ---------------------------------------------------------------------------
# Shared banding helpers (used by analytics and the sample generator)
# ---------------------------------------------------------------------------

FICO_BANDS = [(0, 580, "<580"), (580, 620, "580-619"), (620, 660, "620-659"),
              (660, 700, "660-699"), (700, 740, "700-739"), (740, 9999, "740+")]
LTV_BANDS = [(0, 70, "≤70"), (70, 80, "70-80"), (80, 90, "80-90"),
             (90, 100, "90-100"), (100, 9999, ">100")]
RATE_BANDS = [(0, 0.04, "<4%"), (0.04, 0.06, "4-6%"), (0.06, 0.08, "6-8%"),
              (0.08, 0.12, "8-12%"), (0.12, 99, "12%+")]
TERM_BANDS = [(0, 37, "≤36m"), (37, 61, "37-60m"), (61, 85, "61-84m"),
              (85, 181, "85-180m"), (181, 9999, ">180m")]


def band_label(value, bands):
    if value is None:
        return "Unknown"
    for lo, hi, label in bands:
        if lo <= value < hi:
            return label
    return "Unknown"


def status_from_dpd(dpd: float | None) -> str:
    if dpd is None:
        return STATUS_CURRENT
    if dpd >= 90:
        return STATUS_DPD90
    if dpd >= 60:
        return STATUS_DPD60
    if dpd >= 30:
        return STATUS_DPD30
    return STATUS_CURRENT


def field_specs_json() -> list[dict]:
    """Schema description served to the frontend (mapping UI)."""
    return [
        {
            "name": f.name,
            "label": f.label or f.name,
            "dtype": f.dtype,
            "required": f.required,
            "description": f.description,
            "asset_classes": list(f.asset_classes) or ASSET_CLASSES,
        }
        for f in FIELDS
    ]
