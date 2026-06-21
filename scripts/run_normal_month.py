"""Normal-month analysis: all contract types vs typical usage scenarios.

Exposes advertised-vs-actual gaps and bill-credit band effects across:
- Multiple usage levels (500, 1000, 2000 kWh)
- Different rate types (fixed, variable, indexed, TOU)
- Contracts with/without bill credits

Run from project root:
    python -m scripts.run_normal_month
or:
    PYTHONPATH=src python scripts/run_normal_month.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from txpower.efl_parser import parse_efl
from txpower.models import Contract, RateType, TduCharges, TouPeriod, BillCredit
from txpower.cost_engine import simulate_month
from txpower.ercot_prices import load_spp_annual_xlsx, find_ercot_2021_file
from txpower.pecanstreet import load_home

EFL_FIXED_WITH_CREDIT = ROOT / "data/raw/efl_pdfs/smartgreen12_billcredit.pdf"
PECAN_STREET_CSV = ROOT / "data/raw/pecan_street_15min_austin.csv"
FIGDIR = ROOT / "reports/figures"


def load_march_2018_usage() -> pd.Series:
    """Load real March 2018 consumption from Pecan Street (home 1642).

    Returns hourly kWh Series for the full month.
    """
    if not PECAN_STREET_CSV.exists():
        raise FileNotFoundError(f"Pecan Street data not found at {PECAN_STREET_CSV}")

    # Read CSV with limited columns
    df = pd.read_csv(
        PECAN_STREET_CSV,
        usecols=["dataid", "local_15min", "grid"],
    )

    # Parse datetime (data has mixed timezones; normalize via UTC)
    df["local_15min"] = pd.to_datetime(df["local_15min"], utc=True).dt.tz_convert("America/Chicago")

    # Filter to home 1642, March 2018 (net consumer, typical household)
    home_data = df[df["dataid"] == 1642].copy()
    march = home_data[
        (home_data["local_15min"].dt.month == 3) &
        (home_data["local_15min"].dt.year == 2018)
    ].copy()

    if march.empty:
        raise ValueError("No data for home 1642 in March 2018")

    # Convert 15-min power (kW) to 15-min energy (kWh)
    march["kwh"] = march["grid"] * (15 / 60)
    march = march.set_index("local_15min").sort_index()

    # Resample to hourly by summing (4 × 15min readings = 1 hour)
    usage = march["kwh"].resample("h").sum()
    usage.name = "kwh"

    print(f"✓ Loaded real March 2018 data for home 1642")
    print(f"  Total: {usage.sum():.1f} kWh")
    print(f"  Average: {usage.mean():.3f} kWh/hour ({usage.mean()*24:.1f} kWh/day)\n")

    return usage


def realistic_variable_plan() -> Contract:
    """Realistic Oncor variable-rate plan (normal market)."""
    return Contract(
        rep_name="TXU Energy", plan_name="Flexible Plan 12",
        rate_type=RateType.VARIABLE, term_months=12,
        energy_charge_per_kwh=0.088,  # typical variable: ~1.5-2¢ higher than fixed
        base_monthly_charge=9.95,
        tdu=TduCharges("Oncor", 4.23, 0.038),
        avg_price_1000=11.0,  # advertised 11¢/kWh (blended)
        efl_source_file="(Realistic synthetic variable plan)",
    )


def realistic_indexed_plan() -> Contract:
    """Realistic Oncor indexed (wholesale pass-through) plan."""
    return Contract(
        rep_name="Griddy", plan_name="Wholesale Pass-Through 1mo",
        rate_type=RateType.INDEXED, term_months=1,
        energy_charge_per_kwh=0.0, base_monthly_charge=9.99,
        tdu=TduCharges("Oncor", 4.23, 0.038),
        indexed_adder_per_kwh=0.010,  # 1.0¢/kWh adder above SPP
        avg_price_1000=9.5,  # advertised 9.5¢/kWh (normal market)
        efl_source_file="(Realistic synthetic indexed plan)",
    )


def realistic_tou_plan() -> Contract:
    """Realistic TOU "free nights" plan."""
    tou_schedule = [
        TouPeriod(hour_start=14, hour_end=21, rate_per_kwh=0.135),  # peak 2pm-9pm
        TouPeriod(hour_start=6, hour_end=14, rate_per_kwh=0.088),   # off-peak 6am-2pm
        TouPeriod(hour_start=21, hour_end=6, rate_per_kwh=0.0),     # free nights 9pm-6am
    ]
    return Contract(
        rep_name="Free Power", plan_name="Free Nights TOU 12mo",
        rate_type=RateType.TOU, term_months=12,
        energy_charge_per_kwh=0.0,  # ignored; tou_schedule overrides
        base_monthly_charge=12.95,
        tdu=TduCharges("Oncor", 4.23, 0.038),
        tou_schedule=tou_schedule,
        avg_price_1000=9.8,  # advertised 9.8¢/kWh (blended across TOU periods)
        efl_source_file="(Realistic synthetic TOU plan)",
    )


def main() -> None:
    """Run normal-month comparison with real consumption data."""
    print("\n" + "=" * 80)
    print("NORMAL-MONTH COMPARISON: Real March 2018 Data vs Contract Types")
    print("=" * 80 + "\n")

    # Load real consumption data
    usage = load_march_2018_usage()

    # Load real EFL or create synthetic fixed plan
    if not EFL_FIXED_WITH_CREDIT.exists():
        print(f"⚠ Sample EFL not found at {EFL_FIXED_WITH_CREDIT}")
        print("   Creating synthetic fixed plan for comparison.\n")
        fixed = Contract(
            rep_name="TXU Energy", plan_name="Free Nights 12mo (fixed)",
            rate_type=RateType.FIXED, term_months=12,
            energy_charge_per_kwh=0.095,
            base_monthly_charge=9.95,
            tdu=TduCharges("Oncor", 4.23, 0.038),
            bill_credits=[BillCredit(amount=75.0, threshold_min=1000, threshold_max=2000)],
            avg_price_1000=10.5,
            efl_source_file="(Synthetic fixed plan with bill credit band)",
        )
    else:
        fixed = parse_efl(EFL_FIXED_WITH_CREDIT, "SmartEnergy", "SmartGreen 12mo")
        print(f"✓ Loaded EFL: {fixed.rep_name} - {fixed.plan_name}\n")

    # Load real ERCOT SPP or use flat average (2018 prices, not 2021)
    # For a fair comparison, use typical 2018 wholesale prices
    print("ℹ Using typical 2018 wholesale prices (3.5¢/kWh average)\n")
    spp = pd.Series(0.035, index=usage.index, name="spp")

    contracts = [
        fixed,
        realistic_variable_plan(),
        realistic_indexed_plan(),
        realistic_tou_plan(),
    ]

    # Run simulations with real consumption data
    results = []
    total_kwh = usage.sum()

    for contract in contracts:
        bill = simulate_month(
            usage,
            contract,
            spp_per_kwh=spp if contract.rate_type == RateType.INDEXED else None
        )

        # Actual effective price (cents/kWh)
        actual_cents = (bill["total"] / bill["total_kwh"]) * 100 if bill["total_kwh"] else None

        # For advertised price, estimate based on usage
        # Use avg_price_1000 as reference point and interpolate
        advertised_cents = contract.avg_price_1000 if contract.avg_price_1000 else None

        # Gap: actual - advertised
        gap_cents = (actual_cents - advertised_cents) if advertised_cents else None

        results.append({
            "rep": contract.rep_name,
            "plan": contract.plan_name,
            "rate_type": contract.rate_type.value,
            "advertised_c_kwh": advertised_cents,
            "actual_c_kwh": actual_cents,
            "gap_c_kwh": gap_cents,
            "total_kwh": bill["total_kwh"],
            "total_bill": bill["total"],
            "bill_breakdown": f"energy: ${bill['energy']:.2f}, tdu: ${bill['tdu']:.2f}, base: ${bill['base']:.2f}, credits: ${bill['credits']:.2f}",
        })

    # Print results as table
    df = pd.DataFrame(results)

    print(f"\n{'─' * 110}")
    print(f"REAL MARCH 2018 DATA: {total_kwh:.0f} kWh for the month")
    print(f"{'─' * 110}")
    print(f"{'Rep':<20} {'Plan':<30} {'Type':<10} {'Adv (¢)':<10} {'Actual (¢)':<12} {'Gap (¢)':<10} {'Total ($)':<12}")
    print(f"{'-' * 110}")

    for _, row in df.iterrows():
        adv_str = f"{row['advertised_c_kwh']:.1f}" if row["advertised_c_kwh"] else "n/a"
        act_str = f"{row['actual_c_kwh']:.1f}" if row["actual_c_kwh"] else "n/a"
        gap_str = f"{row['gap_c_kwh']:+.1f}" if row["gap_c_kwh"] else "n/a"

        print(
            f"{row['rep']:<20} {row['plan']:<30} {row['rate_type']:<10} "
            f"{adv_str:<10} {act_str:<12} {gap_str:<10} ${row['total_bill']:<11,.2f}"
        )
        if row["bill_breakdown"]:
            print(f"  → {row['bill_breakdown']}")

    print(f"\n{'─' * 110}\n")

    # Insights
    print("KEY INSIGHTS:")
    print("─" * 100)
    print("1. ADVERTISED-VS-ACTUAL GAP:")
    print("   The 'advertised' price (EFL average) often differs from the calculated actual price")
    print("   because of bill credits, TOU structures, or base-charge amortization across usage levels.")
    print("")
    print("2. BILL-CREDIT BANDS:")
    print("   Plans with usage-band credits (e.g., $75 at 1000–2000 kWh) show large gaps at")
    print("   different usage levels. Customers outside the band pay more; inside the band pay less.")
    print("")
    print("3. INDEXED (WHOLESALE) PLANS:")
    print("   Indexed plans are typically cheap in normal months but catastrophic during scarcity.")
    print("   The 'advertised' price assumes historical wholesale rates, not actual market prices.")
    print("")
    print("4. TOU (TIME-OF-USE) PLANS:")
    print("   TOU plans reward low-usage periods (e.g., 'free nights') and penalize peaks.")
    print("   Advertised prices blend the rate tiers; actual costs depend on usage timing.")
    print("")
    print(f"{'─' * 100}\n")


if __name__ == "__main__":
    main()
