---
name: cap-degs
description: Pull CAP-computed differential expression (marker genes with logFC, score, p-value) per cell type from a celltype.info dataset, via CAP's public GraphQL endpoint. No browser, no authentication, and no h5ad download — the DE is computed server-side and fetched as JSON. Use when you need marker-gene evidence for the cell types in a CAP-hosted atlas.
---

# cap-degs

Fetch the differential expression CAP has computed for each cell type in a
labelset, or have it computed on demand. Seconds, not a 476 MB download.

## When to invoke

- "get the DEGs / marker genes for the cell types in this CAP dataset"
- "what genes distinguish \<cell type\> in \<celltype.info URL\>"
- "pull differential expression from CAP for \<atlas\>"
- gathering marker-gene evidence for a CAS build from a CAP-hosted atlas

**Not** for per-cell annotations (cell type assignments, ontology term ids,
curator rationale) — those live in the h5ad `obs` table; use `remote-h5ad-obs`.
**Not** for "is this gene expressed here?" — a DE list is ranked, so absence from
it is ambiguous; use `cap-gene-expression`.

## Command

```sh
CAP="uvx --from git+https://github.com/dosumis/atlas-curation-skills@v0.1.0#subdirectory=packages/cap-client cap"

$CAP degs <cap-dataset-url> [options]
```

Needs `uv` and, on first run, network access to GitHub. Expects `cap-client`
0.1.0 or later (`$CAP --version`).

The full dataset URL is required (not a bare id): the labelset structure is read
from the dataset page. Start with `$CAP labelsets <url>` when unsure which
annotation level you want.

**Options that change the answer, not just the volume:**

- `--labelset NAME` — default: the `cell-labels` labelset with the most labels,
  usually the finest level.
- `--vs CELL_TYPE` — compare against a named cell type instead of against all
  other cells. **This is the flag for sibling subtypes.** Run it in both
  directions: genes shared by the two populations cancel out, so each direction
  shows only what is specific to that side.
- `--sort-by {log_fold_change,score,p_value}` — default `log_fold_change`. See
  "Sorting" below; the two answer different questions.
- `--on-demand {auto,only,never}` — how to treat cell types CAP has no
  precomputed DE for. `auto` (default) computes them individually.
- `--only CELL_TYPE` — repeatable. **Use this for a cheap test run before
  pulling a whole labelset.**
- `--limit N` (200), `--max-pvalue P` (0.01), `--seed N` (42, what the web UI
  uses — changing it changes the results), `--delay SECONDS` (0.5).
- `--csv FILE` — also write the rows as CSV, for the record.

## Output

JSON on stdout; progress on stderr. One row per (cell type, gene):

```json
{"cell_type": "Paneth Cells", "n_cells": 468, "gene": "DEFA6",
 "logFC": 13.09, "score": 26.65, "pValue": 0.0,
 "method": "on-demand", "compared_to": "all other cells"}
```

`method` records which path produced the row; `compared_to` records the
comparator. Also in the payload: `fellback` (labels that had no precomputed DE)
and `missing` (labels that produced nothing, with the server's reason).

**Never rank or threshold logFC across `method` values.** On-demand reports up to
~30 where precomputed tops out near 9. Filter on `method` first.

## Interpreting the result

**vs-rest DE describes lineage, not discriminating markers.** The default
comparator answers a different question than a curator did. Curated marker genes
are chosen to separate a subtype from its *siblings*; vs-rest DE returns what
separates it from the whole atlas, which is lineage identity. Between two members
of one lineage it returns what they *share* — which reads as evidence the two
labels are interchangeable when it is nothing of the kind. Use vs-rest to confirm
a label sits in the right family; use `--vs` to adjudicate between siblings, and
do not treat a curated marker's absence from a vs-rest top-N as evidence against
the annotation.

**Verify the comparator's identity before trusting a paired comparison.** A
`--vs` result is only as meaningful as the label you compared against. In the
HGCA gut atlas `Smooth Muscle Cells (SMC)` is *visceral* muscle, so it cannot
test a pericyte-vs-vascular-SMC question — and produced a confidently wrong
answer when used that way. Check what the comparator actually is, with the same
rigour as the label under test.

**Absence from a DE list is not absence of expression.** The list is ranked and
truncated. Confirm with `cap-gene-expression`'s `pct_detected` before concluding
a marker is missing. A gene shared with the comparator vanishes from both sides
of a paired comparison while being expressed in 60-97% of both populations.

**Near-ceiling logFC (~26-30) is an artefact.** In sibling comparisons the top of
the logFC ranking is often a block at ~26-29 followed by a sharp discontinuity
down to ~10 — very-low-expression genes with unstable fold changes and
correspondingly weak `score`. Read the tier below the discontinuity, and
cross-check with `score`.

**A curated marker that fails to discriminate is a finding, not a bad query.**
Report it.

## Sorting: logFC vs score

Neither is universally better.

For a transcriptionally distinctive lineage, `score` is cleaner. Paneth Cells by
logFC lead with KLK12, KLK11, FZD9, CABP7, CCL24 (canonical markers only from
rank 9); by `score` they lead DEFA6, DEFA5, REG3A, PLA2G2A, LYZ, ITLN2, REG1A,
TFF3 — textbook, in order.

For a subtype inside a larger lineage, `score` is actively misleading and **logFC
is what recovers curated markers**. Against a whole-atlas background `score`
rewards genes that are abundant across the parent lineage. Measured against the
HGCA curators' own marker lists:

| label | by `score` | by `log_fold_change` |
|---|---|---|
| Homeostatic Macrophages | FOLR2 not in top 40 | FOLR2 #38 |
| Contractile Pericytes | ACTA2 #2, RERGL #24, NTRK2 missed | RERGL #28, ACTA2 #33, NTRK2 #35 |
| Tuft Progenitors | POU2F3 and STMN1 both missed | POU2F3 #9 |

By `score`, Homeostatic Macrophages return C1QA/B/C, HLA-DRA, MS4A6A, AIF1 — a
correct but generic pan-macrophage signature that would fit any of the six
macrophage labels in that atlas.

## Known limitations

**Small populations have no precomputed DE.** CAP's precomputed labelset DE omits
the smallest cell types and the server raises rather than returning an empty
list (`ParquetService.setup_gene_list() missing 1 required positional argument`).
CAP's own heatmap omits the same groups. The cutoff is proportional, and on a
large atlas it is aggressive: on the HGCA gut atlas (94 cell types, 1.5M cells)
only the 10 largest populations had precomputed DE.

`--on-demand auto` handles this; the result reports which labels took that path.
Very small populations can still fail entirely — check `missing`. On the gut atlas
Eosinophils (16 cells) and Interstitial Cells of Cajal (13 cells) are the ones to
watch.

## Be gentle with the endpoint

Requests are serial and paced inside the client; 429s and 5xx are retried with
backoff honouring `Retry-After`. **Do not parallelise** — this is an
unauthenticated public API, and the on-demand path costs three requests per cell
type. A 94-label labelset is ~280 requests; budget a few minutes and test with
`--only` first.

No auth is sent and none is needed. If a dataset requires login the page fetch or
session creation fails; report that rather than attempting auth.

## When it breaks

`QUERY_NOT_IN_SAFELIST` means CAP redeployed and the persisted query bodies no
longer match. Regenerate them:

```sh
$CAP recover-queries
```

It validates its own transform against two known-good queries first and refuses
to emit anything if that check fails, in which case re-capture from browser
devtools (Network → graphql → request payload). Either way the fix is a change to
`cap-client`, not to this skill: open an issue or a PR against
`packages/cap-client/src/cap_client/queries.py`. `$CAP introspect <TypeName>`
dumps an input shape — introspection is enabled — rather than guessing.

## Verified against

- `project/934/dataset/3016` (Human Adipose Tissue Atlas v1.0, Lymphoid cells):
  10/13 cell types, 2000 rows at `--limit 200`, ~8 s. B cells → PAX5, NIBAN3,
  COL19A1, CD22, BANK1; Treg → FOXP3, FANK1, LAYN, CTLA4. Matches the UI's
  "Top 3 genes in each group" heatmap. Same dataset `--labelset lvl2_cell_types`:
  2/2. `project/934/dataset/3012`: 5/5.
- `project/1030/dataset/3400` (HGCA gut v1), `--labelset hgca_celltype_v1`, 94
  labels. `--only "Paneth Cells"` (468 cells, no precomputed DE) returns all seven
  canonical Paneth markers within the top 15 by logFC.
- Cross-check across paths: Plasma Cells via `--on-demand only` returns JCHAIN,
  MZB1, DERL3 — the same leading markers as precomputed, at different magnitudes
  (JCHAIN 11.1 vs 9.4). The methods agree on gene identity, not on logFC scale.
- `--vs`: Contractile Pericytes vs Smooth Muscle Cells (SMC), both directions.
  The pericyte side returns RERGL, NOTCH3, NTRK2 and no SMC genes; the SMC side
  DES, CHRM3, TACR2, GREM1/2 and no pericyte genes. The shared contractile module
  (MYH11, MYOCD, ACTA2, TAGLN) cancels out and appears on neither side — expected,
  and the reason the flag exists.
- Tuft Progenitors vs Tuft Cells returns the proliferation programme (ASPM, AURKB,
  BIRC5 …), covered by a live test in `packages/cap-client/tests/test_live.py`.
