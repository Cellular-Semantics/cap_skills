Dataset 3400 returns nulls from CAP's `downloadUrls`, so `remote-h5ad-obs` cannot
reach it. `cap expression --list-obs-columns` can, because it reads the obs schema
out of a deliberate probe error rather than out of the h5ad.

Attempting the h5ad route first is fine — it is the more obvious one. Stopping there
and reporting that the metadata is unavailable is the failure. The answer should list
obs columns (87 of them on this dataset) and confirm tissue is present.
