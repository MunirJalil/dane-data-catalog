"""Short-term economic indicators for Colombia (coyuntura económica).

DANE compiles Colombia's headline economic statistics (IPC, industrial
production, retail sales, unemployment, consumer/business confidence,
foreign trade) but publishes them only as press releases and Excel files
on dane.gov.co — no API, and the site blocks datacenter IPs. The same
official series that DANE (and Banco de la República) compile are
available programmatically from the OECD Key Economic Indicators (KEI)
database, to which Colombia reports as an OECD member. This module
queries the OECD SDMX REST API (no key, not geo-blocked).

Notes
-----
* The producer-price index (IPP) is intentionally absent: the OECD
  series for Colombia has not been updated since 2022-12.
* Trade values are goods only, in US dollars (as reported to the OECD),
  seasonally adjusted. DANE's own releases are in FOB USD, unadjusted.
* ``trm`` (COP per USD) is compiled by Banco de la República, not DANE;
  it is included for convenience.
"""

from __future__ import annotations

import csv
import io

import requests

FLOW = "OECD.SDD.STES,DSD_KEI@DF_KEI,4.0"
ENDPOINT = f"https://sdmx.oecd.org/public/rest/v1/data/{FLOW}"
USER_AGENT = "dane-data-catalog/1.0 (+https://github.com/)"

SOURCE_NOTE = (
    "Official Colombian statistics via OECD Key Economic Indicators "
    "(DF_KEI). Producers: DANE (IPC, EMM, CMMC, GEIH, ICC/ENE, foreign "
    "trade) and Banco de la República (TRM)."
)

# KEI key: REF_AREA.FREQ.MEASURE.UNIT_MEASURE.ACTIVITY.ADJUSTMENT.TRANSFORMATION
INDICATORS: dict[str, dict] = {
    "ipc": {
        "name": "IPC — índice de precios al consumidor, total nacional",
        "source": "DANE — IPC",
        "key": "COL.M.CP.IX._Z._Z._Z",
        "unit": "index (2015=100)",
        "mult_label": 0,
    },
    "inflacion": {
        "name": "Inflación — variación anual del IPC",
        "source": "DANE — IPC",
        "key": "COL.M.CP.GR._Z._Z.GY",
        "unit": "%",
        "mult_label": 0,
    },
    "produccion_industrial": {
        "name": "Producción industrial real — manufactura (EMM)",
        "source": "DANE — EMM",
        "key": "COL.M.PRVM.IX.C.Y._Z",
        "unit": "index (2015=100), seasonally adjusted",
        "mult_label": 0,
    },
    "ventas_comercio": {
        "name": "Ventas reales del comercio minorista (CMMC)",
        "source": "DANE — CMMC",
        "key": "COL.M.TOVM.IX.G47.Y._Z",
        "unit": "index (2015=100), seasonally adjusted",
        "mult_label": 0,
    },
    "desempleo": {
        "name": "Tasa de desempleo (GEIH)",
        "source": "DANE — GEIH",
        "key": "COL.M.UNEMP.PT_LF._T.Y._Z",
        "unit": "% of labour force, seasonally adjusted",
        "mult_label": 0,
    },
    "empleo": {
        "name": "Ocupados (GEIH)",
        "source": "DANE — GEIH",
        "key": "COL.M.EMP.PS._T.Y._Z",
        "unit": "thousands of persons, seasonally adjusted",
        "mult_label": 3,
    },
    "confianza_consumidor": {
        "name": "Índice de confianza del consumidor (ICC)",
        "source": "DANE — ICC (con Fedesarrollo)",
        "key": "COL.M.CCICP.PB._Z.Y._Z",
        "unit": "balance, seasonally adjusted",
        "mult_label": 0,
    },
    "confianza_empresarial": {
        "name": "Confianza empresarial — manufactura",
        "source": "DANE — ENE",
        "key": "COL.M.BCICP.PB.C.Y._Z",
        "unit": "balance, seasonally adjusted",
        "mult_label": 0,
    },
    "exportaciones": {
        "name": "Exportaciones de bienes",
        "source": "DANE — comercio exterior (DIAN)",
        "key": "COL.M.EX.USD._T.Y._Z",
        "unit": "millions of USD, seasonally adjusted",
        "mult_label": 6,
    },
    "importaciones": {
        "name": "Importaciones de bienes",
        "source": "DANE — comercio exterior (DIAN)",
        "key": "COL.M.IM.USD._T.Y._Z",
        "unit": "millions of USD, seasonally adjusted",
        "mult_label": 6,
    },
    "trm": {
        "name": "TRM — tasa de cambio representativa del mercado",
        "source": "Banco de la República",
        "key": "COL.M.CC.XDC_USD._Z._Z._Z",
        "unit": "COP per USD (monthly average)",
        "mult_label": 0,
    },
    "construccion": {
        "name": "Vivienda — indicador de construcción (dwellings)",
        "source": "DANE — construcción",
        "key": "COL.M.NODW.IX.F41.Y._Z",
        "unit": "index (2015=100), seasonally adjusted",
        "mult_label": 0,
    },
}


def list_indicators() -> list[dict]:
    """Static registry of available indicators."""
    return [
        {"id": k, "name": v["name"], "source": v["source"], "unit": v["unit"], "frequency": "monthly"}
        for k, v in INDICATORS.items()
    ]


def fetch_indicator(
    indicator: str,
    start: str | None = None,
    end: str | None = None,
    timeout: int = 120,
) -> list[dict]:
    """Return the monthly series for one indicator, sorted ascending.

    Each row: ``{period, value, indicator, unit}`` with ``period`` like
    ``2026-05`` and ``value`` expressed in the indicator's labelled unit
    (OECD unit-multipliers already applied).
    """
    if indicator not in INDICATORS:
        raise ValueError(
            f"unknown indicator {indicator!r}; available: {', '.join(INDICATORS)}"
        )
    spec = INDICATORS[indicator]
    params = {"dimensionAtObservation": "AllDimensions"}
    if start:
        params["startPeriod"] = start
    if end:
        params["endPeriod"] = end
    resp = requests.get(
        f"{ENDPOINT}/{spec['key']}",
        params=params,
        headers={"Accept": "text/csv", "User-Agent": USER_AGENT},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"OECD SDMX query for {indicator!r} failed with HTTP "
            f"{resp.status_code}: {resp.text[:300]}"
        )
    rows = []
    for rec in csv.DictReader(io.StringIO(resp.text)):
        try:
            value = float(rec["OBS_VALUE"])
        except (KeyError, TypeError, ValueError):
            continue
        # Apply OECD unit multiplier so values match the labelled unit
        # (e.g. trade arrives in 1e9 USD -> label is millions of USD).
        try:
            mult = int(rec.get("UNIT_MULT") or 0)
        except ValueError:
            mult = 0
        scale = 10.0 ** (mult - spec["mult_label"])
        rows.append(
            {
                "period": rec.get("TIME_PERIOD", ""),
                "value": value * scale,
                "indicator": indicator,
                "unit": spec["unit"],
            }
        )
    rows.sort(key=lambda r: r["period"])
    return rows


def fetch_all(
    start: str | None = None,
    end: str | None = None,
    timeout: int = 120,
) -> dict[str, list[dict]]:
    """Fetch every registered indicator; failed ones carry an 'error' key."""
    out: dict[str, list[dict]] = {}
    for indicator in INDICATORS:
        try:
            out[indicator] = fetch_indicator(indicator, start, end, timeout)
        except Exception as exc:  # noqa: BLE001
            out[indicator] = [{"error": str(exc)}]  # type: ignore[dict-item]
    return out
