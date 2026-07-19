"""DANE microdata archive (microdatos.dane.gov.co) source.

DANE's Central Data Catalog is an IHSN NADA instance exposing a read-only
JSON API with ~570 statistical operations (censuses, surveys, administrative
records), many with downloadable microdata files.

Key endpoints
-------------
* Search:  ``GET /index.php/api/catalog/search?sk=<kw>&ps=<n>&page=<n>``
* Study:   ``GET /index.php/api/catalog/{id}``
* Resources (files): ``GET /index.php/api/catalog/{id}/resources``
* Data files:        ``GET /index.php/api/catalog/{id}/data_files``
"""

from __future__ import annotations

from typing import Iterator

from .client import HttpClient

BASE = "https://microdatos.dane.gov.co"
API = f"{BASE}/index.php/api"

PAGE_SIZE = 100  # ``ps`` parameter; 15 is the server default, 100 works


def normalize(row: dict) -> dict:
    """Flatten a NADA search row into the unified catalog schema."""
    sid = str(row.get("id", ""))
    return {
        "id": sid,
        "source": "microdatos.dane.gov.co",
        "type": "study",
        "idno": row.get("idno", ""),
        "title": row.get("title", ""),
        "description": "",
        "category": row.get("repo_title") or "",
        "repository_id": row.get("repositoryid", ""),
        "tags": [],
        "publisher": row.get("authoring_entity", "") or "",
        "nation": row.get("nation", ""),
        "access": row.get("form_model", ""),  # direct = downloadable microdata
        "year_start": row.get("year_start", ""),
        "year_end": row.get("year_end", ""),
        "created_at": row.get("created", ""),
        "updated_at": row.get("changed", ""),
        "page_views_total": int(row.get("total_views") or 0),
        "download_count": int(row.get("total_downloads") or 0),
        "landing_page": row.get("url") or f"{BASE}/index.php/catalog/{sid}",
        "api_endpoint": f"{API}/catalog/{sid}",
        "columns": [],
    }


class MicrodataCatalog:
    """Client for the DANE microdata (NADA) catalog API."""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def search_raw(
        self,
        sk: str | None = None,
        ps: int = PAGE_SIZE,
        page: int = 1,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> dict:
        # NOTE: this NADA version paginates with 1-based ``page``; the
        # ``offset`` query parameter is silently ignored by the server.
        params: dict = {"ps": ps, "page": page}
        if sk:
            params["sk"] = sk
        if sort_by:
            params["sort_by"] = sort_by
        if sort_order:
            params["sort_order"] = sort_order
        return self.http.get_json(f"{API}/catalog/search", params)

    def iter_all_studies(self) -> Iterator[dict]:
        """Yield normalized records for every study in the catalog."""
        page = 1
        while True:
            data = self.search_raw(page=page)
            result = data.get("result", {})
            rows = result.get("rows", [])
            if not rows:
                break
            for row in rows:
                yield normalize(row)
            total = int(result.get("total") or 0)
            if page * PAGE_SIZE >= total:
                break
            page += 1

    def study_detail(self, study_id: str) -> dict:
        """Full metadata for one study."""
        return self.http.get_json(f"{API}/catalog/{study_id}")

    def study_resources(self, study_id: str) -> list:
        """All resources (microdata files, docs, questionnaires...)."""
        data = self.http.get_json(f"{API}/catalog/{study_id}/resources")
        return data.get("resources", data) if isinstance(data, dict) else data

    def study_data_files(self, study_id: str) -> list:
        """Direct-download microdata files for one study."""
        data = self.http.get_json(f"{API}/catalog/{study_id}/data_files")
        return data.get("data_files", data) if isinstance(data, dict) else data
