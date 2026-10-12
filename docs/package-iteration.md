# Iterating on the package while a skill uses it

How to change `packages/cap-client` without a release for every edit, and how
to release once the behaviour settles.

The `--from` pin in SKILL.md is the only thing that selects a package version.
`plugin.json`'s version selects which copy of the *plugin* an installed user
has: Claude Code refreshes an installed plugin only when that string changes.
So bumping the plugin does not pull new package code, but not bumping it means
nobody already installed receives the new pin.

Three loops, in increasing cost:

**Skill text.** Load the plugin from your worktree for one session, no install
needed:

```
claude --plugin-dir plugins/cap-tools
```

Bump `plugin.json` when you open the PR; `version-bumps` will insist.

**Package code, while the behaviour is still moving.** Use an editable install
and call the binary directly:

```
./dev.sh
packages/cap-client/.venv/bin/cap labelsets https://celltype.info/project/1030/dataset/3400
```

Do **not** point the `--from` pin at a local directory instead. `uvx` caches the
build: editing the source and re-running gives the stale version back, silently.

**Releasing.** Bump `packages/cap-client/pyproject.toml` and `__version__`;
move the pin in every skill; bump `plugin.json`; regenerate `docs/pins.md`.
One PR or two, as suits. On merge `release` tags the package, then the plugin.

A pin must resolve for someone with a cold cache. Check it the way CI does:

```
uvx --no-cache --from "git+https://github.com/Cellular-Semantics/cap_skills@<tag>#subdirectory=packages/cap-client" cap --version
```

### Quoting

Skills must write the full quoted command, or a shell function, not
`CMD="uvx …"` then `$CMD`. Unquoted parameters do not word-split under zsh, the
macOS default shell, so the variable form fails with
`command not found: uvx --from …`.
