"""Smoke tests against the real celltype.info. Excluded from CI (-m 'not live').

These exist for one reason the offline suite cannot cover: CAP's persisted-query
safelist. A redeploy that changes the query bodies makes every call fail with
QUERY_NOT_IN_SAFELIST, and only a real request finds out.

    pytest -m live
"""
import pytest
from cap_client.degs import fetch_degs
from cap_client.downloads import download_urls, resolve_h5ad_url
from cap_client.expression import detect_embedding, fetch_expression
from cap_client.labelsets import fetch_labelsets, select_labelset
from cap_client.session import create_session
from cap_client.targets import parse_target
from cap_client.transport import GraphQLClient

pytestmark = pytest.mark.live

# The Integrated Human Gut Cell Atlas: the best-evidenced slice of the CAP OLS
# report, and the dataset the tuft-lineage review was written against.
TARGET = "https://celltype.info/project/1030/dataset/3400"
LABELSET = "hgca_celltype_v1"


@pytest.fixture(scope="module")
def dataset():
    project_id, dataset_id = parse_target(TARGET)
    labelsets = fetch_labelsets(project_id, dataset_id)
    return dataset_id, select_labelset(labelsets, LABELSET)


def test_labelset_is_reachable(dataset):
    _dataset_id, ls = dataset
    names = {lb["name"] for lb in ls["labels"]}
    assert {"Tuft Cells", "Tuft Progenitors"} <= names


def test_degs_paired_comparison_reproduces_the_review(dataset):
    """Tuft Progenitors vs Tuft Cells returns cell-cycle genes, not tuft genes.

    That is the finding in analysis/tuft_lineage_annotation_review.md (the
    CAP_reports_hacking repo): the progenitor claim rests on proliferation. The
    named markers there are MKI67 and TOP2A, but a logFC-ranked list favours
    restricted genes over abundant ones, so the assertion is against the
    proliferation programme rather than those two symbols.

    If the safelist or the paired-DE path breaks, this is where it shows.
    """
    dataset_id, ls = dataset
    client = GraphQLClient(min_interval=0.5, log=lambda m: None)
    r = fetch_degs(client, dataset_id, ls, only=["Tuft Progenitors"], vs="Tuft Cells",
                   limit=50)
    assert r["compared_to"] == "Tuft Cells"
    assert r["n_rows"] > 0
    assert {row["method"] for row in r["rows"]} == {"on-demand"}
    genes = {row["gene"] for row in r["rows"]}
    proliferation = {"MKI67", "TOP2A", "ASPM", "AURKB", "BIRC5", "CENPF", "CCNB1",
                     "UBE2C", "PLK1", "CDK1", "NUSAP1", "TYMS", "PCNA"}
    assert proliferation & genes, sorted(genes)[:20]


def test_expression_reproduces_stmn1_not_discriminating(dataset):
    """STMN1 is a curated marker of Tuft Progenitors that does not discriminate:
    ~54.5% of progenitors versus ~47.1% of tuft cells. IRAG2 does: ~97.9% vs low.

    Tolerances are wide because CAP may downsample; the point is the ordering and
    the order of magnitude, not the decimal.
    """
    dataset_id, ls = dataset
    client = GraphQLClient(min_interval=0.5, log=lambda m: None)
    session_id, cell_count = create_session(client, dataset_id, [ls])
    embedding, _cols = detect_embedding(client, dataset_id, session_id, ls["name"])
    r = fetch_expression(client, dataset_id, session_id, primary_labelset=ls,
                         group_labelsets=[], genes=["STMN1", "IRAG2"], embedding=embedding,
                         scale_max=float(cell_count),
                         cell_types=["Tuft Cells", "Tuft Progenitors"])
    pct = {(row["gene"], row["cell_type"]): row["pct_detected"] for row in r["rows"]}
    assert r["missing_genes"] == [], "IRAG2 is LRMP's current symbol and must resolve"
    assert pct[("STMN1", "Tuft Progenitors")] == pytest.approx(54.5, abs=8)
    assert pct[("STMN1", "Tuft Cells")] == pytest.approx(47.1, abs=8)
    assert pct[("IRAG2", "Tuft Cells")] > 85
    assert pct[("IRAG2", "Tuft Cells")] > pct[("STMN1", "Tuft Cells")]


def test_retired_symbol_does_not_resolve(dataset):
    """LRMP was retired in 2020. CAP matches the var index exactly, so a curated
    marker under its old symbol silently fails -- which is how this was found."""
    dataset_id, ls = dataset
    client = GraphQLClient(min_interval=0.5, log=lambda m: None)
    session_id, cell_count = create_session(client, dataset_id, [ls])
    embedding, _cols = detect_embedding(client, dataset_id, session_id, ls["name"])
    r = fetch_expression(client, dataset_id, session_id, primary_labelset=ls,
                         group_labelsets=[], genes=["IRAG2", "LRMP"], embedding=embedding,
                         scale_max=float(cell_count), cell_types=["Tuft Cells"])
    assert r["missing_genes"] == ["LRMP"]


def test_download_urls_query_is_still_safelisted(dataset):
    """This dataset exposes no annDataUrl -- many CAP datasets do not -- so the
    check is that the query itself still works, not that a URL comes back."""
    dataset_id, _ls = dataset
    urls = download_urls(GraphQLClient(log=lambda m: None), dataset_id)
    assert "annDataUrl" in urls and "isAnnDataUrlUpToDate" in urls


def test_resolve_h5ad_passes_through_a_plain_url():
    plain = "https://example.org/atlas.h5ad"
    assert resolve_h5ad_url(GraphQLClient(log=lambda m: None), plain) == plain
