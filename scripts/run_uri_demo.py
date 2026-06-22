"""End-to-end demo: real parsed contract + synthetic Uri prices -> headline.

Run from the project root:
    python -m scripts.run_uri_demo
or:
    PYTHONPATH=src python scripts/run_uri_demo.py

Produces the cumulative-cost divergence chart in reports/figures/ and prints
the February-2021 bill comparison. Everything here that is synthetic is clearly
labeled; swap in real ERCOT + Dataport + Wayback files to make it publishable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from txpower.ercot_prices import (
    synthetic_uri_spp, align_price_to_usage, load_spp_annual_xlsx, find_ercot_2021_file,
    load_engie_hourly_csv, find_engie_csv,
)
from txpower.efl_parser import parse_efl
from txpower.models import Contract, RateType, TduCharges
from txpower.cost_engine import simulate_month

EFL = ROOT / "data/raw/efl_pdfs/smartgreen12_billcredit.pdf"
ENGIE_CSV = ROOT / "data/raw/ERCOT_Hourly_Real_Time_2026-06-21.csv"
PTC_OCT_2019_CSV = ROOT / "data/raw/ptc_offers_20191001.csv"
FIGDIR = ROOT / "reports/figures"


def synthetic_winter_consumption() -> pd.Series:
    """~970 kWh Feb-2021 month with a heating spike during the freeze.

    Placeholder until a real Feb-2021 Dataport home is loaded.
    """
    idx = pd.date_range("2021-02-01", periods=28 * 24 * 4, freq="15min",
                        tz="America/Chicago")
    base = 1.0 + 0.4 * np.sin(np.linspace(0, 28 * 2 * np.pi, len(idx)))
    naive = idx.tz_localize(None)
    freeze = (naive >= pd.Timestamp("2021-02-15")) & (naive < pd.Timestamp("2021-02-20"))
    base = base + freeze.astype(float) * 2.5
    return pd.Series(base * 0.25, index=idx, name="kwh")  # kW avg * 0.25h


def load_ptc_oct_2019_plans() -> tuple[Contract, Contract, Contract]:
    """Load real Oct 2019 plans from Wayback Machine snapshot.

    Returns (fixed, variable, indexed) representative plans that existed
    4 months before Winter Storm Uri (Feb 2021). Uses actual advertised
    prices from Power to Choose export at that time.
    """
    if not PTC_OCT_2019_CSV.exists():
        return None

    df = pd.read_csv(PTC_OCT_2019_CSV)

    # Extract one representative plan from each type
    fixed_row = df[df["[RateType]"] == "Fixed"].iloc[0]
    var_row = df[df["[RateType]"] == "Variable"].iloc[0]
    idx_row = df[df["[RateType]"] == "Indexed"].iloc[0]

    fixed = Contract(
        rep_name=fixed_row["[RepCompany]"],
        plan_name=fixed_row["[Product]"],
        rate_type=RateType.FIXED,
        term_months=int(fixed_row["[TermValue]"]) if fixed_row["[TermValue]"] else 12,
        energy_charge_per_kwh=float(fixed_row["[kwh1000]"]),
        base_monthly_charge=0.0,  # Not in CSV; assume included in rate
        tdu=TduCharges("Oncor", 4.23, 0.038),
        etf=float(fixed_row["[CancelFee]"]) if pd.notna(fixed_row["[CancelFee]"]) else 0.0,
        avg_price_500=float(fixed_row["[kwh500]"]),
        avg_price_1000=float(fixed_row["[kwh1000]"]),
        avg_price_2000=float(fixed_row["[kwh2000]"]),
        efl_source_file=f"Wayback Oct 1, 2019: {fixed_row['[FactsURL]']}",
    )

    variable = Contract(
        rep_name=var_row["[RepCompany]"],
        plan_name=var_row["[Product]"],
        rate_type=RateType.VARIABLE,
        term_months=int(var_row["[TermValue]"]) if var_row["[TermValue]"] else 1,
        energy_charge_per_kwh=float(var_row["[kwh1000]"]),
        base_monthly_charge=0.0,
        tdu=TduCharges("Oncor", 4.23, 0.038),
        avg_price_1000=float(var_row["[kwh1000]"]),
        efl_source_file="Wayback Oct 1, 2019",
    )

    indexed = Contract(
        rep_name=idx_row["[RepCompany]"],
        plan_name=idx_row["[Product]"],
        rate_type=RateType.INDEXED,
        term_months=int(idx_row["[TermValue]"]) if idx_row["[TermValue]"] else 1,
        energy_charge_per_kwh=0.0,
        base_monthly_charge=0.0,
        tdu=TduCharges("Oncor", 4.23, 0.038),
        indexed_adder_per_kwh=0.010,  # Estimate: 1¢/kWh markup on wholesale
        avg_price_1000=float(idx_row["[kwh1000]"]),
        efl_source_file="Wayback Oct 1, 2019",
    )

    return fixed, variable, indexed


def main() -> None:
    if not EFL.exists():
        raise SystemExit(f"Missing sample EFL at {EFL}. See README data section.")

    # Try to load real ERCOT 2021 SPP from ENGIE CSV, xlsx, or synthetic
    spp = None
    data_source = None

    # 1. Try ENGIE CSV first
    if ENGIE_CSV.exists():
        try:
            spp = load_engie_hourly_csv(ENGIE_CSV, settlement_point="LZ_NORTH")
            data_source = f"ENGIE ERCOT CSV ({ENGIE_CSV.name})"
        except Exception as e:
            print(f"⚠ Failed to load ENGIE CSV ({e}); trying xlsx...")
            spp = None

    # 2. Fall back to ERCOT annual xlsx
    if spp is None:
        ercot_path = find_ercot_2021_file()
        if ercot_path:
            try:
                spp = load_spp_annual_xlsx(ercot_path, settlement_point="LZ_NORTH")
                data_source = f"ERCOT annual xlsx ({ercot_path.name})"
            except Exception as e:
                print(f"⚠ Failed to load ERCOT xlsx ({e}); using synthetic.")
                spp = None

    # 3. Fall back to synthetic
    if spp is None:
        print("ℹ No real ERCOT data found. Using synthetic SPP for illustration.")
        spp = synthetic_uri_spp()
        data_source = "synthetic SPP"
        spp.attrs["synthetic"] = True
    else:
        print(f"✓ Loaded {data_source}")

    usage = synthetic_winter_consumption()

    # Try to load real Oct 2019 plans; fall back to synthetic
    plans = load_ptc_oct_2019_plans()
    if plans:
        fixed, variable, indexed = plans
        print(f"✓ Loaded real Oct 2019 plans from Wayback Machine")
        print(f"  Fixed:   {fixed.rep_name} - {fixed.plan_name}")
        print(f"  Indexed: {indexed.rep_name} - {indexed.plan_name}\n")
    else:
        print("ℹ Using synthetic contracts (Oct 2019 CSV not found)\n")
        fixed = parse_efl(EFL, "SmartEnergy", "SmartGreen 12 (fixed)")
        indexed = realistic_preuri_indexed()

    price = align_price_to_usage(spp, usage.index)

    bill_fixed = simulate_month(usage, fixed)
    bill_indexed = simulate_month(usage, indexed, spp_per_kwh=price)

    data_label = "Real Oct 2019 plans & Real ERCOT SPP" if plans and not spp.attrs.get("synthetic") else "Mixed real/synthetic data"
    print(f"=== FEBRUARY 2021 BILL ({data_label}) ===")
    print(f"  Fixed  : ${bill_fixed['total']:>10,.2f}  "
          f"({bill_fixed['effective_per_kwh']*100:.1f} c/kWh)")
    print(f"  Indexed: ${bill_indexed['total']:>10,.2f}  "
          f"({bill_indexed['effective_per_kwh']*100:.1f} c/kWh)")
    ratio = bill_indexed['total']/bill_fixed['total']
    print(f"  Indexed is {ratio:.1f}x the fixed bill")

    _plot(spp, usage, fixed, indexed)


def _plot(spp, usage, fixed, indexed) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    price = align_price_to_usage(spp, usage.index)
    cum_fixed = ((fixed.energy_charge_per_kwh + fixed.tdu.per_kwh) * usage).cumsum() \
        + fixed.base_monthly_charge + fixed.tdu.fixed_monthly
    cum_idx = ((price + indexed.indexed_adder_per_kwh + indexed.tdu.per_kwh) * usage).cumsum() \
        + indexed.base_monthly_charge + indexed.tdu.fixed_monthly

    band = (pd.Timestamp("2021-02-15", tz="America/Chicago"),
            pd.Timestamp("2021-02-20", tz="America/Chicago"))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), height_ratios=[2, 1],
                                   sharex=True)
    ax1.plot(cum_fixed.index, cum_fixed.values, lw=2.2, color="#1f6f3d",
             label=f"Fixed: {fixed.rep_name}")
    ax1.plot(cum_idx.index, cum_idx.values, lw=2.2, color="#b3202c",
             label=f"Indexed: {indexed.rep_name}")
    ax1.set_ylabel("Cumulative cost ($)")
    ax1.legend(loc="upper left", frameon=False)
    data_label = "Real Oct 2019 plans, Real ERCOT SPP" if not spp.attrs.get("synthetic") else "Real Oct 2019 plans, Synthetic SPP"
    ax1.set_title(f"Feb 2021 cumulative cost: same home, same usage  ({data_label})")
    ax1.axvspan(*band, alpha=0.10, color="red")
    ax2.plot(spp.index, spp.values, color="#444", lw=0.8)
    ax2.set_ylabel("SPP ($/kWh)")
    ax2.set_xlabel("Date")
    ax2.axvspan(*band, alpha=0.10, color="red")
    plt.tight_layout()
    FIGDIR.mkdir(parents=True, exist_ok=True)
    out = FIGDIR / "uri_divergence_DEMO.png"
    plt.savefig(out, dpi=130)
    print(f"\nChart -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
