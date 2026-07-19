"""Build, save and load the unified DANE data catalog.

The catalog combines two official sources:

1. ``datos.gov.co`` — open datasets published by DANE on the national open
   data portal (queried live, SoQL-ready).
2. ``microdatos.dane.gov.co`` — DANE's central microdata archive (censuses,
   surveys and administrative records with microdata files).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .client import HttpClient
from .microdata import MicrodataCatalog
from .socrata import SocrataCatalog

CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"

DATASETS_JSON = "dane_datasets.json"
DATASETS_CSV = "dane_datasets.csv"
STUDIES_JSON = "dane_microdata.json"
STUDIES_CSV = "dane_microdata.csv"

DATASET_FIELDS = [
    "id", "source", "title", "description", "category", "tags", "publisher",
    "attribution", "sector", "geo_coverage", "update_frequency", "language",
    "created_at", "updated_at", "data_updated_at", "page_views_total",
    "download_count", "license", "landing_page", "api_endpoint",
    "csv_download", "n_columns",
]

STUDY_FIELDS = [
    "id", "source", "idno", "title", "category", "repository_id", "publisher",
    "nation", "access", "year_start", "year_end", "created_at", "updated_at",
    "page_views_total", "download_count", "landing_page", "api_endpoint",
]

SOURCES_META = {
    "datos.gov.co": "https://www.datos.gov.co (Socrata open data portal)",
    "microdatos.dane.gov.co": "https://microdatos.dane.gov.co (NADA microdata archive)",
}


def build_datasets(
    http: HttpClient, verbose: bool = True, full_sweep: bool = False
) -> list[dict]:
    """Fetch all DANE-published datasets from datos.gov.co."""
    datasets = []
    soc = SocrataCatalog(http)
    for rec in soc.iter_dane_datasets(full_sweep=full_sweep):
        datasets.append(rec)
        if verbose and len(datasets) % 100 == 0:
            print(f"  datos.gov.co: {len(datasets)} DANE datasets...")
    datasets.sort(key=lambda r: (-(r.get("download_count") or 0), r["title"]))
    if verbose:
        print(f"  datos.gov.co: {len(datasets)} DANE datasets total")
    return datasets


def build_studies(http: HttpClient, verbose: bool = True) -> list[dict]:
    """Fetch all studies from the DANE microdata archive."""
    studies = []
    md = MicrodataCatalog(http)
    for rec in md.iter_all_studies():
        studies.append(rec)
        if verbose and len(studies) % 100 == 0:
            print(f"  microdatos: {len(studies)} studies...")
    studies.sort(key=lambda r: (-(r.get("download_count") or 0), r["title"]))
    if verbose:
        print(f"  microdatos: {len(studies)} studies total")
    return studies


def wrap(datasets: list[dict], studies: list[dict]) -> dict:
    """Assemble the unified catalog dict from both record lists."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": SOURCES_META,
        "counts": {
            "datasets": len(datasets),
            "studies": len(studies),
            "total": len(datasets) + len(studies),
        },
        "datasets": datasets,
        "studies": studies,
    }


def build(http: HttpClient, verbose: bool = True, full_sweep: bool = False) -> dict:
    """Fetch both sources and return the unified catalog dict."""
    return wrap(
        build_datasets(http, verbose, full_sweep=full_sweep),
        build_studies(http, verbose),
    )


def _flatten_dataset(rec: dict) -> dict:
    row = {k: rec.get(k, "") for k in DATASET_FIELDS}
    row["tags"] = "; ".join(rec.get("tags") or [])
    row["n_columns"] = len(rec.get("columns") or [])
    return row


def _flatten_study(rec: dict) -> dict:
    return {k: rec.get(k, "") for k in STUDY_FIELDS}


def save(catalog: dict, outdir: Path = CATALOG_DIR) -> list[Path]:
    """Write JSON + CSV catalog files; returns written paths."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    written = []

    full = dict(catalog)
    p = outdir / "dane_catalog_full.json"
    p.write_text(
        json.dumps(full, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    written.append(p)

    for records, jname, cname, fields, flatten in (
        (catalog["datasets"], DATASETS_JSON, DATASETS_CSV, DATASET_FIELDS, _flatten_dataset),
        (catalog["studies"], STUDIES_JSON, STUDIES_CSV, STUDY_FIELDS, _flatten_study),
    ):
        pj = outdir / jname
        pj.write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        written.append(pj)
        pc = outdir / cname
        with pc.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for rec in records:
                writer.writerow(flatten(rec))
        written.append(pc)

    return written


def load(outdir: Path = CATALOG_DIR) -> dict:
    """Load the previously built catalog from disk."""
    outdir = Path(outdir)
    with (outdir / "dane_catalog_full.json").open(encoding="utf-8") as fh:
        return json.load(fh)
