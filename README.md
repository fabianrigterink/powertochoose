# Texas Power Contract Cost Simulator

Simulate what real Texas retail electricity contracts would actually cost a
household, using real consumption data and real ERCOT market prices — to show
how vastly contract *structure* changes the bill, especially during scarcity
events like Winter Storm Uri (February 2021).

## The thesis

Two households with identical consumption can pay wildly different amounts
depending only on contract structure. The gap explodes during grid scarcity:
wholesale-indexed plans are cheap most of the time and catastrophic during a
handful of hours. During Uri, ERCOT prices sat pinned at the $9,000/MWh cap for
days, and pass-through customers got bills in the thousands for a single month.

## Data sources

| Layer | Source | Notes |
|-------|--------|-------|
| Consumption | Pecan Street (Kaggle sample + full Dataport) | kW avg per interval → convert to kWh. Kaggle = Aug only; Uri needs Feb 2021 from academic Dataport. |
| Wholesale price | ERCOT annual RTM Settlement Point Prices | $/MWh → ÷1000. 15-min. Use the Load Zone matching your TDU. |
| Contract terms | Power to Choose EFL PDFs | PUCT-standardized format. Auto-extract, then **hand-verify**. |
| TDU delivery | TDU tariff (Oncor/CenterPoint/AEP) | Pass-through; same across retailers. |

## Key gotchas (do not skip)

1. **Apples-to-apples stack.** Power to Choose advertised rates are all-in
   (energy + TDU + fees). ERCOT SPP is wholesale energy only. You MUST add the
   same TDU + adder stack to the indexed simulation or it looks fake-cheap.
2. **Austin is split.** Austin proper = Austin Energy (municipal, NOT on the
   competitive market, not on Power to Choose). The deregulated metro-Austin
   territory is **Oncor** → Load Zone **LZ_NORTH**. Pick an Oncor-served ZIP.
3. **Power units.** Pecan Street columns are average kW, not kWh. Convert:
   kWh = kW × (interval_min / 60). Do it in the loader, not downstream.
4. **Bill-credit bands are the crux.** Many "teaser" plans give a credit only
   in a usage band (e.g. $100 at 1000–2000 kWh). Real spiky load often misses
   the band. This is expressed in EFL prose → parse carefully, verify by hand.
5. **Uri needs winter data.** The Kaggle sample is August. The Feb-2021 chart
   requires full Dataport academic access (or a clearly-labeled simulated load).

## Layout

```
src/txpower/
  models.py        Contract, BillCredit, TduCharges, RateType
  cost_engine.py   simulate_month / simulate_many  (DONE, tested)
  efl_parser.py    EFL PDF → Contract              (stub; build vs real PDFs)
  ercot_prices.py  annual SPP → $/kWh series       (stub; build vs real file)
  pecanstreet.py   CSV → kWh-per-interval series   (stub; build vs real CSV)
data/raw/          efl_pdfs/  ercot/  pecanstreet/  tdu/
data/processed/    verified contracts.json, cleaned series
notebooks/         exploratory analysis
reports/figures/   charts for the writeup
tests/             cost engine sanity checks (passing)
```

## Time-travel: recovering pre-Uri plans

The "export all offers" download lives at a FIXED url:

    http://www.powertochoose.org/en-us/Plan/ExportToCsv

Because that's a plain GET returning a file (not the dynamic ZIP search), the
Wayback Machine can and likely did snapshot it. A Feb-2021 capture = the entire
pre-Uri marketplace, including the Variable/Indexed plans central to the story.

Run `src/txpower/wayback.py` (locally, where archive.org is reachable):

```python
from txpower.wayback import list_snapshots, fetch_snapshot_csv
snaps = list_snapshots("20210101", "20210401")   # find 200-status timestamps
df = fetch_snapshot_csv("20210215XXXXXX")          # frozen all-offers CSV
df.to_csv("data/raw/ptc_offers_2021_uri.csv", index=False)
```

Or, where archive.org is blocked, `python -m txpower.wayback` prints ready-to-
paste browser URLs. Then load with
`ptc_loader.load_ptc_all_offers_csv(path, tdu_filter="ONCOR")` -- same format as
the current export, so it ingests directly.

NOTE: the all-offers CSV is richer than the per-ZIP xlsx. The current statewide
file already has 148 Variable plans (29 Oncor); the per-ZIP xlsx hid them. A
2021 snapshot should add Indexed plans too.

## Status

- [x] Project skeleton
- [x] Data model
- [x] Cost engine + sanity tests
- [ ] EFL parser (waiting on sample PDFs)
- [x] ERCOT SPP loader (real-format parser + synthetic Uri stand-in)
- [ ] Pecan Street loader (waiting on CSV)
- [ ] Normal-month analysis + charts
- [~] Uri blowup analysis + charts (DEMO done on synthetic data; awaits real ERCOT file + Feb-2021 Dataport home)
- [ ] Report

## Report outline

1. Texas setup — deregulation, Power to Choose, contract types.
2. Methodology — sources, the cost stack, EFL parsing.
3. Normal month — advertised-vs-actual gap, bill-credit band effects.
4. The Uri blowup — cumulative-cost divergence chart, indexed bill.
5. Takeaway — what to actually read on an EFL.
