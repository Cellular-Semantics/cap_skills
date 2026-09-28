import random

import pytest

from cap_client.errors import CapError
from cap_client.session import blank_label, create_session, new_session_id
from conftest import LABELSET, SESSION_OK, TISSUE_LABELSET, FakeClient, errors


def test_session_id_shape():
    sid = new_session_id(random.Random(0))
    assert len(sid) == 21
    assert all(c.isalnum() or c in "-_" for c in sid)


def test_blank_label_keeps_only_load_bearing_fields():
    lb = blank_label({"id": 3, "name": "Rare Cells", "count": 3, "color": None,
                      "markerGenes": ["POU2F3"], "rationale": "should not be sent"})
    assert lb["id"] == 3 and lb["name"] == "Rare Cells" and lb["count"] == 3
    assert lb["color"] == "#000000", "a null colour must be filled in, not passed through"
    assert lb["markerGenes"] == [] and lb["rationale"] is None


def test_create_session_registers_every_labelset():
    client = FakeClient({"CreateDatasetSession": SESSION_OK})
    sid, cells = create_session(client, "3400", [LABELSET, TISSUE_LABELSET])
    (op, variables), = client.calls
    assert op == "CreateDatasetSession"
    sent = variables["data"]["dataset"]["labelsets"]
    assert [ls["name"] for ls in sent] == ["hgca_celltype_v1", "tissue"]
    assert [ls["order"] for ls in sent] == [1, 2]
    assert variables["data"]["sessionId"] == sid
    # cellCount is the max across labelsets, not the sum: each labelset covers
    # the same cells.
    assert cells == 153


def test_create_session_sends_all_labels_not_a_subset():
    client = FakeClient({"CreateDatasetSession": SESSION_OK})
    create_session(client, "3400", [LABELSET])
    labels = client.calls[0][1]["data"]["dataset"]["labelsets"][0]["labels"]
    assert len(labels) == 3


def test_create_session_surfaces_server_error():
    client = FakeClient({"CreateDatasetSession": errors("bad input")})
    with pytest.raises(CapError, match="CreateDatasetSession failed"):
        create_session(client, "3400", [LABELSET])


def test_create_session_needs_a_labelset():
    with pytest.raises(CapError):
        create_session(FakeClient({}), "3400", [])
