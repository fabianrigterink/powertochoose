"""Sanity checks for the cost engine using synthetic data.

Run: python -m pytest tests/ -v   (or just python tests/test_cost_engine.py)
These verify the math wiring is correct BEFORE any real data is plugged in.
"""
import sys
from pathlib import Path
import tempfile

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # also set via pyproject pytest pythonpath

from txpower.models import Contract, BillCredit, TduCharges, RateType
from txpower.cost_engine import simulate_month
from txpower.pecanstreet import load_home, to_kwh


def _flat_usage(total_kwh, n=720):
    """Make a month of usage summing to total_kwh, spread over n intervals."""
    idx = pd.date_range("2021-02-01", periods=n, freq="h")
    return pd.Series(total_kwh / n, index=idx)


def test_fixed_plan_basic():
    usage = _flat_usage(1000)  # 1000 kWh month
    oncor = TduCharges("Oncor", fixed_monthly=4.23, per_kwh=0.038)
    c = Contract(
        rep_name="TestREP", plan_name="Fixed 12",
        rate_type=RateType.FIXED, term_months=12,
        energy_charge_per_kwh=0.09, tdu=oncor,
    )
    bill = simulate_month(usage, c)
    # energy: 1000 * 0.09 = 90 ; tdu: 4.23 + 0.038*1000 = 42.23
    assert abs(bill["energy"] - 90.0) < 1e-6
    assert abs(bill["tdu"] - 42.23) < 1e-6
    assert abs(bill["total"] - 132.23) < 1e-6
    print("fixed plan:", bill)


def test_bill_credit_band_hit_and_miss():
    oncor = TduCharges("Oncor", fixed_monthly=4.23, per_kwh=0.038)
    c = Contract(
        rep_name="TestREP", plan_name="Bill Credit 1000-2000",
        rate_type=RateType.FIXED, term_months=12,
        energy_charge_per_kwh=0.12, tdu=oncor,
        bill_credits=[BillCredit(amount=100.0, threshold_min=1000, threshold_max=2000)],
    )
    in_band = simulate_month(_flat_usage(1500), c)   # gets the $100 credit
    out_band = simulate_month(_flat_usage(900), c)    # misses it
    assert in_band["credits"] == -100.0
    assert out_band["credits"] == 0.0
    print("in-band:", in_band)
    print("out-band:", out_band)


def test_indexed_plan_uses_spp():
    usage = _flat_usage(1000)
    # synthetic price: mostly cheap, one ugly spike hour (Uri-style)
    spp = pd.Series(0.03, index=usage.index)        # $0.03/kWh normal
    spp.iloc[100:120] = 9.0                          # $9/kWh = $9000/MWh cap
    oncor = TduCharges("Oncor", fixed_monthly=4.23, per_kwh=0.038)
    c = Contract(
        rep_name="TestREP", plan_name="Wholesale Pass-Through",
        rate_type=RateType.INDEXED, term_months=1,
        energy_charge_per_kwh=0.0, tdu=oncor,
        indexed_adder_per_kwh=0.005,
    )
    bill = simulate_month(usage, c, spp_per_kwh=spp)
    # the 20 spike hours dominate the energy cost
    assert bill["energy"] > 200  # far above the ~$33 a flat plan would see
    print("indexed plan:", bill)


def test_load_home_flat_usage():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("localminute,grid\n")
        idx = pd.date_range("2021-02-01", periods=720, freq="h")
        for ts in idx:
            f.write(f"{ts},1.0\n")
        f.flush()
        path = f.name
    try:
        usage = load_home(path, interval_minutes=60.0)
        assert isinstance(usage.index, pd.DatetimeIndex)
        assert usage.index.tz is not None
        assert str(usage.index.tz) == "America/Chicago"
        total_kwh = usage.sum()
        assert abs(total_kwh - 720.0) < 1e-6, f"Expected ~720 kWh, got {total_kwh}"
        print(f"load_home flat usage: {total_kwh} kWh")
    finally:
        Path(path).unlink()


def test_load_home_minute_intervals():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("localminute,grid\n")
        idx = pd.date_range("2021-02-01", periods=1440, freq="1min")
        for ts in idx:
            f.write(f"{ts},1.0\n")
        f.flush()
        path = f.name
    try:
        usage = load_home(path, interval_minutes=1.0)
        total_kwh = usage.sum()
        assert abs(total_kwh - 24.0) < 1e-6, f"Expected ~24 kWh (1440 min * 1kW / 60), got {total_kwh}"
        print(f"load_home 1-min intervals: {total_kwh} kWh")
    finally:
        Path(path).unlink()


def test_load_home_with_dataid():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("localminute,dataid,grid\n")
        for h in range(24):
            f.write(f"2021-02-01 {h:02d}:00:00,1,1.0\n")
            f.write(f"2021-02-01 {h:02d}:00:00,2,2.0\n")
        f.flush()
        path = f.name
    try:
        usage = load_home(path, dataid=1, interval_minutes=60.0)
        total_kwh = usage.sum()
        assert abs(total_kwh - 24.0) < 1e-6, f"Expected 24 kWh (dataid=1), got {total_kwh}"
        print(f"load_home dataid filter: {total_kwh} kWh")
    finally:
        Path(path).unlink()


def test_load_home_missing_column():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("timestamp,power\n")
        f.write("2021-02-01 00:00:00,1.0\n")
        f.flush()
        path = f.name
    try:
        try:
            load_home(path, timestamp_col="localminute", billing_col="grid")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "localminute" in str(e)
            print(f"load_home missing column error: {e}")
    finally:
        Path(path).unlink()


def test_load_home_integration_with_cost_engine():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("localminute,grid\n")
        idx = pd.date_range("2021-02-01", periods=720, freq="h")
        for ts in idx:
            f.write(f"{ts},1.0\n")
        f.flush()
        path = f.name
    try:
        usage = load_home(path, interval_minutes=60.0)
        oncor = TduCharges("Oncor", fixed_monthly=4.23, per_kwh=0.038)
        c = Contract(
            rep_name="TestREP", plan_name="Fixed 12",
            rate_type=RateType.FIXED, term_months=12,
            energy_charge_per_kwh=0.12, tdu=oncor,
        )
        bill = simulate_month(usage, c)
        assert bill["total"] > 0, "Bill should be positive"
        print(f"load_home → cost_engine: bill={bill}")
    finally:
        Path(path).unlink()


if __name__ == "__main__":
    test_fixed_plan_basic()
    test_bill_credit_band_hit_and_miss()
    test_indexed_plan_uses_spp()
    test_load_home_flat_usage()
    test_load_home_minute_intervals()
    test_load_home_with_dataid()
    test_load_home_missing_column()
    test_load_home_integration_with_cost_engine()
    print("\nAll sanity checks passed.")
