"""Dataset sessions.

CAP will not compute DE, or serve embedding data, for a labelset it has not seen
registered in a session. The sessionId is client-generated (nanoid-style); the
server takes our word for it.
"""
from __future__ import annotations

import json
import random
import string

from .errors import CapError
from .queries import Q_CREATE_SESSION

_ALPHABET = string.ascii_letters + string.digits + "-_"


def new_session_id(rng: random.Random | None = None) -> str:
    return "".join((rng or random).choices(_ALPHABET, k=21))


def blank_label(lb: dict) -> dict:
    """The full Label shape CreateDatasetSession demands.

    Only id/name/count/color are load-bearing for DE and expression, so
    everything else is sent as nulls rather than round-tripped.
    """
    return {"id": lb["id"], "name": lb["name"], "count": lb.get("count", 0),
            "color": lb.get("color") or "#000000",
            "ontologyTermExists": None, "ontologyTerm": None, "ontologyTermId": None,
            "fullName": None, "categoryOntologyTermExists": None,
            "categoryOntologyTerm": None, "categoryOntologyTermId": None,
            "categoryFullName": None, "markerGenes": [], "negativeMarkerGenes": None,
            "canonicalMarkerGenes": None, "synonyms": [], "rationale": None,
            "rationaleDois": None, "ontologyAssessment": None, "averageConfScore": None}


def _labelset_payload(ls: dict, order: int) -> dict:
    return {"id": ls["id"], "order": order, "status": "parsed",
            "mode": ls.get("mode") or "cell-labels", "name": ls["name"],
            "description": None, "annotationMethod": "manual",
            "algorithmName": "NA", "algorithmVersion": "NA", "algorithmRepoUrl": "NA",
            "referenceLocation": "NA", "referenceDescription": "NA",
            "labels": [blank_label(lb) for lb in ls["labels"]]}


def create_session(client, dataset_id: str, labelsets: list[dict],
                   session_id: str | None = None) -> tuple[str, int]:
    """Register a session covering `labelsets`. Returns (session_id, cell_count).

    Every labelset that will be queried -- the primary one and any cross-tab
    labelsets -- must be registered here. The labelsets must be passed WHOLE:
    the server computes DE against the entire dataset, so restricting to a few
    cell types is a matter of what you ask for afterwards, not what you register.
    """
    if not labelsets:
        raise CapError("create_session needs at least one labelset.")
    session_id = session_id or new_session_id()
    cell_count = max(sum(lb.get("count", 0) for lb in ls["labels"]) for ls in labelsets)
    data = {"sessionId": session_id,
            "dataset": {"id": dataset_id, "name": "x", "description": "x",
                        "datasetType": "integrated", "defaultEmbedding": None,
                        "cellCount": cell_count, "geneCount": 0,
                        "labelsets": [_labelset_payload(ls, i + 1)
                                      for i, ls in enumerate(labelsets)]}}
    r = client.call("CreateDatasetSession", {"data": data}, Q_CREATE_SESSION)
    if r.get("errors"):
        raise CapError(f"CreateDatasetSession failed: {json.dumps(r['errors'])[:400]}")
    return session_id, cell_count
