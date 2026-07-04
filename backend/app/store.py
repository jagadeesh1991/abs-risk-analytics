"""Parquet snapshot store. One file per (portfolio, as_of_date).

A tiny mtime-keyed cache avoids re-reading files on every request.
"""
from datetime import date

import pandas as pd

from .config import TAPES_DIR
from .schema.canonical import ALL_FIELD_NAMES

_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def snapshot_path(portfolio_id: int, as_of: date):
    return TAPES_DIR / str(portfolio_id) / f"{as_of.isoformat()}.parquet"


def save_snapshot(portfolio_id: int, as_of: date, df: pd.DataFrame) -> None:
    """Persist a normalized tape. Missing canonical columns are added as nulls."""
    out = df.copy()
    for col in ALL_FIELD_NAMES:
        if col not in out.columns:
            out[col] = None
    out = out[ALL_FIELD_NAMES]
    out["as_of_date"] = pd.to_datetime(as_of)
    path = snapshot_path(portfolio_id, as_of)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)
    _cache.pop(str(path), None)


def load_snapshot(portfolio_id: int, as_of: date) -> pd.DataFrame:
    path = snapshot_path(portfolio_id, as_of)
    key = str(path)
    mtime = path.stat().st_mtime
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    df = pd.read_parquet(path)
    df["portfolio_id"] = portfolio_id
    _cache[key] = (mtime, df)
    return df


def delete_portfolio_data(portfolio_id: int) -> None:
    folder = TAPES_DIR / str(portfolio_id)
    if folder.exists():
        for f in folder.glob("*.parquet"):
            _cache.pop(str(f), None)
            try:
                f.unlink()
            except OSError:
                pass  # transient Windows lock; orphan file is harmless once DB rows are gone
        try:
            folder.rmdir()
        except OSError:
            pass
