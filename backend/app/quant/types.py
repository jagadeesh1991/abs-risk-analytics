"""Typed domain objects for the structured products engine.

Specs (inputs) are frozen dataclasses; results carry per-period numpy arrays.
All rates are annual decimals (0.065 = 6.5%); all periods are monthly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class CollateralPool:
    """Aggregated collateral characteristics driving the projection."""
    balance: float                 # current pool balance
    wac: float                     # weighted-average gross coupon (annual, decimal)
    wam: int                       # weighted-average remaining maturity (months)
    servicing_fee: float = 0.005   # annual servicing strip on performing balance
    name: str = "pool"

    def __post_init__(self) -> None:
        if self.balance <= 0:
            raise ValueError("pool balance must be positive")
        if not 0 < self.wac < 1:
            raise ValueError("wac must be a decimal annual rate in (0, 1)")
        if self.wam < 1:
            raise ValueError("wam must be at least 1 month")


@dataclass(frozen=True)
class FloatingCoupon:
    """Floating-rate coupon: index forward + margin, with optional cap/floor."""
    index: str = "SOFR"
    margin: float = 0.011
    cap: float | None = None
    floor: float = 0.0


@dataclass(frozen=True)
class Tranche:
    name: str
    seniority: int                     # 1 = most senior
    balance: float
    coupon: float | FloatingCoupon     # fixed annual decimal, or floating spec

    def __post_init__(self) -> None:
        if self.balance < 0:
            raise ValueError(f"tranche {self.name}: balance must be >= 0")
        if self.seniority < 1:
            raise ValueError(f"tranche {self.name}: seniority must be >= 1")


@dataclass(frozen=True)
class DealSpec:
    """Rated capital stack + structural features. Residual/equity is implicit:
    whatever cash survives the waterfall flows to it."""
    name: str
    tranches: tuple[Tranche, ...]
    oc_trigger: float = 1.05        # OC test fails when collateral/rated < trigger
    senior_fee: float = 0.0025      # annual, accrued on performing collateral

    def __post_init__(self) -> None:
        ranks = [t.seniority for t in self.tranches]
        if len(set(ranks)) != len(ranks):
            raise ValueError("tranche seniorities must be unique")
        if not self.tranches:
            raise ValueError("deal needs at least one tranche")

    @property
    def ordered_tranches(self) -> tuple[Tranche, ...]:
        return tuple(sorted(self.tranches, key=lambda t: t.seniority))

    @property
    def rated_balance(self) -> float:
        return float(sum(t.balance for t in self.tranches))


@dataclass(frozen=True)
class Assumptions:
    """Scenario assumptions. cpr/cdr may be scalars or per-month vectors."""
    cpr: float | tuple[float, ...] = 0.08
    cdr: float | tuple[float, ...] = 0.02
    severity: float = 0.40          # loss given default (1 - recovery rate)
    recovery_lag: int = 6           # months from default to recovery receipt

    def __post_init__(self) -> None:
        if not 0 <= self.severity <= 1:
            raise ValueError("severity must be in [0, 1]")
        if self.recovery_lag < 0:
            raise ValueError("recovery_lag must be >= 0")


@dataclass
class CollateralCashflows:
    """Per-month collateral projection. Arrays have length n = wam + recovery_lag.
    Invariant (asserted at construction):
        begin - scheduled - prepaid - defaulted == end   for every month.
    """
    n: int
    begin_balance: np.ndarray
    scheduled_principal: np.ndarray
    prepaid_principal: np.ndarray
    defaulted_principal: np.ndarray
    recoveries: np.ndarray          # arrives with lag; cash, not balance
    gross_interest: np.ndarray
    net_interest: np.ndarray        # gross minus servicing strip
    end_balance: np.ndarray

    def __post_init__(self) -> None:
        resid = (self.begin_balance - self.scheduled_principal
                 - self.prepaid_principal - self.defaulted_principal
                 - self.end_balance)
        if not np.allclose(resid, 0, atol=1e-6):
            raise AssertionError(
                f"collateral balance not conserved; max residual {np.abs(resid).max():.2e}")

    @property
    def principal_collected(self) -> np.ndarray:
        return self.scheduled_principal + self.prepaid_principal + self.recoveries

    @property
    def total_collections(self) -> np.ndarray:
        return self.principal_collected + self.net_interest


@dataclass
class TrancheResult:
    """Per-period cash and balance path for one tranche."""
    name: str
    begin_balance: np.ndarray
    coupon_rate: np.ndarray         # effective annual rate applied each period
    interest_due: np.ndarray        # incl. carried shortfall
    interest_paid: np.ndarray
    interest_shortfall: np.ndarray  # cumulative unpaid, carried forward
    principal_paid: np.ndarray
    turbo_principal: np.ndarray     # portion of principal from OC diversion
    writedown: np.ndarray
    end_balance: np.ndarray

    @property
    def total_cash(self) -> np.ndarray:
        return self.interest_paid + self.principal_paid

    def wal_years(self) -> float | None:
        """Weighted-average life of principal repayments, in years."""
        total = self.principal_paid.sum()
        if total <= 0:
            return None
        months = np.arange(1, len(self.principal_paid) + 1)
        return float((self.principal_paid * months).sum() / total / 12.0)

    def principal_window(self) -> tuple[int, int] | None:
        idx = np.nonzero(self.principal_paid > 0.005)[0]
        if len(idx) == 0:
            return None
        return int(idx[0] + 1), int(idx[-1] + 1)


@dataclass
class WaterfallResult:
    deal_name: str
    n: int
    tranches: list[TrancheResult] = field(default_factory=list)
    fees_paid: np.ndarray = field(default_factory=lambda: np.zeros(0))
    oc_ratio: np.ndarray = field(default_factory=lambda: np.zeros(0))
    oc_pass: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    residual_cash: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def tranche(self, name: str) -> TrancheResult:
        for t in self.tranches:
            if t.name == name:
                return t
        raise KeyError(f"no tranche named {name!r}")
