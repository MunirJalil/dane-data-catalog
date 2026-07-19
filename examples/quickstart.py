"""Quickstart: search the catalog and pull data, all from Python.

Run from the repository root after building the catalog once:

    python -m dane_catalog.cli catalog            # one-time build
    python examples/quickstart.py
"""

from dane_catalog.catalog import load
from dane_catalog.client import HttpClient
from dane_catalog.microdata import MicrodataCatalog
from dane_catalog.search import search, stats
from dane_catalog.socrata import SocrataCatalog

# 1. Work offline with the prebuilt catalog ---------------------------
catalog = load()

print("== Catalog stats ==")
print(stats(catalog)["counts"])

print("\n== Search: 'pobreza monetaria' ==")
hits = search(catalog, "pobreza monetaria", limit=5)
for r in hits["results"]:
    print(f"  [{r['source']}] {r['id']} — {r['title']}")

print("\n== Search: GEIH microdata only ==")
hits = search(
    catalog,
    "gran encuesta integrada de hogares",
    source="microdatos.dane.gov.co",
    limit=5,
)
for r in hits["results"]:
    print(f"  {r['id']} — {r['title']}")

# 2. Query a live dataset with SoQL -----------------------------------
# DIVIPOLA department codes (id vcjz-niiq) — tiny demo table.
http = HttpClient()  # add proxy="rotate" if your IP is CDN-blocked
soc = SocrataCatalog(http)
rows = soc.query("vcjz-niiq", limit=5)
print("\n== DIVIPOLA departamentos (first 5 rows) ==")
for row in rows:
    print(" ", row)

# 3. Inspect a microdata study ----------------------------------------
md = MicrodataCatalog(http)
detail = md.study_detail("643")  # Censo Nacional de Población y Vivienda 2018
print("\n== CNPV 2018 study metadata (keys) ==")
print(sorted(detail)[:20] if isinstance(detail, dict) else type(detail))
