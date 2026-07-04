"""Structured products quantitative core.

Pure NumPy/pandas — no heavy dependencies. Layers:

    curves      discount curve, parallel shifts, 1m forward projection
    collateral  CPR/CDR vector engine -> CollateralCashflows
    waterfall   stateful priority-of-payments with OC trigger / turbo
    risk        PV, effective duration/convexity, parallel scenario grids
    demo_deal   reference 3-tranche deal + pool seeding from loan tapes
"""
