"""Load ERCOT Settlement Point Prices (SPP) and align them to consumption.

SOURCE (verified format)
------------------------
Product: "Historical RTM Load Zone and Hub Prices" (EMIL NP6-785-ER).
  https://www.ercot.com/mp/data-products/data-product-details?id=np6-785-er
Each year is one .zip containing an .xlsx with ONE SHEET PER MONTH.
Columns: Delivery Date | Delivery Hour | Delivery Interval |
         Repeated Hour Flag | Settlement Point Name | Settlement Point Price

Parsing facts (from gridstatus' implementation, confirmed against the product):
  - Delivery Hour is HOUR-ENDING 1..24 (not 0..23). Hour 24 = the last interval
    of the day; subtract 1 to get a 0..23 hour for timestamp construction.
  - Delivery Interval is 1..4 (the four 15-min intervals within the hour).
  - There is a known stray all-null row per year -> drop rows null in
    Delivery Hour & Delivery Interval.
  - Settlement Point Price is in $/MWh. The cost engine wants $/kWh -> /1000.

CHOICES FOR THIS PROJECT
  - Load Zone: LZ_NORTH (Oncor territory, matches Round Rock 78664).
  - Window: Feb 2021 for the Winter Storm Uri analysis, where SPP sat pinned at
    the $9,000/MWh system offer cap for an extended stretch.

If you don't yet have the real file, `synthetic_uri_spp()` builds a documented
stand-in pinned to known Uri facts so the pipeline runs end-to-end; swap in the
real file the moment you have it (same downstream interface).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

CENTRAL_TZ = "America/Chicago"
PRICE_CAP_PER_MWH = 9000.0


def load_spp_annual_xlsx(
    path: str | Path,
    settlement_point: str = "LZ_NORTH",
    tz: str | None = CENTRAL_TZ,
) -> pd.Series:
    """Load an ERCOT annual RTM SPP xlsx, return a $/kWh series for one zone.

    Returns a tz-aware (or naive if tz=None) DatetimeIndex Series at 15-min
    resolution, in $/kWh. Reads every monthly sheet and concatenates.
    """
    sheets = pd.read_excel(path, sheet_name=None)
    df = pd.concat(sheets.values(), ignore_index=True)

    # drop the known stray null row(s)
    df = df.dropna(subset=["Delivery Hour", "Delivery Interval"], how="all")
    df = df[df["Settlement Point Name"] == settlement_point].copy()
    if df.empty:
        pts = pd.concat(sheets.values())["Settlement Point Name"].unique()
        raise ValueError(
            f"No rows for '{settlement_point}'. Available include: {sorted(pts)[:12]}"
        )

    df["Delivery Date"] = pd.to_datetime(df["Delivery Date"])
    hour0 = df["Delivery Hour"].astype(int) - 1          # 1..24 -> 0..23
    minute = (df["Delivery Interval"].astype(int) - 1) * 15  # 1..4 -> 0,15,30,45
    ts = (df["Delivery Date"]
          + pd.to_timedelta(hour0, unit="h")
          + pd.to_timedelta(minute, unit="m"))

    s = pd.Series(
        df["Settlement Point Price"].astype(float).values / 1000.0,  # $/MWh -> $/kWh
        index=pd.DatetimeIndex(ts), name="spp_per_kwh",
    ).sort_index()
    if tz:
        s.index = s.index.tz_localize(tz, ambiguous="infer", nonexistent="shift_forward")
    return s


def synthetic_uri_spp(
    start: str = "2021-02-01",
    end: str = "2021-02-28",
    cap_start: str = "2021-02-15",
    cap_end: str = "2021-02-19",
    tz: str | None = CENTRAL_TZ,
    seed: int = 7,
) -> pd.Series:
    """Documented synthetic Feb-2021 LZ_NORTH SPP in $/kWh (stand-in only).

    Pinned to known Uri facts: normal ~$20-40/MWh most of the month, then pinned
    at the $9,000/MWh cap (=$9/kWh) across the Feb 15-19 emergency stretch, with
    elevated, volatile prices on the shoulders. Clearly NOT real data -- for
    pipeline wiring and illustration until the ERCOT file is dropped in.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, end=pd.Timestamp(end) + pd.Timedelta(days=1),
                        freq="15min", inclusive="left")
    mwh = np.full(len(idx), np.nan)
    cs, ce = pd.Timestamp(cap_start), pd.Timestamp(cap_end) + pd.Timedelta(days=1)
    naive = idx.tz_localize(None) if idx.tz else idx
    for i, t in enumerate(naive):
        if cs <= t < ce:
            mwh[i] = PRICE_CAP_PER_MWH                       # pinned at cap
        elif (cs - pd.Timedelta(days=1)) <= t < cs or ce <= t < (ce + pd.Timedelta(days=2)):
            mwh[i] = float(rng.uniform(500, 6000))           # volatile shoulders
        else:
            mwh[i] = float(rng.uniform(15, 45))              # normal
    s = pd.Series(mwh / 1000.0, index=idx, name="spp_per_kwh")
    if tz and s.index.tz is None:
        s.index = s.index.tz_localize(tz, ambiguous="infer", nonexistent="shift_forward")
    s.attrs["synthetic"] = True
    return s


def align_price_to_usage(
    spp_per_kwh: pd.Series,
    usage_index: pd.DatetimeIndex,
    method: str = "ffill",
) -> pd.Series:
    """Reindex a 15-min price series onto the consumption index.

    Carries each 15-min price across the finer (e.g. 1-min) usage grid.
    Both indexes must share a timezone; localize upstream if needed.
    """
    return spp_per_kwh.reindex(usage_index, method=method)


def load_engie_hourly_csv(
    path: str | Path,
    settlement_point: str = "LZ_NORTH",
    tz: str | None = CENTRAL_TZ,
) -> pd.Series:
    """Load ENGIE Resources hourly real-time pricing CSV.

    Downloads from: https://www.engieresources.com/historical-pricing-data/
    Select: ERCOT > LZ_NORTH > HourlyRT > date range > download CSV

    Returns a tz-aware $/kWh Series at 15-min resolution.
    """
    df = pd.read_csv(path)

    # Parse DATE + START_TIME into DatetimeIndex
    # DATE is "DD-MMM-YYYY", START_TIME is "HH:MM"
    df["datetime"] = pd.to_datetime(
        df["DATE"] + " " + df["START_TIME"],
        format="%d-%b-%Y %H:%M"
    )

    # Extract the settlement point column (should be "LZ_NORTH")
    if settlement_point not in df.columns:
        raise ValueError(f"Column '{settlement_point}' not found. Available: {df.columns.tolist()}")

    # Parse price: remove "$" and convert to float
    prices_str = df[settlement_point].str.replace("$", "").astype(float)

    # Create Series with datetime index
    s = pd.Series(
        prices_str.values / 1000.0,  # $/MWh -> $/kWh
        index=pd.DatetimeIndex(df["datetime"]),
        name="spp_per_kwh"
    ).sort_index()

    if tz and s.index.tz is None:
        s.index = s.index.tz_localize(tz, ambiguous="infer", nonexistent="shift_forward")

    return s


def find_ercot_2021_file() -> Path | None:
    """Search for ERCOT 2021 annual SPP xlsx in common locations.

    Returns path if found, None otherwise. Checks:
    - data/raw/ercot/2021*.*  (project data directory)
    - ~/Downloads/2021*.xlsx  (user Downloads)
    """
    candidates = [
        Path(__file__).resolve().parents[2] / "data" / "raw" / "ercot",
        Path.home() / "Downloads",
    ]

    for candidate_dir in candidates:
        if not candidate_dir.exists():
            continue
        for xlsx_file in candidate_dir.glob("2021*.xlsx"):
            if "RTM" in xlsx_file.name or "SPP" in xlsx_file.name or len(xlsx_file.name) < 50:
                return xlsx_file
    return None


def find_engie_csv() -> Path | None:
    """Search for ENGIE ERCOT CSV in common locations.

    Returns path if found, None otherwise. Checks:
    - data/raw/ERCOT*.csv  (project data directory)
    - ~/Downloads/ERCOT*.csv  (user Downloads)
    """
    candidates = [
        Path(__file__).resolve().parents[2] / "data" / "raw",
        Path.home() / "Downloads",
    ]

    for candidate_dir in candidates:
        if not candidate_dir.exists():
            continue
        for csv_file in candidate_dir.glob("ERCOT*.csv"):
            return csv_file
    return None
