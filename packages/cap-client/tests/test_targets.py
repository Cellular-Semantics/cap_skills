import pytest
from cap_client.errors import CapError
from cap_client.targets import dataset_page_url, parse_target


@pytest.mark.parametrize("target,expected", [
    ("https://celltype.info/project/1030/dataset/3400", ("1030", "3400")),
    ("https://celltype.info/project/1030/dataset/3400/label/12", ("1030", "3400")),
    ("celltype.info/project/9/dataset/8", ("9", "8")),
    ("/project/1/dataset/2", ("1", "2")),
    ("3400", (None, "3400")),
])
def test_parse_target(target, expected):
    assert parse_target(target) == expected


@pytest.mark.parametrize("bad", ["", "celltype.info", "https://celltype.info/project/1030",
                                 "not a url"])
def test_parse_target_rejects(bad):
    with pytest.raises(CapError):
        parse_target(bad)


def test_page_url():
    assert dataset_page_url("1030", "3400") == \
        "https://celltype.info/project/1030/dataset/3400"


def test_page_url_needs_project():
    # A bare dataset id parses, but cannot locate the page the labelsets live on.
    with pytest.raises(CapError, match="not enough to locate the page"):
        dataset_page_url(None, "3400")
