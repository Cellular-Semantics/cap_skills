"""Community feedback on labels: scores and typed explanations.

CAP dataset pages carry a /feedback tab where readers score a label
(agree / disagree / idk) and can attach an explanation -- a comment, a `refine`
carrying field-level before/after values, or a `split` / `merge` proposal.

There is no API for it. The GraphQL endpoint safelists query bodies, and the
page's `DatasetFeedbacks` operation runs server-side, so nothing leaves the
browser to replay. What there is: the server embeds the operation's *result* in
the page's Next.js RSC payload, the same place `labelsets` reads from. So the
route is the same -- fetch the page, parse the payload -- and `fetch_page` is
injectable so this is testable against a constructed page.

That makes this module structurally fragile in a way the GraphQL ones are not:
it depends on CAP's page build, not on a published contract. Two consequences
are deliberate:

* `fetch_feedback` **raises** when a page yields no labels at all. CAP
  intermittently serves the page shell without its payload, and an empty parse
  is indistinguishable from "this dataset has no feedback" unless you refuse to
  guess. Reporting zero feedback for a dataset that has some is the failure mode
  that matters, so this one is loud.
* Nested objects in the payload are deduplicated into `$...` pointer strings.
  A pointer is not resolvable from one label's slice, so it is treated as absent
  rather than crashing the parse.

Attribution is included: feedback is signed work and the name is the point of
it. Email is never collected, even though the payload may carry it.
"""
from __future__ import annotations

import html as html_mod
import json
import re

from .errors import CapError
from .targets import dataset_page_url
from .transport import fetch_page as _default_fetch_page

#: Explanation types CAP's own enum defines (FeedbackExplanationType).
EXPLANATION_TYPES = ("agree", "disagree", "idk", "refine", "split", "merge")

_LABEL_RE = re.compile(
    r'\{"__typename":"Label","feedbacks":(\[.*?\]),"id":"(\d+)",'
    r'"name":"((?:[^"\\]|\\.)*)","scores":\{"__typename":"LabelScores",'
    r'"agree":(-?[\d.]+),"disagree":(-?[\d.]+),"idk":(-?[\d.]+)\},"count":(\d+)\}'
)
_LABELSET_RE = re.compile(
    r'\{"__typename":"Labelset","name":"((?:[^"\\]|\\.)*)","labels":\['
)

#: Fields of CapUser we pass through. `email` is deliberately absent: the
#: payload may carry it and republishing it is not ours to do.
_USER_FIELDS = ("displayName", "institution", "orcidId")


def _obj(value):
    """Flight payloads dedupe repeated objects into `$...` pointer strings.
    Those carry nothing we need and cannot be resolved from a single label's
    slice, so treat them as absent."""
    return value if isinstance(value, dict) else {}


def flight_payload(page_html: str) -> str:
    """Concatenate the page's Next.js flight chunks into plain JSON text."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)',
                        page_html)
    if not chunks:
        return ""
    joined = "".join(chunks)
    try:
        joined = json.loads('"' + joined + '"')
    except json.JSONDecodeError:
        joined = joined.encode().decode("unicode_escape", "replace")
    return html_mod.unescape(joined)


def parse_feedback(page_html: str) -> list[dict]:
    """Every label on the page, with its scores and any feedback.

    Returns labels with and without feedback: the caller needs the denominator,
    and an all-empty result is how a failed fetch is detected.
    """
    payload = flight_payload(page_html)
    bounds = [(m.start(), m.group(1)) for m in _LABELSET_RE.finditer(payload)]
    out: list[dict] = []
    for m in _LABEL_RE.finditer(payload):
        labelset = ""
        for pos, name in bounds:
            if pos < m.start():
                labelset = name
            else:
                break
        try:
            feedbacks = json.loads(m.group(1))
        except json.JSONDecodeError:
            feedbacks = []
        out.append({
            "labelset": labelset,
            "label_id": m.group(2),
            "label": m.group(3),
            "count": int(m.group(7)),
            "agree": float(m.group(4)),
            "disagree": float(m.group(5)),
            "idk": float(m.group(6)),
            "feedbacks": [_entry(fb) for fb in feedbacks],
        })
    return out


def _entry(raw) -> dict:
    """One feedback entry, flattened. Shape depends on the explanation type."""
    raw = _obj(raw)
    explanation = _obj(raw.get("explanation"))
    data = _obj(explanation.get("data"))
    user = _obj(raw.get("user"))
    entry = {
        "type": explanation.get("type"),
        "created_at": raw.get("createdAt"),
        "user": {k: user.get(k) for k in _USER_FIELDS if user.get(k)} or None,
        "comment": data.get("comment") or None,
    }
    changes = [
        {"attribute": c.get("attribute"), "from": c.get("originalValue"),
         "to": c.get("newValue")}
        for c in (data.get("changes") or []) if isinstance(c, dict)
    ]
    if changes:
        entry["changes"] = changes
    proposed = [
        {"name": g.get("name"), "marker_genes": g.get("markerGenes") or []}
        for g in (data.get("groups") or data.get("labels") or [])
        if isinstance(g, dict)
    ]
    if proposed:
        entry["proposed_labels"] = proposed
    return entry


def fetch_feedback(project_id: str | None, dataset_id: str, fetch_page=None,
                   attempts: int = 3, sleep=None) -> list[dict]:
    """Labels and their feedback for one dataset.

    Raises rather than returning an empty list when a page yields no labels:
    CAP intermittently serves the shell without its payload, and silently
    recording "no feedback" for a dataset that has some is the failure this
    guards against. Retries first, because the condition is transient.
    """
    url = dataset_page_url(project_id, dataset_id)
    fetch = fetch_page or _default_fetch_page
    for attempt in range(1, attempts + 1):
        labels = parse_feedback(fetch(f"{url}/feedback"))
        if labels:
            return labels
        if attempt < attempts and sleep is not None:
            sleep(2.0 * attempt)
    raise CapError(
        f"No labels parsed from the feedback page of dataset {dataset_id} after "
        f"{attempts} attempt(s). CAP serves the page shell without its payload "
        "intermittently, so this is usually transient -- but it is also what a "
        "changed page structure looks like. Re-run; if it persists, the parser "
        "needs updating."
    )


def with_feedback(labels: list[dict]) -> list[dict]:
    """Only the labels carrying feedback or a non-zero score."""
    return [lb for lb in labels
            if lb["feedbacks"] or lb["agree"] or lb["disagree"] or lb["idk"]]


def summarise(labels: list[dict], dataset_id: str) -> list[dict]:
    """Flat, CSV-friendly rows: one per label carrying feedback."""
    rows = []
    for lb in with_feedback(labels):
        types = [fb["type"] for fb in lb["feedbacks"] if fb.get("type")]
        who = [(fb.get("user") or {}).get("displayName")
               for fb in lb["feedbacks"]]
        rows.append({
            "dataset_id": dataset_id, "labelset": lb["labelset"],
            "label_id": lb["label_id"], "label": lb["label"], "count": lb["count"],
            "agree": lb["agree"], "disagree": lb["disagree"], "idk": lb["idk"],
            "n_feedback": len(lb["feedbacks"]),
            "types": ",".join(types),
            "users": ",".join(u for u in who if u),
        })
    return rows
