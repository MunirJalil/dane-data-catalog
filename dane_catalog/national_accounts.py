"""Quarterly national accounts (GDP) for Colombia.

DANE is the producer of Colombia's national accounts, but it publishes
quarterly GDP only as Excel annexes on dane.gov.co (no API, and the site
blocks datacenter IPs). The same official figures that DANE compiles are
available programmatically from the OECD Quarterly National Accounts
database, to which DANE reports. This module queries the OECD SDMX REST
API (no key required, not geo-blocked) and returns tidy rows.

Verified against DANE's own publications:

* 2025 annual nominal GDP = 1,852,670,034 million COP; DANE reports
  1.852.670 miles de millones de pesos (exact match).
* 2026-Q1 nominal YoY growth = 5.9 %, matching the DANE technical
  bulletin (bol-PIB-Itrim2026.pdf, 15/05/2026).

Price bases (OECD PRICE_BASE dimension):

* ``V`` — values at current prices (nominal; DANE "precios corrientes")
* ``L`` — chained volume, reference year 2015 (real; DANE "precios
  constantes", series encadenadas de volumen)
"""

from __future__ import annotations

import csv
import io

import requests

FLOW = "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_NATIO_CURR"
ENDPOINT = f"https://sdmx.oecd.org/public/rest/v1/data/{FLOW}"

SOURCE_NOTE = (
    "DANE national accounts via OECD Quarterly National Accounts "
    "(DF_QNA_EXPENDITURE_NATIO_CURR), transaction B1GQ, total economy (S1). "
    "Values in millions of Colombian pesos (XDC)."
)

# SDMX key positions (13 dimensions, NAMAIN1 DSD):
# 0 FREQ, 1 ADJUSTMENT, 2 REF_AREA, 3 SECTOR, 4 COUNTERPART_SECTOR,
# 5 TRANSACTION, 6 INSTR_ASSET, 7 ACTIVITY, 8 EXPENDITURE,
# 9 UNIT_MEASURE, 10 PRICE_BASE, 11 TRANSFORMATION, 12 TABLE_IDENTIFIER
PRICE_BASES = {"current": "V", "constant": "L"}
USER_AGENT = "dane-data-catalog/1.0 (+https://github.com/)"


def _key(prices: str, adjustment: str) -> str:
    if prices not in PRICE_BASES:
        raise ValueError(f"prices must be one of {sorted(PRICE_BASES)}")
    if adjustment not in ("N", "Y"):
        raise ValueError("adjustment must be 'N' (original) or 'Y' (seasonally adjusted)")
    segs = [
        "Q",            # FREQ: quarterly
        adjustment,     # ADJUSTMENT: N original / Y seasonally & calendar adjusted
        "COL",          # REF_AREA: Colombia
        "S1",           # SECTOR: total economy
        "",             # COUNTERPART_SECTOR
        "B1GQ",         # TRANSACTION: gross domestic product
        "",             # INSTR_ASSET
        "",             # ACTIVITY
        "",             # EXPENDITURE
        "",             # UNIT_MEASURE (XDC, national currency, implied)
        PRICE_BASES[prices],  # PRICE_BASE: V current / L chained volume 2015
        "N",            # TRANSFORMATION: none (levels)
        "T0102",        # TABLE_IDENTIFIER
    ]
    return ".".join(segs)


def quarterly_gdp(
    prices: str = "current",
    adjustment: str = "N",
    start: str | None = None,
    end: str | None = None,
    timeout: int = 120,
) -> list[dict]:
    """Return quarterly GDP rows for Colombia, sorted ascending.

    Each row: ``{quarter, value, prices, adjustment, unit}`` where
    ``quarter`` looks like ``2026-Q1`` and ``value`` is in millions of COP.
    """
    params = {"dimensionAtObservation": "AllDimensions"}
    if start:
        params["startPeriod"] = start
    if end:
        params["endPeriod"] = end
    url = f"{ENDPOINT}/{_key(prices, adjustment)}"
    resp = requests.get(
        url,
        params=params,
        headers={"Accept": "text/csv", "User-Agent": USER_AGENT},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"OECD SDMX query failed with HTTP {resp.status_code}: "
            f"{resp.text[:300]}"
        )
    rows = []
    reader = csv.DictReader(io.StringIO(resp.text))
    for rec in reader:
        try:
            value = float(rec["OBS_VALUE"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append(
            {
                "quarter": rec.get("TIME_PERIOD", ""),
                "value": value,
                "prices": prices,
                "adjustment": adjustment,
                "unit": "millions of COP",
            }
        )
    rows.sort(key=lambda r: r["quarter"])
    return rows


def with_yoy(rows: list[dict]) -> list[dict]:
    """Add year-over-year nominal growth (%) to a quarterly series."""
    by_quarter = {r["quarter"]: r["value"] for r in rows}
    out = []
    for r in rows:
        year, q = r["quarter"].split("-")
        prev = by_quarter.get(f"{int(year) - 1}-{q}")
        yoy = round((r["value"] / prev - 1) * 100, 2) if prev else None
        out.append({**r, "yoy_pct": yoy})
    return out
