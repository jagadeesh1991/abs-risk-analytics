"""ORM models for portfolio/snapshot metadata."""
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    asset_class: Mapped[str] = mapped_column(String(50))  # auto | mortgage | consumer | mixed
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    snapshots: Mapped[list["Snapshot"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("portfolio_id", "as_of_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    as_of_date: Mapped[date] = mapped_column(Date)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    total_balance: Mapped[float] = mapped_column(Float, default=0.0)
    source_filename: Mapped[str] = mapped_column(String(400), default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    portfolio: Mapped[Portfolio] = relationship(back_populates="snapshots")


class ColumnMapping(Base):
    __tablename__ = "column_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    mapping_json: Mapped[str] = mapped_column(Text)  # {file_column: canonical_field}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
