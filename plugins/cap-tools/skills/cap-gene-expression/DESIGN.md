# cap-gene-expression — how it works, why, and what it assumes

Background note for maintainers. `SKILL.md` is the operational reference (what
the flags do, what breaks); this document explains the reasoning and records the
checks that were run before the skill was trusted. If the two ever disagree,
`SKILL.md` wins on usage and this file wins on rationale.

---

## 1. The problem

CAP serves precomputed differential expression, which the sibling `cap-degs`
skill pulls. DE gives you a **ranked list** of genes per cell type. That is the
right tool for "what marks this population?" but it cannot answer "is this gene
expressed in this population?", because a gene can be missing from the top N for
two completely different reasons:

1. it is not expressed, or
2. it is expressed, but other genes rank above it.

These look identical in the output. Any argument of the form "marker X is absent
from this cell type's DE list, therefore the annotation is wrong" is unsound
until you distinguish them.

This is not a hypothetical. In our gut-atlas analysis, PDGFRβ — a canonical
mural marker — is absent from the Contractile Pericytes top-60 DE list, yet is
detected in **63.1%** of those cells. Concluding "no PDGFRB" from the DE list
alone would have been flatly wrong.

The skill measures the thing directly: for a named gene, what fraction of the
cells in each label actually express it.

## 2. How it works

CAP's web UI draws feature plots — a UMAP coloured by one gene. To do that the
server must hand the browser a per-cell expression vector. That endpoint is
`EmbeddingData`, and it is what the skill calls:

```
datasetSession(datasetId) { embeddingData(options: {
    embedding: "umap", scaleMaxPlan: <cell count>,
    selectionGene: "<GENE>", sessionId: <id>, labelsets: "<labelset>"
}) { obsIds geneExpression annotations { name labelIds } expressionMin expressionMax } }
```

It returns three arrays of equal length — one element per cell:

| array | contents |
|---|---|
| `obsIds` | cell barcodes / row ids |
| `geneExpression` | that gene's normalised value in each cell |
| `annotations[].labelIds` | which label each cell carries, in the requested labelset |

The skill zips the second and third arrays, groups by label, and counts. That's
the whole idea. Everything else is plumbing:

- **Session registration.** The server refuses to serve a labelset it has not
  seen in a session, so the skill registers one first (client-generated id,
  same as `cap-degs`).
- **Embedding auto-detection.** `embedding` is required but not discoverable
  from any safelisted query. Asking for a nonexistent embedding makes the server
  dump the entire obs schema in its error message; coordinates live in obs as
  `<name>1`/`<name>2`, so any such column pair names an embedding.
- **Cross-tabulation.** Extra labelsets are fetched once each (gene omitted →
  labels returned, expression empty) and reused across all genes, which is only
  valid because cell ordering is stable — see assumption A2.

This is the same public, unauthenticated API the browser uses. Nothing is being
circumvented; the skill is a scripted client.

## 3. Why not read the h5ad

The obvious alternative is a byte-range read of `X` from the published h5ad, as
the `remote-h5ad-obs` skill does for `obs`. Two reasons it loses:

1. **Access.** Many CAP datasets expose no anonymous download URL. Dataset 3400
   returns nulls from `downloadUrls`, so that route cannot reach it at all.
2. **Storage layout.** h5ad expression matrices are usually CSR, which is
   cell-major: pulling four genes means reading every gene for every cell you
   care about. `EmbeddingData` is gene-major by construction — one gene, one
   vector.

The tradeoff is that transfer scales with the *whole dataset's* cell count
regardless of how few cell types you want, because the server returns all cells
and filtering happens locally. On a 944k-cell atlas that is ~11-16 s per gene.

## 4. Assumptions

These are load-bearing. If one breaks, the numbers are wrong — in most cases
silently.

**A1. The three arrays are positionally aligned.** Element *i* of
`geneExpression` is the same cell as element *i* of `labelIds` and `obsIds`.
Nothing in the API states this; it is inferred from the fact that the UI must
colour each plotted point by its own value. *Checked indirectly by A4 and by the
marker-identity controls in §5.*

**A2. Cell ordering is stable across separate calls.** Required only for
`--group-by`, which zips a label vector fetched in one call against expression
fetched in another. *Directly verified* (§5.3), and the skill re-checks `obsIds`
at runtime and aborts rather than misaligning cells.

**A3. `scaleMaxPlan` ≥ cell count returns every cell.** Below the cell count it
downsamples, so percentages become estimates. The skill defaults it to the cell
count and warns if lowered. *Checked by A4 — label totals match exactly, which
they could not if cells were being dropped.*

**A4. The labels CAP returns are the dataset's real labels**, not something
derived from the session we registered. We send label ids and names when
creating the session, so in principle the join could be circular. It is not:
per-label cell counts come back matching the dataset page independently.

**A5. Values are normalised, zero-preserving expression.** `pct_detected` treats
`> 0` as "expressed", which is only meaningful if normalisation maps zero counts
to zero. Log1p-of-normalised-counts does; the observed value ranges
(max ≈ 3-6, many exact zeros) are consistent with it. **This is an assumption
about CAP's preprocessing that we have not seen documented.** It means
`pct_detected` is a *detection* rate, subject to dropout — it is a lower bound
on the fraction of cells truly expressing the gene, not a biological truth.

**A6. Gene symbols match the var index exactly.** No case-folding, no alias
resolution. A symbol that does not match returns empty and is reported as "no
expression" — which means *not found*, not *expressed at zero*. These are very
different conclusions and the skill cannot tell them apart. Always check the
symbol before drawing a biological inference from a null result.

**A7. Expression and DE come from the same underlying matrix.** Assumed because
both are served by the same session-scoped API. If CAP ever computed DE on a
different layer than it plots, the concordance in §5 would degrade.

## 5. Evidence

### 5.1 Marker-identity controls on an independent dataset

Run on `project/934/dataset/3016` (adipose lymphoid, 49,387 cells) — a dataset
unrelated to the analysis the skill was built for, with textbook expected
answers:

| gene | expected top | result |
|---|---|---|
| MS4A1 (B-cell) | B cells | **48.1%** in B cells; every other label ≤2.3% |
| CD3E (T-cell) | T cells | 20.2% in CD4⁺ T cells; 1.2% in B cells |

If the label join were scrambled, or the arrays misaligned, these would not come
out clean. They do.

### 5.2 Cell counts reconcile exactly

On dataset 3400, `n_cells` per label from the joined arrays matches the label
counts shown on the dataset page: Angiogenic Pericytes 891, Contractile
Pericytes 1313, Secretory Pericytes 204, SMC 706. Exact agreement, not
approximate. This simultaneously supports A1, A3 and A4 — a misalignment,
silent downsampling, or a bogus label mapping would all show up here.

### 5.3 Cell ordering is stable

Three separate `EmbeddingData` calls on dataset 3400 (two different genes, plus
one gene-less call for a different labelset) returned `obsIds` arrays that were
element-wise identical, all of length 944,502. This is what licenses A2.

### 5.4 Cross-check against the DE results

The strongest test: the skill and `cap-degs` are independent paths through the
same data, so they should agree — and where they disagree, it should be in a
direction we can predict.

Across 18 genes x 4 mural labels (72 gene-label pairs), splitting on whether the
gene appeared in that label's top-60 DE list by logFC:

| | n | median `pct_detected` |
|---|---|---|
| gene **is** in that label's DE top-60 | 36 | **78.0%** |
| gene is **not** in the list | 36 | **8.2%** |

A ~10x separation in the expected direction. The two methods broadly agree,
which is what you want from a correctness check.

**Where they disagree is the point of the skill.** Nine gene-label pairs are
expressed in >30% of cells yet absent from that label's DE top-60:

| gene | label | detected |
|---|---|---|
| TAGLN | Secretory Pericytes | 65.2% |
| PDGFRB | Contractile Pericytes | 63.1% |
| MYH11 | Secretory Pericytes | 62.7% |
| TAGLN | Angiogenic Pericytes | 61.4% |
| STEAP4 | Secretory Pericytes | 47.1% |
| NDUFA4L2 | Contractile Pericytes | 46.3% |
| CSPG4 | Secretory Pericytes | 40.7% |
| CSPG4 | Contractile Pericytes | 36.3% |
| MYH11 | Angiogenic Pericytes | 31.3% |

Every one of these is a case where reading absence-from-DE-list as
absence-of-expression would have produced a wrong biological conclusion. CSPG4
(NG2, a canonical pericyte marker) appears in **no** label's top-60 while being
detected in 36-41% of two of them.

The converse also occurs: genes that rank well in DE without being broadly
expressed — MYOCD is in the SMC top-60 at only 27.2% detection. DE rank and
detection rate are genuinely different quantities, and conflating them in either
direction misleads.

### 5.5 The case the skill was built to settle

The concrete payoff. `cap-degs` showed ABCC9/KCNJ8 absent from the Contractile
Pericytes DE list, suggesting a misannotation, but could not rule out "merely
outranked". Per-cell:

| gene | Angiogenic Per | Secretory Per | Contractile Per | SMC |
|---|---|---|---|---|
| ABCC9 | 41.3% | 73.0% | **2.6%** | 7.9% |
| STEAP4 | 78.7% | 47.1% | **2.5%** | 0.3% |

Genuinely absent, not outranked — while the same cells retain PDGFRB at 63.1%,
which the DE list had also omitted. The DE result alone supported neither half
of that conclusion.

### 5.6 Query provenance

CAP enforces a persisted-query safelist, so query bodies were recovered from the
web client's JS bundle and normalised the way Apollo does. The extractor and
normaliser were validated by running them over `query DEGenes` and
`query GeneralDE` and confirming byte-for-byte equality with the strings already
known-good in `cap-degs`. Only after that were they used on `EmbeddingData`.

## 6. Known limits

- `pct_detected` is a detection rate, not a truth (A5). Dropout means it
  understates real expression, more so for lowly-expressed genes and shallower
  assays. It is reliable for *comparisons between labels in the same dataset*,
  which is how it is used above; treat absolute values with more caution.
- Means are on CAP's normalised scale and are not comparable across datasets.
- A null result is ambiguous between "not expressed" and "symbol not found"
  (A6).
- Transfer scales with total dataset size, not with the cell types requested.
- Untested against datasets whose embedding is not named `umap`, or which have
  several coordinate pairs in obs.

## 7. On where this file lives

It sits in the skill directory alongside `SKILL.md`. The code it describes lives
in the `cap-client` package (`packages/cap-client/src/cap_client/expression.py`),
which the skill calls through its CLI. That is safe:
skills load `SKILL.md` into context when invoked, and other files in the
directory are only read if something explicitly opens them. So this document
costs nothing at invocation time and stays with the code it describes, which is
where provenance belongs.

The real risk is not context bloat but **drift** — two files describing the same
tool, diverging. Mitigated by keeping the split clean: operational rules live in
`SKILL.md` and are not restated here; rationale, assumptions and evidence live
here and are not restated there. `SKILL.md` carries a single pointer to this
file.
