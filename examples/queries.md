# Example queries

All commands default to JSON output — pipe them into `jq` for slicing.
Add `--format table` right after `cli` for human-readable output.

## Find data

```bash
# poverty measurement studies
python -m dane_catalog.cli search "pobreza monetaria"

# everything about the 2018 census
python -m dane_catalog.cli search "censo nacional de población"

# labour market only (microdata source)
python -m dane_catalog.cli search "empleo" --source microdatos.dane.gov.co --limit 50

# DANE datasets on the national open-data portal
python -m dane_catalog.cli search "" --source datos.gov.co

# browse a category
python -m dane_catalog.cli search "" --category "Mercado Laboral." --limit 100

# accent-insensitive: "educación" == "educacion"
python -m dane_catalog.cli search "educacion formal"

# paginate
python -m dane_catalog.cli search "encuesta" --limit 20 --offset 60
```

## Inspect a record

```bash
# by id or idno — same result
python -m dane_catalog.cli info DANE-DCD-CNPV-2018
python -m dane_catalog.cli info vcjz-niiq

# just the landing page and download stats
python -m dane_catalog.cli info DANE-DIMPE-GEIH-2025 | jq '{landing_page, download_count, page_views_total}'
```

## Catalog statistics

```bash
python -m dane_catalog.cli stats
python -m dane_catalog.cli stats | jq '.by_category'
python -m dane_catalog.cli stats | jq '.top_by_downloads[:5]'
```

## Fetch live data (datos.gov.co / Socrata)

```bash
# DIVIPOLA department codes
python -m dane_catalog.cli fetch vcjz-niiq --limit 5

# municipalities of one department, sorted
python -m dane_catalog.cli fetch gdxc-w37w \
  --where "codigo_departamento='05'" \
  --order "nombre_municipio" --limit 200 --out antioquia.json

# aggregation
python -m dane_catalog.cli fetch gdxc-w37w \
  --select "nombre_departamento,count(*) as n_municipios" \
  --group "nombre_departamento" --out municipios_por_depto.csv
```

## Microdata studies (NADA)

```bash
# study detail + downloadable files
python -m dane_catalog.cli study 643
python -m dane_catalog.cli study 643 --resources | jq '.data_files[] | {filename, file_type, size}'
```

## Quarterly GDP (national accounts, via OECD QNA)

```bash
# nominal GDP since 2015, with YoY growth
python -m dane_catalog.cli gdp --start 2015-Q1

# just the latest quarter
python -m dane_catalog.cli gdp | jq '.series[-1]'

# real GDP (chained volume, 2015 reference year), seasonally adjusted
python -m dane_catalog.cli gdp --prices constant --sa | jq '.series[-4:]'

# export for a spreadsheet
python -m dane_catalog.cli gdp --out gdp_nominal.csv

# annual totals from the quarterly series
python -m dane_catalog.cli gdp \
  | jq '[.series[] | {y: .quarter[:4], v: .value}] | group_by(.y)
        | map({year: .[0].y, gdp_millions_cop: ([.[].v] | add)})'
```

## Rebuild the catalog yourself

```bash
# full rebuild (scans the whole datos.gov.co portal)
python -m dane_catalog.cli catalog --full-sweep

# behind a blocked IP (global options go before the subcommand)
python -m dane_catalog.cli --proxy rotate --app-token "$SOCRATA_APP_TOKEN" catalog --full-sweep

# refresh only one side
python -m dane_catalog.cli catalog --source microdata
```

## Python snippets

```python
from dane_catalog import load, search, get

catalog = load()

# all GEIH years, newest first
hits = search(catalog, "GEIH", limit=100)["results"]
for h in hits:
    print(h["idno"] if "idno" in h else h["id"], "-", h["title"])

# everything with downloadable microdata
studies = [s for s in catalog["studies"] if s["access"] == "direct"]
print(len(studies), "studies with direct microdata")

# most downloaded records overall
recs = catalog["datasets"] + catalog["studies"]
for r in sorted(recs, key=lambda x: -(x["download_count"] or 0))[:10]:
    print(f'{r["download_count"]:>10}  {r["title"][:70]}')
```
