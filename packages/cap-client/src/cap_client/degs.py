"""Differential expression per cell type.

Two paths, and the distinction matters for interpretation:

  precomputed  CAP computed DE for the whole labelset in advance, each label
               against all other cells. One call per label.
  on-demand    we ask the server to compute one comparison now: a label against
               all other cells, or against a named sibling. Three calls per
               label.

The two are on DIFFERENT logFC SCALES (~9 vs ~30 ceilings). Never rank across
them -- the `method` field on every row records which produced it.
"""
from __future__ import annotations

import base64
import json

from .errors import CapError
from .labelsets import find_label
from .queries import Q_CUSTOM_DIFF, Q_DE_GENES, Q_GENERAL_DE, Q_SELECTION
from .session import create_session
from .transport import first_error

ROW_FIELDS = ["cell_type", "n_cells", "gene", "logFC", "score", "pValue",
              "method", "compared_to"]

SORT_KEYS = ["log_fold_change", "score", "p_value"]


def _de_genes(client, dataset_id, diff_key, selection_names, sort_by, max_pvalue, limit):
    return client.call("DEGenes", {
        "datasetId": dataset_id,
        "options": {"diffKey": diff_key, "selectionNames": selection_names,
                    "sortBy": sort_by, "sortOrder": "desc", "useGenesPattern": True,
                    "maxPValue": max_pvalue, "limit": limit, "offset": 0}}, Q_DE_GENES)


def selection_key(client, dataset_id, session_id, label):
    """sha256 key identifying the cell set of one label. Returns (key, error)."""
    r = client.call("Selection", {
        "datasetId": dataset_id,
        "options": {"sessionId": session_id,
                    "selection": [{"labelIdSelection": {"labelId": label["id"]}}]}}, Q_SELECTION)
    err = first_error(r, "Selection")
    if err:
        return None, err
    return r["data"]["datasetSession"]["singleSelectionKey"], None


def ondemand_genes(client, dataset_id, session_id, label, *, sort_by, max_pvalue,
                   limit, seed, bg_key=None):
    """On-demand DE for one label. Returns (genes, error); exactly one is set.

    Three calls, mirroring what CAP's web client does when you select a group in
    the embedding and hit "Compute DE":

      Selection(labelIdSelection) -> singleSelectionKey   (sha256 of the cell set)
      CustomDiff(currentSelectionKey, no background) -> diffKey
      DEGenes(diffKey, selectionNames=["selection"]) -> genes

    Leaving `backgroundSelectionsKey` unset is what makes the comparator "all
    other cells": the diffKey decodes to `<fgKey>;None;<downsampling>;<seed>`,
    and that `None` in the background slot is CAP's vs-rest default. Do NOT try
    to build the background with RemainingSelection(labelset=...) -- that means
    "cells carrying no label in this labelset", which on a fully annotated
    labelset is the empty set (it returns the sha256 of the empty string).

    `selectionNames` must be the literal "selection", not the cell type name: a
    custom diff has no label names in it, just the one anonymous selection.
    Passing the cell type name fails with the same setup_gene_list error the
    precomputed path raises, which is a misleading way for it to fail.
    """
    fg_key, err = selection_key(client, dataset_id, session_id, label)
    if err:
        return None, err

    opts = {"currentSelectionKey": fg_key, "downsamplingAllowed": True, "randomSeed": seed}
    if bg_key is not None:
        opts["backgroundSelectionsKey"] = bg_key
    r = client.call("CustomDiff", {"datasetId": dataset_id, "options": opts}, Q_CUSTOM_DIFF)
    err = first_error(r, "CustomDiff")
    if err:
        return None, err
    diff_key = r["data"]["datasetSession"]["differentialExpressions"]

    r = _de_genes(client, dataset_id, diff_key, ["selection"], sort_by, max_pvalue, limit)
    err = first_error(r, "DEGenes")
    if err:
        return None, err
    return r["data"]["datasetSession"]["diffGenesBySelection"][0]["genes"], None


def decode_diff_key(diff_key: str) -> str:
    """The human-readable inside of a `gen_de_<base64>` key, for the log."""
    prefix = "gen_de_"
    if not diff_key.startswith(prefix):
        return diff_key
    try:
        return base64.b64decode(diff_key[len(prefix):], validate=True).decode()
    except Exception:
        return diff_key


def fetch_degs(client, dataset_id, labelset, *, only=None, vs=None, limit=200,
               max_pvalue=0.01, sort_by="log_fold_change", seed=42,
               on_demand="auto", log=lambda m: None) -> dict:
    """Pull DE for the labels of one labelset. Returns a JSON-ready result dict.

    `only` restricts which labels are asked about (not which are registered).
    `vs` names a comparator label, which forces the on-demand path: the
    precomputed path only ever compares a label against everything else.
    """
    if sort_by not in SORT_KEYS:
        raise CapError(f"--sort-by must be one of {', '.join(SORT_KEYS)}")
    if on_demand not in ("auto", "only", "never"):
        raise CapError("--on-demand must be auto, only or never")
    if vs:
        on_demand = "only"

    session_labels = labelset["labels"]
    labels = session_labels
    if only:
        wanted = set(only)
        labels = [lb for lb in session_labels if lb["name"] in wanted]
        unknown = wanted - {lb["name"] for lb in labels}
        if unknown:
            raise CapError(f"No such cell type(s): {', '.join(sorted(unknown))}")
        log(f"  --only: {len(labels)} of {len(session_labels)} labels")

    bg_label = None
    if vs:
        bg_label = find_label(labelset, vs)
        if any(lb["id"] == bg_label["id"] for lb in labels):
            raise CapError(f"--vs '{vs}' is also in the foreground; pick a different "
                           "comparator or narrow --only.")
        log(f'  comparator: {bg_label["name"]} ({bg_label.get("count", 0)} cells)')

    session_id, _ = create_session(client, dataset_id, [labelset])

    diff_key = None
    if on_demand != "only":
        r = client.call("GeneralDE", {
            "datasetId": dataset_id,
            "options": {"labelsetId": labelset["id"], "randomSeed": seed,
                        "sessionId": session_id}}, Q_GENERAL_DE)
        if r.get("errors"):
            raise CapError(f"GeneralDE failed: {json.dumps(r['errors'])[:400]}")
        diff_key = r["data"]["datasetSession"]["generalDifferentialExpressions"]
        log(f"  diffKey: {decode_diff_key(diff_key)}")

    bg_key = None
    if bg_label is not None:
        bg_key, err = selection_key(client, dataset_id, session_id, bg_label)
        if err:
            raise CapError(f"Could not build comparator selection for "
                           f"'{bg_label['name']}': {err}")

    compared_to = bg_label["name"] if bg_label else "all other cells"
    rows, missing, fellback = [], [], []

    def emit(name, count, genes, method):
        for g in genes:
            rows.append({"cell_type": name, "n_cells": count, "gene": g["name"],
                         "logFC": g["logFoldChange"], "score": g["score"],
                         "pValue": g["pValue"], "method": method,
                         "compared_to": compared_to})

    for lb in labels:
        name, count = lb["name"], lb.get("count", 0)
        err = None
        if diff_key is not None:
            r = _de_genes(client, dataset_id, diff_key, [name], sort_by, max_pvalue, limit)
            if not r.get("errors"):
                emit(name, count,
                     r["data"]["datasetSession"]["diffGenesBySelection"][0]["genes"],
                     "precomputed")
                continue
            # Small populations are absent from CAP's precomputed DE, and the
            # server raises rather than returning an empty list.
            err = first_error(r, limit=80)

        if on_demand == "never":
            missing.append({"cell_type": name, "n_cells": count, "error": err})
            continue

        genes, oderr = ondemand_genes(client, dataset_id, session_id, lb, sort_by=sort_by,
                                      max_pvalue=max_pvalue, limit=limit, seed=seed,
                                      bg_key=bg_key)
        if oderr:
            missing.append({"cell_type": name, "n_cells": count, "error": oderr})
        else:
            emit(name, count, genes, "on-demand")
            if diff_key is not None:
                fellback.append({"cell_type": name, "n_cells": count})

    return {"dataset_id": dataset_id, "labelset": labelset["name"],
            "labelset_id": str(labelset["id"]), "compared_to": compared_to,
            "sort_by": sort_by, "max_pvalue": max_pvalue, "limit": limit, "seed": seed,
            "cell_types_requested": len(labels),
            "cell_types_done": len(labels) - len(missing),
            "n_rows": len(rows), "fellback": fellback, "missing": missing, "rows": rows}
