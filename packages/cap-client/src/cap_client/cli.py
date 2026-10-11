"""The `cap` command line: the supported interface to this package.

Two output channels, kept strictly apart:

  stdout  the result, as JSON by default (`--format text` for a human summary).
  stderr  progress, warnings, retries. Always safe to ignore or discard.

That split is what makes `cap degs ... | jq` work while a run is still chatty
about which cell types fell back to on-demand DE.
"""
from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .datasets import DEFAULT_LIMIT, consortium_tags, resolve_consortium, search_datasets
from .datasets import FIELDS as DATASET_FIELDS
from .degs import ROW_FIELDS as DEG_FIELDS
from .degs import SORT_KEYS, fetch_degs
from .downloads import download_urls, resolve_h5ad_url
from .errors import CapError
from .expression import PER_CELL_FIELDS, detect_embedding, fetch_expression, obs_columns
from .expression import ROW_FIELDS as EXPR_FIELDS
from .feedback import fetch_feedback, with_feedback
from .feedback import summarise as summarise_feedback
from .labelsets import fetch_labelsets, select_labelset, summarise
from .output import emit_json, write_csv
from .session import create_session
from .targets import parse_target
from .transport import GraphQLClient


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _client(args) -> GraphQLClient:
    return GraphQLClient(min_interval=args.delay, log=_log)


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("target", help="CAP dataset URL, e.g. "
                                  "https://celltype.info/project/1030/dataset/3400")
    ap.add_argument("--delay", type=float, default=0.5, metavar="SECONDS",
                    help="Minimum gap between API calls (default 0.5). Requests are "
                         "always serial; this spaces them out further.")
    ap.add_argument("--format", default="json", choices=["json", "text"],
                    help="stdout format (default json)")


# --- cap datasets ----------------------------------------------------------

def cmd_datasets(args) -> int:
    client = _client(args)
    tag_ids = resolve_consortium(client, args.consortium) if args.consortium else None
    rows = search_datasets(
        client, consortium_tag_ids=tag_ids, name=args.name,
        project_name=args.project_name, project_description=args.project_description,
        cell_types=args.cell_type, labelset=args.labelset,
        labelset_names=args.with_labelsets, limit=args.limit, offset=args.offset)

    if args.csv:
        write_csv(args.csv, DATASET_FIELDS,
                  [{**r, "consortium_tags": "|".join(r["consortium_tags"])} for r in rows])
        _log(f"{len(rows)} rows -> {args.csv}")

    if args.format == "json":
        emit_json({"n_datasets": len(rows), "limit": args.limit, "offset": args.offset,
                   "consortium_tag_ids": tag_ids, "datasets": rows})
    else:
        for r in rows:
            tags = ",".join(r["consortium_tags"])
            cells = f'{r["cell_count"]:,}' if r["cell_count"] is not None else "?"
            print(f'{r["dataset_id"]:>7}  {cells:>12}  {tags:20s} {r["dataset_name"]}')
        print(f"\n{len(rows)} datasets", file=sys.stderr)
    if len(rows) == args.limit:
        _log(f"warning: exactly --limit ({args.limit}) rows came back; there may be "
             "more. Raise --limit or page with --offset.")
    return 0


def cmd_consortia(args) -> int:
    tags = consortium_tags(_client(args))
    if args.format == "json":
        emit_json({"n_tags": len(tags), "consortium_tags": tags})
    else:
        for t in tags:
            print(f'{t["id"]:>4}  {t["title"]}')
    return 0


# --- cap labelsets ---------------------------------------------------------

def cmd_feedback(args, labels=None) -> int:
    project_id, dataset_id = parse_target(args.target)
    if labels is None:
        labels = fetch_feedback(project_id, dataset_id, sleep=time.sleep)
    rows = summarise_feedback(labels, dataset_id)
    if args.csv:
        write_csv(args.csv, list(rows[0]) if rows else
                  ["dataset_id", "labelset", "label_id", "label", "count",
                   "agree", "disagree", "idk", "n_feedback", "types", "users"], rows)
    if args.format == "json":
        emit_json({"dataset_id": dataset_id, "n_labels": len(labels),
                   "n_with_feedback": len(rows),
                   "labels": with_feedback(labels) if args.full else rows})
    else:
        print(f"{len(labels)} labels, {len(rows)} carrying feedback")
        for r in rows:
            print(f'{r["label_id"]:>8}  {r["label"][:34]:34s} '
                  f'{r["types"]:24s} agree={r["agree"]:g} disagree={r["disagree"]:g}')
    return 0


def cmd_labelsets(args, labelsets=None) -> int:
    project_id, dataset_id = parse_target(args.target)
    if labelsets is None:
        labelsets = fetch_labelsets(project_id, dataset_id)
    listing = summarise(labelsets)
    if args.format == "json":
        emit_json({"dataset_id": dataset_id, "n_labelsets": len(listing),
                   "labelsets": listing})
    else:
        for ls in listing:
            print(f'{ls["id"]:>8}  {(ls["mode"] or "?"):14s} {ls["name"]:24s} '
                  f'{ls["n_labels"]} labels')
    return 0


# --- cap degs --------------------------------------------------------------

def cmd_degs(args) -> int:
    project_id, dataset_id = parse_target(args.target)
    labelsets = fetch_labelsets(project_id, dataset_id)
    if args.list_labelsets:
        return cmd_labelsets(args, labelsets)
    chosen = select_labelset(labelsets, args.labelset)
    _log(f'Dataset {dataset_id}, labelset "{chosen["name"]}" ({chosen["id"]}), '
         f'{len(chosen["labels"])} labels')

    result = fetch_degs(_client(args), dataset_id, chosen, only=args.only, vs=args.vs,
                        limit=args.limit, max_pvalue=args.max_pvalue, sort_by=args.sort_by,
                        seed=args.seed, on_demand=args.on_demand, log=_log)

    if args.csv:
        write_csv(args.csv, DEG_FIELDS, result["rows"])
        _log(f'{result["n_rows"]} rows -> {args.csv}')
        result["csv"] = args.csv

    if result["fellback"]:
        _log(f'\n{len(result["fellback"])} cell types had no precomputed DE and were '
             "computed on demand vs all other cells:")
        for f in result["fellback"]:
            _log(f'  {f["cell_type"]} ({f["n_cells"]} cells)')
        _log("  NOTE: on-demand logFC is on a different scale to the precomputed values "
             "-- see the `method` column and do not rank across the two.")
    if result["missing"]:
        _log("\nNo DE obtained:")
        for m in result["missing"]:
            _log(f'  {m["cell_type"]} ({m["n_cells"]} cells): {m["error"]}')

    if args.format == "json":
        emit_json(result)
    else:
        _log("")
        print(f'{result["n_rows"]} rows across '
              f'{result["cell_types_done"]}/{result["cell_types_requested"]} cell types')
        for r in result["rows"]:
            print(f'{r["cell_type"]}\t{r["gene"]}\t{r["logFC"]}\t{r["score"]}\t{r["method"]}')
    return 0


# --- cap expression --------------------------------------------------------

def cmd_expression(args) -> int:
    project_id, dataset_id = parse_target(args.target)
    all_ls = fetch_labelsets(project_id, dataset_id)
    chosen = select_labelset(all_ls, args.labelset)

    group_sets = []
    for name in args.group_by or []:
        extra = select_labelset(all_ls, name)
        if extra["id"] != chosen["id"]:
            group_sets.append(extra)

    _log(f'Dataset {dataset_id}, labelset "{chosen["name"]}" '
         f'({len(chosen["labels"])} labels)')
    client = _client(args)
    session_id, cell_count = create_session(client, dataset_id, [chosen, *group_sets])

    cols = None
    if args.embedding == "auto":
        embedding, cols = detect_embedding(client, dataset_id, session_id, chosen["name"])
        _log(f"  embedding: {embedding} (auto-detected)")
    else:
        embedding = args.embedding

    if args.list_obs_columns:
        if cols is None:
            cols, _msg = obs_columns(client, dataset_id, session_id, chosen["name"])
        if args.format == "json":
            emit_json({"dataset_id": dataset_id, "labelset": chosen["name"],
                       "embedding": embedding, "n_obs_columns": len(cols),
                       "obs_columns": cols})
        else:
            print(f"\n{len(cols)} obs columns:")
            for c in cols:
                print("  " + c)
        return 0

    if not args.genes:
        raise CapError("--genes is required (or use --list-obs-columns)")

    scale_max = args.scale_max if args.scale_max is not None else float(cell_count)
    if scale_max < cell_count:
        _log(f"  warning: --scale-max {scale_max:.0f} < cell count {cell_count}; CAP will "
             "DOWNSAMPLE and the percentages will be estimates")

    result = fetch_expression(client, dataset_id, session_id, primary_labelset=chosen,
                              group_labelsets=group_sets, genes=args.genes,
                              embedding=embedding, scale_max=scale_max,
                              cell_types=args.cell_types, min_expression=args.min_expression,
                              per_cell=bool(args.per_cell), log=_log)

    if args.csv:
        write_csv(args.csv, EXPR_FIELDS, result["rows"])
        _log(f'\n{result["n_rows"]} rows -> {args.csv}')
        result["csv"] = args.csv
    if args.per_cell and result["per_cell"]:
        write_csv(args.per_cell, PER_CELL_FIELDS, result["per_cell"])
        _log(f'{len(result["per_cell"])} per-cell rows -> {args.per_cell}')
    if not args.per_cell:
        result.pop("per_cell", None)

    if result["missing_genes"]:
        _log("\nNo expression for: " + ", ".join(result["missing_genes"]))
        _log("  Check the symbol matches the dataset's var index (CAP matches exactly). "
             "A retired symbol is the usual cause.")

    if args.format == "json":
        emit_json(result)
    else:
        for r in result["rows"]:
            print(f'{r["cell_type"]}\t{r["gene"]}\t{r["pct_detected"]}\t'
                  f'{r["mean_expressing"]}\t{r["n_cells"]}')
    return 0


# --- cap download-urls -----------------------------------------------------

def cmd_download_urls(args) -> int:
    _project, dataset_id = parse_target(args.target)
    urls = download_urls(_client(args), dataset_id)
    if args.format == "json":
        emit_json({"dataset_id": dataset_id, **urls})
    else:
        for k, v in urls.items():
            if k != "__typename":
                print(f"{k}: {v}")
    return 0


def cmd_h5ad_url(args) -> int:
    url = resolve_h5ad_url(_client(args), args.target, log=_log)
    if args.format == "json":
        emit_json({"target": args.target, "h5ad_url": url})
    else:
        print(url)
    return 0


# --- maintenance -----------------------------------------------------------

def cmd_recover_queries(args) -> int:
    from .recover import DEFAULT_PAGE, recover
    return recover(args.page or DEFAULT_PAGE, args.operations or
                   ["Selection", "CustomDiff", "EmbeddingData", "DownloadUrls"])


def cmd_introspect(args) -> int:
    from .introspect import introspect
    return introspect(args.types)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="cap", description="Read annotation evidence out of CAP (celltype.info).")
    ap.add_argument("--version", action="version", version=f"cap-client {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("datasets", help="Search CAP's dataset catalogue")
    p.add_argument("--consortium", action="append", metavar="ID_OR_NAME",
                   help="Only datasets tagged by this consortium; id or name, "
                        "case-insensitive (e.g. 1 or 'Human Cell Atlas'). Repeatable. "
                        "The consortium tag is NOT in CAP's OLS report -- this is the "
                        "only way to get it.")
    p.add_argument("--name", help="Substring match on dataset name")
    p.add_argument("--project-name", help="Substring match on project name")
    p.add_argument("--project-description", help="Substring match on project description")
    p.add_argument("--cell-type", nargs="+", metavar="NAME",
                   help="Only datasets annotating these cell types")
    p.add_argument("--labelset", nargs="+", metavar="NAME",
                   help="Only datasets carrying a labelset with these names "
                        "(filtered server-side)")
    p.add_argument("--with-labelsets", nargs="*", metavar="NAME", default=None,
                   help="Include labelsets in the output: bare for all, or named ones. "
                        "Off by default because 'all' means every label of every "
                        "labelset -- 2.4 MB across the 61 HCA datasets, versus 95 KB "
                        "without. Prefer `cap labelsets <url>` for one dataset.")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                   help=f"Max datasets (default {DEFAULT_LIMIT}; 127 are public)")
    p.add_argument("--offset", type=int, default=0, help="Skip this many (default 0)")
    p.add_argument("--csv", metavar="FILE", help="Also write the rows as CSV")
    p.add_argument("--delay", type=float, default=0.5, metavar="SECONDS",
                   help="Minimum gap between API calls (default 0.5)")
    p.add_argument("--format", default="json", choices=["json", "text"],
                   help="stdout format (default json)")
    p.set_defaults(func=cmd_datasets)

    p = sub.add_parser("consortia", help="List the consortium tags datasets can carry")
    p.add_argument("--delay", type=float, default=0.5, metavar="SECONDS")
    p.add_argument("--format", default="json", choices=["json", "text"])
    p.set_defaults(func=cmd_consortia)

    p = sub.add_parser(
        "feedback", help="Community feedback on a dataset's labels",
        description="Scores and typed explanations readers have left on labels. "
                    "Read from the page payload: CAP exposes no API for this.")
    _common(p)
    p.add_argument("--full", action="store_true",
                   help="Emit every feedback entry, not one summary row per label")
    p.add_argument("--csv", metavar="FILE", help="Also write the rows as CSV")
    p.set_defaults(func=cmd_feedback)

    p = sub.add_parser("labelsets", help="List the labelsets and labels of a dataset")
    _common(p)
    p.set_defaults(func=cmd_labelsets)

    p = sub.add_parser("degs", help="Differential expression per cell type",
                       description="Pull CAP's DE results per cell type.")
    _common(p)
    p.add_argument("--labelset", help="Labelset name (default: the cell-labels labelset "
                                     "with the most labels)")
    p.add_argument("--list-labelsets", action="store_true", help="List labelsets and exit")
    p.add_argument("--limit", type=int, default=200, help="Max genes per cell type (default 200)")
    p.add_argument("--max-pvalue", type=float, default=0.01, help="p-value cutoff (default 0.01)")
    p.add_argument("--sort-by", default="log_fold_change", choices=SORT_KEYS,
                   help="Ranking. log_fold_change favours restricted, specific genes; "
                        "score favours abundant ones. Both are worth checking.")
    p.add_argument("--seed", type=int, default=42, help="CAP downsampling seed (default 42)")
    p.add_argument("--only", action="append", metavar="CELL_TYPE",
                   help="Restrict to this cell type (repeatable). Use for a cheap test "
                        "run before pulling a whole labelset.")
    p.add_argument("--vs", metavar="CELL_TYPE",
                   help="Compare against this cell type instead of all other cells. "
                        "Forces the on-demand path. Use for sibling subtypes, where a "
                        "vs-rest comparison only returns shared lineage genes.")
    p.add_argument("--on-demand", default="auto", choices=["auto", "only", "never"],
                   help="On-demand DE for cell types with no precomputed DE. auto "
                        "(default): fall back per missing label. only: skip the "
                        "precomputed path. never: precomputed only.")
    p.add_argument("--csv", metavar="FILE", help="Also write the rows as CSV")
    p.set_defaults(func=cmd_degs)

    p = sub.add_parser("expression", help="Per-cell-type expression of named genes")
    _common(p)
    p.add_argument("--genes", nargs="+", metavar="GENE",
                   help="Gene symbols. Required unless --list-obs-columns.")
    p.add_argument("--labelset", help="Labelset to group by (default: the cell-labels "
                                     "labelset with the most labels)")
    p.add_argument("--cell-types", nargs="+", metavar="NAME",
                   help="Restrict output to these labels (default: all)")
    p.add_argument("--group-by", nargs="+", metavar="LABELSET",
                   help="Cross-tabulate each cell type against these labelsets (tissue, "
                        "disease, donor). One extra call per labelset in total, not per gene.")
    p.add_argument("--embedding", default="auto",
                   help="Embedding name (default: auto-detect). Bare name, e.g. 'umap', "
                        "NOT 'X_umap'.")
    p.add_argument("--min-expression", type=float, default=0.0,
                   help="Detection threshold; a cell counts as expressing when value > "
                        "this (default 0.0)")
    p.add_argument("--scale-max", type=float, default=None,
                   help="scaleMaxPlan row cap (default: the dataset cell count). Lower "
                        "values DOWNSAMPLE.")
    p.add_argument("--per-cell", metavar="FILE",
                   help="Also write raw per-cell values (obs_id, cell_type, gene, value). Large.")
    p.add_argument("--list-obs-columns", action="store_true",
                   help="Print the obs columns CAP exposes, then exit")
    p.add_argument("--csv", metavar="FILE", help="Also write the summary rows as CSV")
    p.set_defaults(func=cmd_expression)

    p = sub.add_parser("download-urls", help="The download URLs CAP exposes for a dataset")
    _common(p)
    p.set_defaults(func=cmd_download_urls)

    p = sub.add_parser("h5ad-url", help="Resolve a CAP dataset URL to its h5ad URL")
    _common(p)
    p.set_defaults(func=cmd_h5ad_url)

    p = sub.add_parser("recover-queries",
                       help="Regenerate the persisted query bodies from CAP's JS bundle")
    p.add_argument("--page", help="Dataset page to read the bundle from")
    p.add_argument("operations", nargs="*", help="Operation names to recover")
    p.set_defaults(func=cmd_recover_queries)

    p = sub.add_parser("introspect", help="Dump a GraphQL input/enum type from CAP")
    p.add_argument("types", nargs="+", metavar="TYPE")
    p.set_defaults(func=cmd_introspect)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CapError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
