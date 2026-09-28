Measured against the live dataset on 2026-09-28, `cap degs --only "Tuft Cells"`
returns, by `log_fold_change`: TRPM5, SH2D7, GNG13, ITPRID1, HTR3E, GNAT3 …; and by
`score`: IRAG2, SH2D6, ZFHX3, BMX, AVIL, TPM1, HCK … Either is a correct answer to
this prompt, and the check is a union over both.

**This is the brittle case.** It asserts the content of a live third-party dataset,
so a CAP re-annotation or a re-run of their DE can move it. If it starts failing,
check whether the dataset changed before assuming the skill regressed.

Credit for saying which ranking was used and what that choice favours — against a
whole-atlas background `score` favours abundant lineage genes and logFC favours
restricted, specific ones. Credit for noting these are vs-rest markers, so they
describe tuft identity against the whole gut atlas rather than separating tuft cells
from a near neighbour.
