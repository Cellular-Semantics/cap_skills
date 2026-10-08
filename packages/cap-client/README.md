# cap-client

Reads cell-type annotation evidence out of [CAP](https://celltype.info) through
its public GraphQL endpoint. No browser, no authentication, no h5ad download.

```sh
uvx --from "git+https://github.com/Cellular-Semantics/cap_skills@v0.4.0#subdirectory=packages/cap-client" \
    cap degs https://celltype.info/project/1030/dataset/3400 --labelset hgca_celltype_v1
```

Subcommands: `labelsets`, `degs`, `expression`, `download-urls`, `h5ad-url`, and
the maintenance pair `recover-queries` / `introspect`.

stdout carries the result as JSON (`--format text` for a human summary); stderr
carries progress. `--csv FILE` additionally writes the rows as CSV.

Interpretation guidance — which query answers which question, and how to avoid
the traps — lives in the `cap-tools` plugin skills, not here.
