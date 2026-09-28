import json

import pytest
from conftest import N_CELLS
from h5ad_obs import cli


def run(capsys, argv, code=0):
    assert cli.main(argv) == code
    return capsys.readouterr()


def test_list_columns_json(capsys, served):
    url, _server = served
    out = run(capsys, [url, "--list-columns"])
    payload = json.loads(out.out)
    assert payload["n_obs_columns"] == 5
    assert payload["obs_columns"][0] == {"name": "cell_type", "kind": "categorical"}
    assert payload["range_requests"] > 0
    assert payload["file_bytes"] > 0


def test_writes_parquet_and_reports_it(capsys, served, tmp_path):
    url, _server = served
    out_path = tmp_path / "obs.parquet"
    out = run(capsys, [url, "--out", str(out_path)])
    payload = json.loads(out.out)
    assert payload["n_rows"] == N_CELLS and payload["n_columns"] == 4
    assert payload["skipped_columns"] == ["weird"]
    assert payload["out"] == str(out_path)
    import pandas as pd
    assert pd.read_parquet(out_path).shape == (N_CELLS, 4)


def test_writes_tsv(capsys, served, tmp_path):
    url, _server = served
    out_path = tmp_path / "obs.tsv"
    run(capsys, [url, "--format", "tsv", "--out", str(out_path),
                 "--columns", "cell_type", "donor_id"])
    header = out_path.read_text().splitlines()[0]
    assert header.split("\t") == ["cell_id", "cell_type", "donor_id"]


def test_column_subset(capsys, served, tmp_path):
    url, _server = served
    out = run(capsys, [url, "--columns", "cell_type", "--out", str(tmp_path / "o.parquet")])
    assert json.loads(out.out)["columns"] == ["cell_type"]


def test_unknown_column_exits_nonzero(capsys, served, tmp_path):
    url, _server = served
    out = run(capsys, [url, "--columns", "nope", "--out", str(tmp_path / "o.parquet")], code=1)
    assert "error: Unknown obs column" in out.err


def test_no_range_support_exits_nonzero(capsys, no_range_url):
    out = run(capsys, [no_range_url], code=1)
    assert "does not advertise range support" in out.err


def test_no_preflight_skips_the_head(capsys, served, tmp_path):
    url, _server = served
    out = run(capsys, [url, "--no-preflight", "--out", str(tmp_path / "o.parquet")])
    assert json.loads(out.out)["file_bytes"] is None


def test_cap_url_is_resolved_through_cap_client(capsys, served, tmp_path, monkeypatch):
    """A celltype.info URL must be handed to cap-client, not fetched directly."""
    url, _server = served
    seen = []

    def fake_resolve(client, target, log=None):
        seen.append(target)
        return url

    monkeypatch.setattr("cap_client.downloads.resolve_h5ad_url", fake_resolve)
    cap = "https://celltype.info/project/1030/dataset/3400"
    out = run(capsys, [cap, "--out", str(tmp_path / "o.parquet")])
    assert seen == [cap]
    assert json.loads(out.out)["h5ad_url"] == url


def test_version(capsys):
    from h5ad_obs import __version__
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out
