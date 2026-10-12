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
plugins/cap-tools/       the skills, pinned to a package tag
.claude-plugin/          marketplace manifest
scripts/versions.py      bump check, release planning, pin report
docs/pins.md             plugin -> package pins on main (generated)
docs/package-iteration.md  changing the package while a skill uses it
```

Nothing under `plugins/` imports from, or references by relative path, anything
outside its own directory. Everything a skill needs at runtime arrives as a pinned,
installable dependency — which is what makes the plugin work on a machine that has
only ever seen the plugin directory.

## Using the plugin

Prerequisites: `uv`, and network access to GitHub on first run. The skills call
their CLI through `uvx`, which builds and caches it; nothing else to install.

### Install

Into the project you are working in, rather than globally:

```sh
claude plugin marketplace add Cellular-Semantics/cap_skills --scope local
claude plugin install cap-tools@cap_skills --scope local
```

| scope | written to | who gets it |
|---|---|---|
| `local` | `.claude/settings.local.json` (gitignored) | you, in this checkout |
| `project` | `.claude/settings.json` (committed) | everyone who clones the repo |
| `user` | `~/.claude/settings.json` | you, everywhere |

`user` is the default if you omit `--scope`, which is usually more than you
meant. Remove with `claude plugin uninstall cap-tools@cap_skills --scope local`.

### Set it up for a team repo

From inside the repo, use `--scope project` in the two commands above and
**commit** the `.claude/settings.json` they write:

```json
{
  "extraKnownMarketplaces": {
    "cap_skills": {
      "source": { "source": "github", "repo": "Cellular-Semantics/cap_skills" }
    }
  },
  "enabledPlugins": {
    "cap-tools@cap_skills": true
  }
}
```

That *enables* the plugin for everyone but does not download it. Each person
runs, once per clone:

```sh
claude plugin install cap-tools@cap_skills --scope project
```

If `.claude/settings.json` already exists, merge the two keys in. `atlas-tools`
from [atlas-skills](https://github.com/Cellular-Semantics/atlas-skills) installs
the same way and can sit alongside.

### Update

Updates are not automatic. To get the latest release, then restart Claude Code:

```sh
claude plugin marketplace update cap_skills
claude plugin update cap-tools@cap_skills
```

`claude plugin list` shows which plugin version you have. Each version's
[GitHub Release](https://github.com/Cellular-Semantics/cap_skills/releases) says
what changed and which `cap-client` version its skills run.

### Pin a release

To stay on one tested version instead of following the latest, add a `ref` to
the marketplace source:

```json
"source": {
  "source": "github",
  "repo": "Cellular-Semantics/cap_skills",
  "ref": "cap-tools--v0.4.1"
}
```

The project then gets that release exactly, including the package version its
skills call. Each GitHub Release's notes carry this snippet with its tag filled in.

Caveat: Claude Code keeps **one registration per marketplace name per machine**,
so a pinned and an unpinned project on the same machine end up on whichever
registered last. Pinning is reliable where a machine needs one version.

## Use the CLIs directly

```sh
# A function, not a variable: `CAP="uvx …"; $CAP …` does not re-split in zsh.
cap() { uvx --from "git+https://github.com/Cellular-Semantics/cap_skills@pkg-cap-client--v0.4.0#subdirectory=packages/cap-client" cap "$@"; }

cap datasets --consortium "Human Cell Atlas" --format text
cap labelsets https://celltype.info/project/1030/dataset/3400
cap degs https://celltype.info/project/1030/dataset/3400 \
    --labelset hgca_celltype_v1 --only "Tuft Progenitors" --vs "Tuft Cells"
cap expression https://celltype.info/project/1030/dataset/3400 \
    --genes MKI67 TOP2A POU2F3 --cell-types "Tuft Progenitors" "Tuft Cells"
```

stdout is JSON with stable field names; stderr is progress. `--csv FILE` also
writes CSV.

**Be gentle with CAP's endpoints.** They are unauthenticated and public. Requests
are serial and paced inside the client; do not parallelise.

## Making a change

The plugin and the package have separate versions. Bump what you changed, open a
PR, merge. **Tagging and releasing are automatic** — never tag by hand.

| You changed | Bump | Also |
|---|---|---|
| Skill text only | `plugin.json` | — |
| Package code, compatible | `pyproject.toml` **and** `__version__` | to ship it: move the skills' pin to `pkg-cap-client--v<new>`, bump `plugin.json`, regenerate `docs/pins.md` |
| CLI flags or output (breaking) | as above, minor while 0.x | update every skill that relies on the old behaviour |
| Package tests, READMEs, `docs/` | nothing | — |

Patch for fixes, minor for new features. A released version never changes.

Before pushing:

```sh
./dev.sh                                                     # everything CI runs offline
python3 scripts/versions.py check-bumps --base origin/main   # did you bump what you changed?
python3 scripts/versions.py report > docs/pins.md            # after moving a pin
```

See `docs/package-iteration.md` for trying package changes before releasing them.

### When a check fails

| Check | Fix |
|---|---|
| `version-bumps`: "the version is still X" | bump the version file it names |
| `version-bumps`: "tag … already exists" | that version is released; bump past it |
| `version-bumps`: "`__version__` … pyproject.toml says …" | make the two agree |
| `pins-report`: "docs/pins.md is stale" | `python3 scripts/versions.py report > docs/pins.md` |
| `skill-pins-resolve`: "DOES NOT RESOLVE" | the pin names a tag that doesn't exist — usually a typo, or the package version wasn't bumped to match |
| `nightly` | an old release no longer installs or passes tests, usually a dependency change upstream; the job log names the tag |
| `release` failed after merge | fix the cause, then re-run it: `gh workflow run release.yml` |

## Develop

```sh
./dev.sh            # package, eval graders, release tooling, pins report
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

Rules: deterministic and testable → the package, with tests; when/how/why →
skill text. CLI output for agents is JSON with stable field names, and every CLI
supports `--version`. Skills pin package tags, never a branch or commit.

## Reading per-cell obs

`remote-h5ad-obs` used to live here. It is portal-agnostic — it reads any remote
h5ad over range requests — so it now lives in
[atlas-skills](https://github.com/Cellular-Semantics/atlas-skills), and this repo
carries no h5ad dependencies at all. The two plugins install side by side, and
`cap h5ad-url` bridges them:

```sh
h5ad-obs "$(cap h5ad-url https://celltype.info/project/934/dataset/3016 --format text)"
```

## Skill evals

`evals/` holds the behavioural layer: does the right skill fire from an
intent-shaped prompt, does the agent reach for the right flag, does it read the
result correctly.

```sh
python3 evals/runner.py --dry-run     # prompts only, free
python3 evals/runner.py               # the suite: ~$2, hits celltype.info
```

Not in CI — they cost money and depend on a live third-party dataset. The
graders themselves are unit-tested and free (`pytest evals`). See
`evals/README.md`; `./dev.sh` runs the grader tests alongside the packages.

## How releases are automated

| | Plugin | Package |
|---|---|---|
| Version lives in | `plugins/cap-tools/.claude-plugin/plugin.json` | `packages/cap-client/pyproject.toml` |
| Tag | `cap-tools--v<version>` | `pkg-cap-client--v<version>` |
| Read by | a marketplace `ref` pin | the `uvx --from …@<tag>` line in each skill |

A plugin tag freezes its skills, and the skills hold the package pin — so each
plugin release fixes exactly which package version it runs. `docs/pins.md` shows
that mapping for main.

| Workflow | When | What |
|---|---|---|
| `test` | every PR and push | lint; plugin validation; tests on Python 3.11–3.13; `docs/pins.md` current; the package installs from git; every skill pin resolves; on PRs, `version-bumps` |
| `release` | after `test` passes on main | tags any version that has no tag yet (package first, then plugin) and writes a GitHub Release for each |
| `nightly` | 03:17 UTC daily | re-installs every pin used by main and the newest 3 plugin releases, and runs the package tests at each pinned tag |

Why nightly: `uvx` resolves dependencies fresh and ignores `uv.lock`, so a tag
that worked when it was cut can break later with no commit. (cap-client's one
dependency, `certifi`, is unpinned on purpose — a frozen CA bundle goes stale.)
The newest 3 plugin releases are the supported ones; older tags still install,
but nothing checks them.

A pin to a package version released in the same PR can't resolve before merge,
since its tag doesn't exist yet. CI checks that pin against the PR's commit
instead, and `release` tags the package before the plugin. For the minute or two
between merge and `release` finishing, main points at a tag that doesn't exist yet.

The older `v0.1.0`–`v0.4.0` tags, from when plugin and package shared one number,
stay so old pins keep working; the `cap-tools--v*` and `pkg-cap-client--v*` tags
for those versions name the same commits.
