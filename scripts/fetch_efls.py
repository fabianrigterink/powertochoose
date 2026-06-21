"""Fetch the shortlisted EFL PDFs from their Fact Sheet URLs.

Reads data/processed/efl_shortlist.csv (produced from the PTC export) and
downloads each EFL into data/raw/efl_pdfs/. Run where the provider sites are
reachable (they are public; this works from a normal machine).

    PYTHONPATH=src python scripts/fetch_efls.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:
    requests = None
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parents[1]
SHORTLIST = ROOT / "data/processed/efl_shortlist.csv"
OUTDIR = ROOT / "data/raw/efl_pdfs"


def _get(url: str, timeout: int = 30) -> bytes:
    if requests is not None:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.content
    req = Request(url, headers={"User-Agent": "txpower-efl/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def slugify(rep: str, plan: str) -> str:
    s = f"{rep}_{plan}".lower()
    return "".join(c if c.isalnum() else "_" for c in s).strip("_")[:60]


def main() -> None:
    if not SHORTLIST.exists():
        raise SystemExit(f"Missing {SHORTLIST}. Build it from the PTC export first.")
    df = pd.read_csv(SHORTLIST)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for _, r in df.iterrows():
        url = str(r["efl_url"])
        if not url.startswith("http"):
            print(f"skip (no url): {r['plan']}")
            continue
        name = f"{r['category']}__{slugify(r['rep'], r['plan'])}.pdf"
        dest = OUTDIR / name
        try:
            data = _get(url)
            if not data[:4] == b"%PDF":
                print(f"WARN not a PDF ({len(data)}b): {r['plan']} <- {url}")
            dest.write_bytes(data)
            print(f"ok  {name}  ({len(data):,}b)")
        except Exception as e:
            print(f"FAIL {r['plan']}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
