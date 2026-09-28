"""Parsing CAP dataset references."""
from __future__ import annotations

import re

from .errors import CapError

_URL_RE = re.compile(r"/project/(\d+)/dataset/(\d+)")


def parse_target(target: str) -> tuple[str | None, str]:
    """Accept a CAP dataset URL or a bare dataset id.

    Returns (project_id, dataset_id); project_id is None for a bare id. Anything
    needing the dataset *page* (labelsets) requires the project id too, because
    the page URL carries both.
    """
    m = _URL_RE.search(target)
    if m:
        return m.group(1), m.group(2)
    if target.isdigit():
        return None, target
    raise CapError(f"Cannot parse '{target}'. Give a CAP dataset URL "
                   "(https://celltype.info/project/<p>/dataset/<d>) or a numeric dataset id.")


def dataset_page_url(project_id: str | None, dataset_id: str) -> str:
    if project_id is None:
        raise CapError("A dataset id alone is not enough to locate the page; pass the "
                       "full CAP dataset URL (/project/<p>/dataset/<d>).")
    return f"https://celltype.info/project/{project_id}/dataset/{dataset_id}"
