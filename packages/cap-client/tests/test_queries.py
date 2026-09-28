"""The safelist bodies are load-bearing: CAP rejects anything it does not
recognise byte-for-byte. These tests catch a reformat, not a CAP redeploy."""
import hashlib

from cap_client import queries

#: sha256 of each body as captured from CAP's web client. If a change to
#: queries.py is deliberate, update these together and note why.
EXPECTED = {
    "Q_CREATE_SESSION": "61d54e7cffde38af6542ed036a97f64ca7a22b876acd4cc2d5d9dc045af3847f",
}


def test_all_queries_registered():
    names = {n for n in dir(queries) if n.startswith("Q_")}
    bodies = set(queries.ALL.values())
    assert len(queries.ALL) == len(names)
    assert all(getattr(queries, n) in bodies for n in names)


def test_operation_name_matches_body():
    for op, body in queries.ALL.items():
        assert body.startswith((f"query {op}(", f"mutation {op}(")), op


def test_typename_on_every_selection_set():
    # Apollo appends __typename to every non-root selection set; dropping one
    # breaks the safelist match.
    for op, body in queries.ALL.items():
        closes = [line for line in body.split("\n")
                  if line.strip() == "}" and line.startswith("  ")]
        assert body.count("__typename") >= len(closes), op


def test_no_trailing_whitespace_or_newline():
    for op, body in queries.ALL.items():
        assert body == body.rstrip(), op
        assert "\t" not in body, op


def test_create_session_digest_stable():
    got = hashlib.sha256(queries.Q_CREATE_SESSION.encode()).hexdigest()
    assert got == EXPECTED["Q_CREATE_SESSION"], (
        "Q_CREATE_SESSION changed. If deliberate, update EXPECTED; if not, this is "
        "the reformat that would have produced QUERY_NOT_IN_SAFELIST.")
