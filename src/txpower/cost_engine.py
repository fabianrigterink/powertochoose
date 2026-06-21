"""Cost engine: turn a consumption time series + a contract into a simulated bill.

The whole credibility of the project rests on an apples-to-apples stack:

    total = energy_component + tdu_component + base_charges - bill_credits

where, for every plan type, the TDU delivery layer is added the SAME way.
The only thing that differs between a fixed and an indexed plan is how the
energy_component is priced.

Consumption is expected as a pandas Series indexed by timestamp, in kWh per
interval (NOT kW). For Pecan Street that means converting average power per
minute into energy per interval before calling this.
"""
from __future__ import annotations

import pandas as pd

from .models import Contract, RateType


def _energy_component_fixed(usage_kwh: pd.Series, contract: Contract) -> float:
    """Flat REP energy charge applied to total kWh."""
    return float(usage_kwh.sum()) * contract.energy_charge_per_kwh


def _energy_component_indexed(
    usage_kwh: pd.Series,
    spp_per_kwh: pd.Series,
    contract: Contract,
) -> float:
    """Wholesale pass-through: each interval's kWh billed at that interval's SPP.

    spp_per_kwh must be aligned to the same index as usage_kwh (resample/ffill
    upstream). Units: $/kWh. ERCOT publishes $/MWh, so divide by 1000 before
    passing in. An optional retailer adder ($/kWh) is added on top.
    """
    aligned = usage_kwh.to_frame("kwh").join(spp_per_kwh.rename("spp"), how="inner")
    adder = contract.indexed_adder_per_kwh or 0.0
    return float(((aligned["spp"] + adder) * aligned["kwh"]).sum())


def _energy_component_tou(usage_kwh: pd.Series, contract: Contract) -> float:
    """Time-of-use: each interval billed at its hour's rate from tou_schedule.

    Each timestamp's hour (0-23) is matched against tou_schedule periods.
    If no period matches an hour, that usage is not charged (should not happen
    if tou_schedule is complete; log a warning in production).
    """
    total_cost = 0.0
    for ts, kwh in usage_kwh.items():
        hour = ts.hour
        matched_rate = None
        for period in contract.tou_schedule:
            if period.hour_start <= period.hour_end:
                # Normal period (no wrap-around)
                if period.hour_start <= hour < period.hour_end:
                    matched_rate = period.rate_per_kwh
                    break
            else:
                # Wrap-around period (e.g., 21-6 means 9pm-6am)
                if hour >= period.hour_start or hour < period.hour_end:
                    matched_rate = period.rate_per_kwh
                    break
        if matched_rate is not None:
            total_cost += kwh * matched_rate
    return total_cost



def _tdu_component(usage_kwh: pd.Series, contract: Contract) -> float:
    if contract.tdu is None:
        return 0.0
    total_kwh = float(usage_kwh.sum())
    return contract.tdu.fixed_monthly + contract.tdu.per_kwh * total_kwh


def _credit_component(usage_kwh: pd.Series, contract: Contract) -> float:
    """Sum of applicable bill credits given the month's total usage."""
    total_kwh = float(usage_kwh.sum())
    return sum(c.amount for c in contract.bill_credits if c.applies(total_kwh))


def simulate_month(
    usage_kwh: pd.Series,
    contract: Contract,
    spp_per_kwh: pd.Series | None = None,
) -> dict:
    """Simulate one month's bill. Returns a breakdown dict.

    usage_kwh : kWh per interval, timestamp-indexed, for ONE billing month.
    spp_per_kwh : required only for indexed contracts; $/kWh per interval.
    """
    total_kwh = float(usage_kwh.sum())

    if contract.rate_type == RateType.INDEXED:
        if spp_per_kwh is None:
            raise ValueError(
                f"Contract '{contract.plan_name}' is indexed but no SPP series given."
            )
        energy = _energy_component_indexed(usage_kwh, spp_per_kwh, contract)
    elif contract.rate_type == RateType.TOU:
        energy = _energy_component_tou(usage_kwh, contract)
    else:
        # fixed and (simple) variable both use the flat energy charge here;
        # a true variable plan would vary energy_charge_per_kwh by month.
        energy = _energy_component_fixed(usage_kwh, contract)

    tdu = _tdu_component(usage_kwh, contract)
    base = contract.base_monthly_charge
    credits = _credit_component(usage_kwh, contract)

    total = energy + tdu + base - credits
    return {
        "plan_name": contract.plan_name,
        "rep_name": contract.rep_name,
        "rate_type": contract.rate_type.value,
        "total_kwh": total_kwh,
        "energy": round(energy, 2),
        "tdu": round(tdu, 2),
        "base": round(base, 2),
        "credits": round(-credits, 2),
        "total": round(total, 2),
        "effective_per_kwh": round(total / total_kwh, 4) if total_kwh else None,
    }


def simulate_many(
    usage_kwh: pd.Series,
    contracts: list[Contract],
    spp_per_kwh: pd.Series | None = None,
) -> pd.DataFrame:
    """Simulate a set of contracts against one consumption month."""
    rows = [simulate_month(usage_kwh, c, spp_per_kwh) for c in contracts]
    return pd.DataFrame(rows).sort_values("total").reset_index(drop=True)
