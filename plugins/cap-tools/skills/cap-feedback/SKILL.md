---
name: cap-feedback
description: Read the community feedback left on a CAP dataset's cell-type labels — agree/disagree/idk scores plus typed explanations, including `refine` entries that propose a specific replacement ontology term and `split`/`merge` proposals with marker evidence. Use before critiquing an annotation, to find out whether someone has already raised it, and to find corrections that were filed but never applied.
---

# Community feedback on CAP labels

CAP dataset pages carry a `/feedback` tab. Readers score a label — agree,
disagree or idk — and can attach an explanation: a free-text comment, a
**`refine`** carrying field-level before/after values, or a **`split`** /
**`merge`** proposal with proposed daughter labels and their markers.

**Check this before working up an annotation critique.** Of the first 63
findings in one HCA review, six had already been filed here by other people —
and none had reached the labels or CAP's exported ontology report. A finding
that duplicates filed feedback is still worth recording, but it says *the loop
is not closing*, which is a different claim from *this mapping is wrong*.

## Command

```sh
cap() { uvx --from "git+https://github.com/Cellular-Semantics/cap_skills@v0.4.0#subdirectory=packages/cap-client" cap "$@"; }

cap feedback https://celltype.info/project/574/dataset/1242
cap feedback <datasetURL> --format text          # one line per label
cap feedback <datasetURL> --full                 # every entry, not a summary row
cap feedback <datasetURL> --csv feedback.csv
```

Takes a **full** `/project/<p>/dataset/<d>` URL — the page cannot be located
from a dataset id alone, and the command says so rather than guessing.

JSON on stdout: `n_labels` (the denominator — every label on the page) and
`n_with_feedback`. Default rows are one per label carrying feedback; `--full`
emits each entry with its explanation.

## Reading the result

**Scores and explanations are independent, and ranking by score is wrong.** A
`refine` carries *no* score, so a label with a filed correction reads
`agree=0, disagree=0, idk=0` and looks untouched. All five refinements on
dataset 1242 look like this. Select on `n_feedback`, not on scores.

**`refine` is the most actionable type.** It names the exact change:

```json
{"type": "refine",
 "changes": [{"attribute": "ontologyTermId", "from": "CL:0000057", "to": "CL:7770003"}]}
```

That is a reviewer saying "this label is mapped to generic *fibroblast* and
should be *beam A cell*" — already diagnosed, already specific, and still not
applied.

**Feedback is usually filed on one dataset of a project, not all of them.** The
same label commonly appears in a lineage dataset and the project's all-cells
dataset, and in both the sc and sn arms. Check the siblings with
`cap datasets --project-name "<name>"` before concluding a correction is
already handled — on project 574 all five refinements sit on the scRNA arm and
none on the snRNA arm.

**Expect test entries in production data.** At least one label carries
"test agree." alongside genuine comments.

**Attribution is included and is the point** — `displayName`, and `orcidId` and
`institution` where the commenter supplied them. **Email is never returned**,
even though CAP's payload carries it. Treat the rest as signed public comment:
it is attributed criticism of colleagues' work, so quote it as you would a
review, and think before republishing it in bulk.

## Why this is fragile, and what that means for you

CAP exposes **no API** for feedback. Its GraphQL endpoint enforces a
persisted-query safelist, and the page's `DatasetFeedbacks` operation runs
server-side, so nothing leaves the browser to replay. The result is embedded in
the page's Next.js payload, and that is what this reads — the same route
`cap labelsets` already uses.

So this depends on CAP's page build rather than on a published contract, and it
will break when that changes. Two behaviours follow, and you should rely on
both:

- **An empty parse raises, it does not return "no feedback".** CAP
  intermittently serves the page shell without its payload. The command retries
  and then fails loudly, because silently reporting zero feedback for a dataset
  that has some is the error that actually costs you. If you see that error,
  re-run before believing it.
- **`n_labels` is the denominator.** A plausible-looking result with
  `n_labels: 0` is a failed fetch, not an empty dataset.

If CAP later safelists a feedback query, the backend swaps and this interface
stays put.
