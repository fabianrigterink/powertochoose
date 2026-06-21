"""Load Pecan Street consumption data and convert to kWh per interval.

TWO SOURCES (see project notes):
  - Kaggle sample: 3 August days, 10 Austin homes, 1-min, circuit-level.
    Great for the "normal month" mechanics and building the pipeline. But it's
    SUMMER, so it cannot produce the Winter Storm Uri (Feb 2021) chart.
  - Full Dataport (academic access): needed for real FEB 2021 consumption.
    Requires university signup + verification at dataport.pecanstreet.org.

IMPORTANT UNIT CONVERSION:
  Pecan Street columns are average POWER in kW over the interval (e.g. 'grid',
  'use', 'solar', plus per-circuit like 'air1', 'furnace1', 'car1').
  Energy per interval (kWh) = power_kW * (interval_minutes / 60).
  For 1-min data: kWh = kW / 60. For 15-min: kWh = kW * 0.25.
  The cost engine expects kWh per interval, so convert here, not downstream.

WHICH COLUMN: use whole-home draw from the grid for billing. 'grid' is net
import from the utility; 'use' is total consumption. For a home WITHOUT solar
they're ~equal. For solar homes, billing is on net import -> use 'grid'
(clip negatives to 0 unless you're modeling net metering / sellback).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_home(
    path: str | Path,
    dataid: int | None = None,
    timestamp_col: str = "localminute",
    billing_col: str = "grid",
    interval_minutes: float = 1.0,
) -> pd.Series:
    """Load one home's whole-home draw as kWh per interval.

    Returns a timestamp-indexed Series of kWh per interval, ready for the
    cost engine. TODO: confirm exact column names against the downloaded CSV
    (Kaggle vs Dataport exports differ slightly).
    """
    raise NotImplementedError(
        "Implement against the real CSV once downloaded; confirm the timestamp "
        "and whole-home column names, which differ between Kaggle and Dataport."
    )


def to_kwh(power_kw: pd.Series, interval_minutes: float) -> pd.Series:
    """Convert average-power-per-interval (kW) to energy-per-interval (kWh)."""
    return power_kw * (interval_minutes / 60.0)


def to_monthly_kwh_series(usage_kwh: pd.Series) -> pd.Series:
    """Group interval kWh into monthly totals (sanity check vs EFL usage bands)."""
    return usage_kwh.groupby(usage_kwh.index.to_period("M")).sum()
