"""Read raw CSV/XLSX files into DataFrames for preview and import."""
from pathlib import Path

import pandas as pd


def list_sheets(path: Path) -> list[str]:
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xltx"):
        with pd.ExcelFile(path) as xf:
            return [str(s) for s in xf.sheet_names]
    return []


def read_file(path: Path, sheet: str | None = None, header_row: int = 0,
              nrows: int | None = None) -> pd.DataFrame:
    """Read a CSV or Excel file with everything as strings (parsing happens later,
    with proper error reporting, in the normalizer)."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xltx"):
        df = pd.read_excel(path, sheet_name=sheet or 0, header=header_row,
                           nrows=nrows, dtype=str)
    elif suffix in (".csv", ".txt", ".tsv"):
        sep = "\t" if suffix == ".tsv" else None  # None => sniff
        df = pd.read_csv(path, header=header_row, nrows=nrows, dtype=str,
                         sep=sep, engine="python", encoding_errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    df.columns = [str(c).strip() for c in df.columns]
    # drop fully-empty rows and unnamed empty columns
    df = df.dropna(how="all")
    df = df.loc[:, [c for c in df.columns if c and not c.lower().startswith("unnamed:")]]
    return df


def preview(path: Path, sheet: str | None = None, header_row: int = 0,
            rows: int = 50) -> dict:
    df = read_file(path, sheet=sheet, header_row=header_row, nrows=rows)
    return {
        "columns": list(df.columns),
        "rows": df.fillna("").astype(str).values.tolist(),
        "sheets": list_sheets(path),
    }
