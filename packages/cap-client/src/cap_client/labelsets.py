"""Labelsets: recovering them from the dataset page, and choosing between them.

There is no safelisted GraphQL operation that returns the labelset structure --
CAP's own web client reads it out of the page's embedded Next.js RSC payload --
so scraping the page is the only route. `fetch_page` is injectable so this is
testable against a saved page.
"""
from __future__ import annotations

import json
import re

from .errors import CapError
from .targets import dataset_page_url
from .transport import fetch_page as _default_fetch_page

_MARKER = '"__typename":"Labelset"'


def parse_labelsets(html: str) -> dict[str, dict]:
    """Pull every Labelset object out of a dataset page's HTML.

    The payload is JSON embedded in a JS string, so quotes and backslashes are
    escaped once; undo that, then brace-match outwards from each Labelset marker.
    """
    text = html.replace('\\"', '"').replace("\\\\", "\\")
    found: dict[str, dict] = {}
    for m in re.finditer(re.escape(_MARKER), text):
        start = text.rfind("{", 0, m.start())
        if start < 0:
            continue
        depth = 0
        for j in range(start, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:j + 1])
                    except Exception:
                        pass
                    else:
                        if obj.get("id") and "labels" in obj:
                            found[str(obj["id"])] = obj
                    break
    return found


def fetch_labelsets(project_id: str | None, dataset_id: str, fetch_page=None) -> dict[str, dict]:
    url = dataset_page_url(project_id, dataset_id)
    html = (fetch_page or _default_fetch_page)(url)
    found = parse_labelsets(html)
    if not found:
        raise CapError("No labelsets found in the page payload -- CAP's page structure may "
                       "have changed, or the dataset is private.")
    return found


def select_labelset(labelsets: dict[str, dict], name: str | None = None) -> dict:
    """The named labelset, or the cell-labels labelset with the most labels.

    Datasets carry several labelsets (cell labels plus obs-derived ones like
    tissue or donor); defaulting to the largest cell-labels one picks the
    annotation under review rather than a metadata column.
    """
    if name:
        chosen = next((ls for ls in labelsets.values() if ls.get("name") == name), None)
        if chosen is None:
            available = ", ".join(sorted(str(ls.get("name")) for ls in labelsets.values()))
            raise CapError(f"No labelset named '{name}'. Available: {available}")
        return chosen
    cands = [ls for ls in labelsets.values()
             if ls.get("mode") == "cell-labels" and ls.get("labels")]
    if not cands:
        raise CapError("No cell-labels labelset with labels in this dataset; "
                       "name one explicitly (see `cap labelsets`).")
    return max(cands, key=lambda ls: len(ls["labels"]))


def find_label(labelset: dict, name: str) -> dict:
    lb = next((lb for lb in labelset["labels"] if lb["name"] == name), None)
    if lb is None:
        raise CapError(f"No cell type named '{name}' in labelset {labelset['name']}.")
    return lb


def summarise(labelsets: dict[str, dict]) -> list[dict]:
    """Flat, JSON-friendly listing of the labelsets in a dataset."""
    return [{"id": str(ls.get("id")), "name": ls.get("name"),
             "mode": ls.get("mode"), "n_labels": len(ls.get("labels") or []),
             "labels": [{"id": str(lb["id"]), "name": lb["name"],
                         "count": lb.get("count", 0)}
                        for lb in (ls.get("labels") or [])]}
            for ls in sorted(labelsets.values(), key=lambda ls: str(ls.get("id")))]
