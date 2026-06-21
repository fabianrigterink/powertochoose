"""Recover real pre-Uri Indexed/Variable plans from Wayback Machine snapshot.

Run locally where archive.org is accessible:

    python scripts/fetch_indexed_plan.py [timestamp]

Or fetch manually:
1. Visit one of these CDX URLs in your browser:
   - http://web.archive.org/cdx/search/cdx?url=www.powertochoose.org/en-us/Plan/ExportToCsv&from=20210201&to=20210220&output=json&collapse=digest

2. Find a row with status=200 and a timestamp between Feb 15-19 (peak Uri dates).

3. Run: python scripts/fetch_indexed_plan.py 20210217123456
   (Replace with your chosen timestamp)

4. Script downloads the CSV to data/raw/ptc_offers_snapshot_YYYYMMDD.csv and
   extracts the best pre-Uri Oncor Indexed plan for use in run_uri_demo.py.

This recovers the real market state right before Winter Storm Uri struck,
enabling a historically accurate bill comparison.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from txpower.wayback import fetch_snapshot_csv, list_snapshots
from txpower.ptc_loader import load_ptc_all_offers_csv, all_offers_to_contracts


def fetch_and_analyze(timestamp: str | None = None) -> None:
    """Fetch Wayback snapshot and extract representative pre-Uri Oncor Indexed plan."""
    if timestamp is None:
        # Auto-detect best snapshot
        print("Searching for best Feb 2021 pre-Uri snapshot...")
        snaps = list_snapshots(from_date="20210213", to_date="20210220")
        ok_snaps = [s for s in snaps if s.get("statuscode") == "200"
                    and "csv" in s.get("mimetype", "").lower()]
        if not ok_snaps:
            raise SystemExit("No valid snapshots found. Try manually via CDX URLs in docstring.")
        timestamp = ok_snaps[0]["timestamp"]
        print(f"Using {timestamp}\n")

    try:
        df = fetch_snapshot_csv(timestamp)
    except Exception as e:
        raise SystemExit(f"Failed to fetch snapshot: {e}")

    path = ROOT / "data" / "raw" / f"ptc_offers_snapshot_{timestamp[:8]}.csv"
    df.to_csv(path, index=False)
    print(f"✓ Saved snapshot to {path.relative_to(ROOT)}")

    # Load and filter to Oncor Indexed plans
    offers = load_ptc_all_offers_csv(path, tdu_filter="ONCOR")
    indexed = offers[
        offers["[RateType]"].str.contains("Indexed|Variable", case=False, na=False)
    ]

    if indexed.empty:
        print("\n⚠ No Indexed/Variable plans found for Oncor in this snapshot.")
        print("Available rate types:", offers["[RateType]"].unique()[:5])
        return

    print(f"\n✓ Found {len(indexed)} Oncor Indexed/Variable plans:\n")
    for _, row in indexed.iterrows():
        rep = row.get("[RepCompany]", "?")
        plan = row.get("[Product]", "?")
        rate = row.get("[RateType]", "?")
        p1000 = row.get("[kwh1000]", "?")
        term = row.get("[TermValue]", "?")
        print(f"  {rep:20} | {plan:40} | {rate:10} | {p1000:6} c/kWh | {int(term) if term else '?'} mo")

    best = indexed.iloc[0]
    print(f"\n→ Recommended for Uri analysis (first/lowest):")
    print(f"  Rep: {best['[RepCompany]']}")
    print(f"  Plan: {best['[Product]']}")
    print(f"  Type: {best['[RateType]']}")
    print(f"  1000 kWh: {best['[kwh1000]']} c/kWh")
    print(f"  EFL: {best['[FactsURL]']}")


if __name__ == "__main__":
    ts = sys.argv[1] if len(sys.argv) > 1 else None
    fetch_and_analyze(ts)
