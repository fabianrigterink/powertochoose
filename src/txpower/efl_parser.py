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

from .models import Contract, RateType, TduCharges, TouPeriod


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


def _parse_12hr(time_str: str) -> int | None:
    """Convert '2pm', '2 pm', '2:00pm', '6am', etc. to 0-23 hour."""
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_str.strip().lower())
    if not m:
        return None
    hour = int(m.group(1))
    is_pm = m.group(3) == "pm"
    if hour == 12:
        return 0 if not is_pm else 12
    return (hour + 12) if is_pm else hour


def parse_tou_schedule(text: str) -> list[TouPeriod]:
    """Extract time-of-use rate periods from EFL text.

    Looks for patterns like:
      "Peak (2pm-9pm): 12.5¢/kWh"
      "Off-Peak (6am-2pm): 8.3¢/kWh"
      "Free Nights (10pm-6am): 0¢/kWh"

    Returns a list of TouPeriod objects sorted by hour_start.
    """
    periods = []
    # Match full time range: e.g., "2:00 PM - 9:00 PM" or "6am - 2 pm" or "10pm-6am"
    # Groups: (1) start hour, (2) start am/pm, (3) end hour, (4) end am/pm
    hour_range_pattern = r"(\d{1,2})(?::\d{2})?\s*(am|pm)\s*(?:–|to|-)\s*(\d{1,2})(?::\d{2})?\s*(am|pm)"
    rate_pattern = r"([\d.]+)\s*(?:(¢|cents)|(\$)?)(?:\s*(?:/|per))?\s*kWh"

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        hour_m = re.search(hour_range_pattern, line, re.IGNORECASE)
        rate_m = re.search(rate_pattern, line)
        if hour_m and rate_m:
            start_hour_str = hour_m.group(1)
            start_am_pm = hour_m.group(2).lower()
            end_hour_str = hour_m.group(3)
            end_am_pm = hour_m.group(4).lower()

            start_str = f"{start_hour_str}{start_am_pm}"
            end_str = f"{end_hour_str}{end_am_pm}"
            start_hour = _parse_12hr(start_str)
            end_hour = _parse_12hr(end_str)
            rate_value = float(rate_m.group(1))
            # If in cents (¢ or cents), convert to dollars; if in $, already in dollars
            if rate_m.group(2):  # matched ¢ or cents
                rate_dollars = rate_value / 100.0
            else:  # matched $ or nothing (assume cents if no currency marker)
                rate_dollars = rate_value / 100.0 if not rate_m.group(3) else rate_value
            if start_hour is not None and end_hour is not None:
                periods.append(TouPeriod(start_hour, end_hour, rate_dollars))

    return sorted(periods, key=lambda p: p.hour_start)


def reconstruct_avg_price(fields: dict, usage_kwh: float) -> float | None:
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


def estimate_bill_credit_impact(fields: dict, usage_kwh: float) -> dict | None:
    """Estimate total bill credit by comparing reconstructed vs stated average.

    If a mismatch exists, returns a dict with estimated_credit_cents showing the
    per-kWh credit effect (total credit / usage_kwh). Returns None if no mismatch.

    Usage-band credits appear in pricing tables when the advertised average is
    lower than base rates would produce. The difference indicates credits at that
    usage level. Thresholds and amounts require manual extraction from EFL prose.
    """
    reconstructed = reconstruct_avg_price(fields, usage_kwh)
    if not reconstructed or not fields.get(f"avg_price_{int(usage_kwh)}"):
        return None

    stated = fields[f"avg_price_{int(usage_kwh)}"]
    mismatch_cents = reconstructed - stated
    if abs(mismatch_cents) < 0.5:
        return None

    total_bill_reconstructed = reconstructed * usage_kwh
    total_bill_stated = stated * usage_kwh
    estimated_credit_dollars = (total_bill_reconstructed - total_bill_stated) / 100
    return {
        "estimated_credit_dollars": estimated_credit_dollars,
        "credit_per_kwh_cents": mismatch_cents,
        "usage_level": usage_kwh,
    }


def parse_efl(pdf_path, rep_name: str = "", plan_name: str = "") -> Contract:
    """Parse one EFL PDF into a Contract (cents converted to dollars)."""
    text = extract_text(pdf_path)
    f = parse_efl_fields(text)

    rate_map = {"Fixed Rate": RateType.FIXED, "Variable Rate": RateType.VARIABLE,
                "Indexed": RateType.INDEXED}
    tdu = None
    if f.get("tdu_fixed_monthly") is not None and f.get("tdu_cents_per_kwh") is not None:
        tdu = TduCharges("Oncor", f["tdu_fixed_monthly"], f["tdu_cents_per_kwh"] / 100.0)

    # Detect TOU plans by checking if reconstructed avg mismatches stated avg
    rate_type = rate_map.get(f.get("rate_type"), RateType.FIXED)
    tou_schedule = []
    bill_credits = []
    has_bill_credit = False

    if f.get("avg_price_1000") and rate_type == RateType.FIXED:
        reconstructed = reconstruct_avg_price(f, 1000)
        if reconstructed and abs(reconstructed - f["avg_price_1000"]) > 0.5:
            # Check if it's TOU (multiple rate periods) or bill credits (pricing discount)
            tou_schedule = parse_tou_schedule(text)
            if tou_schedule:
                rate_type = RateType.TOU
            else:
                has_bill_credit = True

    return Contract(
        rep_name=rep_name,
        plan_name=plan_name,
        rate_type=rate_type,
        term_months=f.get("term_months") or 0,
        energy_charge_per_kwh=(f.get("energy_charge_cents_per_kwh") or 0) / 100.0,
        base_monthly_charge=f.get("base_monthly_charge") or 0.0,
        tdu=tdu,
        tou_schedule=tou_schedule,
        bill_credits=bill_credits,
        etf=f.get("etf_per_month") or 0.0,
        avg_price_500=f.get("avg_price_500"),
        avg_price_1000=f.get("avg_price_1000"),
        avg_price_2000=f.get("avg_price_2000"),
        efl_source_file=str(pdf_path),
    )
