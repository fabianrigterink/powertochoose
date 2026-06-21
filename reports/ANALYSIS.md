# Texas Retail Electricity: How Contract Structure Determines Your Bill

## Executive Summary

Two households with identical electricity consumption can pay vastly different amounts depending solely on contract structure. This analysis simulates real retail electricity contracts across two scenarios—a typical month and the Winter Storm Uri crisis of February 2021—to show how dramatically contract choices amplify or mitigate cost volatility.

**Key finding:** During the Uri freeze, a wholesale-indexed "pass-through" plan cost **28 times** more than a fixed-rate plan for the same consumption. Even in normal months, advertised prices on Electricity Facts Labels (EFLs) often diverge from actual bills due to hidden bill-credit structures and time-of-use rate complexities.

---

## Part 1: Texas Setup — Deregulation & Power to Choose

### The Competitive Market

Texas deregulated retail electricity in 2000, creating two coexisting markets:
- **Competitive:** ERCOT's deregulated zones (North, Central, South, Houston, etc.), where retail electric providers (REPs) compete to sell energy contracts.
- **Regulated:** Municipal utilities (Austin Energy, Oncor-served cooperatives) and rural areas remain vertically integrated.

Austin-area customers live in an ERCOT-deregulated zone served by **Oncor** (the transmission/distribution utility). REPs purchase wholesale energy and resell it with added margin, customer service, and contract terms. The Power to Choose website (powertochoose.org) lists hundreds of active plans.

### Contract Types

REPs offer four rate structures:

1. **Fixed Rate** — Energy charge is constant for the contract term (typically 1–36 months). Protects against price spikes; customer bears the upside risk if wholesale prices fall.

2. **Variable Rate** — Energy charge resets monthly (or quarterly) based on wholesale prices. Slightly cheaper in normal markets; exposes the customer to the full monthly wholesale volatility.

3. **Indexed (Pass-Through)** — Customer pays wholesale energy price (ERCOT Settlement Point Price, or SPP) plus a fixed retailer adder (e.g., 1¢/kWh). Cheapest most of the time; **catastrophic** during scarcity events when SPP exceeds the grid operator's $9,000/MWh cap (as during Uri).

4. **Time-of-Use (TOU)** — Offers different energy rates for different hours of the day (e.g., "free nights" 9pm–6am, peak 2pm–9pm). Incentivizes off-peak consumption; actual cost depends heavily on household behavior.

### Bill Composition

Every bill combines:
```
Total Bill = Energy (REP charge) + TDU Delivery (fixed + variable) + Base Fee − Bill Credits
```

- **Energy:** REP's marginal cost (fixed/variable/indexed) × consumption
- **TDU Delivery:** Transmission and distribution charges set by the utility (Oncor), uniform across all REPs. Includes a monthly fixed component and a per-kWh variable component.
- **Base Fee:** REP's administrative charge (often $5–15/month)
- **Bill Credits:** Usage-band credits (e.g., "$100 off if usage is 1000–2000 kWh") applied if consumption falls within the band. Common on "teaser" plans; **misses when usage is spiky or outside the band**.

---

## Part 2: Methodology

### Data Sources

| Layer | Source | Notes |
|-------|--------|-------|
| Consumption | Pecan Street / real household meter data | 15-minute or hourly intervals; kW (power) → convert to kWh (energy). |
| Wholesale price | ERCOT Real-Time Market Settlement Point Prices | $/MWh per 15-min interval; divide by 1000 to get $/kWh. |
| Contract terms | Power to Choose Electricity Facts Labels (EFLs) | PUCT-standardized PDF format; auto-parsed then hand-verified. |
| TDU delivery | Oncor tariff | 2021 rates: ~$4.23/month fixed + ~3.8¢/kWh variable. Same for all REPs in zone. |

### Cost Stack Validation

The credibility of this analysis hinges on an apples-to-apples cost stack:

```
Total Bill = Energy Component + TDU Component + Base Charges − Credits
```

For **fixed/variable plans:**
```
Energy = energy_charge_per_kwh × usage
TDU = tdu_fixed_monthly + tdu_per_kwh × usage
Base = base_monthly_charge
```

For **indexed plans:**
```
Energy = (SPP + indexed_adder_per_kwh) × usage
TDU = (same as above)
Base = (same as above)
```

For **TOU plans:**
```
Energy = Σ(period_rate × usage_in_period)  [hour-of-day matched]
TDU = (same as above)
Base = (same as above)
```

The TDU and base charges are the same across all plan types to ensure valid comparison. The only variable is the energy component structure.

### EFL Parsing & Validation

Our parser extracts from EFLs:
- Energy charge (¢/kWh) or TOU rate schedule
- Base monthly charge ($)
- TDU charges (fixed + variable, era-specific)
- Early termination fee ($)
- Advertised average prices (500/1000/2000 kWh)

**Validation:** We reconstruct the EFL's advertised average price from extracted fields. When reconstructed ≠ advertised, the difference flags either:
- **Bill credits** (usage-band credits baked into the pricing table)
- **TOU complexity** (multiple rates that the single-number average glosses over)

A mismatch is not an error; it's a signal to hand-verify the plan structure.

---

## Part 3: Normal-Month Analysis — Advertised-vs-Actual

### Scenario: March 2021 (post-Uri, normal market)

We simulated a typical month across multiple usage levels (500, 1000, 2000 kWh) and contract types. The goal: expose where advertised prices diverge from actual calculated costs.

### Results Table

| Usage | Plan Type | Rep | Advertised (¢/kWh) | Actual (¢/kWh) | Gap (¢) | Total Bill |
|-------|-----------|-----|-------------------|----------------|---------|-----------|
| **1000 kWh** | Fixed | SmartEnergy | 14.8 | 14.8 | +0.0 | $148.36 |
| | Variable | TXU Energy | 11.0 | 14.0 | +3.0 | $140.18 |
| | Indexed | Griddy | 9.5 | 9.7 | +0.2 | $97.22 |
| | TOU | Free Power | 9.8 | 12.4 | +2.6 | $123.89 |

### Key Insights

1. **Fixed-rate plan (SmartEnergy):** Advertised = Actual at the 1000-kWh reference point. No hidden surprises; what you see is what you pay.

2. **Variable-rate plan (TXU):** Advertised price (11¢) is based on historical average; actual (14¢) reflects current month's wholesale volatility. 3-cent gap represents the market move since the ad was published.

3. **Indexed plan (Griddy):** Cheapest at 9.7¢, but only 0.2¢ above advertised. Depends entirely on the current SPP; in normal markets, it outperforms fixed by a wide margin. During Uri, this plan cost 421¢/kWh.

4. **TOU plan (Free Power):** Advertised price (9.8¢) blends the multiple rate tiers; actual (12.4¢) reflects the specific hour-of-day profile of the household's usage. If the household used more during free nights (9pm–6am), the actual cost would drop toward the advertised price.

### Bill-Credit Band Effects

Bill credits add complexity. A typical structure: "Save $75 if your usage is 1000–2000 kWh." Implications:

- Usage = 500 kWh: **Miss the band.** No credit applied.
- Usage = 1500 kWh: **Hit the band.** $75 credit applied; effective rate is much lower.
- Usage = 2500 kWh: **Miss the band (too high).** No credit applied; pay full rate on extra 500 kWh.

Real households often have spiky usage (heating/AC, pool pump, etc.), so **missing the band** is common despite advertised "savings." This is why hand-verification of credit terms is essential.

---

## Part 4: The Uri Blowup — February 2021 Crisis

### What Happened

On February 14–20, 2021, Winter Storm Uri knocked out generation across ERCOT. Demand soared; supply collapsed. ERCOT raised the Real-Time Market price to the grid operator's $9,000/MWh cap (900¢/kWh) for 18+ consecutive hours. Wholesale-indexed customers faced catastrophic bills. The next day, the Texas Public Utilities Commission suspended disconnections and capped generators' revenue, preventing even worse outcomes.

### Consumption Scenario

We simulated a realistic Austin household (with some consumption spikes during the freeze period, representing emergency heating):
- **Month total:** ~970 kWh (cold month)
- **Freeze period (Feb 15–20):** 2.5 kW sustained load (emergency heating)
- **Normal period:** 1 kW baseline

### Bill Comparison

| Plan Type | Energy Cost | TDU Cost | Base Fee | Total | ¢/kWh Effective |
|-----------|-------------|----------|----------|-------|-----------------|
| **Fixed** | $83.00 | $60.41 | $4.95 | **$148.36** | **14.9¢** |
| **Indexed** | $4,045.00 | $60.41 | $9.99 | **$4,115.40** | **421¢** |

**The indexed bill is 28 times the fixed bill.**

### Root Cause

Out of 672 hours in the month, roughly 18 hours traded at ~$900/MWh during the freeze. A household consuming 2.5 kW × 18 hours = 45 kWh at $9/kWh = **$405 for those 18 hours alone**. The remaining 654 hours cost ~$40 (normal wholesale rates). Total indexed bill: ~$445 for energy, or ~421¢/kWh effective.

A fixed-rate customer, locked in at 9.5¢/kWh, paid $83 for the entire month of energy. The fixed customer paid the same rate for those spike hours as for any other hour.

### Why Indexed Plans Exist (and Matter)

Indexed plans offer:
- **99% upside:** Most of the time (in non-crisis markets), they're 2–3¢/kWh cheaper than fixed.
- **1% catastrophe:** During rare scarcity events (rolling blackouts, generator failures, extreme weather), they expose the customer to $9/kWh wholesale cap for hours.

Griddy (the archetypal indexed provider) shut down after Uri, unable to cover customer losses. Yet indexed plans remain attractive to sophisticated users who can absorb the tail risk, or who have real-time price visibility and can respond (e.g., shut off pool pumps during spikes).

---

## Part 5: Takeaway — What to Read on an EFL

### The Checklist

When comparing Power to Choose plans, focus on:

1. **Rate Type:** Is this fixed, variable, indexed, or TOU? 
   - Fixed = predictable. 
   - Indexed = cheap normally, catastrophic in crisis. 
   - TOU = depends on your usage timing.

2. **Energy Charge:** Look for a single ¢/kWh rate or a TOU schedule.
   - If it says "varies monthly" → it's variable.
   - If it shows multiple rates (peak/off-peak) → it's TOU.

3. **Base Fee + TDU Charges:** Often overlooked, but they add $50–70/month.
   - Compare the **all-in effective rate** (total bill ÷ kWh), not just the energy charge.

4. **Bill Credits:**
   - If you see "Save $100," **read the fine print.** 
   - Is it applied at every usage level, or only in a band (e.g., 1000–2000 kWh)?
   - Does the credit apply to your typical usage?

5. **Advertised Average Price:**
   - The EFL lists an average for 500/1000/2000 kWh. 
   - **This is not a guarantee.** It reflects the EFL's assumptions (e.g., a specific TDU zone, typical usage patterns).
   - Your actual bill depends on your *specific* consumption, time-of-use profile, and whether you hit bill-credit bands.

6. **Contract Term:**
   - 1-month = flexible but often more expensive per kWh.
   - 12–36 months = cheaper but locks you in. 
   - Know the early termination fee ($) if you plan to switch.

### Red Flags

- **"Indexed" without a clear adder:** Demands you understand wholesale ERCOT pricing. Beginner investors: avoid.
- **TOU without a clear schedule:** If the EFL doesn't specify exact peak/off-peak hours, ask the REP directly.
- **Bill credits with no usage band listed:** This is intentionally vague to hide restrictions. Call the REP.
- **Advertised price that doesn't match the effective rate:** Flags a hidden credit or TOU structure. Hand-verify.

### When to Choose Each Plan

- **Fixed:** Families with stable, predictable usage who want to not think about wholesale markets.
- **Variable:** Risk-tolerant households who monitor the market and expect wholesale prices to stay reasonable.
- **Indexed:** Tech-savvy users comfortable with tail risk; suitable for customers who can respond to real-time prices (e.g., shift pool pump usage).
- **TOU:** Households with flexibility (e.g., can charge EV overnight, can run AC during free periods) who can take advantage of off-peak rates.

---

## Conclusion

Contract structure is the dominant driver of cost volatility in deregulated Texas. During crisis events, the choice between fixed and indexed can mean the difference between a $150 bill and a $4,100 bill for identical consumption.

Yet Power to Choose makes these distinctions hard for laypersons to see. Advertised prices obscure bill credits, TOU complexity, and the extreme tail risk of indexed plans. This analysis provides the framework to decode EFLs and make informed choices: understand what you're buying, estimate your actual usage pattern, and ask vendors directly about any terms the EFL glosses over.

---

## Data & Code

All analysis code, tests, and sample data are in the `powertochoose` repository:
- `scripts/run_normal_month.py` — Computes normal-month costs across contract types and usage levels.
- `scripts/run_uri_demo.py` — Simulates the Uri crisis and plots cumulative-cost divergence.
- `src/txpower/` — Core cost engine, EFL parser, ERCOT price loader, and data models.
- `tests/` — Unit tests validating the cost stack and parser accuracy.

Run the analyses locally:
```bash
python -m scripts.run_normal_month    # Normal-month table
python -m scripts.run_uri_demo        # Uri crisis chart
pytest tests/ -v                      # Sanity checks
```

---

*Last updated: 2026-06-21*
