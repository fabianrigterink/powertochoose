"""Data models for Texas retail electricity contracts.

These mirror the structure of a PUCT-mandated Electricity Facts Label (EFL).
Everything the cost engine needs to simulate a bill lives here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RateType(str, Enum):
    FIXED = "fixed"
    VARIABLE = "variable"
    INDEXED = "indexed"  # passes through wholesale (ERCOT SPP)-linked pricing


@dataclass
class BillCredit:
    """A usage-band bill credit.

    Applies `amount` (dollars, subtracted from the bill) when monthly usage
    in kWh falls in [threshold_min, threshold_max). Use None for an open end.

    Example: a $100 credit for usage between 1000 and 2000 kWh is
        BillCredit(amount=100.0, threshold_min=1000, threshold_max=2000)
    """
    amount: float
    threshold_min: float = 0.0
    threshold_max: Optional[float] = None  # None = no upper bound

    def applies(self, monthly_kwh: float) -> bool:
        lo = self.threshold_min
        hi = self.threshold_max if self.threshold_max is not None else float("inf")
        return lo <= monthly_kwh < hi


@dataclass
class TduCharges:
    """Transmission/Distribution Utility delivery charges (pass-through).

    These are the same regardless of retailer, set by the TDU (Oncor,
    CenterPoint, AEP, etc.). EFLs list them so customers see the all-in rate.
    """
    name: str                  # e.g. "Oncor"
    fixed_monthly: float       # $/month
    per_kwh: float             # $/kWh


@dataclass
class Contract:
    """A single retail plan, parsed from one EFL."""
    rep_name: str              # Retail Electric Provider
    plan_name: str
    rate_type: RateType
    term_months: int

    # Energy component
    energy_charge_per_kwh: float          # $/kWh (REP's energy charge)
    base_monthly_charge: float = 0.0      # $/month (REP base/minimum-usage fee)

    # Usage-band credits (the tricky part of many "teaser" plans)
    bill_credits: list[BillCredit] = field(default_factory=list)

    # TDU pass-through (store the snapshot used, for reproducibility)
    tdu: Optional[TduCharges] = None

    # For indexed plans: an adder on top of wholesale SPP, in $/kWh
    indexed_adder_per_kwh: Optional[float] = None

    # Contract metadata
    etf: float = 0.0                       # early termination fee ($)
    # Advertised average prices from the EFL table (cents/kWh) for sanity checks
    avg_price_500: Optional[float] = None
    avg_price_1000: Optional[float] = None
    avg_price_2000: Optional[float] = None

    # Provenance
    efl_source_file: Optional[str] = None
    zip_code: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.rate_type, str):
            self.rate_type = RateType(self.rate_type)
