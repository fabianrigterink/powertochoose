# Data Sources & Provenance

This document explains where to find and how to regenerate the real data used in the analysis.

## ERCOT Wholesale Prices (Settlement Point Prices)

### Source
**ENGIE Resources Historical Pricing Data**  
https://www.engieresources.com/historical-pricing-data/

### Download Instructions
1. Go to https://www.engieresources.com/historical-pricing-data/
2. Select:
   - **Market:** ERCOT
   - **Settlement Point:** LZ_NORTH (Round Rock 78664 / Austin area)
   - **Product:** HourlyRT (Hourly Real-Time)
   - **Date Range:** Select desired month (e.g., 02/01-02/28/2021 for Uri analysis)
3. Click **Download** → saves as CSV (e.g., `ERCOT_Hourly_Real_Time_YYYY-MM-DD.csv`)

### File Location
Place the downloaded CSV in: **`data/raw/`**

The scripts auto-detect it via `find_engie_csv()`.

### Format
```
"DATE","START_TIME","END_TIME","LZ_NORTH"
"02-FEB-2021","23:00","00:00","$16.28"
"02-FEB-2021","23:15","00:15","$16.56"
...
```

- **DATE:** DD-MMM-YYYY format
- **START_TIME/END_TIME:** HH:MM format (15-minute intervals)
- **LZ_NORTH:** Price in $/MWh (parser converts to $/kWh)

### Integration
- `src/txpower/ercot_prices.py:load_engie_hourly_csv()` parses the CSV
- `scripts/run_uri_demo.py` uses it for Feb 2021 Uri analysis
- `scripts/run_normal_month.py` can use it for any month's wholesale prices

---

## Pecan Street Consumption Data

### Source
**Kaggle: Austin Smart Grid Energy Data**  
https://www.kaggle.com/datasets/bassam165/pecan-street-austin-smart-grid-energy-data

Or academic access:  
https://dataport.pecanstreet.org

### Download Instructions
**Quick (Kaggle):**
```bash
pip install kagglehub
python -c "import kagglehub; path = kagglehub.dataset_download('bassam165/pecan-street-austin-smart-grid-energy-data'); print(path)"
```

**Academic (Dataport):**
1. Request access at https://dataport.pecanstreet.org
2. Download household data as CSV (choose time period & resolution)
3. Column names: `local_15min` (timestamp), `grid` (net kW import)

### File Location
Place in: **`data/raw/pecan_street_15min_austin.csv`**

### Format
```
dataid,local_15min,grid,air1,air2,...
661,2018-03-01 00:00:00-06,0.448,0.0,0.0,...
661,2018-03-01 00:15:00-06,0.391,0.0,0.0,...
```

- **local_15min:** 15-minute timestamps with timezone
- **grid:** Net power (kW) from utility (negative = export)
- **air1, air2, ...:** Individual circuit loads (not used in analysis)

### Integration
- `src/txpower/pecanstreet.load_home()` parses the CSV
- `scripts/run_normal_month.py` uses March 2018 data for home 1642
- `scripts/run_uri_demo.py` can use Feb 2021 data if available

---

## Electricity Facts Labels (EFLs)

### Source
**Texas Power to Choose**  
https://www.powertochoose.org

### Download Instructions
1. Go to https://www.powertochoose.org
2. Select service area: **Round Rock, TX 78664** (Oncor / ERCOT LZ_NORTH)
3. Browse available plans, click a plan name
4. Download the **Electricity Facts Label (PDF)**
5. Or use the batch downloader:
   ```bash
   python -m scripts.fetch_efls
   ```

### File Location
Place PDFs in: **`data/raw/efl_pdfs/`**

### Integration
- `src/txpower/efl_parser.parse_efl()` extracts contract terms
- `scripts/run_normal_month.py` uses SmartGreen 12mo (if available)
- `scripts/run_uri_demo.py` uses SmartGreen 12mo (fixed plan example)

### Parsing Notes
- Parser extracts: energy rate, base charge, TDU charges, contract term, bill credits
- Validates by reconstructing advertised average prices from parsed fields
- TOU schedules (peak/off-peak) require regex matching on EFL text

---

## Gotchas & Timezones

### Pecan Street
- **Timezone-aware:** `local_15min` includes timezone offset (e.g., `-06:00`)
- **Mixed timezones:** Data may have `-05:00` (CDT) and `-06:00` (CST) in same month
- **Handling:** Parse via UTC, then localize to "America/Chicago"

### ERCOT Prices
- **Two formats:** Old xlsx (per-month sheets) and new ENGIE CSV (15-min intervals)
- **Units:** $/MWh in source → convert to $/kWh (÷ 1000)
- **Time zones:** ERCOT prices are in Central Time (UTC-6 or UTC-5)

### Power to Consumption
- **Grid column:** Net power (kW) over 15-min interval
- **Conversion:** kWh = kW × (minutes / 60)
- **Sign:** Negative = exporting (solar/battery). Filter to positive-only for consumption.

---

## Cost Stack Validation

All analyses use the same cost formula:

```
Total Bill = Energy + TDU + Base Charges − Credits

Energy = {
  Fixed plan:    rate_per_kwh × usage_kwh
  Variable:      monthly_market_rate × usage_kwh
  Indexed:       (settlement_point_price + adder) × usage_kwh
  TOU:           Σ(period_rate × usage_in_period)
}

TDU = tdu_fixed_monthly + (tdu_per_kwh × usage_kwh)
Base = base_monthly_charge
Credits = Σ(credit_amount if usage in threshold_band)
```

See `src/txpower/cost_engine.py` for implementation.

---

## Reproducibility

To fully reproduce the analysis with real data:

1. Download ENGIE ERCOT CSV for Feb 2021 (Feb 15-20 freeze)
2. Download Kaggle Pecan Street data (or Dataport Feb 2021 subset)
3. Download a few EFLs from Power to Choose (Round Rock 78664)
4. Run:
   ```bash
   python -m scripts.run_normal_month   # March 2018 normal-month analysis
   python -m scripts.run_uri_demo       # Feb 2021 Uri crisis with real prices
   ```

All data files are `.gitignore`'d except small samples. Document URLs above rather than storing large files in git.

