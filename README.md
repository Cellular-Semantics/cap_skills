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

## Install the plugin

Install into the project you are working in, rather than globally:

```sh
claude plugin marketplace add Cellular-Semantics/cap_skills --scope local
claude plugin install cap-tools@cap_skills --scope local
```

`--scope local` writes `.claude/settings.local.json`, which is gitignored by
convention: the plugin is available in this checkout, for you, and nowhere else.
Nothing leaks into your other projects and nothing is committed. Remove it with
`claude plugin uninstall cap-tools@cap_skills --scope local`.

The three scopes, and when each is right:

| scope | written to | who gets it |
|---|---|---|
| `local` | `.claude/settings.local.json` (gitignored) | you, in this checkout |
| `project` | `.claude/settings.json` (committed) | everyone who clones the repo |
| `user` | `~/.claude/settings.json` | you, everywhere |

`user` is the default if you omit `--scope`, which is usually more than you
meant. Prefer `local` to try something out, `project` to give a repo's whole team
the same tools.

The skills invoke their CLIs with `uvx --from git+…@pkg-cap-client--vX.Y.Z`, so the only
prerequisites are `uv` and network access to GitHub on first run. Environments are
cached after that.

### Setting it up for a repo

To make these tools part of a repository's setup — so anyone who clones it has
them without being told to install anything — install at **project** scope from
inside that repo:

```sh
claude plugin marketplace add Cellular-Semantics/cap_skills --scope project
claude plugin install cap-tools@cap_skills --scope project
```

That writes `.claude/settings.json`. **Commit it.**

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

You can equally write that file by hand and skip the two commands — it is the
whole of the configuration. It *enables* the plugin but does not download it:
everyone else who clones the repo runs, once,

```sh
claude plugin install cap-tools@cap_skills --scope project
```

Three things worth knowing:

- It layers rather than replaces. Someone who already has `cap-tools` at user
  scope keeps that too; the project-scope copy takes precedence in this repo.
- The marketplace tracks the default branch, so a clone gets the current release,
  not the one you tested against — to fix that, pin a release (below). An
  installed copy refreshes when the plugin's version string changes and someone
  runs `claude plugin update`; auto-update is off by default for marketplaces
  outside Anthropic's own.

To add these tools to a repo whose `.claude/settings.json` already exists, merge
the two keys into it rather than overwriting.

`atlas-tools` from [atlas-skills](https://github.com/Cellular-Semantics/atlas-skills)
installs the same way and is designed to be used alongside this one; both entries
can sit in the same `.claude/settings.json`.

### Pin a release

Add a `ref` naming a plugin tag:

```json
"source": {
  "source": "github",
  "repo": "Cellular-Semantics/cap_skills",
  "ref": "cap-tools--v0.4.1"
}
```

Claude Code reads the marketplace from that tag, and the plugin from the same
checkout, so the project gets that release exactly — including the package pin
in its skills. Each GitHub Release's notes carry this snippet with its own tag
filled in.

**One registration per marketplace name per machine.** Claude Code keeps a
single entry for `cap_skills` in `~/.claude/plugins/known_marketplaces.json`,
not one per project, and a project's `ref` rewrites it — so a pinned project and
an unpinned one on the same machine end up on whichever registered last. A ref
pin is reliable where a machine needs one version of the plugin. (It does not
touch `atlas-skills`, which is a different marketplace name.)

## Versions

| | Plugin | Package |
|---|---|---|
| Version lives in | `plugins/cap-tools/.claude-plugin/plugin.json` | `packages/cap-client/pyproject.toml` |
| Tag | `cap-tools--v<version>` | `pkg-cap-client--v<version>` |
| Who reads the tag | a ref-pinned marketplace | the `uvx --from …@<tag>` line in a skill |

The two version independently: a skill-wording change bumps the plugin alone,
and the package moves only when its code does. A plugin tag freezes its
SKILL.md, and the SKILL.md holds the package pin, so a plugin release
determines its package release. `docs/pins.md` shows the mapping for main; the
nightly run's summary shows it for every supported tag.

The older `v0.1.0`–`v0.4.0` tags, from when both shared one number, stay — old
pins resolve against them. `cap-tools--v*` and `pkg-cap-client--v*` aliases
name the same commits.

The newest **3** `cap-tools` tags are supported: the nightly workflow
re-installs every package they pin and runs its tests at that tag. Older tags
still install, but nothing checks that they still work.

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

## Develop

```sh
./dev.sh            # package, eval graders, release tooling, pins report
./dev.sh -m live    # also hit celltype.info (excluded from CI)
python3 scripts/versions.py check-bumps --base origin/main   # before pushing
python3 scripts/versions.py report > docs/pins.md            # after moving a pin
```

The live suite exists for one thing the offline suite cannot cover: CAP enforces a
**persisted-query safelist**, so a redeploy that changes the query bodies makes
every call fail with `QUERY_NOT_IN_SAFELIST`. Only a real request finds that out.
When it happens, `cap recover-queries` regenerates the bodies from CAP's JS bundle,
validating its transform against two known-good queries first.

Two live tests pin conclusions from a real annotation review — STMN1 at ~54.5% in
Tuft Progenitors versus ~47.1% in Tuft Cells, and `LRMP` failing to resolve because
the symbol was retired in 2020 — so a refactor that changes the numbers is caught.

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

## Releasing

Releases are cut by CI from main, never by hand.

1. **Change the package**: edit, bump `pyproject.toml` and `__version__`.
   `version-bumps` fails if the code changed and the version did not.
2. **Adopt it in the plugin** — same PR or a later one: move the skills' pin to
   the new package tag, bump `plugin.json`, regenerate `docs/pins.md`.
3. Merge. Once `test` is green on main, `release` tags `pkg-cap-client--v<new>`,
   checks it installs from a cold cache, then runs `claude plugin tag` — which
   validates the plugin against the marketplace — and writes a GitHub Release
   listing the plugin's package pins.

A pin to a package tag that does not exist yet fails `skill-pins-resolve`,
except the tag this very commit's release will cut: that is checked at the
commit instead, since the tag can only appear after merge. For the few minutes
between merge and `release` finishing, main pins a tag that does not exist yet.

A skill-only change is step 2 alone.

## Rules for changes

- Deterministic and testable → a package, with tests. About when/how/why → skill text.
- CLI output for agents is `--json`-shaped with stable field names, and every CLI
  supports `--version`.
- **Any change under `plugins/cap-tools/` bumps the plugin's version.** Installed
  copies refresh only when the version string changes. CI enforces this.
- **Any change to the package's code or `pyproject.toml` bumps its version.**
  Tests, README and `uv.lock` do not. CI enforces this.
- A released version never changes. CI refuses a bump to a version already tagged.
- Changing a CLI contract is a breaking change: bump the package's major version
  (minor while 0.x) and move the skills' pin deliberately.
- Pin skills to package tags, never to a branch or commit.

## CI

| Workflow | When | What |
|---|---|---|
| `test` | every PR and push | lint; `claude plugin validate`; package, grader and tooling tests on 3.11–3.13; `docs/pins.md` current; the package installs from git at the PR head; every pin on the branch resolves; on PRs, `version-bumps` |
| `release` | after `test` passes on main | tag every untagged package, then plugin; a GitHub Release for each |
| `nightly` | 03:17 UTC daily | every pin on main and at the supported tags installs; each pinned package tag's tests pass on a fresh install |

Why nightly: `uvx --from git+…` resolves dependencies fresh and ignores
`uv.lock`, so a tag that worked when it was cut can break later without any
commit. cap-client's one runtime dependency, `certifi`, is unpinned on purpose —
it is the CA bundle, and a frozen one goes stale.
