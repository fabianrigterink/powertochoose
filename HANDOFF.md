# HANDOFF — for continuing in VS Code / Claude Code

This is a working scaffold for simulating and comparing Texas retail electricity
contract costs, with the Winter Storm Uri (Feb 2021) blowup as the headline.
Everything structural is built and tested; what remains is swapping three
synthetic stand-ins for real data, then a few analysis extensions and the writeup.

## Run it now
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                       # cost-engine sanity checks should pass
python scripts/run_uri_demo.py   # prints the bill comparison, writes the chart
```

## What's DONE (real, tested)
- `src/txpower/models.py` — Contract / BillCredit / TduCharges / RateType.
- `src/txpower/cost_engine.py` — apples-to-apples bill simulation; unit-tested.
- `src/txpower/efl_parser.py` — parses real PUCT EFL PDFs; VALIDATED (parsed
  components reconstruct the EFL's own advertised prices exactly).
- `src/txpower/ptc_loader.py` — ingests both PTC exports (per-ZIP xlsx and the
  statewide all-offers CSV, which includes Variable/Indexed plans).
- `src/txpower/ercot_prices.py` — real ERCOT annual-SPP-format parser, plus a
  documented synthetic Uri price series for wiring.
- `src/txpower/wayback.py` — recover historical pre-Uri plan data from the fixed
  all-offers endpoint (see below).
- `scripts/run_uri_demo.py` — end-to-end demo + divergence chart.
- `scripts/fetch_efls.py` — batch-download the shortlisted EFLs.

## What's SYNTHETIC (clearly labeled — replace with real data)
**Feb-2021 consumption.** One Austin-metro home from full Dataport academic
access (dataport.pecanstreet.org). The `pecanstreet.load_home()` function is
implemented; ready to consume real CSV once downloaded.

## Suggested next steps (good Claude Code tasks)
- [x] Implement `pecanstreet.load_home` against a real Dataport CSV; add a test.
- [x] Pull real ERCOT 2021 SPP; verify LZ_NORTH parses; re-run the demo on real
      prices and drop the "synthetic" labels from the chart.
- [x] Recover a Feb-2021 all-offers snapshot (`wayback.list_snapshots`); load
      Oncor Variable/Indexed plans; pick the real indexed contract.
- [ ] Extend `efl_parser` for **time-of-use** plans (multiple energy rates +
      hour-of-day schedule) — the "free nights" structures.
- [ ] Add usage-band **bill-credit** extraction (detect when reconstructed avg
      != stated avg; parse thresholds from EFL prose) and verify by hand.
- [ ] Build the **normal-month** comparison (all contract types vs a regular
      billing period) to expose advertised-vs-actual and bill-credit band misses.
- [ ] Write the report around the charts (outline in README).

## Gotchas to keep in mind (full list in README)
- Apples-to-apples: always add the SAME TDU + adder stack to indexed sims.
- Round Rock 78664 = Oncor = ERCOT LZ_NORTH. Keep this consistent (config.py).
- TDU delivery charges differ by era — use 2021 rates for the Uri analysis;
  each EFL embeds its own era's TDU charges, so prefer those.
- "Bill credit" is ambiguous: usage-band (in EFL pricing) vs promotional
  sign-up credit (Terms of Service only). They behave very differently.

## Data provenance note
`data/raw/` is gitignored except for the two PTC exports and one sample EFL,
which are small and useful as fixtures. Large ERCOT/Dataport files should stay
out of git; document their source URLs instead.
