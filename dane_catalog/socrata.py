"""datos.gov.co (Socrata) source: catalog discovery and data queries.

DANE publishes open datasets on the Colombian national open-data portal
https://www.datos.gov.co, a Socrata instance. This module wraps the Socrata
Discovery (catalog) API and the SoQL query API.

Key facts
---------
* Catalog API: ``https://api.us.socrata.com/api/catalog/v1``
* DANE publisher account id on the portal: ``9jyr-mj4e``
  (display name "Departamento Administrativo Nacional de Estadística - DANE")
* Per-dataset query endpoint: ``https://www.datos.gov.co/resource/{id}.json``
"""

from __future__ import annotations

import os
from typing import Iterator

from .client import HttpClient

CATALOG_API = "https://api.us.socrata.com/api/catalog/v1"
DOMAIN = "www.datos.gov.co"
DANE_OWNER_ID = "9jyr-mj4e"

# Strings that mark a catalog record as published by DANE. Matched (lowercase)
# against owner name, attribution and the entity-name domain metadata.
DANE_MARKERS = (
    "departamento administrativo nacional de estad",  # Estadística(s)
    "- dane",
    " dane",
)

# Socrata Discovery API page size. Lower it (env DANE_PAGE_SIZE=25) when going
# through slow proxies that time out on large pages.
PAGE_SIZE = int(os.environ.get("DANE_PAGE_SIZE", "100"))


def _domain_metadata_map(record: dict) -> dict:
    out = {}
    for item in record.get("classification", {}).get("domain_metadata", []):
        out[item.get("key", "")] = item.get("value", "")
    return out


def is_dane_record(entry: dict) -> bool:
    """True if the catalog entry was published by DANE."""
    owner = entry.get("owner") or {}
    if owner.get("id") == DANE_OWNER_ID:
        return True
    haystacks = [
        (owner.get("display_name") or ""),
        (entry.get("resource", {}).get("attribution") or ""),
        _domain_metadata_map(entry).get(
            "Información-de-la-Entidad_Nombre-de-la-Entidad", ""
        ),
    ]
    blob = " ".join(haystacks).lower()
    return any(m in blob for m in DANE_MARKERS)


def normalize(entry: dict) -> dict:
    """Flatten a Socrata catalog entry into the unified catalog schema."""
    res = entry.get("resource", {})
    cls = entry.get("classification", {})
    dm = _domain_metadata_map(entry)
    ds_id = res.get("id", "")
    columns = []
    names = res.get("columns_name") or []
    fields = res.get("columns_field_name") or []
    types = res.get("columns_datatype") or []
    descs = res.get("columns_description") or []
    for i, fname in enumerate(fields):
        columns.append(
            {
                "field": fname,
                "name": names[i] if i < len(names) else "",
                "type": types[i] if i < len(types) else "",
                "description": descs[i] if i < len(descs) else "",
            }
        )
    views = res.get("page_views") or {}
    return {
        "id": ds_id,
        "source": "datos.gov.co",
        "type": res.get("type", "dataset"),
        "title": res.get("name", ""),
        "description": res.get("description", "") or "",
        "category": cls.get("domain_category", "") or "",
        "tags": cls.get("domain_tags") or cls.get("tags") or [],
        "publisher": (entry.get("owner") or {}).get("display_name", ""),
        "attribution": res.get("attribution", "") or "",
        "sector": dm.get("Información-de-la-Entidad_Sector", ""),
        "geo_coverage": dm.get("Información-de-Datos_Cobertura-Geográfica", ""),
        "update_frequency": dm.get(
            "Información-de-Datos_Frecuencia-de-Actualización", ""
        ),
        "language": dm.get("Información-de-Datos_Idioma", ""),
        "created_at": res.get("createdAt", ""),
        "updated_at": res.get("updatedAt", ""),
        "data_updated_at": res.get("data_updated_at", ""),
        "page_views_total": views.get("page_views_total", 0),
        "download_count": res.get("download_count", 0),
        "license": (entry.get("metadata") or {}).get("license", ""),
        "landing_page": entry.get("permalink") or f"https://{DOMAIN}/d/{ds_id}",
        "api_endpoint": f"https://{DOMAIN}/resource/{ds_id}.json",
        "csv_download": f"https://{DOMAIN}/api/views/{ds_id}/rows.csv?accessType=DOWNLOAD",
        "columns": columns,
    }


class SocrataCatalog:
    """Discovery-API client for DANE datasets on datos.gov.co."""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def search_raw(
        self,
        q: str | None = None,
        category: str | None = None,
        limit: int = PAGE_SIZE,
        offset: int = 0,
        order: str | None = None,
    ) -> dict:
        params = {
            "domains": DOMAIN,
            "search_context": DOMAIN,
            "only": "datasets",
            "limit": limit,
            "offset": offset,
        }
        if q:
            params["q"] = q
        if category:
            params["categories"] = category
        if order:
            params["order"] = order
        return self.http.get_json(CATALOG_API, params)

    def iter_dane_datasets(
        self, queries=("DANE",), full_sweep: bool = False
    ) -> Iterator[dict]:
        """Yield normalized records for every DANE-published dataset.

        Pages through a superset of full-text queries and filters locally to
        records whose owner / attribution / entity metadata identifies DANE.

        With ``full_sweep=True`` every dataset on the portal is scanned
        (``q=''``), which catches DANE records that mention neither "DANE"
        nor the full entity name in any indexed text field. This is the
        most complete option and is what the scheduled refresh uses.
        """
        if full_sweep:
            queries = ("",)
        seen: set[str] = set()
        for q in queries:
            offset = 0
            while True:
                page = self.search_raw(q=q, offset=offset)
                results = page.get("results", [])
                if not results:
                    break
                for entry in results:
                    ds_id = entry.get("resource", {}).get("id")
                    if not ds_id or ds_id in seen:
                        continue
                    if is_dane_record(entry):
                        seen.add(ds_id)
                        yield normalize(entry)
                total = page.get("resultSetSize", 0)
                offset += len(results)
                if offset >= total:
                    break

    def dataset_metadata(self, dataset_id: str) -> dict:
        """Full Socrata view metadata for one dataset."""
        return self.http.get_json(f"https://{DOMAIN}/api/views/{dataset_id}")

    def query(
        self,
        dataset_id: str,
        select: str | None = None,
        where: str | None = None,
        order: str | None = None,
        group: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list:
        """Run a SoQL query against a dataset (``/resource/{id}.json``)."""
        params: dict = {"$limit": limit, "$offset": offset}
        if select:
            params["$select"] = select
        if where:
            params["$where"] = where
        if order:
            params["$order"] = order
        if group:
            params["$group"] = group
        return self.http.get_json(
            f"https://{DOMAIN}/resource/{dataset_id}.json", params
        )

    def iter_query(self, dataset_id: str, page_size: int = 5000, **kwargs):
        """Yield rows for a SoQL query, paging automatically."""
        offset = kwargs.pop("offset", 0)
        while True:
            rows = self.query(
                dataset_id, limit=page_size, offset=offset, **kwargs
            )
            if not rows:
                break
            yield from rows
            if len(rows) < page_size:
                break
            offset += len(rows)
