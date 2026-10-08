---
name: cap-datasets
description: Search the CAP (celltype.info) dataset catalogue — find datasets by name, project, cell type or labelset, and filter to a consortium such as the Human Cell Atlas. Returns dataset ids, cell counts, project ids and URLs. Use when you need to find which CAP datasets exist for a tissue or consortium, or to resolve a dataset name to the URL the other CAP skills take.
---

# cap-datasets

Search CAP's dataset catalogue over its public GraphQL API. No browser, no
authentication. 127 datasets are public as of 2026-09; 61 carry the Human Cell
Atlas tag.

This is the entry point to the other CAP skills: they all take a dataset URL,
and this is how you find one.

## When to invoke

- "what datasets are on CAP for \<tissue\>?"
- "which CAP datasets are Human Cell Atlas?"
- "find the gut atlas on CAP" / "what's the URL for \<dataset name\>?"
- "which datasets annotate \<cell type\>?"
- building a worklist of datasets to review

**Not** for the labelsets *inside* one dataset — that is `cap labelsets <url>`,
and see the warning about `--with-labelsets` below.

**Not** for per-cell `obs`. That moved to the portal-agnostic `remote-h5ad-obs`
skill in [atlas-skills](https://github.com/Cellular-Semantics/atlas-skills), which
takes a file URL; `cap h5ad-url <dataset-url>` resolves one:

```sh
h5ad-obs "$(cap h5ad-url https://celltype.info/project/934/dataset/3016 --format text)"
```

Many CAP datasets expose no public h5ad at all, and then that route is closed —
`cap expression --list-obs-columns` still reports what obs contains.

## Command

```sh
uvx --from "git+https://github.com/Cellular-Semantics/cap_skills@v0.4.0#subdirectory=packages/cap-client" \
    cap datasets [options]
```

Needs `uv` and, on first run, network access to GitHub. Expects `cap-client`
0.4.0 or later (`cap --version`).

Define the prefix once per shell if you are making several calls — but note that
`CAP="uvx …"; $CAP datasets` does **not** work in zsh (the string is not
re-split into words). Either write the command out each time, or use a function:

```sh
cap() { uvx --from "git+https://github.com/Cellular-Semantics/cap_skills@v0.4.0#subdirectory=packages/cap-client" cap "$@"; }
cap datasets --consortium "Human Cell Atlas" --format text
```

**Filters** (all optional; combine freely):

- `--consortium ID_OR_NAME` — id or name, case-insensitive, repeatable.
  `--consortium 1` and `--consortium "Human Cell Atlas"` are the same thing.
- `--name`, `--project-name`, `--project-description` — substring match.
- `--cell-type NAME ...` — datasets annotating these cell types.
- `--labelset NAME ...` — datasets carrying a labelset with these names, filtered
  server-side.
- `--limit` (500), `--offset` (0) — the default covers the whole catalogue; the
  run warns on stderr if exactly `--limit` rows come back, which means there may
  be more.
- `--format text` for a terminal listing, `--csv FILE` to keep the rows.

`cap consortia` lists the consortium tags that exist. As of 2026-09 there is
exactly one, `1 = Human Cell Atlas`, so `--consortium` is in practice an HCA
filter — but do not hardcode that, since CAP can add tags.

## Output

JSON on stdout, one object per dataset:

```json
{"dataset_id": "3400",
 "dataset_name": "Human Gut Cell Atlas (HGCA) v1 - All Cells",
 "cell_count": 944502, "project_id": "1030",
 "project_name": "Human Gut Cell Atlas",
 "created_at": "2026-02-01T00:00:00.000Z",
 "consortium_tags": ["Human Cell Atlas"],
 "url": "https://celltype.info/project/1030/dataset/3400"}
```

`url` is what every other CAP skill takes as its target.

## The consortium tag is only available here

It is **not** in CAP's exported OLS report. If you are working from that report
and need to know which rows are Human Cell Atlas, the only route is to pull the
HCA dataset ids from here and join on dataset id — and join on the **id parsed
from the `url` column**, not on dataset name. Names are not unique in the report
and do not always match CAP's current names.

Verified 2026-09-28 against an independent Playwright scrape of CAP's search
page: identical ids, all 61. The one name that differed did so because HTML
rendering had collapsed a double space, so the API is the more faithful source.

## Do not ask for labelsets here

`--with-labelsets` exists but is off by default, and the default is almost always
what you want. CAP expands **every labelset and every label** unless told
otherwise — across the 61 HCA datasets that is 2,365 labelsets and 24,096 labels,
**2.4 MB** of response versus **21 KB** with it suppressed.

Omitting the option, or passing an empty list, both mean "all of them" as far as
the server is concerned; suppression is done by requesting a labelset name chosen
not to exist. If you need labelsets for one dataset, `cap labelsets <url>` is the
right call. If you need to know *which* datasets carry a named labelset,
`--labelset NAME` filters server-side and costs nothing.

## Cost

One request, about a second, for the whole catalogue. Cheap enough to run
speculatively — unlike the DE and expression skills, which transfer per-cell
vectors from million-cell atlases.

`cap consortia` costs two requests: the tag list is global, but the only
operation exposing it demands a project id and 404s without a real one, so a
single dataset is looked up first purely to borrow one.

## When it breaks

`QUERY_NOT_IN_SAFELIST` means CAP redeployed and the persisted query bodies no
longer match. Run `cap recover-queries` — but note `SearchDatasets` uses GraphQL
**fragments**, and `recover-queries` prints only the operation. The fragments
(`DatasetResult`, and `ProjectAuthors_project` which it reaches) have to be
appended, separated by blank lines, and the whole document re-printed the way
Apollo prints it. See `cap_client/recover.py`; the fix belongs in `cap-client`.

## Verified against

- The full catalogue: 127 datasets, ~1.2 s, 195 KB with labelsets suppressed.
- `--consortium 1`: 61 datasets, 21 KB, matching the Playwright scrape exactly.
- `--name gut`: the five HGCA v1 lineage datasets, including 3400 (944,502 cells).
- `cap consortia`: one tag, `1 = Human Cell Atlas`.
- Live tests in `packages/cap-client/tests/test_live.py` pin the HCA count, the
  presence of dataset 3400, and that labelset suppression still works.
