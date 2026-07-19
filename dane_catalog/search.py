"""Local, structured search over the unified DANE catalog.

This is the "API" layer: every function takes the loaded catalog (see
:func:`dane_catalog.catalog.load`) and returns plain dicts/lists that the CLI
serializes as JSON (or renders as a table).
"""

from __future__ import annotations

import unicodedata


def _fold(text: str) -> str:
    """Lowercase + strip accents so 'pobreza' matches 'Pobreza'."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _haystack(rec: dict) -> str:
    parts = [
        rec.get("title", ""),
        rec.get("description", ""),
        rec.get("category", ""),
        rec.get("publisher", ""),
        rec.get("idno", ""),
        " ".join(rec.get("tags") or []),
    ]
    return _fold(" ".join(parts))


def _score(rec: dict, terms: list[str]) -> int:
    title = _fold(rec.get("title", ""))
    hay = _haystack(rec)
    score = 0
    for t in terms:
        if t in title:
            score += 10
        elif t in hay:
            score += 3
        else:
            return 0  # all terms must match
    # popularity tie-breaker, capped so relevance dominates
    dl = rec.get("download_count") or 0
    return score + min(dl // 1000, 5)


def all_records(catalog: dict) -> list[dict]:
    return catalog.get("datasets", []) + catalog.get("studies", [])


def get(catalog: dict, record_id: str) -> dict | None:
    """Find one record by id (Socrata 4x4 id or microdata numeric id/idno)."""
    rid = _fold(record_id)
    for rec in all_records(catalog):
        if _fold(rec.get("id", "")) == rid or _fold(rec.get("idno", "")) == rid:
            return rec
    return None


def search(
    catalog: dict,
    query: str = "",
    source: str | None = None,
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Full-text search with optional source/category filters.

    Returns a structured result: ``{query, filters, total, results: [...]}``.
    """
    terms = [_fold(t) for t in query.split() if t.strip()]
    src = _fold(source) if source else None
    cat = _fold(category) if category else None

    scored = []
    for rec in all_records(catalog):
        if src and _fold(rec.get("source", "")) != src:
            continue
        if cat and cat not in _fold(rec.get("category", "")):
            continue
        s = _score(rec, terms) if terms else (min((rec.get("download_count") or 0) // 1000, 5) + 1)
        if s > 0:
            scored.append((s, rec))
    scored.sort(key=lambda sr: (-sr[0], sr[1].get("title", "")))
    hits = [rec for _, rec in scored]

    def brief(rec: dict) -> dict:
        return {
            "id": rec.get("id"),
            "source": rec.get("source"),
            "title": rec.get("title"),
            "category": rec.get("category"),
            "publisher": rec.get("publisher"),
            "updated_at": rec.get("updated_at"),
            "download_count": rec.get("download_count"),
            "landing_page": rec.get("landing_page"),
            "api_endpoint": rec.get("api_endpoint"),
        }

    window = hits[offset : offset + limit]
    return {
        "query": query,
        "filters": {"source": source, "category": category},
        "total": len(hits),
        "offset": offset,
        "limit": limit,
        "results": [brief(r) for r in window],
    }


def stats(catalog: dict) -> dict:
    """Summary counts by source and category."""
    by_source: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for rec in all_records(catalog):
        by_source[rec["source"]] = by_source.get(rec["source"], 0) + 1
        c = rec.get("category") or "(sin categoría)"
        by_category[c] = by_category.get(c, 0) + 1
    top = sorted(
        all_records(catalog),
        key=lambda r: (-(r.get("download_count") or 0)),
    )[:15]
    return {
        "generated_at": catalog.get("generated_at"),
        "counts": catalog.get("counts"),
        "by_source": by_source,
        "by_category": dict(
            sorted(by_category.items(), key=lambda kv: -kv[1])
        ),
        "top_by_downloads": [
            {
                "id": r.get("id"),
                "source": r.get("source"),
                "title": r.get("title"),
                "downloads": r.get("download_count"),
            }
            for r in top
        ],
    }
