"""Ingest a Power to Choose export (xlsx for a ZIP, or the all-offers CSV)
into draft Contract records.

The PTC export gives us most of what we need WITHOUT parsing PDFs:
rep, plan, rate type, term, cancellation fee, advertised prices, and the
Fact Sheet (EFL) URL. What it does NOT reliably give:
  - the underlying energy charge / base charge split
  - exact bill-credit thresholds and amounts (the 'Min Usage Fees/Credits'
    flag is unreliable -- all False in the 78664 export despite real
    credit plans existing, e.g. 'SmartGreen 12 $200 Bill Credit')

So: use this to build the candidate list and advertised-price sanity checks,
then pull the EFL PDFs ONLY for the handful of plans selected for the report
and hand-verify their credit/TOU structure.

Columns differ between the two exports; this handles the xlsx (per-ZIP) layout.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .models import Contract, RateType


# Map PTC xlsx columns -> our fields
_XLSX_COLS = {
    "RepCompany": "rep_name",
    "Plan Name": "plan_name",
    "Rate Type": "rate_type",
    "Term Value": "term_months",
    "Price/kWh 500": "avg_price_500",
    "Price/kWh 1000": "avg_price_1000",
    "Price/kWh 2000": "avg_price_2000",
    "Fact Sheet": "efl_source_file",   # actually a URL here
}


# Map the all-offers CSV bracketed columns -> our fields.
# This is the format from /en-us/Plan/ExportToCsv (and Wayback snapshots of it).
_CSV_COLS = {
    "[RepCompany]": "rep_name",
    "[Product]": "plan_name",
    "[RateType]": "rate_type",
    "[TermValue]": "term_months",
    "[kwh500]": "avg_price_500",
    "[kwh1000]": "avg_price_1000",
    "[kwh2000]": "avg_price_2000",
    "[CancelFee]": "etf",
    "[FactsURL]": "efl_source_file",
    "[TduCompanyName]": "tdu_company",
    "[TimeOfUse]": "time_of_use",
}


def load_ptc_all_offers_csv(
    path: str | Path,
    tdu_filter: str | None = None,
) -> pd.DataFrame:
    """Load the statewide all-offers CSV (current export OR a Wayback snapshot).

    Unlike the per-ZIP xlsx, this is every active offer statewide with bracketed
    column names. Optionally filter to one TDU (e.g. 'ONCOR') to match a ZIP's
    delivery territory. Crucially, this format includes Variable/Indexed/TOU
    plans -- exactly the pre-Uri products missing from today's marketplace.

    Adds the same price-curve diagnostics as the xlsx loader for consistency.
    """
    df = pd.read_csv(path, dtype=str)
    # numeric coercion for the price/term/fee columns
    for col in ["[kwh500]", "[kwh1000]", "[kwh2000]", "[TermValue]", "[CancelFee]"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if tdu_filter:
        df = df[df["[TduCompanyName]"].str.contains(tdu_filter, case=False, na=False)].copy()
    df["drop_500_1000"] = df["[kwh500]"] - df["[kwh1000]"]
    df["drop_1000_2000"] = df["[kwh1000]"] - df["[kwh2000]"]
    df["likely_structure"] = "flat"
    df.loc[df["drop_500_1000"] > 0.008, "likely_structure"] = "credit_or_tou"
    if "[TimeOfUse]" in df.columns:
        df.loc[df["[TimeOfUse]"].astype(str).str.lower() == "true", "likely_structure"] = "time_of_use"
    df.loc[df["[RateType]"].str.contains("Variable|Indexed", case=False, na=False),
           "likely_structure"] = df["[RateType]"].str.lower()
    return df


def all_offers_to_contracts(df: pd.DataFrame) -> list[Contract]:
    """Convert all-offers CSV rows to DRAFT Contracts (advertised prices only)."""
    contracts = []
    for _, r in df.iterrows():
        rate = str(r.get("[RateType]", "")).lower()
        rate_type = (RateType.FIXED if "fix" in rate else
                     RateType.VARIABLE if "var" in rate else
                     RateType.INDEXED if "index" in rate else RateType.FIXED)
        p1000 = r.get("[kwh1000]")
        contracts.append(Contract(
            rep_name=str(r.get("[RepCompany]", "")),
            plan_name=str(r.get("[Product]", "")),
            rate_type=rate_type,
            term_months=int(r["[TermValue]"]) if pd.notna(r.get("[TermValue]")) else 0,
            energy_charge_per_kwh=float(p1000) if pd.notna(p1000) else 0.0,
            avg_price_500=float(r["[kwh500]"]) if pd.notna(r.get("[kwh500]")) else None,
            avg_price_1000=float(p1000) if pd.notna(p1000) else None,
            avg_price_2000=float(r["[kwh2000]"]) if pd.notna(r.get("[kwh2000]")) else None,
            etf=float(r["[CancelFee]"]) if pd.notna(r.get("[CancelFee]")) else 0.0,
            efl_source_file=str(r.get("[FactsURL]", "")),
        ))
    return contracts


def load_ptc_xlsx(path: str | Path, zip_code: str = "78664") -> pd.DataFrame:
    """Load the per-ZIP PTC xlsx into a tidy DataFrame with EFL URLs.

    Adds price-curve diagnostics used to flag likely bill-credit / TOU plans:
    a steep 500->1000 drop in advertised c/kWh is the bill-credit signature.
    """
    df = pd.read_excel(path)
    df = df[df["ZipCode"].astype(str) == str(zip_code)].copy()
    df["drop_500_1000"] = df["Price/kWh 500"] - df["Price/kWh 1000"]
    df["drop_1000_2000"] = df["Price/kWh 1000"] - df["Price/kWh 2000"]
    # heuristic label; NOT authoritative -- verify against the EFL
    df["likely_structure"] = "flat"
    df.loc[df["drop_500_1000"] > 0.008, "likely_structure"] = "credit_or_tou"
    df.loc[df["Time Of Use"] == True, "likely_structure"] = "time_of_use"
    return df


def to_contracts(df: pd.DataFrame, zip_code: str = "78664") -> list[Contract]:
    """Convert PTC rows to DRAFT Contracts (advertised prices only).

    These are incomplete on purpose: energy_charge_per_kwh is left at the
    advertised 1000-kWh price as a rough stand-in, and bill credits are EMPTY
    until filled from the EFL. Do not use for final numbers unverified.
    """
    contracts = []
    for _, r in df.iterrows():
        rate = str(r["Rate Type"]).lower()
        rate_type = RateType.FIXED if "fix" in rate else (
            RateType.VARIABLE if "var" in rate else RateType.INDEXED
        )
        contracts.append(Contract(
            rep_name=str(r["RepCompany"]),
            plan_name=str(r["Plan Name"]),
            rate_type=rate_type,
            term_months=int(r["Term Value"]) if pd.notna(r["Term Value"]) else 0,
            # rough stand-in; replace with true energy charge from EFL:
            energy_charge_per_kwh=float(r["Price/kWh 1000"]),
            avg_price_500=float(r["Price/kWh 500"]),
            avg_price_1000=float(r["Price/kWh 1000"]),
            avg_price_2000=float(r["Price/kWh 2000"]),
            efl_source_file=str(r.get("Fact Sheet", "")),
            zip_code=zip_code,
        ))
    return contracts
