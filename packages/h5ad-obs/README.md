# h5ad-obs

Reads the `obs` table out of a remote `.h5ad` by fetching only the byte ranges
that back it. `X`, `layers`, `obsm`, `var` and `raw` are never read — on a 476 MB
atlas that is ~27 MB in ~8-13 s.

Works against any host honouring range requests (GCS, S3, Sanger COG, static
hosts). A [CAP](https://celltype.info) dataset URL is also accepted and resolved
to its underlying h5ad via `cap-client`.

```sh
uvx --from "git+https://github.com/Cellular-Semantics/cap_skills@v0.2.0#subdirectory=packages/h5ad-obs" \
    h5ad-obs https://celltype.info/project/1030/dataset/3400 --list-columns
```

stdout is a JSON summary including byte accounting; the obs table itself is
written to `--out` (parquet by default) because it is usually large.
