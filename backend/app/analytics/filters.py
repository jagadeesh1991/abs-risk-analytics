"""Shared filters and data-loading context for all charts."""
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store
from ..models import Snapshot
from ..schema.canonical import ACTIVE_STATUSES, FICO_BANDS, LTV_BANDS, RATE_BANDS, TERM_BANDS


def band_series(values: pd.Series, bands: list[tuple]) -> pd.Series:
    """Vectorized banding: numeric series -> band labels ('Unknown' for nulls)."""
    edges = [b[0] for b in bands] + [bands[-1][1]]
    labels = [b[2] for b in bands]
    out = pd.cut(pd.to_numeric(values, errors="coerce"), bins=edges,
                 labels=labels, right=False).astype(object)
    return out.where(out.notna(), "Unknown")


def fico_band(values):
    return band_series(values, FICO_BANDS)


def ltv_band(values):
    return band_series(values, LTV_BANDS)


def rate_band(values):
    return band_series(values, RATE_BANDS)


def term_band(values):
    return band_series(values, TERM_BANDS)


def wavg(values: pd.Series, weights: pd.Series) -> float | None:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce").where(v.notna(), 0).fillna(0)
    if w.sum() <= 0:
        return None
    return float(np.average(v.fillna(0), weights=w))


@dataclass
class Filters:
    portfolio_id: int | None = None
    as_of: date | None = None
    asset_class: str | None = None
    vintage: int | None = None
    fico_band: str | None = None
    state: str | None = None


class Ctx:
    """Lazy, filter-aware access to tape data for chart compute functions."""

    def __init__(self, session: Session, filters: Filters):
        self.session = session
        self.filters = filters
        self._snapshots: list[Snapshot] | None = None
        self._current: pd.DataFrame | None = None
        self._history: pd.DataFrame | None = None

    # -- snapshot metadata ------------------------------------------------
    def snapshots(self) -> list[Snapshot]:
        """All snapshots in scope (portfolio filter + as_of cap), sorted by date."""
        if self._snapshots is None:
            q = select(Snapshot).order_by(Snapshot.as_of_date)
            snaps = list(self.session.scalars(q))
            f = self.filters
            if f.portfolio_id is not None:
                snaps = [s for s in snaps if s.portfolio_id == f.portfolio_id]
            if f.as_of is not None:
                snaps = [s for s in snaps if s.as_of_date <= f.as_of]
            self._snapshots = snaps
        return self._snapshots

    def snapshot_dates(self) -> list[date]:
        return sorted({s.as_of_date for s in self.snapshots()})

    # -- row-level filters -------------------------------------------------
    def _apply_row_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        f = self.filters
        if df.empty:
            return df
        if f.asset_class:
            df = df[df["asset_class"] == f.asset_class]
        if f.vintage:
            df = df[pd.to_datetime(df["origination_date"]).dt.year == int(f.vintage)]
        if f.fico_band:
            df = df[fico_band(df["fico"]) == f.fico_band]
        if f.state:
            df = df[df["state"] == f.state]
        return df

    # -- data --------------------------------------------------------------
    def current(self) -> pd.DataFrame:
        """Latest snapshot (per portfolio) at or before the as-of filter."""
        if self._current is None:
            latest: dict[int, Snapshot] = {}
            for s in self.snapshots():
                cur = latest.get(s.portfolio_id)
                if cur is None or s.as_of_date > cur.as_of_date:
                    latest[s.portfolio_id] = s
            frames = [store.load_snapshot(s.portfolio_id, s.as_of_date) for s in latest.values()]
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            self._current = self._apply_row_filters(df)
        return self._current

    def history(self) -> pd.DataFrame:
        """All snapshots in scope concatenated (time series)."""
        if self._history is None:
            frames = [store.load_snapshot(s.portfolio_id, s.as_of_date) for s in self.snapshots()]
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            self._history = self._apply_row_filters(df)
        return self._history

    @staticmethod
    def active(df: pd.DataFrame) -> pd.DataFrame:
        """Only loans still on the books (drop terminal DEFAULT/PREPAID rows)."""
        if df.empty:
            return df
        return df[df["status"].isin(ACTIVE_STATUSES)]


def empty_payload(message: str) -> dict:
    return {"empty": True, "message": message}
