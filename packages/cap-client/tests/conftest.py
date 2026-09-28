"""Shared fakes. No test in this package touches the network."""
from __future__ import annotations

import pytest

LABELSET = {
    "id": "77", "name": "hgca_celltype_v1", "mode": "cell-labels",
    "labels": [
        {"id": 1, "name": "Tuft Cells", "count": 100, "color": "#111111"},
        {"id": 2, "name": "Tuft Progenitors", "count": 50, "color": "#222222"},
        {"id": 3, "name": "Rare Cells", "count": 3, "color": None},
    ],
}

TISSUE_LABELSET = {
    "id": "78", "name": "tissue", "mode": "obs",
    "labels": [
        {"id": 10, "name": "small intestine", "count": 90, "color": "#333333"},
        {"id": 11, "name": "colon", "count": 60, "color": "#444444"},
    ],
}

LABELSETS = {"77": LABELSET, "78": TISSUE_LABELSET}


def gene(name, logfc, score, pvalue=0.001):
    return {"name": name, "logFoldChange": logfc, "score": score, "pValue": pvalue}


def de_payload(genes):
    return {"data": {"datasetSession": {"id": "s",
            "diffGenesBySelection": [{"genes": genes}]}}}


def errors(message):
    return {"errors": [{"message": message}]}


class FakeClient:
    """Stands in for GraphQLClient: dispatches on operation name.

    Handlers are callables taking the variables dict and returning a payload, or
    plain payloads for operations answered the same way every time.
    """

    def __init__(self, handlers: dict):
        self.handlers = handlers
        self.calls: list[tuple[str, dict]] = []

    def call(self, op, variables, query):
        assert query, f"{op} was called with an empty query body"
        self.calls.append((op, variables))
        try:
            h = self.handlers[op]
        except KeyError:  # pragma: no cover - a test asked for something unstubbed
            raise AssertionError(f"unstubbed operation: {op}") from None
        return h(variables) if callable(h) else h

    def ops(self) -> list[str]:
        return [op for op, _ in self.calls]


SESSION_OK = {"data": {"saveDatasetSession": {"id": "s"}}}


@pytest.fixture
def labelset():
    import copy
    return copy.deepcopy(LABELSET)


@pytest.fixture
def tissue_labelset():
    import copy
    return copy.deepcopy(TISSUE_LABELSET)
