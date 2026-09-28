"""End-to-end CLI tests: the JSON on stdout is the contract skills depend on, so
it is checked against golden files."""
import json
import pathlib

import pytest
from test_degs import base_handlers
from test_expression import OBS_PROBE_ERROR
from test_expression import handler as expr_handler

from cap_client import cli
from conftest import LABELSETS

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def stub(monkeypatch):
    """Serve labelsets from the fixture and route every GraphQL call to a fake."""
    import copy

    def install(handlers):
        monkeypatch.setattr(cli, "fetch_labelsets",
                            lambda p, d: copy.deepcopy(LABELSETS))
        from conftest import FakeClient
        client = FakeClient(handlers)
        monkeypatch.setattr(cli, "GraphQLClient", lambda **kw: client)
        return client

    return install


TARGET = "https://celltype.info/project/1030/dataset/3400"


def run(capsys, argv):
    assert cli.main(argv) == 0
    return capsys.readouterr()


def golden(name, payload):
    """Compare against a golden file, writing it when CAP_UPDATE_GOLDEN is set."""
    import os

    path = FIXTURES / name
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if os.environ.get("CAP_UPDATE_GOLDEN"):
        path.write_text(text)
    assert json.loads(path.read_text()) == json.loads(text), f"{name} drifted"


def test_labelsets_json(capsys, stub):
    stub({})
    out = run(capsys, ["labelsets", TARGET])
    golden("labelsets.json", json.loads(out.out))


def test_labelsets_text(capsys, stub):
    stub({})
    out = run(capsys, ["labelsets", TARGET, "--format", "text"])
    assert "hgca_celltype_v1" in out.out and "3 labels" in out.out
    assert "tissue" in out.out


def test_degs_json_golden(capsys, stub):
    stub(base_handlers())
    out = run(capsys, ["degs", TARGET, "--labelset", "hgca_celltype_v1",
                       "--only", "Tuft Cells", "--on-demand", "never"])
    golden("degs.json", json.loads(out.out))


def test_degs_row_fields_are_stable(capsys, stub):
    stub(base_handlers())
    out = run(capsys, ["degs", TARGET, "--only", "Tuft Cells", "--on-demand", "never"])
    from cap_client.degs import ROW_FIELDS
    assert list(json.loads(out.out)["rows"][0]) == ROW_FIELDS


def test_degs_writes_csv(capsys, stub, tmp_path):
    stub(base_handlers())
    csv_path = tmp_path / "degs.csv"
    out = run(capsys, ["degs", TARGET, "--only", "Tuft Cells", "--on-demand", "never",
                       "--csv", str(csv_path)])
    header, first, *_ = csv_path.read_text().splitlines()
    assert header == "cell_type,n_cells,gene,logFC,score,pValue,method,compared_to"
    assert first.startswith("Tuft Cells,100,IRAG2,")
    assert json.loads(out.out)["csv"] == str(csv_path)


def test_progress_goes_to_stderr_only(capsys, stub):
    stub(base_handlers())
    out = run(capsys, ["degs", TARGET, "--only", "Tuft Cells", "--on-demand", "never"])
    json.loads(out.out)  # stdout must be parseable JSON and nothing else
    assert "labelset" in out.err and "diffKey" not in out.out


def test_degs_list_labelsets(capsys, stub):
    stub({})
    out = run(capsys, ["degs", TARGET, "--list-labelsets", "--format", "text"])
    assert "hgca_celltype_v1" in out.out


def test_expression_json_golden(capsys, stub):
    from conftest import SESSION_OK
    stub({"CreateDatasetSession": SESSION_OK,
          "EmbeddingData": expr_handler({"IRAG2": [0.0, 1.0, 3.0, 0.0, 0.0, 0.0]})})
    out = run(capsys, ["expression", TARGET, "--genes", "IRAG2"])
    golden("expression.json", json.loads(out.out))


def test_expression_needs_genes(capsys, stub):
    from conftest import SESSION_OK
    stub({"CreateDatasetSession": SESSION_OK, "EmbeddingData": OBS_PROBE_ERROR})
    assert cli.main(["expression", TARGET]) == 1
    assert "--genes is required" in capsys.readouterr().err


def test_list_obs_columns(capsys, stub):
    from conftest import SESSION_OK
    stub({"CreateDatasetSession": SESSION_OK, "EmbeddingData": OBS_PROBE_ERROR})
    out = run(capsys, ["expression", TARGET, "--list-obs-columns"])
    payload = json.loads(out.out)
    assert payload["obs_columns"][:3] == ["cell_id", "umap1", "umap2"]
    assert payload["embedding"] == "umap"


def test_datasets_json_golden(capsys, stub, monkeypatch):
    from test_datasets import HIT, TAGS_OK
    stub({"SearchDatasets": {"data": {"results": [HIT]}},
          "SetProjectTagsDialogQuery": TAGS_OK})
    out = run(capsys, ["datasets", "--consortium", "Human Cell Atlas"])
    golden("datasets.json", json.loads(out.out))


def test_datasets_text_format(capsys, stub):
    from test_datasets import HIT, TAGS_OK
    stub({"SearchDatasets": {"data": {"results": [HIT]}},
          "SetProjectTagsDialogQuery": TAGS_OK})
    out = run(capsys, ["datasets", "--format", "text"])
    assert "3400" in out.out and "944,502" in out.out
    assert "Human Gut Cell Atlas" in out.out


def test_datasets_warns_when_the_page_is_full(capsys, stub):
    """Exactly --limit rows back means there are probably more, and a silent
    truncation would look like a complete catalogue."""
    from test_datasets import HIT
    stub({"SearchDatasets": {"data": {"results": [HIT, HIT]}}})
    out = run(capsys, ["datasets", "--limit", "2"])
    assert "there may be more" in out.err


def test_datasets_csv_flattens_tags(capsys, stub, tmp_path):
    from test_datasets import HIT
    stub({"SearchDatasets": {"data": {"results": [HIT]}}})
    csv_path = tmp_path / "d.csv"
    run(capsys, ["datasets", "--csv", str(csv_path)])
    header, row = csv_path.read_text().splitlines()[:2]
    assert header.startswith("dataset_id,dataset_name,cell_count")
    assert "Human Cell Atlas" in row


def test_consortia_listing(capsys, stub):
    from test_datasets import HIT, TAGS_OK
    stub({"SearchDatasets": {"data": {"results": [HIT]}},
          "SetProjectTagsDialogQuery": TAGS_OK})
    out = run(capsys, ["consortia", "--format", "text"])
    assert "Human Cell Atlas" in out.out


def test_unknown_consortium_exits_nonzero(capsys, stub):
    from test_datasets import HIT, TAGS_OK
    stub({"SearchDatasets": {"data": {"results": [HIT]}},
          "SetProjectTagsDialogQuery": TAGS_OK})
    assert cli.main(["datasets", "--consortium", "Nope"]) == 1
    assert "Unknown consortium" in capsys.readouterr().err


def test_download_urls(capsys, stub):
    stub({"DownloadUrls": {"data": {"downloadUrls": {
        "annDataUrl": "https://example.org/a.h5ad", "seuratUrl": None,
        "isAnnDataUrlUpToDate": True, "__typename": "DownloadUrls"}}}})
    out = run(capsys, ["h5ad-url", TARGET])
    assert json.loads(out.out)["h5ad_url"] == "https://example.org/a.h5ad"


def test_errors_exit_nonzero_with_a_message(capsys, monkeypatch):
    assert cli.main(["degs", "nonsense"]) == 1
    assert "error: Cannot parse" in capsys.readouterr().err


def test_version(capsys):
    from cap_client import __version__
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out
