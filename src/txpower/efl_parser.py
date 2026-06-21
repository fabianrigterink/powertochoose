"""Parse PUCT Electricity Facts Labels (EFLs) into structured Contract records.

Built and VALIDATED against the real standardized EFL format (verified: the
parsed components reconstruct the EFL's own advertised 500/1000/2000 average
prices exactly). The PUCT format is consistent enough that regexes on the
extracted text are reliable for the core pricing fields:

    - SmartEnergy Fixed/Energy Charge   -> energy_charge_per_kwh
    - Base Charge per billing cycle      -> base_monthly_charge
    - Oncor pass thru Delivery Charges   -> TDU fixed + per-kWh (era-correct!)
    - early termination fee              -> etf
    - Contract Term / Type of Product    -> term_months / rate_type

IMPORTANT caveats (still require human eyes for plans selected for the report):
  - "Bill credit" plans come in TWO flavors: (a) usage-band credits baked into
    pricing, which DO move the advertised averages, vs (b) promotional sign-up
    credits described only in the Terms of Service, which do NOT appear in the
    EFL pricing chart. Detect (a) when reconstructed avg != stated avg.
  - Time-of-use plans have multiple energy charges (peak/off-peak/free) that a
    single-rate regex won't capture; handle per-plan.

A handy self-check: reconstruct the 1000-kWh average from parsed fields and
compare to the stated value. A mismatch flags a credit/TOU structure to verify.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import Contract, RateType, TduCharges


def extract_text(pdf_path: str | Path) -> str:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def _f(pattern: str, text: str, group: int = 1):
    m = re.search(pattern, text)
    return float(m.group(group)) if m else None


def parse_efl_fields(text: str) -> dict:
    """Extract the core pricing fields from EFL text. Cents stay as cents here."""
    out: dict = {}
    m = re.search(
        r"Average price per kWh\s+([\d.]+)\s*¢\s+([\d.]+)\s*¢\s+([\d.]+)\s*¢", text
    )
    if m:
        out["avg_price_500"] = float(m.group(1))
        out["avg_price_1000"] = float(m.group(2))
        out["avg_price_2000"] = float(m.group(3))
    out["energy_charge_cents_per_kwh"] = _f(
        r"(?:Fixed Charge|Energy Charge)\s+([\d.]+)\s*¢\s*per kWh", text
    )
    out["base_monthly_charge"] = _f(
        r"Base Charge\s*\$?\s*([\d.]+)\s*per billing cycle", text
    )
    out["tdu_fixed_monthly"] = _f(
        r"Delivery Charges:\s*\$\s*([\d.]+)\s*per billing cycle", text
    )
    out["tdu_cents_per_kwh"] = _f(
        r"Delivery Charges:\s*([\d.]+)\s*¢\s*per kWh", text
    )
    out["etf_per_month"] = _f(r"\$\s*([\d.]+)\s*early termination fee", text)
    m = re.search(r"Contract Term\s+(\d+)\s*monthly billing cycles", text)
    out["term_months"] = int(m.group(1)) if m else None
    m = re.search(r"Type of Product\s+(Fixed Rate|Variable Rate|Indexed)", text)
    out["rate_type"] = m.group(1) if m else None
    return out


def reconstruct_avg_price(fields: dict, usage_kwh: float):
    """Rebuild the EFL average c/kWh from parsed components (no credits).

    If this disagrees with the stated avg at that usage, a usage-band credit
    or TOU structure is present -> flag for manual verification.
    """
    needed = ["energy_charge_cents_per_kwh", "base_monthly_charge",
              "tdu_fixed_monthly", "tdu_cents_per_kwh"]
    if any(fields.get(k) is None for k in needed):
        return None
    total_cents = (
        fields["energy_charge_cents_per_kwh"] * usage_kwh
        + fields["base_monthly_charge"] * 100
        + fields["tdu_cents_per_kwh"] * usage_kwh
        + fields["tdu_fixed_monthly"] * 100
    )
    return total_cents / usage_kwh


def parse_efl(pdf_path, rep_name: str = "", plan_name: str = "") -> Contract:
    """Parse one EFL PDF into a Contract (cents converted to dollars)."""
    text = extract_text(pdf_path)
    f = parse_efl_fields(text)

    rate_map = {"Fixed Rate": RateType.FIXED, "Variable Rate": RateType.VARIABLE,
                "Indexed": RateType.INDEXED}
    tdu = None
    if f.get("tdu_fixed_monthly") is not None and f.get("tdu_cents_per_kwh") is not None:
        tdu = TduCharges("Oncor", f["tdu_fixed_monthly"], f["tdu_cents_per_kwh"] / 100.0)

    return Contract(
        rep_name=rep_name,
        plan_name=plan_name,
        rate_type=rate_map.get(f.get("rate_type"), RateType.FIXED),
        term_months=f.get("term_months") or 0,
        energy_charge_per_kwh=(f.get("energy_charge_cents_per_kwh") or 0) / 100.0,
        base_monthly_charge=f.get("base_monthly_charge") or 0.0,
        tdu=tdu,
        etf=f.get("etf_per_month") or 0.0,
        avg_price_500=f.get("avg_price_500"),
        avg_price_1000=f.get("avg_price_1000"),
        avg_price_2000=f.get("avg_price_2000"),
        efl_source_file=str(pdf_path),
    )
