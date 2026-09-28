---
name: remote-h5ad-obs
description: Read the `obs` table out of a remote .h5ad over HTTP range requests, without downloading the expression matrix. Works against any host honouring range requests (GCS, S3, Sanger COG, static hosts); also accepts a celltype.info (CAP) dataset URL and resolves it to the underlying h5ad. Use when you need per-cell annotations, cell-type assignments or ontology term ids from a published atlas that is too large to download.
---

# remote-h5ad-obs

Pull `obs` from a remote h5ad by fetching only the byte ranges that back it. `X`,
`layers`, `obsm`, `var` and `raw` are never read. On a 476 MB atlas this transfers
~27 MB in ~8-13 s.

## When to invoke

- "get the obs / cell metadata from this h5ad URL"
- "what cell types are in \<atlas URL\>" (per-cell assignments)
- "pull the annotations from this CAP dataset"
- needing ontology term ids, donor/tissue/assay covariates, or curator rationale
  fields that live in `obs`

**Not** for differential expression from a CAP dataset — CAP serves DE through its
GraphQL API far more cheaply; use `cap-degs`. **Not** for expression values: those
mean reading `X`, which is a real download. For a handful of genes use
`cap-gene-expression`, which is gene-major and needs no h5ad at all.

## Command

```sh
uvx --from "git+https://github.com/Cellular-Semantics/cap_skills@v0.2.0#subdirectory=packages/h5ad-obs" \
    h5ad-obs <url> [options]
```

Needs `uv` and network access to GitHub on first run — this one pulls h5py,
pandas, fsspec and pyarrow, so expect the first invocation to take a minute while
uv builds the environment. Cached thereafter. Expects `h5ad-obs` 0.2.0 or later
(`h5ad-obs --version`).

`<url>` is either a direct h5ad URL or a `celltype.info/project/<p>/dataset/<d>`
URL, which is resolved to its `annDataUrl` first. **Many CAP datasets expose no
anonymous `annDataUrl`** — dataset 3400 returns nulls — and then this route is
closed; `cap-gene-expression --list-obs-columns` still shows what obs contains.

**Options:**

- `--list-columns` — print obs columns and their encodings, then exit.
- `--columns COL ...` — read only these. Saves less than you would expect; see
  "Cost".
- `--out FILE`, `--format {parquet,csv,tsv}` (default parquet).
- `--block-size MB` — range block size, default 2. Smaller fetches fewer bytes but
  makes more round trips; on a high-latency link larger is faster.
- `--no-preflight` — skip the range-support check.

stdout is a JSON summary — row and column counts, skipped columns, and byte
accounting (`range_requests`, `mb_fetched`, `file_bytes`). The obs table itself
goes to the output file, because it is usually large.

## Cost

Measured on CAP dataset 3016 (476 MB, 49,387 cells x 51 obs columns):

| request | range requests | fetched | time |
|---|---|---|---|
| all 51 columns | 13 | 27.3 MB | ~8-13 s |
| `--list-columns` | 10 | 21.0 MB | ~7 s |
| 1 column | 10 | 21.0 MB | ~7 s |

The floor is ~21 MB because HDF5 metadata — superblock, B-trees, object headers —
is scattered through the file and must be walked before any column is readable.
**Reading one column costs nearly as much as reading all of them**, so pull the
whole table once and subset locally. `--columns` trims the output, not the
transfer.

At `--block-size 0.25` the same full read fetches 8.7 MB but takes ~15 s.

## What you get back

Column order comes from `obs.attrs["column-order"]`, with any columns present in
the group but missing from that attribute appended. Three AnnData encodings are
handled: plain arrays (bytes decoded to str), categorical (`categories`/`codes`),
and nullable masked (`values`/`mask`, where masked entries come back as null, not
`False`). An unrecognised encoding is skipped and named in `skipped_columns`
rather than aborting the run.

If CAP reports `isAnnDataUrlUpToDate: false` the run warns on stderr: the h5ad may
lag the annotations shown in the web UI, which matters if you are reviewing
annotations rather than cells.

## Traps

- **Range support is mandatory.** The preflight `HEAD` requires
  `accept-ranges: bytes` and stops with that message rather than silently pulling
  gigabytes. A host without it means the file must be downloaded whole.
- **`cache_type="blockcache"` is not optional** in the implementation. fsspec's
  default `readahead` cache holds only the current block, so h5py's scattered
  chunk reads refetch endlessly — the read that takes 8 s with blockcache ran 10+
  minutes without finishing a single column. If you adapt this pattern elsewhere,
  carry that setting with it.
- **An explicit certifi SSL context is required.** aiohttp does not read the macOS
  keychain, so GCS/S3 otherwise fail with `CERTIFICATE_VERIFY_FAILED`.
- 401/403 means the store needs credentials. This does not handle auth; report it.

## Verified against

- CAP dataset 3016 (Human Adipose Tissue Atlas v1.0, Lymphoid cells, 476 MB): full
  obs 49,387 x 51 in 27.3 MB, via the CAP URL and via the direct GCS URL;
  `--columns`, `--list-columns`, csv and tsv output.
- Preflight correctly refuses a host without range support.
- The offline test suite runs the whole path against a localhost range server,
  including a check that the matrix's byte ranges are never touched.

Not yet exercised against S3 or Sanger COG hosts. An earlier one-off script does
read a 92.8 GB Sanger COG h5ad this way, so the pattern holds there — but it
predates the `blockcache` finding and uses fsspec's default cache, so it is likely
far slower than it needs to be.
