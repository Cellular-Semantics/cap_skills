import base64

import pytest

from cap_client.degs import ROW_FIELDS, decode_diff_key, fetch_degs
from cap_client.errors import CapError
from conftest import SESSION_OK, FakeClient, de_payload, errors, gene

DIFF_KEY = "gen_de_" + base64.b64encode(b"abc;None;downsample;42").decode()

PRECOMPUTED = {
    "Tuft Cells": [gene("IRAG2", 8.1, 300.0), gene("POU2F3", 7.4, 250.0)],
    "Tuft Progenitors": [gene("MKI67", 6.0, 120.0)],
}


def general_de(_v):
    return {"data": {"datasetSession": {"id": "s",
            "generalDifferentialExpressions": DIFF_KEY}}}


def precomputed_de(variables):
    name, = variables["options"]["selectionNames"]
    if name not in PRECOMPUTED:
        # Small populations are absent from CAP's precomputed DE, and the server
        # raises rather than returning an empty list.
        return errors(f"setup_gene_list: no selection named {name}")
    return de_payload(PRECOMPUTED[name])


def base_handlers(**over):
    h = {"CreateDatasetSession": SESSION_OK,
         "GeneralDE": general_de,
         "DEGenes": precomputed_de,
         "Selection": {"data": {"datasetSession": {"id": "s", "singleSelectionKey": "fg"}}},
         "CustomDiff": {"data": {"datasetSession": {"id": "s",
                        "differentialExpressions": "diff"}}}}
    h.update(over)
    return h


def test_decode_diff_key():
    assert decode_diff_key(DIFF_KEY) == "abc;None;downsample;42"
    assert decode_diff_key("not base64 at all") == "not base64 at all"


def test_precomputed_path(labelset):
    client = FakeClient(base_handlers())
    r = fetch_degs(client, "3400", labelset, only=["Tuft Cells"])
    assert r["compared_to"] == "all other cells"
    assert r["n_rows"] == 2
    assert {row["method"] for row in r["rows"]} == {"precomputed"}
    assert r["rows"][0] == {"cell_type": "Tuft Cells", "n_cells": 100, "gene": "IRAG2",
                            "logFC": 8.1, "score": 300.0, "pValue": 0.001,
                            "method": "precomputed", "compared_to": "all other cells"}
    assert set(r["rows"][0]) == set(ROW_FIELDS)
    assert r["missing"] == [] and r["fellback"] == []


def test_labels_not_requested_are_still_registered(labelset):
    client = FakeClient(base_handlers())
    fetch_degs(client, "3400", labelset, only=["Tuft Cells"])
    registered = client.calls[0][1]["data"]["dataset"]["labelsets"][0]["labels"]
    assert len(registered) == 3, "DE is computed against the whole dataset"


def test_falls_back_to_on_demand_for_a_label_with_no_precomputed_de(labelset):
    client = FakeClient(base_handlers(
        DEGenes=lambda v: (de_payload([gene("XIST", 29.9, 1.2)])
                           if v["options"]["selectionNames"] == ["selection"]
                           else precomputed_de(v))))
    r = fetch_degs(client, "3400", labelset)
    assert r["fellback"] == [{"cell_type": "Rare Cells", "n_cells": 3}]
    assert r["cell_types_done"] == 3 and r["missing"] == []
    methods = {row["cell_type"]: row["method"] for row in r["rows"]}
    assert methods == {"Tuft Cells": "precomputed", "Tuft Progenitors": "precomputed",
                       "Rare Cells": "on-demand"}
    # The on-demand path must ask for the anonymous "selection", never the label name.
    assert ["selection"] in [v["options"].get("selectionNames")
                             for op, v in client.calls if op == "DEGenes"]


def test_on_demand_never_reports_missing_instead_of_falling_back(labelset):
    client = FakeClient(base_handlers())
    r = fetch_degs(client, "3400", labelset, on_demand="never")
    assert [m["cell_type"] for m in r["missing"]] == ["Rare Cells"]
    assert "setup_gene_list" in r["missing"][0]["error"]
    assert "Selection" not in client.ops()


def test_on_demand_only_skips_the_precomputed_path(labelset):
    client = FakeClient(base_handlers(
        DEGenes=lambda v: de_payload([gene("XIST", 12.0, 3.0)])))
    r = fetch_degs(client, "3400", labelset, only=["Tuft Cells"], on_demand="only")
    assert "GeneralDE" not in client.ops()
    assert {row["method"] for row in r["rows"]} == {"on-demand"}
    assert r["fellback"] == [], "nothing 'fell back' when there was no precomputed attempt"


def test_vs_forces_on_demand_and_sends_a_background_key(labelset):
    def key_for(v):
        label_id = v["options"]["selection"][0]["labelIdSelection"]["labelId"]
        return {"data": {"datasetSession": {"id": "s",
                "singleSelectionKey": f"key-{label_id}"}}}

    client = FakeClient(base_handlers(
        Selection=key_for,
        DEGenes=lambda v: de_payload([gene("MKI67", 5.5, 40.0)])))
    r = fetch_degs(client, "3400", labelset, only=["Tuft Progenitors"], vs="Tuft Cells")
    assert "GeneralDE" not in client.ops()
    assert r["compared_to"] == "Tuft Cells"
    assert all(row["compared_to"] == "Tuft Cells" for row in r["rows"])
    custom, = [v for op, v in client.calls if op == "CustomDiff"]
    assert custom["options"]["backgroundSelectionsKey"] == "key-1", \
        "the background must be Tuft Cells (label 1), the named comparator"


def test_no_background_key_means_vs_rest(labelset):
    client = FakeClient(base_handlers(
        DEGenes=lambda v: de_payload([gene("XIST", 9.0, 2.0)])))
    fetch_degs(client, "3400", labelset, only=["Rare Cells"], on_demand="only")
    custom, = [v for op, v in client.calls if op == "CustomDiff"]
    assert "backgroundSelectionsKey" not in custom["options"], \
        "an unset background slot is what makes the comparator 'all other cells'"


def test_vs_must_not_be_in_the_foreground(labelset):
    with pytest.raises(CapError, match="also in the foreground"):
        fetch_degs(FakeClient(base_handlers()), "3400", labelset, vs="Tuft Cells")


def test_vs_unknown_label(labelset):
    with pytest.raises(CapError, match="No cell type named 'Goblet'"):
        fetch_degs(FakeClient(base_handlers()), "3400", labelset, vs="Goblet")


def test_only_unknown_label(labelset):
    with pytest.raises(CapError, match="No such cell type"):
        fetch_degs(FakeClient(base_handlers()), "3400", labelset, only=["Goblet"])


def test_bad_sort_key(labelset):
    with pytest.raises(CapError, match="sort-by"):
        fetch_degs(FakeClient(base_handlers()), "3400", labelset, sort_by="logfc")


def test_general_de_failure_is_fatal(labelset):
    client = FakeClient(base_handlers(GeneralDE=errors("no such labelset")))
    with pytest.raises(CapError, match="GeneralDE failed"):
        fetch_degs(client, "3400", labelset)


def test_selection_failure_on_the_comparator_is_fatal(labelset):
    client = FakeClient(base_handlers(Selection=errors("session expired")))
    with pytest.raises(CapError, match="Could not build comparator selection"):
        fetch_degs(client, "3400", labelset, only=["Tuft Progenitors"], vs="Tuft Cells")


def test_on_demand_errors_are_collected_not_raised(labelset):
    client = FakeClient(base_handlers(
        CustomDiff=errors("compute failed"),
        DEGenes=lambda v: precomputed_de(v)))
    r = fetch_degs(client, "3400", labelset)
    assert [m["cell_type"] for m in r["missing"]] == ["Rare Cells"]
    assert "CustomDiff" in r["missing"][0]["error"]
    assert r["cell_types_done"] == 2


def test_request_options_are_passed_through(labelset):
    client = FakeClient(base_handlers())
    fetch_degs(client, "3400", labelset, only=["Tuft Cells"], limit=25,
               max_pvalue=0.05, sort_by="score", seed=7)
    opts = next(v["options"] for op, v in client.calls if op == "DEGenes")
    assert opts["limit"] == 25 and opts["maxPValue"] == 0.05
    assert opts["sortBy"] == "score" and opts["sortOrder"] == "desc"
    assert [v["options"]["randomSeed"] for op, v in client.calls if op == "GeneralDE"] == [7]
