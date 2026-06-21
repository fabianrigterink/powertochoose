"""Time-travel helpers for recovering historical Power to Choose data.

THE KEY INSIGHT
---------------
PTC's ZIP search is a dynamic POST the Wayback Machine can't capture. But the
"export all offers" download lives at a FIXED GET URL:

    http://www.powertochoose.org/en-us/Plan/ExportToCsv

A plain GET that returns a file is exactly what the Wayback Machine snapshots.
If any crawler hit that URL near Feb 2021, the entire statewide offers CSV for
that day is frozen in the archive -- including the variable/indexed plans that
were live right before Winter Storm Uri.

USAGE (run where archive.org is reachable, e.g. your own machine)
-----------------------------------------------------------------
    from txpower.wayback import list_snapshots, snapshot_url, fetch_snapshot_csv

    snaps = list_snapshots(from_date="20210101", to_date="20210401")
    # pick a 200-status timestamp near the storm, then:
    df = fetch_snapshot_csv(snaps[0]["timestamp"])
    df.to_csv("data/raw/ptc_offers_20210215.csv", index=False)

Then feed it straight into ptc_loader -- same column format as the 2026 export.

NOTE: archive.org is egress-blocked inside the Claude sandbox, so these call
out to the live Wayback Machine and are meant to be run locally. They degrade
gracefully (clear error) if the network is unavailable.
"""
from __future__ import annotations

import io
import json
from urllib.parse import quote

import pandas as pd

try:
    import requests
except ImportError:  # requests is optional; urllib fallback below
    requests = None
from urllib.request import urlopen, Request


# The historically stable all-offers endpoint (documented since ~2018).
PTC_EXPORT_PATHS = [
    "powertochoose.org/en-us/Plan/ExportToCsv",
    "www.powertochoose.org/en-us/Plan/ExportToCsv",
    "powertochoose.org/Plan/ExportToCsv",
]

CDX_BASE = "http://web.archive.org/cdx/search/cdx"
WAYBACK_BASE = "https://web.archive.org/web"


def _get(url: str, timeout: int = 60) -> bytes:
    """Minimal GET that works with or without `requests`."""
    if requests is not None:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    req = Request(url, headers={"User-Agent": "txpower-wayback/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
        return resp.read()


def cdx_query_url(
    path: str = PTC_EXPORT_PATHS[0],
    from_date: str = "20210101",
    to_date: str = "20210401",
    match_prefix: bool = False,
) -> str:
    """Build a CDX API URL listing archived captures of a path.

    from_date/to_date are YYYYMMDD (or any YYYY / YYYYMM / YYYYMMDDhhmmss).
    Set match_prefix=True to catch query-string variants of the endpoint.
    """
    params = [
        f"url={quote(path, safe='/')}",
        f"from={from_date}",
        f"to={to_date}",
        "output=json",
        "collapse=digest",
    ]
    if match_prefix:
        params.append("matchType=prefix")
    return f"{CDX_BASE}?" + "&".join(params)


def list_snapshots(
    from_date: str = "20210101",
    to_date: str = "20210401",
    paths: list[str] | None = None,
) -> list[dict]:
    """Return archived captures of the export endpoint across known path variants.

    Each item: {timestamp, statuscode, mimetype, original, snapshot_url}.
    Only successful (200) captures with a CSV-ish mimetype are usually useful,
    but we return all so you can inspect redirects/empties too.
    """
    paths = paths or PTC_EXPORT_PATHS
    out: list[dict] = []
    for path in paths:
        url = cdx_query_url(path, from_date, to_date)
        try:
            raw = _get(url)
        except Exception as e:  # network / egress problems surface here
            out.append({"error": f"{type(e).__name__}: {e}", "query": url})
            continue
        try:
            rows = json.loads(raw.decode("utf-8") or "[]")
        except json.JSONDecodeError:
            continue
        if not rows:
            continue
        header, *data = rows
        for r in data:
            d = dict(zip(header, r))
            d["snapshot_url"] = snapshot_url(d["timestamp"], d["original"])
            out.append(d)
    # sort by timestamp where present
    out.sort(key=lambda d: d.get("timestamp", ""))
    return out


def snapshot_url(timestamp: str, original: str | None = None) -> str:
    """Construct the direct Wayback URL for a frozen capture.

    The 'id_' suffix on the timestamp asks Wayback for the raw, unmodified
    bytes (no archive toolbar injected) -- important for a clean CSV.
    """
    target = original or f"http://{PTC_EXPORT_PATHS[1]}"
    return f"{WAYBACK_BASE}/{timestamp}id_/{target}"


def fetch_snapshot_csv(timestamp: str, original: str | None = None) -> pd.DataFrame:
    """Download a frozen all-offers CSV snapshot into a DataFrame.

    Validates that the response looks like the PTC offers file (has the
    expected bracketed columns) rather than an archived error/redirect page.
    """
    url = snapshot_url(timestamp, original)
    raw = _get(url)
    text = raw.decode("utf-8", errors="replace")
    if "<html" in text[:2000].lower() and "[idKey]" not in text[:2000]:
        raise ValueError(
            f"Snapshot {timestamp} returned an HTML page, not the CSV "
            f"(likely an archived redirect/error). Try a different timestamp."
        )
    df = pd.read_csv(io.StringIO(text))
    # sanity: the all-offers export has bracketed column names like [RepCompany]
    bracket_cols = [c for c in df.columns if str(c).startswith("[")]
    if not bracket_cols:
        raise ValueError(
            f"Snapshot {timestamp} parsed but columns look wrong: {list(df.columns)[:5]}"
        )
    return df


def print_lookup_links(from_date="20200101", to_date="20220101") -> None:
    """Print ready-to-paste browser URLs for manual time-travel.

    Handy when running where archive.org is blocked: copy these into a browser.
    """
    print("# CDX capture lists (open in browser, look for 200-status rows):")
    for path in PTC_EXPORT_PATHS:
        print(cdx_query_url(path, from_date, to_date))
    print("\n# Once you have a timestamp TS, the frozen CSV is at:")
    print(f"{WAYBACK_BASE}/<TS>id_/http://{PTC_EXPORT_PATHS[1]}")


if __name__ == "__main__":
    print_lookup_links()
