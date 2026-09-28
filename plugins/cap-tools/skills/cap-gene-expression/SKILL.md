---
name: cap-gene-expression
description: Pull per-cell expression of named genes from a CAP (celltype.info) dataset and summarise it per cell type — fraction of cells expressing and mean expression, optionally cross-tabulated against tissue/disease/donor. Use when you need to check whether a marker is actually expressed in a population, rather than whether it ranks highly in a differential-expression list.
---

# cap-gene-expression

Ask CAP for one gene's expression vector across every cell in a dataset, join it
to the per-cell labels, and report per cell type.

This answers the question `cap-degs` cannot: **is this gene expressed in this
population at all?** DE returns a ranked list, so a gene's absence from the top N
is ambiguous — unexpressed, or merely outranked. This measures it directly.

## When to invoke

- "is \<gene\> actually expressed in \<cell type\> in this atlas?"
- "what fraction of \<cell type\> express \<gene\>?"
- "check these marker genes across the mural/immune/epithelial populations"
- validating or challenging an annotation against a marker panel
- following up a `cap-degs` result where a gene was absent from the top N

**Not** for ranked marker discovery — use `cap-degs`, which is one call per cell
type rather than one per gene. Use this when you already know which genes matter.

**Not** for per-cell `obs` annotations on their own — use `remote-h5ad-obs`. That
needs a public `annDataUrl`, which many CAP datasets do not expose; this works
regardless (see "Why not the h5ad").

## Command

```sh
CAP="uvx --from git+https://github.com/Cellular-Semantics/cap_skills@v0.1.0#subdirectory=packages/cap-client cap"

$CAP expression <cap-dataset-url> --genes GENE [GENE ...] [options]
```

Needs `uv` and, on first run, network access to GitHub. Expects `cap-client`
0.1.0 or later (`$CAP --version`).

The full dataset URL is required; the labelset structure is read from the page.
Gene symbols are matched **exactly** against the dataset's var index — no
case-folding, no alias resolution.

**Options:**

- `--labelset NAME` — labelset to group by. Default: the `cell-labels` labelset
  with the most labels.
- `--cell-types NAME ...` — restrict output rows. Does **not** reduce transfer;
  CAP returns all cells either way.
- `--group-by LABELSET ...` — cross-tabulate against another labelset, e.g.
  `--group-by tissue disease`. **One extra call per labelset in total**, not per
  gene.
- `--min-expression FLOAT` — detection threshold, `value > this`. Default 0.0.
- `--embedding NAME` — default auto. The **bare** name (`umap`), not the obsm key
  (`X_umap`), which fails with `No match for FieldRef.Name(X_umap1)`.
- `--scale-max FLOAT` — row cap. Default: the dataset cell count. **Lowering it
  downsamples**; it does not rescale.
- `--per-cell FILE` — also write raw per-cell values. Large.
- `--list-obs-columns` — print the obs columns CAP exposes, then exit. The cheap
  way to see what `--group-by` could use, and it works on datasets
  `remote-h5ad-obs` cannot reach.
- `--delay SECONDS` (0.5), `--csv FILE`.

## Output

JSON on stdout; progress on stderr. One row per (cell type, gene), plus cross-tab
rows when `--group-by` is used:

```json
{"dataset_id": "3400", "labelset": "hgca_celltype_v1",
 "cell_type": "Angiogenic Pericytes", "group_by": "tissue", "group_value": "ileum",
 "gene": "RERGL", "n_cells": 337, "n_detected": 2, "pct_detected": 0.59,
 "mean_all": 0.0098, "mean_expressing": 1.653, "embedding": "umap"}
```

- `pct_detected` — **the number that settles marker questions.**
- `mean_all` — mean over all cells in the group, zeros included.
- `mean_expressing` — mean over detected cells only. High `mean_expressing` with
  low `pct_detected` means a small subpopulation, not weak expression.
- `group_by`/`group_value` — empty on the plain rows, populated on cross-tab rows,
  so both live in one output. Filter `group_by == ""` for the headline numbers.

Values are CAP's **normalised, log1p-scale** expression, not raw counts. Means are
of that quantity and are not comparable across datasets normalised differently.

A gene listed in `missing_genes` had **no match in the var index** — which is not
the same as "expressed at zero". Check the symbol before concluding anything
biological: retired symbols are a live hazard. `LRMP` was retired in 2020 and does
not resolve against this atlas; under its current symbol `IRAG2` it is the best
tuft-cell marker in the panel (97.9% vs ≤10.9%). HGNC settles it in one call:
`rest.genenames.org/fetch/prev_symbol/<SYMBOL>`.

## Traps

- **`scale-max` fails quietly.** At `1.0` it returns a single cell with
  `expressionMax: 0.0`, which reads like "gene not expressed" rather than "you
  asked for one cell". At `0.0` it raises `float division by zero`. It must be ≥
  the cell count for exact percentages; the default is the cell count, and
  lowering it emits a warning.
- **Do not parallelise.** Unauthenticated public API; requests are serial and
  paced, with backoff on 429/5xx honouring `Retry-After`.
- **Cross-tabulation assumes stable cell ordering.** `obsIds` ordering is stable
  across calls (verified byte-equal across three calls on 944,502 cells), which is
  what lets a `--group-by` labelset be fetched once and reused. The client
  re-checks it per gene and aborts rather than misaligning cells.

## Cost

One call per gene, each returning arrays of `n_cells`. The query also fetches the
UMAP coordinates — dead weight here, but it cannot be dropped without breaking the
persisted-query match — so transfer scales with cell count regardless of how few
cell types you want.

| dataset | cells | per gene |
|---|---|---|
| 934/3016 (adipose lymphoid) | 49,387 | ~1.3-1.8 s |
| 1030/3400 (HGCA gut, all cells) | 944,502 | ~11-16 s |

18 genes on the 944k-cell atlas took ~4 minutes. `--cell-types` does not reduce
this; the filtering is local.

## Why not the h5ad

1. **Many CAP datasets expose no anonymous `annDataUrl`.** Dataset 3400 returns
   nulls from `downloadUrls`, so `remote-h5ad-obs` cannot reach it at all.
2. Even where the h5ad is public, CSR storage is cell-major, so pulling four genes
   means reading every gene for the cells you want. This endpoint is gene-major by
   construction.

## When it breaks

`QUERY_NOT_IN_SAFELIST` means CAP redeployed. Run `$CAP recover-queries`; it
validates its transform against two known-good queries and refuses to emit if that
check fails, in which case re-capture from browser devtools (Network → graphql →
request payload). The fix belongs in `cap-client`, not here.

`DESIGN.md` in this directory covers the assumptions the array join rests on —
positional alignment, stable cell ordering, zero-preserving normalisation — and the
cross-checks against `cap-degs` that validated it. Read it before changing how the
arrays are joined, or before citing `pct_detected` as a biological quantity.

## Verified against

- **`project/934/dataset/3016`** (adipose lymphoid, 49,387 cells, 13 labels):
  MS4A1 ranks B cells top at **48.1%** with every other label ≤2.3%; CD3E is 20.2%
  in CD4⁺ T cells and 1.2% in B cells. 26 rows, ~4 s.
- **`project/1030/dataset/3400`** (HGCA gut v1, 944,502 cells, 94 labels): 18 genes
  x 4 mural labels. Reproduced the ABCC9 split a `cap-degs` run could only infer —
  Angiogenic Pericytes 41.3%, Secretory Pericytes 73.0%, Contractile Pericytes
  **2.6%**, SMC 7.9% — confirming the gene is genuinely absent from Contractile
  Pericytes rather than outranked. `n_cells` per label matches the dataset page.
- `--group-by tissue` on 3400: cross-tab rows sum back to the per-cell-type totals.
- `--list-obs-columns`: 87 columns on 3400. Auto-detection picks `umap` on both.
- A nonexistent gene is reported without aborting the run; a downsampling
  `--scale-max` warns and returns 5,488 of 49,387 cells.
- STMN1 at 54.5% in Tuft Progenitors vs 47.1% in Tuft Cells — a curated marker that
  does not discriminate — is pinned by a live test in
  `packages/cap-client/tests/test_live.py`.

Not yet exercised against a dataset whose embedding is not named `umap`, nor one
with several coordinate pairs in obs; the preference order (`umap`, `tsne`, `pca`,
then first match) is untested there.
