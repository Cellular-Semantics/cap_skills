import pytest
from cap_client.errors import CapError
from cap_client.expression import ROW_FIELDS, detect_embedding, fetch_expression, obs_columns
from conftest import FakeClient, errors

OBS_PROBE_ERROR = errors(
    "No match for FieldRef.Name(__cap_probe__1) in \n"
    "cell_id: string\numap1: double\numap2: double\ntissue: string\n"
    "donor_id: string\npca1: double\npca2: double\n")

# Six cells: three Tuft Cells (ids 1), three Tuft Progenitors (ids 2).
LIDS = [1, 1, 1, 2, 2, 2]
TISSUE_LIDS = [10, 10, 11, 10, 11, 11]
OBS_IDS = ["c1", "c2", "c3", "c4", "c5", "c6"]


def embedding(gene_values=None, lids=LIDS, labelset="hgca_celltype_v1", obs_ids=OBS_IDS):
    ann = [{"name": labelset, "labelIds": lids}]
    data = {"obsIds": obs_ids, "annotations": ann, "expressionMax": 5.0}
    if gene_values is not None:
        data["geneExpression"] = gene_values
    return {"data": {"datasetSession": {"embeddingData": data}}}


def handler(genes, tissue=False):
    """Answer EmbeddingData: the probe, the cross-tab labelset, then each gene."""
    def h(variables):
        opts = variables["options"]
        if opts["embedding"] == "__cap_probe__":
            return OBS_PROBE_ERROR
        if opts["labelsets"] == "tissue":
            return embedding(lids=TISSUE_LIDS, labelset="tissue")
        g = opts.get("selectionGene")
        if g not in genes:
            return errors(f"Gene {g} not found in var index")
        return embedding(genes[g])
    return h


def test_obs_columns_read_out_of_the_probe_error():
    client = FakeClient({"EmbeddingData": OBS_PROBE_ERROR})
    cols, msg = obs_columns(client, "3400", "s", "hgca_celltype_v1")
    assert cols == ["cell_id", "umap1", "umap2", "tissue", "donor_id", "pca1", "pca2"]
    assert "No match for FieldRef" in msg


def test_detect_embedding_prefers_umap_over_pca():
    client = FakeClient({"EmbeddingData": OBS_PROBE_ERROR})
    name, cols = detect_embedding(client, "3400", "s", "hgca_celltype_v1")
    assert name == "umap"
    assert "tissue" in cols


def test_detect_embedding_needs_a_coordinate_pair():
    client = FakeClient({"EmbeddingData": errors("No match for FieldRef.Name(x1) in "
                                                "cell_id: string\ntissue: string\n")})
    with pytest.raises(CapError, match="No <name>1/<name>2 coordinate pair"):
        detect_embedding(client, "3400", "s", "hgca_celltype_v1")


def test_detect_embedding_needs_obs_columns():
    client = FakeClient({"EmbeddingData": errors("something else entirely")})
    with pytest.raises(CapError, match="Could not read obs columns"):
        detect_embedding(client, "3400", "s", "hgca_celltype_v1")


def run(labelset, genes, **kw):
    client = FakeClient({"EmbeddingData": handler(genes, tissue="group_labelsets" in kw)})
    kw.setdefault("group_labelsets", [])
    result = fetch_expression(client, "3400", "s", primary_labelset=labelset,
                              genes=list(genes), embedding="umap", scale_max=6.0, **kw)
    return client, result


def test_pct_detected_and_means(labelset):
    # Tuft Cells: 0, 1, 3 -> 2/3 detected, mean_all 4/3, mean_expressing 2.
    _client, r = run(labelset, {"IRAG2": [0.0, 1.0, 3.0, 0.0, 0.0, 0.0]})
    by_ct = {row["cell_type"]: row for row in r["rows"]}
    assert set(by_ct) == {"Tuft Cells", "Tuft Progenitors"}
    tc = by_ct["Tuft Cells"]
    assert (tc["n_cells"], tc["n_detected"], tc["pct_detected"]) == (3, 2, 66.67)
    assert tc["mean_all"] == 1.3333 and tc["mean_expressing"] == 2.0
    tp = by_ct["Tuft Progenitors"]
    assert tp["pct_detected"] == 0.0 and tp["mean_expressing"] == 0.0
    assert set(tc) == set(ROW_FIELDS)


def test_min_expression_threshold_is_exclusive(labelset):
    _client, r = run(labelset, {"G": [1.0, 1.0, 1.0, 2.0, 2.0, 2.0]}, min_expression=1.0)
    by_ct = {row["cell_type"]: row["pct_detected"] for row in r["rows"]}
    assert by_ct == {"Tuft Cells": 0.0, "Tuft Progenitors": 100.0}


def test_cell_types_filter(labelset):
    _client, r = run(labelset, {"G": [1.0] * 6}, cell_types=["Tuft Cells"])
    assert {row["cell_type"] for row in r["rows"]} == {"Tuft Cells"}


def test_unknown_cell_type(labelset):
    with pytest.raises(CapError, match="No such cell type"):
        run(labelset, {"G": [1.0] * 6}, cell_types=["Goblet"])


def test_missing_gene_is_reported_not_fatal(labelset):
    _client, r = run(labelset, {"IRAG2": [1.0] * 6, "LRMP": None})
    # LRMP: a symbol retired in 2020. CAP matches the var index exactly, so it
    # simply does not resolve -- worth surfacing rather than silently dropping.
    assert r["missing_genes"] == ["LRMP"]
    assert {row["gene"] for row in r["rows"]} == {"IRAG2"}


def test_all_genes_missing_is_fatal(labelset):
    with pytest.raises(CapError, match="retired"):
        run(labelset, {"LRMP": None})


def test_no_genes(labelset):
    with pytest.raises(CapError, match="At least one gene"):
        run(labelset, {})


def test_cross_tabulation(labelset, tissue_labelset):
    client, r = run(labelset, {"GNAT3": [1.0, 1.0, 0.0, 0.0, 0.0, 0.0]},
                    group_labelsets=[tissue_labelset])
    ungrouped = [row for row in r["rows"] if row["group_by"] == ""]
    grouped = [row for row in r["rows"] if row["group_by"] == "tissue"]
    assert len(ungrouped) == 2
    assert {(row["cell_type"], row["group_value"]): row["pct_detected"] for row in grouped} == {
        ("Tuft Cells", "small intestine"): 100.0,
        ("Tuft Cells", "colon"): 0.0,
        ("Tuft Progenitors", "small intestine"): 0.0,
        ("Tuft Progenitors", "colon"): 0.0,
    }
    # The cross-tab labelset costs one call in total, not one per gene.
    tissue_calls = [v for op, v in client.calls
                    if v["options"].get("labelsets") == "tissue"]
    assert len(tissue_calls) == 1
    assert r["group_by"] == ["tissue"]


def test_obs_order_change_aborts_cross_tabulation(labelset, tissue_labelset):
    calls = {"n": 0}

    def h(variables):
        opts = variables["options"]
        if opts["labelsets"] == "tissue":
            return embedding(lids=TISSUE_LIDS, labelset="tissue")
        calls["n"] += 1
        shuffled = list(reversed(OBS_IDS)) if calls["n"] > 1 else OBS_IDS
        return embedding([1.0] * 6, obs_ids=shuffled)

    client = FakeClient({"EmbeddingData": h})
    with pytest.raises(CapError, match="obsIds ordering changed"):
        fetch_expression(client, "3400", "s", primary_labelset=labelset,
                         group_labelsets=[tissue_labelset], genes=["A", "B"],
                         embedding="umap", scale_max=6.0)


def test_per_cell_rows(labelset):
    _client, r = run(labelset, {"G": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]}, per_cell=True)
    assert len(r["per_cell"]) == 6
    assert r["per_cell"][0] == {"obs_id": "c1", "cell_type": "Tuft Cells",
                                "gene": "G", "value": 0.0}


def test_unlabelled_cells_are_dropped(labelset):
    client = FakeClient({"EmbeddingData": lambda v: embedding([1.0] * 6,
                                                             lids=[1, 1, 1, 2, 2, 999])})
    r = fetch_expression(client, "3400", "s", primary_labelset=labelset,
                         group_labelsets=[], genes=["G"], embedding="umap", scale_max=6.0)
    counts = {row["cell_type"]: row["n_cells"] for row in r["rows"]}
    assert counts == {"Tuft Cells": 3, "Tuft Progenitors": 2}
