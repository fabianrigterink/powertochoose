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

EFL_FIXED_WITH_CREDIT = ROOT / "data/raw/efl_pdfs/smartgreen12_billcredit.pdf"
FIGDIR = ROOT / "reports/figures"


def flat_usage(total_kwh: float, days: int = 30, tz: str = "America/Chicago") -> pd.Series:
    """Create flat usage profile for a month.

    Args:
        total_kwh: Total monthly energy
        days: Number of days in the month
        tz: Timezone

    Returns:
        Series indexed by hourly timestamps, values in kWh
    """
    idx = pd.date_range("2021-03-01", periods=days * 24, freq="h", tz=tz)
    hourly_kwh = total_kwh / len(idx)
    return pd.Series(hourly_kwh, index=idx, name="kwh")


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
    """Run normal-month comparison across usage levels and rate types."""
    print("\n" + "=" * 80)
    print("NORMAL-MONTH COMPARISON: Advertised-vs-Actual Costs")
    print("=" * 80 + "\n")

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

    # Load real ERCOT SPP for indexed plan, or use flat average
    ercot_path = find_ercot_2021_file()
    spp_series = None
    if ercot_path:
        try:
            spp_series = load_spp_annual_xlsx(ercot_path, settlement_point="LZ_NORTH")
            print(f"✓ Loaded real ERCOT 2021 SPP from {ercot_path.name}\n")
        except Exception as e:
            print(f"⚠ Failed to load ERCOT ({e}); using flat SPP average\n")
    else:
        print("ℹ No ERCOT 2021 file found; using flat SPP average\n")

    contracts = [
        fixed,
        realistic_variable_plan(),
        realistic_indexed_plan(),
        realistic_tou_plan(),
    ]

    usage_levels = [500, 1000, 2000]

    # Run simulations across all usage × contract combinations
    results = []
    for usage_kwh in usage_levels:
        usage = flat_usage(usage_kwh)

        # Align SPP if available (indexed plan needs it)
        spp = None
        if spp_series is not None:
            # Use average SPP for normal month (not the Uri spike)
            spp = pd.Series(
                spp_series.mean(),
                index=usage.index,
                name="spp"
            )
        else:
            # Use typical normal-market SPP (~3.5-4 ¢/kWh) when ERCOT file not available
            spp = pd.Series(
                0.035,  # $0.035/kWh = 3.5¢/kWh (typical non-Uri wholesale price)
                index=usage.index,
                name="spp"
            )

        for contract in contracts:
            bill = simulate_month(
                usage,
                contract,
                spp_per_kwh=spp if contract.rate_type == RateType.INDEXED else None
            )

            # Calculate advertised price (cents/kWh) if available
            advertised_cents = contract.avg_price_1000 if usage_kwh == 1000 else None

            # Actual effective price (cents/kWh)
            actual_cents = (bill["total"] / bill["total_kwh"]) * 100 if bill["total_kwh"] else None

            # Gap: actual - advertised
            gap_cents = (actual_cents - advertised_cents) if advertised_cents else None

            results.append({
                "usage_kwh": usage_kwh,
                "rep": contract.rep_name,
                "plan": contract.plan_name,
                "rate_type": contract.rate_type.value,
                "advertised_c_kwh": advertised_cents,
                "actual_c_kwh": actual_cents,
                "gap_c_kwh": gap_cents,
                "total_bill": bill["total"],
                "bill_breakdown": f"energy: ${bill['energy']:.2f}, tdu: ${bill['tdu']:.2f}, base: ${bill['base']:.2f}, credits: ${bill['credits']:.2f}",
            })

    # Print results as table
    df = pd.DataFrame(results)

    for usage_kwh in usage_levels:
        subset = df[df["usage_kwh"] == usage_kwh]
        print(f"\n{'─' * 100}")
        print(f"USAGE: {usage_kwh:,} kWh/month")
        print(f"{'─' * 100}")
        print(f"{'Rep':<20} {'Plan':<35} {'Type':<10} {'Adv (¢)':<10} {'Actual (¢)':<12} {'Gap (¢)':<10} {'Total ($)':<12}")
        print(f"{'-' * 100}")

        for _, row in subset.iterrows():
            adv_str = f"{row['advertised_c_kwh']:.1f}" if row["advertised_c_kwh"] else "n/a"
            act_str = f"{row['actual_c_kwh']:.1f}" if row["actual_c_kwh"] else "n/a"
            gap_str = f"{row['gap_c_kwh']:+.1f}" if row["gap_c_kwh"] else "n/a"

            print(
                f"{row['rep']:<20} {row['plan']:<35} {row['rate_type']:<10} "
                f"{adv_str:<10} {act_str:<12} {gap_str:<10} ${row['total_bill']:<11,.2f}"
            )
            if row["bill_breakdown"]:
                print(f"  → {row['bill_breakdown']}")

    print(f"\n{'─' * 100}\n")

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
