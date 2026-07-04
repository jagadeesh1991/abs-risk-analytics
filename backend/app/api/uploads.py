"""Upload flow: file -> preview -> mapping -> validate -> import."""
import json
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import store
from ..config import UPLOADS_DIR
from ..db import get_session
from ..ingestion import parser
from ..ingestion.normalizer import normalize
from ..ingestion.validator import validate
from ..models import ColumnMapping, Portfolio, Snapshot
from ..schema.autodetect import suggest_mapping
from ..schema.canonical import field_specs_json

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {".csv", ".txt", ".tsv", ".xlsx", ".xlsm", ".xltx"}


def _upload_path(upload_id: str) -> Path:
    matches = list(UPLOADS_DIR.glob(f"{upload_id}.*"))
    if not matches:
        raise HTTPException(404, "Upload not found — it may have been cleaned up; re-upload the file")
    return matches[0]


@router.get("/schema")
def canonical_schema():
    return field_specs_json()


_TEMPLATE_ROWS = [
    {"loan_id": "LN-000001", "as_of_date": "2026-06-30", "asset_class": "auto",
     "origination_date": "2025-03-15", "original_balance": 32000, "current_balance": 29450.10,
     "interest_rate": 0.0679, "original_term": 72, "remaining_term": 57, "fico": 689,
     "dpd": 0, "status": "CURRENT", "state": "TX", "monthly_payment": 545.12,
     "ltv": 95.0, "vehicle_new_used": "Used", "vehicle_type": "SUV"},
    {"loan_id": "LN-000002", "as_of_date": "2026-06-30", "asset_class": "mortgage",
     "origination_date": "2023-08-01", "original_balance": 385000, "current_balance": 362104.55,
     "interest_rate": 0.0525, "original_term": 360, "remaining_term": 325, "fico": 741,
     "dpd": 45, "status": "DPD30", "state": "CA", "monthly_payment": 2126.44,
     "ltv": 78.5, "dti": 36.2, "property_type": "SFR", "lien_position": 1},
    {"loan_id": "LN-000003", "as_of_date": "2026-06-30", "asset_class": "consumer",
     "origination_date": "2024-11-20", "original_balance": 15000, "current_balance": 11890.72,
     "interest_rate": 0.1149, "original_term": 48, "remaining_term": 29, "fico": 665,
     "dpd": 0, "status": "CURRENT", "state": "FL", "monthly_payment": 391.55,
     "dti": 28.4, "loan_purpose": "Debt Consolidation"},
]


@router.get("/template")
def template_csv():
    """Blank loan tape template: canonical headers + one example row per asset class."""
    import pandas as pd

    from fastapi.responses import Response

    from ..schema.canonical import ALL_FIELD_NAMES

    df = pd.DataFrame(_TEMPLATE_ROWS)
    for col in ALL_FIELD_NAMES:
        if col not in df.columns:
            df[col] = None
    df = df[ALL_FIELD_NAMES]
    return Response(
        df.to_csv(index=False),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="loan_tape_template.csv"'},
    )


@router.post("")
async def upload_file(file: UploadFile, session: Session = Depends(get_session)):
    ext = Path(file.filename or "upload.csv").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Use CSV or Excel.")
    upload_id = uuid.uuid4().hex[:12]
    dest = UPLOADS_DIR / f"{upload_id}{ext}"
    content = await file.read()
    dest.write_bytes(content)

    try:
        pv = parser.preview(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read the file: {e}")

    return {
        "upload_id": upload_id,
        "filename": file.filename,
        "sheets": pv["sheets"],
        "columns": pv["columns"],
        "rows": pv["rows"],
        "suggested_mapping": suggest_mapping(pv["columns"]),
    }


class PreviewBody(BaseModel):
    sheet: str | None = None
    header_row: int = 0


@router.post("/{upload_id}/preview")
def re_preview(upload_id: str, body: PreviewBody):
    path = _upload_path(upload_id)
    try:
        pv = parser.preview(path, sheet=body.sheet, header_row=body.header_row)
    except Exception as e:
        raise HTTPException(400, f"Could not read the file with those settings: {e}")
    return {
        "columns": pv["columns"],
        "rows": pv["rows"],
        "sheets": pv["sheets"],
        "suggested_mapping": suggest_mapping(pv["columns"]),
    }


class ImportBody(BaseModel):
    mapping: dict[str, str]              # {file_column: canonical_field}
    sheet: str | None = None
    header_row: int = 0
    as_of_date: date | None = None       # used when no as_of column is mapped
    portfolio_id: int | None = None
    new_portfolio_name: str | None = None
    new_portfolio_asset_class: str | None = None
    asset_class: str | None = None       # default asset class for rows


def _load_and_normalize(upload_id: str, body: ImportBody):
    path = _upload_path(upload_id)
    raw = parser.read_file(path, sheet=body.sheet, header_row=body.header_row)
    df, issues = normalize(raw, body.mapping, default_as_of=body.as_of_date,
                           default_asset_class=body.asset_class)
    return path, df, issues


@router.post("/{upload_id}/validate")
def validate_upload(upload_id: str, body: ImportBody):
    _, df, issues = _load_and_normalize(upload_id, body)
    return validate(df, issues)


@router.post("/{upload_id}/import")
def import_upload(upload_id: str, body: ImportBody,
                  session: Session = Depends(get_session)):
    path, df, issues = _load_and_normalize(upload_id, body)
    report = validate(df, issues)
    if not report["ok"]:
        raise HTTPException(422, "Validation failed — fix the errors before importing")

    if body.portfolio_id is not None:
        portfolio = session.get(Portfolio, body.portfolio_id)
        if not portfolio:
            raise HTTPException(404, "Portfolio not found")
    else:
        name = (body.new_portfolio_name or "").strip()
        if not name:
            raise HTTPException(400, "Provide portfolio_id or new_portfolio_name")
        if session.query(Portfolio).filter_by(name=name).first():
            raise HTTPException(409, f"Portfolio '{name}' already exists")
        portfolio = Portfolio(name=name,
                              asset_class=body.new_portfolio_asset_class or body.asset_class or "mixed")
        session.add(portfolio)
        session.commit()

    import pandas as pd
    as_of_values = pd.to_datetime(df["as_of_date"]).dt.date
    imported = []
    for as_of, grp in df.groupby(as_of_values):
        existing = (session.query(Snapshot)
                    .filter_by(portfolio_id=portfolio.id, as_of_date=as_of).first())
        if existing:
            session.delete(existing)
            session.commit()
        store.save_snapshot(portfolio.id, as_of, grp.reset_index(drop=True))
        session.add(Snapshot(
            portfolio_id=portfolio.id, as_of_date=as_of,
            row_count=int(len(grp)),
            total_balance=float(pd.to_numeric(grp["current_balance"], errors="coerce").fillna(0).sum()),
            source_filename=path.name,
        ))
        imported.append({"as_of_date": as_of.isoformat(), "rows": int(len(grp))})
    session.add(ColumnMapping(portfolio_id=portfolio.id, mapping_json=json.dumps(body.mapping)))
    session.commit()

    return {"ok": True, "portfolio_id": portfolio.id, "portfolio_name": portfolio.name,
            "snapshots": imported}


@router.get("/mappings/{portfolio_id}")
def saved_mapping(portfolio_id: int, session: Session = Depends(get_session)):
    row = (session.query(ColumnMapping).filter_by(portfolio_id=portfolio_id)
           .order_by(ColumnMapping.id.desc()).first())
    return {"mapping": json.loads(row.mapping_json) if row else None}
