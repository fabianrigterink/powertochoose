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
    cost engine. Supports both Kaggle (3-day sample) and Dataport (full-year)
    CSV exports. If dataid is provided, filters to that home only.

    Args:
        path: CSV file path (Kaggle or Dataport export).
        dataid: Optional home ID to filter on. If None, assumes single home.
        timestamp_col: Column name for timestamps (default "localminute").
        billing_col: Column name for whole-home power in kW (default "grid").
        interval_minutes: Duration of each interval in minutes (default 1.0).

    Returns:
        Timestamp-indexed Series of kWh per interval, timezone-aware ("America/Chicago").

    Raises:
        ValueError: If required columns are missing from CSV.
    """
    df = pd.read_csv(path)

    if timestamp_col not in df.columns:
        raise ValueError(
            f"Missing timestamp column '{timestamp_col}'. Available: {list(df.columns)}"
        )
    if billing_col not in df.columns:
        raise ValueError(
            f"Missing billing column '{billing_col}'. Available: {list(df.columns)}"
        )

    if dataid is not None and "dataid" in df.columns:
        df = df[df["dataid"] == dataid]

    df[timestamp_col] = pd.to_datetime(df[timestamp_col])
    df = df.set_index(timestamp_col).sort_index()

    if df.index.tz is None:
        df.index = df.index.tz_localize("America/Chicago")

    power_kw = df[billing_col].astype(float)
    usage_kwh = to_kwh(power_kw, interval_minutes)
    usage_kwh.name = "consumption_kwh"

    return usage_kwh


def to_kwh(power_kw: pd.Series, interval_minutes: float) -> pd.Series:
    """Convert average-power-per-interval (kW) to energy-per-interval (kWh)."""
    return power_kw * (interval_minutes / 60.0)


def to_monthly_kwh_series(usage_kwh: pd.Series) -> pd.Series:
    """Group interval kWh into monthly totals (sanity check vs EFL usage bands)."""
    return usage_kwh.groupby(usage_kwh.index.to_period("M")).sum()
