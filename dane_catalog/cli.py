"""Command-line interface for the DANE data catalog.

Every command prints structured JSON with ``--format json`` (the default) so
the CLI can be piped into other tools exactly like an API. ``--format table``
renders a compact human view.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import catalog as cat_mod
from .search import get as get_record
from .search import search as run_search
from .search import stats as catalog_stats
from .client import HttpClient
from .microdata import MicrodataCatalog
from .socrata import SocrataCatalog


def _emit(obj, fmt: str = "json") -> None:
    if fmt == "json":
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    elif fmt == "table":
        _emit_table(obj)
    else:
        raise SystemExit(f"unknown format: {fmt}")


def _emit_table(obj) -> None:
    if isinstance(obj, dict) and "results" in obj:
        rows = obj["results"]
        print(f"# {obj['total']} result(s) for query={obj['query']!r}")
        for r in rows:
            print(
                f"[{r['source']:>24}] {r['id']:<12} {r['title'][:90]}"
            )
        return
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _make_http(args) -> HttpClient:
    return HttpClient(
        proxy=getattr(args, "proxy", None),
        app_token=getattr(args, "app_token", None),
    )


def cmd_catalog(args) -> None:
    http = _make_http(args)
    outdir = Path(args.outdir)
    print("Building DANE catalog from live sources...", file=sys.stderr)

    if args.source == "all":
        catalog = cat_mod.build(http, full_sweep=args.full_sweep)
        if not catalog["datasets"] and not catalog["studies"]:
            print(
                "error: both sources returned zero records; refusing to "
                "save an empty catalog",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        # Partial rebuild: refresh one source, keep the other from the
        # existing catalog files if present.
        existing = {}
        full = outdir / "dane_catalog_full.json"
        if full.exists():
            try:
                existing = cat_mod.load(outdir)
            except Exception:  # noqa: BLE001
                existing = {}
        datasets = existing.get("datasets", [])
        studies = existing.get("studies", [])
        if args.source == "socrata":
            fresh = cat_mod.build_datasets(http, full_sweep=args.full_sweep)
            if not fresh and datasets:
                print(
                    "error: rebuild returned 0 datasets; keeping existing "
                    "catalog files",
                    file=sys.stderr,
                )
                sys.exit(1)
            datasets = fresh
        else:
            fresh = cat_mod.build_studies(http)
            if not fresh and studies:
                print(
                    "error: rebuild returned 0 studies; keeping existing "
                    "catalog files",
                    file=sys.stderr,
                )
                sys.exit(1)
            studies = fresh
        catalog = cat_mod.wrap(datasets, studies)

    written = cat_mod.save(catalog, outdir)
    _emit(
        {
            "status": "ok",
            "counts": catalog["counts"],
            "generated_at": catalog["generated_at"],
            "files": [str(p) for p in written],
        },
        args.format,
    )


def cmd_search(args) -> None:
    catalog = cat_mod.load(Path(args.catalog_dir))
    result = run_search(
        catalog,
        query=args.query,
        source=args.source,
        category=args.category,
        limit=args.limit,
        offset=args.offset,
    )
    _emit(result, args.format)


def cmd_info(args) -> None:
    catalog = cat_mod.load(Path(args.catalog_dir))
    rec = get_record(catalog, args.id)
    if rec is None:
        raise SystemExit(f"record not found in catalog: {args.id}")
    _emit(rec, args.format)


def cmd_stats(args) -> None:
    catalog = cat_mod.load(Path(args.catalog_dir))
    _emit(catalog_stats(catalog), args.format)


def cmd_fetch(args) -> None:
    http = _make_http(args)
    soc = SocrataCatalog(http)
    rows = soc.query(
        args.id,
        select=args.select,
        where=args.where,
        order=args.order,
        group=args.group,
        limit=args.limit,
        offset=args.offset,
    )
    if args.out:
        out = Path(args.out)
        if out.suffix.lower() == ".csv":
            keys = sorted({k for row in rows for k in row}) or ["result"]
            with out.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=keys)
                writer.writeheader()
                writer.writerows(rows)
        else:
            out.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        _emit({"status": "ok", "rows": len(rows), "file": str(out)}, args.format)
    else:
        _emit({"id": args.id, "rows_returned": len(rows), "data": rows}, args.format)


def cmd_study(args) -> None:
    http = _make_http(args)
    md = MicrodataCatalog(http)
    detail = md.study_detail(args.id)
    out = {"id": args.id, "detail": detail}
    if args.resources:
        try:
            out["resources"] = md.study_resources(args.id)
        except Exception as exc:  # noqa: BLE001
            out["resources_error"] = str(exc)
    _emit(out, args.format)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dane-catalog",
        description=(
            "Catalog and query all data published by Colombia's DANE: "
            "open datasets on datos.gov.co and microdata at "
            "microdatos.dane.gov.co."
        ),
    )
    p.add_argument(
        "--catalog-dir",
        default=str(cat_mod.CATALOG_DIR),
        help="directory containing the built catalog files",
    )
    p.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="output format (default: json)",
    )
    p.add_argument(
        "--proxy",
        default=None,
        help=(
            "route requests through a read-through proxy: 'allorigins', "
            "'corslol', 'rotate', or a custom template containing {url}. "
            "Useful when your IP range is blocked by the upstream CDN."
        ),
    )
    p.add_argument(
        "--app-token",
        default=None,
        help="Socrata application token (X-App-Token) for datos.gov.co",
    )
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("catalog", help="rebuild the catalog from live sources")
    c.add_argument("--outdir", default=str(cat_mod.CATALOG_DIR))
    c.add_argument(
        "--source",
        choices=["all", "socrata", "microdata"],
        default="all",
        help=(
            "which source to rebuild; partial rebuilds keep the other source "
            "from the existing catalog files (default: all)"
        ),
    )
    c.add_argument(
        "--full-sweep",
        action="store_true",
        help=(
            "scan every dataset on datos.gov.co instead of full-text "
            "pre-filtering; most complete but slower (used by the "
            "scheduled refresh)"
        ),
    )
    c.set_defaults(func=cmd_catalog)

    s = sub.add_parser("search", help="search the local catalog")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--source", choices=["datos.gov.co", "microdatos.dane.gov.co"])
    s.add_argument("--category")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--offset", type=int, default=0)
    s.set_defaults(func=cmd_search)

    i = sub.add_parser("info", help="full catalog record for one id")
    i.add_argument("id")
    i.set_defaults(func=cmd_info)

    st = sub.add_parser("stats", help="catalog summary statistics")
    st.set_defaults(func=cmd_stats)

    f = sub.add_parser("fetch", help="query a datos.gov.co dataset (SoQL)")
    f.add_argument("id", help="dataset id (4x4, e.g. vcjz-niiq)")
    f.add_argument("--select", help="SoQL $select")
    f.add_argument("--where", help="SoQL $where")
    f.add_argument("--order", help="SoQL $order")
    f.add_argument("--group", help="SoQL $group")
    f.add_argument("--limit", type=int, default=1000)
    f.add_argument("--offset", type=int, default=0)
    f.add_argument("--out", help="write rows to .json or .csv instead of stdout")
    f.set_defaults(func=cmd_fetch)

    m = sub.add_parser("study", help="microdata study detail (live)")
    m.add_argument("id", help="numeric study id, e.g. 643 (CNPV 2018)")
    m.add_argument("--resources", action="store_true", help="include file list")
    m.set_defaults(func=cmd_study)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
