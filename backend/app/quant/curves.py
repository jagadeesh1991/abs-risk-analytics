"""Discount curve: zero-rate pillars, continuous-compounding discount factors,
parallel shifts, and 1-month forward projection for floating coupons."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DiscountCurve:
    """Zero curve on monthly pillars. Rates are annual, continuously compounded.

    Interpolation is linear in the zero rate (flat extrapolation beyond the
    last pillar) — the standard simple choice; swap for monotone-convex or a
    QuantLib-bootstrapped curve behind the same interface when needed.
    """
    pillar_months: tuple[float, ...]
    zero_rates: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.pillar_months) != len(self.zero_rates):
            raise ValueError("pillars and rates must have equal length")
        if len(self.pillar_months) < 1:
            raise ValueError("curve needs at least one pillar")
        if list(self.pillar_months) != sorted(self.pillar_months):
            raise ValueError("pillars must be ascending")

    # -- construction -------------------------------------------------------
    @classmethod
    def flat(cls, rate: float) -> "DiscountCurve":
        return cls(pillar_months=(1.0,), zero_rates=(rate,))

    @classmethod
    def demo_sofr(cls) -> "DiscountCurve":
        """A plausible upward-sloping SOFR-style curve for demos and tests."""
        return cls(
            pillar_months=(1, 3, 6, 12, 24, 36, 60, 84, 120, 240, 360),
            zero_rates=(0.0430, 0.0432, 0.0435, 0.0440, 0.0448, 0.0455,
                        0.0467, 0.0476, 0.0488, 0.0505, 0.0512),
        )

    # -- core ----------------------------------------------------------------
    def zero(self, t_months: np.ndarray | float) -> np.ndarray:
        return np.interp(np.asarray(t_months, dtype=float),
                         self.pillar_months, self.zero_rates)

    def df(self, t_months: np.ndarray | float) -> np.ndarray:
        t = np.asarray(t_months, dtype=float)
        return np.exp(-self.zero(t) * t / 12.0)

    def dfs(self, n: int) -> np.ndarray:
        """Discount factors for month-end payments 1..n."""
        return self.df(np.arange(1, n + 1, dtype=float))

    def forward_1m(self, n: int) -> np.ndarray:
        """Simple 1-month forward rates (annualized) for periods 1..n,
        implied from discount-factor ratios: f = 12 * (DF(t-1)/DF(t) - 1)."""
        t = np.arange(0, n + 1, dtype=float)
        d = self.df(t)
        return (d[:-1] / d[1:] - 1.0) * 12.0

    def shifted(self, bps: float) -> "DiscountCurve":
        """Parallel shift of the zero curve by `bps` basis points."""
        return DiscountCurve(
            pillar_months=self.pillar_months,
            zero_rates=tuple(r + bps / 10_000.0 for r in self.zero_rates),
        )
