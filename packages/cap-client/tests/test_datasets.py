import pytest

from cap_client.datasets import (
    NO_LABELSETS,
    consortium_tags,
    dataset_url,
    resolve_consortium,
    search_datasets,
    summarise,
)
from cap_client.errors import CapError
from conftest import FakeClient, errors

HIT = {
    "id": 3400, "name": "Human Gut Cell Atlas (HGCA) v1 - All Cells",
    "cellCount": 944502,
    "consortiumTags": [{"id": "1", "title": "Human Cell Atlas", "logoUrl": "x",
                        "sortOrder": 1}],
    "labelsets": [{"id": "77", "name": "hgca_celltype_v1",
                   "labels": [{"id": 1, "name": "Tuft Cells", "count": 2993}]}],
    "scores": {"total": 9},
    "project": {"id": 1030, "name": "Human Gut Cell Atlas",
                "createdAt": "2026-02-01T00:00:00.000Z",
                "permissions": [{"user": {"displayName": "someone"}}],
                "externalAuthors": []},
}

TAGS_OK = {"data": {"consortiumTags": [
    {"id": "1", "title": "Human Cell Atlas", "parentId": None, "sortOrder": 1},
    {"id": "2", "title": "Fly Cell Atlas", "parentId": "1", "sortOrder": 2}]}}


def client(results=(HIT,), tags=TAGS_OK):
    return FakeClient({"SearchDatasets": {"data": {"results": list(results)}},
                       "SetProjectTagsDialogQuery": tags})


def variables(c, op="SearchDatasets"):
    return next(v for name, v in c.calls if name == op)


def test_dataset_url():
    assert dataset_url(1030, 3400) == "https://celltype.info/project/1030/dataset/3400"


def test_summarise_keeps_only_the_useful_fields():
    row = summarise(HIT)
    assert row == {
        "dataset_id": "3400",
        "dataset_name": "Human Gut Cell Atlas (HGCA) v1 - All Cells",
        "cell_count": 944502, "project_id": "1030",
        "project_name": "Human Gut Cell Atlas",
        "created_at": "2026-02-01T00:00:00.000Z",
        "consortium_tags": ["Human Cell Atlas"],
        "url": "https://celltype.info/project/1030/dataset/3400"}
    # authors, permissions and scores are dropped; they cost tokens and help nobody
    # find a dataset.
    assert "labelsets" not in row and "scores" not in row


def test_summarise_ids_are_strings():
    """CAP returns ids as ints here and strings elsewhere; joins against the OLS
    report break if that leaks."""
    row = summarise(HIT)
    assert isinstance(row["dataset_id"], str) and isinstance(row["project_id"], str)


def test_summarise_survives_a_missing_project():
    row = summarise({"id": 1, "name": "x", "consortiumTags": []})
    assert row["project_id"] is None and row["cell_count"] is None


def test_summarise_with_labelsets():
    row = summarise(HIT, with_labelsets=True)
    assert row["labelsets"] == [{"id": "77", "name": "hgca_celltype_v1", "n_labels": 1}]


def test_labelsets_are_suppressed_by_default():
    """Omitting labelsetNames means 'every labelset and every label' -- 2.4 MB across
    the HCA datasets. The sentinel is the only way to turn that off."""
    c = client()
    rows = search_datasets(c)
    assert variables(c)["labelsetNames"] == [NO_LABELSETS]
    assert "labelsets" not in rows[0]


def test_with_labelsets_requests_them():
    c = client()
    rows = search_datasets(c, labelset_names=["hgca_celltype_v1"])
    assert variables(c)["labelsetNames"] == ["hgca_celltype_v1"]
    assert rows[0]["labelsets"][0]["name"] == "hgca_celltype_v1"


def test_empty_labelset_names_means_all_and_is_honoured():
    # The server treats [] as "all", same as omitting it. That is a footgun, but
    # passing it through is more honest than silently rewriting the caller's intent.
    c = client()
    search_datasets(c, labelset_names=[])
    assert variables(c)["labelsetNames"] == []


def test_consortium_filter_is_sent():
    c = client()
    search_datasets(c, consortium_tag_ids=["1"])
    assert variables(c)["filter"] == {"consortiumTagIds": ["1"]}


def test_search_terms_are_sent():
    c = client()
    search_datasets(c, name="gut", project_name="HGCA", cell_types=["Tuft Cells"])
    assert variables(c)["search"] == {"name": "gut", "projectName": "HGCA",
                                      "cellTypes": ["Tuft Cells"]}


def test_unset_search_and_filter_are_omitted_entirely():
    # Sending `search: {}` is not the same as omitting it, and CAP is picky.
    c = client()
    search_datasets(c)
    assert "search" not in variables(c) and "filter" not in variables(c)


def test_paging_is_passed_through():
    c = client()
    search_datasets(c, limit=10, offset=20)
    assert variables(c)["options"] == {"limit": 10, "offset": 20}


def test_search_failure_raises():
    c = FakeClient({"SearchDatasets": errors("bad filter")})
    with pytest.raises(CapError, match="SearchDatasets failed"):
        search_datasets(c)


def test_consortium_tags_borrows_a_project_id():
    """The tags are global but the only query exposing them 404s without a real
    project id, so one dataset is looked up purely to borrow one."""
    c = client()
    tags = consortium_tags(c)
    assert [t["id"] for t in tags] == ["1", "2"]
    assert tags[1]["parent_id"] == "1"
    assert variables(c, "SetProjectTagsDialogQuery")["projectId"] == "1030"
    assert variables(c)["options"] == {"limit": 1, "offset": 0}


def test_consortium_tags_with_no_datasets_to_seed_from():
    c = client(results=())
    with pytest.raises(CapError, match="borrow a project id"):
        consortium_tags(c)


def test_consortium_tags_empty_response():
    c = client(tags={"data": {"consortiumTags": []}})
    with pytest.raises(CapError, match="No consortium tags"):
        consortium_tags(c)


@pytest.mark.parametrize("given", ["1", 1, "Human Cell Atlas", "human cell atlas",
                                   "HUMAN CELL ATLAS"])
def test_resolve_consortium_accepts_id_or_name_any_case(given):
    assert resolve_consortium(client(), [given]) == ["1"]


def test_resolve_consortium_multiple():
    assert resolve_consortium(client(), ["1", "Fly Cell Atlas"]) == ["1", "2"]


def test_resolve_consortium_unknown_lists_what_is_available():
    with pytest.raises(CapError, match="1=Human Cell Atlas"):
        resolve_consortium(client(), ["Mouse Atlas"])
