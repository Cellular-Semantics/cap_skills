# cap_skills

Agentic skills for cell atlas annotation and ontology-mapping review, plus the
packages they call.

The split is deliberate: **skills hold judgment** — when to use a capability, how
to read the result, what the traps are — and **packages hold deterministic logic**,
with dependencies, tests and tagged releases. A skill calls code through a CLI; it
never contains non-trivial code.

## Layout

```
packages/cap-client/     CAP (celltype.info) GraphQL client + `cap` CLI
packages/h5ad-obs/       remote h5ad obs reader + `h5ad-obs` CLI
plugins/cap-tools/       the skills, pinned to a package tag
.claude-plugin/          marketplace manifest
```

Nothing under `plugins/` imports from, or references by relative path, anything
outside its own directory. Everything a skill needs at runtime arrives as a pinned,
installable dependency — which is what makes the plugin work on a machine that has
only ever seen the plugin directory.

## Install the plugin

In Claude Code:

```
/plugin marketplace add Cellular-Semantics/cap_skills
/plugin install cap-tools
```

The skills invoke their CLIs with `uvx --from git+…@vX.Y.Z`, so the only
prerequisites are `uv` and network access to GitHub on first run. Environments are
cached after that; the first `h5ad-obs` call is slow while uv builds h5py and pandas.

## Use the CLIs directly

```sh
CAP="uvx --from git+https://github.com/Cellular-Semantics/cap_skills@v0.1.0#subdirectory=packages/cap-client cap"

$CAP labelsets https://celltype.info/project/1030/dataset/3400
$CAP degs https://celltype.info/project/1030/dataset/3400 \
    --labelset hgca_celltype_v1 --only "Tuft Progenitors" --vs "Tuft Cells"
$CAP expression https://celltype.info/project/1030/dataset/3400 \
    --genes MKI67 TOP2A POU2F3 --cell-types "Tuft Progenitors" "Tuft Cells"
```

stdout is JSON with stable field names; stderr is progress. `--csv FILE` also
writes CSV.

**Be gentle with CAP's endpoints.** They are unauthenticated and public. Requests
are serial and paced inside the client; do not parallelise.

## Develop

```sh
./dev.sh            # both packages, offline suites
./dev.sh -m live    # also hit celltype.info (excluded from CI)
```

The live suite exists for one thing the offline suite cannot cover: CAP enforces a
**persisted-query safelist**, so a redeploy that changes the query bodies makes
every call fail with `QUERY_NOT_IN_SAFELIST`. Only a real request finds that out.
When it happens, `cap recover-queries` regenerates the bodies from CAP's JS bundle,
validating its transform against two known-good queries first.

Two live tests pin conclusions from a real annotation review — STMN1 at ~54.5% in
Tuft Progenitors versus ~47.1% in Tuft Cells, and `LRMP` failing to resolve because
the symbol was retired in 2020 — so a refactor that changes the numbers is caught.

## Rules for changes

- Deterministic and testable → a package, with tests. About when/how/why → skill text.
- CLI output for agents is `--json`-shaped with stable field names, and every CLI
  supports `--version`.
- Changing a CLI contract is a breaking change: bump the version and update every
  pinning skill in the same PR.
- Pin skills to tags, never to a branch.
