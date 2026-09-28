import io
import json
import urllib.error

import pytest

from cap_client.errors import CapError
from cap_client.transport import GraphQLClient, first_error


def test_first_error():
    assert first_error({"data": {}}) is None
    assert first_error({"errors": [{"message": "boom"}]}) == "boom"
    assert first_error({"errors": [{"message": "boom"}]}, "Selection") == "Selection: boom"
    assert first_error({"errors": [{"message": "x" * 300}]}, limit=5) == "xxxxx"


def make_client(monkeypatch, responses, **kw):
    """Replace urlopen with a scripted sequence of payloads or exceptions."""
    calls = []
    seq = iter(responses)

    def fake_urlopen(req, context=None, timeout=None):
        calls.append(json.loads(req.data))
        item = next(seq)
        if isinstance(item, Exception):
            raise item
        body = io.BytesIO(json.dumps(item).encode())
        body.__enter__ = lambda: body
        body.__exit__ = lambda *a: False
        return body

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return GraphQLClient(min_interval=0, log=lambda m: None, **kw), calls


def test_call_sends_operation_name_and_client_headers(monkeypatch):
    client, calls = make_client(monkeypatch, [{"data": {"ok": True}}])
    assert client.call("Op", {"a": 1}, "query Op { x }") == {"data": {"ok": True}}
    assert calls[0]["operationName"] == "Op"
    assert calls[0]["variables"] == {"a": 1}
    assert calls[0]["query"] == "query Op { x }"
    assert calls[0]["extensions"]["clientLibrary"]["name"] == "@apollo/client"
    assert client.n_requests == 1


def http_error(code):
    return urllib.error.HTTPError("u", code, "msg", {}, io.BytesIO(b"server said no"))


def test_retries_then_succeeds_on_503(monkeypatch):
    client, calls = make_client(monkeypatch, [http_error(503), {"data": {"ok": True}}])
    assert client.call("Op", {}, "q")["data"]["ok"] is True
    assert len(calls) == 2


def test_gives_up_after_the_attempt_budget(monkeypatch):
    client, calls = make_client(monkeypatch, [http_error(503)] * 4)
    with pytest.raises(CapError, match="HTTP 503"):
        client.call("Op", {}, "q")
    assert len(calls) == 4


def test_does_not_retry_a_400(monkeypatch):
    # QUERY_NOT_IN_SAFELIST arrives as a 400: retrying cannot help.
    client, calls = make_client(monkeypatch, [http_error(400)])
    with pytest.raises(CapError, match="server said no"):
        client.call("Op", {}, "q")
    assert len(calls) == 1


def test_network_error_retried(monkeypatch):
    client, calls = make_client(
        monkeypatch, [urllib.error.URLError("down"), {"data": {"ok": True}}])
    client.call("Op", {}, "q")
    assert len(calls) == 2


def test_graphql_errors_are_returned_not_raised(monkeypatch):
    # Several callers read GraphQL errors as signal (a missing precomputed DE,
    # the obs-column probe), so they must survive the transport intact.
    client, _calls = make_client(monkeypatch, [{"errors": [{"message": "nope"}]}])
    assert client.call("Op", {}, "q")["errors"][0]["message"] == "nope"


def test_pacing_waits_between_calls(monkeypatch):
    slept = []
    client, _calls = make_client(monkeypatch, [{"data": {}}, {"data": {}}])
    client.min_interval = 0.5
    monkeypatch.setattr("time.sleep", slept.append)
    monkeypatch.setattr("time.monotonic", lambda: 100.0)  # no time passes between calls
    client.call("Op", {}, "q")
    client.call("Op", {}, "q")
    assert slept and slept[-1] == pytest.approx(0.5)
