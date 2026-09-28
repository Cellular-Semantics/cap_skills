"""Discovering what datasets CAP hosts, and which consortium tagged them.

This is the entry point to an atlas review: before you can ask what distinguishes
a cluster, you have to find the dataset. CAP's dataset search is a public
GraphQL query, so this needs no browser -- earlier versions of this workflow
drove the search page with Playwright and paged a virtualised table 30 rows at a
time.

**The consortium tag is only available here.** It is not in CAP's exported OLS
report, so "which of these rows are Human Cell Atlas?" can only be answered by
joining the report against this query on dataset id.
"""
from __future__ import annotations

import json

from .errors import CapError
from .queries import Q_CONSORTIUM_TAGS, Q_SEARCH_DATASETS

#: A labelset name chosen not to exist. Passing one is the only way to stop the
#: server expanding every labelset and every label into the response: omitting
#: `labelsetNames`, or passing an empty list, both mean "all of them". On the 61
#: HCA datasets that is 2,365 labelsets and 24,096 labels -- 2.4 MB, versus
#: 95 KB with this set. Labelsets are available per dataset from `cap labelsets`,
#: so the search does not need to carry them.
NO_LABELSETS = "__cap_client_no_labelsets__"

#: 127 datasets are public as of 2026-09, so one page covers the whole catalogue
#: with room to spare. Omitting `options` entirely gets a server default of 20.
DEFAULT_LIMIT = 500

FIELDS = ["dataset_id", "dataset_name", "cell_count", "project_id", "project_name",
          "created_at", "consortium_tags", "url"]


def dataset_url(project_id, dataset_id) -> str:
    return f"https://celltype.info/project/{project_id}/dataset/{dataset_id}"


def summarise(node: dict, with_labelsets: bool = False) -> dict:
    """One search hit, reduced to the fields worth carrying.

    The raw node also holds author lists, permissions, avatar URLs and scores.
    None of it helps you find a dataset, and all of it costs tokens.
    """
    project = node.get("project") or {}
    pid = project.get("id")
    row = {
        "dataset_id": str(node["id"]),
        "dataset_name": node.get("name"),
        "cell_count": node.get("cellCount"),
        "project_id": str(pid) if pid is not None else None,
        "project_name": project.get("name"),
        "created_at": project.get("createdAt"),
        "consortium_tags": [t.get("title") for t in (node.get("consortiumTags") or [])],
        "url": dataset_url(pid, node["id"]),
    }
    if with_labelsets:
        row["labelsets"] = [
            {"id": str(ls["id"]), "name": ls.get("name"),
             "n_labels": len(ls.get("labels") or [])}
            for ls in (node.get("labelsets") or [])
        ]
    return row


def search_datasets(client, *, consortium_tag_ids=None, name=None, project_name=None,
                    project_description=None, cell_types=None, labelset=None,
                    labelset_names=None, limit=DEFAULT_LIMIT, offset=0) -> list[dict]:
    """Search CAP's dataset catalogue. Returns summarised rows.

    `labelset_names` controls which labelsets are expanded in the response; the
    default suppresses them entirely (see NO_LABELSETS). Pass a list of names to
    include matching ones. To ask *which datasets carry a labelset called X*,
    prefer `labelset=[...]`, which filters server-side.
    """
    search = {k: v for k, v in (("name", name), ("projectName", project_name),
                                ("projectDescription", project_description),
                                ("cellTypes", cell_types)) if v}
    filters = {k: v for k, v in (("consortiumTagIds", consortium_tag_ids),
                                 ("labelset", labelset)) if v}
    variables = {
        "options": {"limit": limit, "offset": offset},
        "labelsetNames": labelset_names if labelset_names is not None else [NO_LABELSETS],
    }
    if search:
        variables["search"] = search
    if filters:
        variables["filter"] = filters

    r = client.call("SearchDatasets", variables, Q_SEARCH_DATASETS)
    if r.get("errors"):
        raise CapError(f"SearchDatasets failed: {json.dumps(r['errors'])[:400]}")
    nodes = r["data"]["results"]
    return [summarise(n, with_labelsets=labelset_names is not None) for n in nodes]


def consortium_tags(client) -> list[dict]:
    """The consortium tag vocabulary: id, title, parent.

    The only operation exposing this is CAP's project-tagging dialog, which
    demands a project id and 404s without a real one -- even though the tag list
    it returns is global. So one dataset is looked up first, purely to borrow its
    project id. Two calls, and no hardcoded ids to go stale.
    """
    seed = search_datasets(client, limit=1, offset=0)
    if not seed or not seed[0]["project_id"]:
        raise CapError("Could not find any dataset to borrow a project id from; the "
                       "consortium tag list cannot be fetched without one.")
    r = client.call("SetProjectTagsDialogQuery", {"projectId": seed[0]["project_id"]},
                    Q_CONSORTIUM_TAGS)
    tags = ((r.get("data") or {}).get("consortiumTags")) or []
    if not tags:
        raise CapError(f"No consortium tags returned: {json.dumps(r.get('errors'))[:300]}")
    return [{"id": str(t["id"]), "title": t.get("title"),
             "parent_id": str(t["parentId"]) if t.get("parentId") is not None else None}
            for t in tags]


def resolve_consortium(client, wanted: list[str]) -> list[str]:
    """Turn consortium names or ids into tag ids, case-insensitively.

    Accepts either, so a caller can write `--consortium 1` or
    `--consortium "Human Cell Atlas"` without looking anything up first.
    """
    tags = consortium_tags(client)
    by_id = {t["id"] for t in tags}
    by_title = {(t["title"] or "").lower(): t["id"] for t in tags}
    out, unknown = [], []
    for w in wanted:
        key = str(w)
        tag_id = key if key in by_id else by_title.get(key.lower())
        if tag_id:
            out.append(tag_id)
        else:
            unknown.append(key)
    if unknown:
        available = ", ".join(f'{t["id"]}={t["title"]}' for t in tags)
        raise CapError(f"Unknown consortium: {', '.join(unknown)}. Available: {available}")
    return out
