# DANE Data Catalog

A unified, machine-readable catalog of **all data published by DANE**
(Departamento Administrativo Nacional de Estadística — Colombia's national
statistics office), queryable like an API.

The catalog is rebuilt weekly by GitHub Actions and committed to this
repository, so the files under [`catalog/`](catalog/) are always a fresh,
offline-queryable snapshot. A small CLI (and Python library) lets you search,
inspect and fetch any record — every command returns structured JSON so it
can be piped into `jq` or other tools.

## Sources

| Source | Type | Records | Access |
|---|---|---|---|
| `microdatos.dane.gov.co` | IHSN NADA microdata archive | 569 studies | Microdata files (SPSS/Stata/CSV), metadata |
| `www.datos.gov.co` | National open-data portal (Socrata) | 3 datasets | REST API (SoQL), CSV/JSON export |

**Coverage note.** This catalog scans *every* dataset on datos.gov.co and
keeps those published by DANE. As of the latest build, DANE's presence on
the national portal is limited to its three DIVIPOLA geographic-reference
datasets — virtually all of DANE's data output is published through its own
microdata archive, which is why the catalog treats it as the primary source.
The weekly refresh re-scans the whole portal, so any future DANE publication
on datos.gov.co is picked up automatically.

## Install

```bash
git clone https://github.com/<user>/dane-data-catalog.git
cd dane-data-catalog
pip install -r requirements.txt
```

Only dependency: `requests`. Python ≥ 3.10.

## Quick start

Search the offline catalog (accent-insensitive, ranked):

```bash
python -m dane_catalog.cli search "pobreza monetaria" --limit 5
```

```json
{
  "query": "pobreza monetaria",
  "filters": {"source": null, "category": null},
  "total": 38,
  "offset": 0,
  "limit": 5,
  "results": [
    {
      "id": "DANE-POBREZA-MONETARIA-Y-DESIGUALDAD-2024",
      "source": "microdatos.dane.gov.co",
      "type": "study",
      "title": "Medición de Pobreza Monetaria y Desigualdad - 2024",
      "year_start": "2024",
      "download_count": 4697
    }
  ]
}
```

Full details for one record (by `id` or `idno`):

```bash
python -m dane_catalog.cli info DANE-DCD-CNPV-2018
```

Catalog statistics:

```bash
python -m dane_catalog.cli stats
python -m dane_catalog.cli stats | jq '.by_source'
```

Human-readable table output:

```bash
python -m dane_catalog.cli --format table search "gran encuesta integrada" --limit 10
```

Filter by source or category, paginate:

```bash
python -m dane_catalog.cli search "empleo" --source microdatos.dane.gov.co --limit 20 --offset 40
python -m dane_catalog.cli search "agropecuario" --source datos.gov.co
```

## Fetching live data

`fetch` runs a SoQL query against any datos.gov.co dataset and prints JSON
(or saves `.json`/`.csv`):

```bash
# DIVIPOLA codes for departments, first 5 rows
python -m dane_catalog.cli fetch vcjz-niiq --limit 5

# filtered + aggregated
python -m dane_catalog.cli fetch vcjz-niiq \
  --select "nombre_departamento,count(*)" \
  --group "nombre_departamento" \
  --out departamentos.csv
```

`study` shows a microdata study's detail and downloadable files:

```bash
python -m dane_catalog.cli study 643 --resources
```

## Quarterly GDP (national accounts)

DANE publishes quarterly GDP only as Excel annexes on dane.gov.co — no
API, and the site blocks datacenter IPs. The `gdp` command fetches the
same official DANE figures from the OECD Quarterly National Accounts
database (to which DANE reports), which has a free SDMX REST API:

```bash
# nominal GDP (precios corrientes), original series, millions of COP
python -m dane_catalog.cli gdp

# real GDP (chained volume, reference year 2015), seasonally adjusted
python -m dane_catalog.cli gdp --prices constant --sa

# a window, table view, CSV export
python -m dane_catalog.cli --format table gdp --start 2019-Q1
python -m dane_catalog.cli gdp --start 2005-Q1 --out gdp_nominal.csv
```

Each row carries `quarter`, `value` (millions of COP) and `yoy_pct`.
Coverage: 2005-Q1 to the latest quarter DANE has published (currently
2026-Q1). Verified against DANE's own publications: the 2025 annual
total is 1,852,670,034 million COP (DANE: 1.852.670 miles de millones)
and 2026-Q1 nominal YoY growth is 5.9 % (DANE technical bulletin,
15/05/2026). The latest snapshot is also committed as
[`catalog/gdp_quarterly_nominal.csv`](catalog/gdp_quarterly_nominal.csv)
and refreshed weekly.

## Python API

```python
from dane_catalog import load, search, get, stats

catalog = load()                       # reads ./catalog
print(stats(catalog)["counts"])        # {'datasets': 3, 'studies': 569, 'total': 572}

hits = search(catalog, "censo", limit=10)
rec = get(catalog, "DANE-DIMPE-GEIH-2025")

# live querying
from dane_catalog import HttpClient, SocrataCatalog, MicrodataCatalog
http = HttpClient()
rows = SocrataCatalog(http).query("vcjz-niiq", limit=10)
detail = MicrodataCatalog(http).study_detail("643")

# quarterly GDP (DANE national accounts via OECD QNA)
from dane_catalog import national_accounts
gdp = national_accounts.with_yoy(national_accounts.quarterly_gdp(prices="current"))
latest = gdp[-1]   # {'quarter': '2026-Q1', 'value': 472759713.3, 'yoy_pct': 5.9, ...}
```

## Rebuilding the catalog

```bash
# both sources
python -m dane_catalog.cli catalog --full-sweep

# one source only (keeps the other from the existing files)
python -m dane_catalog.cli catalog --source microdata
python -m dane_catalog.cli catalog --source socrata --full-sweep
```

If your IP range is blocked by the CDNs (common for datacenter IPs), use a
read-through proxy and/or a free Socrata app token (global options go
before the subcommand):

```bash
python -m dane_catalog.cli --proxy rotate --app-token "$SOCRATA_APP_TOKEN" catalog --full-sweep
```

> **Note on `microdatos.dane.gov.co`:** its WAF blocks datacenter IPs
> (cloud providers, GitHub Actions runners, public CORS proxies) with
> HTTP 401/403. Rebuilding the microdata side works from Colombian
> residential ISPs; otherwise the committed catalog snapshot is used as-is.
> The datos.gov.co side refreshes without restrictions.

## Repository layout

```
dane_catalog/          # the package (client, socrata, microdata, national_accounts, catalog, search, cli)
catalog/               # generated catalog files (auto-updated weekly)
  dane_catalog_full.json   # everything, one file
  dane_datasets.json/csv   # datos.gov.co datasets only
  dane_microdata.json/csv  # microdata studies only
  gdp_quarterly_nominal.csv # quarterly nominal GDP (via OECD QNA)
examples/              # runnable examples
.github/workflows/     # weekly auto-refresh
```

## Record schema (common fields)

`id`, `source`, `type`, `title`, `description`, `category`, `tags`,
`publisher`, `nation`, `access`, `year_start`, `year_end`, `created_at`,
`updated_at`, `page_views_total`, `download_count`, `license`,
`landing_page`, `api_endpoint`, `csv_download`, `columns[]`.
Datasets add Socrata specifics (domain metadata); studies add
`idno`, `repository_id`, `authoring_entity` (as `publisher`).

## Automatic updates

[`.github/workflows/update-catalog.yml`](.github/workflows/update-catalog.yml)
rebuilds each source independently every Monday 06:00 UTC (and on demand),
and commits any changes to `catalog/`. Add a `SOCRATA_APP_TOKEN`
([free](https://www.datos.gov.co/profile/edit/developer_settings)) as a repo
secret for higher rate limits; without it the workflow falls back to proxy
rotation. As a safety guard, a rebuild that returns zero records for a
source exits with an error instead of overwriting the committed snapshot —
so a blocked or malfunctioning upstream can never shrink the catalog.

## License

Code: MIT (see [LICENSE](LICENSE)). Data and metadata remain property of
DANE and the respective publishing entities, subject to the terms of each
source portal.
