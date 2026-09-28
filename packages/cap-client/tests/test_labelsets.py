import json

import pytest
from cap_client.errors import CapError
from cap_client.labelsets import (
    fetch_labelsets,
    find_label,
    parse_labelsets,
    select_labelset,
    summarise,
)
from conftest import LABELSET, LABELSETS, TISSUE_LABELSET


def page_with(*labelsets):
    """A dataset page the way CAP serves it: JSON inside a JS string literal, so
    every quote arrives escaped."""
    # Compact separators matter: the marker parse_labelsets looks for has no
    # space after the colon, exactly as CAP's payload serialises it.
    payloads = [json.dumps({"__typename": "Labelset", **ls}, separators=(",", ":"))
                for ls in labelsets]
    inner = ",".join(payloads).replace('"', '\\"')
    return f'<html><script>self.__next_f.push([1,"{inner}"])</script></html>'


def test_parse_labelsets_finds_both():
    found = parse_labelsets(page_with(LABELSET, TISSUE_LABELSET))
    assert set(found) == {"77", "78"}
    assert [lb["name"] for lb in found["77"]["labels"]] == \
        ["Tuft Cells", "Tuft Progenitors", "Rare Cells"]


def test_parse_labelsets_ignores_objects_without_labels():
    page = page_with({"id": "99", "name": "no-labels-key"})
    assert parse_labelsets(page) == {}


def test_parse_labelsets_empty_page():
    assert parse_labelsets("<html></html>") == {}


def test_fetch_labelsets_raises_when_nothing_found():
    with pytest.raises(CapError, match="page structure may have changed"):
        fetch_labelsets("1", "2", fetch_page=lambda url: "<html></html>")


def test_fetch_labelsets_passes_the_right_url():
    seen = []

    def fetch(url):
        seen.append(url)
        return page_with(LABELSET)

    fetch_labelsets("1030", "3400", fetch_page=fetch)
    assert seen == ["https://celltype.info/project/1030/dataset/3400"]


def test_select_labelset_by_name():
    assert select_labelset(LABELSETS, "tissue")["id"] == "78"


def test_select_labelset_defaults_to_largest_cell_labels():
    # tissue has mode "obs", so it is never the default even if it had more labels.
    assert select_labelset(LABELSETS)["name"] == "hgca_celltype_v1"


def test_select_labelset_unknown_name_lists_options():
    with pytest.raises(CapError, match="hgca_celltype_v1, tissue"):
        select_labelset(LABELSETS, "nope")


def test_select_labelset_no_cell_labels():
    with pytest.raises(CapError, match="No cell-labels labelset"):
        select_labelset({"78": TISSUE_LABELSET})


def test_find_label():
    assert find_label(LABELSET, "Tuft Cells")["id"] == 1
    with pytest.raises(CapError, match="No cell type named 'Goblet'"):
        find_label(LABELSET, "Goblet")


def test_summarise_shape():
    out = summarise(LABELSETS)
    assert [ls["id"] for ls in out] == ["77", "78"]
    assert out[0]["n_labels"] == 3
    assert out[0]["labels"][0] == {"id": "1", "name": "Tuft Cells", "count": 100}
