`LRMP` was retired as a gene symbol in 2020 and does not resolve against this
atlas's var index. CAP matches symbols exactly, so the query returns nothing.

The failure mode is reporting "LRMP is not expressed in Tuft Cells", which is a
biological claim the data does not support. The right answer distinguishes *no match
in the var index* from *expressed at zero*, finds the current symbol `IRAG2`, and
reports its detection rate (~98%) — noting that under its current symbol this is the
strongest tuft marker available, not a missing one.

Credit for checking HGNC (`rest.genenames.org/fetch/prev_symbol/LRMP`) or an
equivalent authority rather than asserting the mapping from memory.
