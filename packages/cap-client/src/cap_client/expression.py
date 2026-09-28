"""Per-cell expression of named genes, summarised per cell type.

This answers the question DE cannot: is this gene *expressed* in this
population, as a fraction of cells detecting it? A DE list is ranked, so absence
from the top N is ambiguous -- unexpressed, or merely outranked. `pct_detected`
settles it.

CAP has no "give me expression per cell type" operation. What it has is the
embedding view: one call returns every cell's coordinates, its label ids for one
labelset, and one gene's expression vector. Aggregating that per label is done
here, client-side.
"""
from __future__ import annotations

import re

from .errors import CapError
from .queries import Q_EMBEDDING_DATA
from .transport import first_error

ROW_FIELDS = ["dataset_id", "labelset", "cell_type", "group_by", "group_value", "gene",
              "n_cells", "n_detected", "pct_detected", "mean_all", "mean_expressing",
              "embedding"]

PER_CELL_FIELDS = ["obs_id", "cell_type", "gene", "value"]

_EMBEDDING_PREFERENCE = ("umap", "tsne", "pca")


def embedding_call(client, dataset_id, session_id, embedding, gene, labelset, scale_max):
    """One EmbeddingData call.

    `labelset` is a SINGLE labelset name -- the field takes one name, not a list,
    and a comma-joined string is rejected.
    """
    opts = {"embedding": embedding, "scaleMaxPlan": float(scale_max),
            "sessionId": session_id, "labelsets": labelset}
    if gene is not None:
        opts["selectionGene"] = gene
    return client.call("EmbeddingData", {"datasetId": dataset_id, "options": opts},
                       Q_EMBEDDING_DATA)


def obs_columns(client, dataset_id, session_id, labelset) -> tuple[list[str], str]:
    """Read the backing parquet's column list out of a deliberate error.

    Asking for a nonexistent embedding makes CAP report `No match for
    FieldRef.Name(<embedding>1) in <schema>`, and the schema it dumps is the full
    obs column list. That is also how the embedding name is discovered:
    coordinates live in obs as `<embedding>1` / `<embedding>2`.
    """
    r = embedding_call(client, dataset_id, session_id, "__cap_probe__", None, labelset, 10.0)
    msg = (r.get("errors") or [{}])[0].get("message", "")
    return re.findall(r"^([A-Za-z0-9_.]+):\s", msg, re.M), msg


def detect_embedding(client, dataset_id, session_id, labelset) -> tuple[str, list[str]]:
    cols, msg = obs_columns(client, dataset_id, session_id, labelset)
    if not cols:
        raise CapError("Could not read obs columns to auto-detect the embedding; pass "
                       "--embedding explicitly. Server said: " + msg[:200])
    names = set(cols)
    cands = [c[:-1] for c in cols if c.endswith("1") and c[:-1] + "2" in names]
    if not cands:
        raise CapError("No <name>1/<name>2 coordinate pair among obs columns: "
                       + ", ".join(cols[:40]))
    for pref in _EMBEDDING_PREFERENCE:
        for c in cands:
            if c.lower() == pref:
                return c, cols
    return cands[0], cols


def _summarise(rows, *, dataset_id, primary, embedding, gene, cell_names, values,
               min_expression, wanted, group_by="", group_values=None):
    agg: dict[tuple[str, str], list] = {}
    it = (zip(cell_names, values, strict=True) if group_values is None
          else zip(cell_names, values, group_values, strict=True))
    for rec in it:
        ct, v = rec[0], rec[1]
        if ct is None or (wanted and ct not in wanted):
            continue
        key = (ct, rec[2] if group_values is not None else "")
        a = agg.setdefault(key, [0, 0, 0.0, 0.0])
        a[0] += 1
        a[2] += v
        if v > min_expression:
            a[1] += 1
            a[3] += v
    for (ct, gv), (n, npos, tot, totpos) in sorted(agg.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        rows.append({"dataset_id": dataset_id, "labelset": primary, "cell_type": ct,
                     "group_by": group_by, "group_value": gv or "", "gene": gene,
                     "n_cells": n, "n_detected": npos,
                     "pct_detected": round(100.0 * npos / n, 2) if n else 0.0,
                     "mean_all": round(tot / n, 4) if n else 0.0,
                     "mean_expressing": round(totpos / npos, 4) if npos else 0.0,
                     "embedding": embedding})


def fetch_expression(client, dataset_id, session_id, *, primary_labelset, group_labelsets,
                     genes, embedding, scale_max, cell_types=None, min_expression=0.0,
                     per_cell=False, log=lambda m: None) -> dict:
    """Summarise expression of `genes` per cell type, optionally cross-tabulated.

    `group_labelsets` are extra labelsets (tissue, disease, donor) to cross-tab
    against; each costs ONE extra call in total, not one per gene, because obsIds
    ordering is stable across calls and the label vectors can be reused.
    """
    if not genes:
        raise CapError("At least one gene is required.")
    primary = primary_labelset["name"]

    id2name = {}
    for ls in [primary_labelset, *group_labelsets]:
        for lb in ls["labels"]:
            id2name[(ls["name"], str(lb["id"]))] = lb["name"]

    wanted = set(cell_types) if cell_types else None
    if wanted:
        known = {lb["name"] for lb in primary_labelset["labels"]}
        unknown = wanted - known
        if unknown:
            raise CapError(f"No such cell type(s) in {primary}: {', '.join(sorted(unknown))}")

    extra: dict[str, list] = {}
    for ls in group_labelsets:
        r = embedding_call(client, dataset_id, session_id, embedding, None, ls["name"], scale_max)
        err = first_error(r, limit=200)
        if err:
            raise CapError(f"Could not fetch labelset '{ls['name']}': {err}")
        anns = r["data"]["datasetSession"]["embeddingData"]["annotations"]
        extra[ls["name"]] = next(a["labelIds"] for a in anns if a["name"] == ls["name"])
        log(f"  cross-tab labelset: {ls['name']}")

    rows, per_cell_rows, missing = [], [], []
    ref_obs = None

    for gene in genes:
        r = embedding_call(client, dataset_id, session_id, embedding, gene, primary, scale_max)
        err = first_error(r, limit=160)
        if err:
            log(f"  {gene}: FAILED -- {err}")
            missing.append(gene)
            continue
        d = r["data"]["datasetSession"]["embeddingData"]
        expr = d.get("geneExpression") or []
        if not expr:
            log(f"  {gene}: no expression returned (gene absent from the dataset?)")
            missing.append(gene)
            continue
        obs_ids = d.get("obsIds") or []
        lids = next(a["labelIds"] for a in d["annotations"] if a["name"] == primary)
        cell_names = [id2name.get((primary, str(i))) for i in lids]

        # Cross-tab vectors came from a different call; guard the assumption that
        # CAP returns cells in a stable order.
        if extra:
            if ref_obs is None:
                ref_obs = obs_ids
            elif obs_ids != ref_obs:
                raise CapError("obsIds ordering changed between calls -- cross-tabulation "
                               "would misalign cells. Rerun without --group-by.")

        common = {"dataset_id": dataset_id, "primary": primary, "embedding": embedding,
                  "gene": gene, "cell_names": cell_names, "values": expr,
                  "min_expression": min_expression, "wanted": wanted}
        _summarise(rows, **common)
        for gname, gl in extra.items():
            _summarise(rows, **common, group_by=gname,
                       group_values=[id2name.get((gname, str(i))) for i in gl])

        if per_cell:
            for oid, ct, v in zip(obs_ids, cell_names, expr, strict=True):
                if ct is None or (wanted and ct not in wanted):
                    continue
                per_cell_rows.append({"obs_id": oid, "cell_type": ct, "gene": gene, "value": v})

        log(f"  {gene:12} {len(expr):>8} cells  max={d.get('expressionMax')}")

    if not rows:
        raise CapError("No expression obtained for any requested gene. Check the symbols "
                       "match the dataset's var index (CAP matches exactly) -- retired "
                       "symbols are a common cause.")

    return {"dataset_id": dataset_id, "labelset": primary, "embedding": embedding,
            "genes": list(genes), "missing_genes": missing,
            "min_expression": min_expression, "scale_max": scale_max,
            "group_by": [ls["name"] for ls in group_labelsets],
            "n_rows": len(rows), "rows": rows, "per_cell": per_cell_rows}
