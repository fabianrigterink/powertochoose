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

from txpower.ercot_prices import synthetic_uri_spp, align_price_to_usage
from txpower.efl_parser import parse_efl
from txpower.models import Contract, RateType, TduCharges
from txpower.cost_engine import simulate_month

EFL = ROOT / "data/raw/efl_pdfs/smartgreen12_billcredit.pdf"
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


def griddy_style_contract() -> Contract:
    """Synthetic wholesale pass-through plan (Griddy model).

    Replace with a real pre-Uri Indexed/Variable plan recovered via
    txpower.wayback once available.
    """
    return Contract(
        rep_name="(Griddy-style)", plan_name="Wholesale Pass-Through",
        rate_type=RateType.INDEXED, term_months=1,
        energy_charge_per_kwh=0.0, base_monthly_charge=9.99,
        tdu=TduCharges("Oncor", 4.23, 0.038),  # 2021-era Oncor (verify)
        indexed_adder_per_kwh=0.0,
    )


def main() -> None:
    if not EFL.exists():
        raise SystemExit(f"Missing sample EFL at {EFL}. See README data section.")

    spp = synthetic_uri_spp()
    usage = synthetic_winter_consumption()
    fixed = parse_efl(EFL, "SmartEnergy", "SmartGreen 12 (fixed)")
    indexed = griddy_style_contract()
    price = align_price_to_usage(spp, usage.index)

    bill_fixed = simulate_month(usage, fixed)
    bill_indexed = simulate_month(usage, indexed, spp_per_kwh=price)

    print("=== FEBRUARY 2021 BILL  (ILLUSTRATIVE / synthetic price & usage) ===")
    print(f"  Fixed  : ${bill_fixed['total']:>10,.2f}  "
          f"({bill_fixed['effective_per_kwh']*100:.1f} c/kWh)")
    print(f"  Indexed: ${bill_indexed['total']:>10,.2f}  "
          f"({bill_indexed['effective_per_kwh']*100:.1f} c/kWh)")
    print(f"  Indexed is {bill_indexed['total']/bill_fixed['total']:.0f}x the fixed bill")

    _plot(spp, usage, fixed)


def _plot(spp, usage, fixed) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    price = align_price_to_usage(spp, usage.index)
    cum_fixed = ((fixed.energy_charge_per_kwh + fixed.tdu.per_kwh) * usage).cumsum() \
        + fixed.base_monthly_charge + fixed.tdu.fixed_monthly
    cum_idx = ((price + 0.038) * usage).cumsum() + 9.99 + 4.23

    band = (pd.Timestamp("2021-02-15", tz="America/Chicago"),
            pd.Timestamp("2021-02-20", tz="America/Chicago"))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), height_ratios=[2, 1],
                                   sharex=True)
    ax1.plot(cum_fixed.index, cum_fixed.values, lw=2.2, color="#1f6f3d",
             label="Fixed plan")
    ax1.plot(cum_idx.index, cum_idx.values, lw=2.2, color="#b3202c",
             label="Wholesale pass-through (Griddy-style)")
    ax1.set_ylabel("Cumulative cost ($)")
    ax1.legend(loc="upper left", frameon=False)
    ax1.set_title("Feb 2021 cumulative cost: same home, same usage  "
                  "(ILLUSTRATIVE / synthetic)")
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
