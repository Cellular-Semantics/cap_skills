# Skill evals

The second test layer `CLAUDE_dev.md` asks for. The package tests in
`packages/*/tests/` check deterministic logic; these check **skill behaviour** —
does the right skill fire from an intent-shaped prompt, does the agent reach for
the right flag, does it read the result correctly and avoid the documented traps.

## Running them

```sh
python3 evals/runner.py                    # every case, one run each
python3 evals/runner.py --case 'tuft-*'    # a subset
python3 evals/runner.py --tag expression   # by tag
python3 evals/runner.py --dry-run          # print the prompts, spend nothing
python3 evals/runner.py --runs 3           # three runs per case, for flakiness
```

Needs the plugin installed (`claude plugin install cap-tools@cap_skills --scope
user`) — the cases test the **published** plugin, not the working tree, so a
SKILL.md edit needs a push plus `claude plugin marketplace update cap_skills`
before it shows up here.

Each case runs in a fresh temporary directory, so nothing but the user-scope
plugin is in scope: no project `CLAUDE.md`, no `.claude/skills`.

**These cost money and hit celltype.info.** About $0.20-0.60 per run, ~$2 for the
suite. One run per case by default; `--max-cost-usd` (default 10) aborts a suite
that runs away. They are deliberately **not** in CI.

## Layout

```
cases/<name>/prompt.md              what the agent is asked
cases/<name>/checks.json            deterministic checks + tags + limits
cases/<name>/graders/criteria.md    what a good answer looks like, in prose
graders.py                          pure grading logic
runner.py                           subprocess driver
test_graders.py                     unit tests for the graders (free, offline)
```

`prompt.md` + `graders/criteria.md` is the layout `claude plugin eval` expects,
so the cases migrate to it unchanged when it leaves early access — only
`runner.py` and `checks.json` are throwaway. `plugin eval` additionally brings a
no-plugin **ablation arm**, which these lack and which matters: without it, a
case that a bare model could answer from latent knowledge scores the same as one
the skill actually earned.

## Check kinds

| kind | matches against |
|---|---|
| `command_matches` / `command_not_matches` | every tool call's name and JSON input |
| `answer_matches` / `answer_not_matches` | the final answer |
| `answer_any_of` | word-bounded list, with `min_hits` |
| `numeric_present` | any number in the answer falling in `[min, max]` |
| `numeric_in_range` | a number captured by an anchored `pattern` |

Every check carries a `why` saying what behaviour it pins, printed on failure.
Anything not expressible deterministically belongs in `criteria.md` for an LLM
grader to judge once `plugin eval` is available.

Prefer `numeric_present` over `numeric_in_range`. Anchoring a number to a nearby
label is brittle twice over: the agent lays results out as a table either way
round (cell types as rows, or genes as rows with cell types as columns), and a
neighbouring sentence can hold a *different* percentage. An early version of the
STMN1 grader matched "Tuft Progenitors, well behind Cycling Macrophages (94.9%)"
and failed a correct answer.

## The cases

| case | pins |
|---|---|
| `tuft-sibling-de` | a sibling question reaches for `--vs`, not vs-rest |
| `expression-not-de` | "is X expressed" goes to `cap expression`, not a DE ranking |
| `stmn1-does-not-discriminate` | the DE → expression cross-check: a curated marker tested and found not to discriminate |
| `retired-gene-symbol` | `LRMP` returns nothing because the symbol was retired, not because the gene is absent |
| `tuft-markers-vs-rest` | vs-rest DE returns the tuft programme |
| `obs-columns-without-h5ad` | a null `annDataUrl` is not a dead end |

## Brittleness

`tuft-markers-vs-rest` and `tuft-sibling-de` assert the **content of a live
third-party dataset**. A CAP re-annotation or a re-run of their DE can move them.
That is an accepted trade for now — they are the cases that would catch a real
regression in the DE path — but when one fails, check whether the dataset changed
before assuming the skill did. Expectations were measured on **2026-09-28** and
each case's `criteria.md` records what was returned then.

Both are written as a **union over both rankings**, because the same sibling
comparison gives two different and both-correct answers: by `log_fold_change`
Tuft Progenitors vs Tuft Cells returns a cell-cycle tier (CHEK1, CDCA3, AURKB,
E2F1, RAD51), and by `score` a secretory/absorptive one (TSPAN8, PHGR1, PIGR,
AGR2). A check naming only one would fail a correct run.

## Infrastructure versus regression

A run stopped by a spend or rate limit is reported separately and not counted as
a failure — `graders.INFRA_MARKERS` lists what that looks like. Scoring those as
failures buries a real regression under noise. Rerun them.
