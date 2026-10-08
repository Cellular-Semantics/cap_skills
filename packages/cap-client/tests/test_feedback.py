"""Feedback parsing. No network, and no real person's name in any fixture:
the pages here are constructed, the way test_labelsets.py constructs its own."""
import json

import pytest

from cap_client.errors import CapError
from cap_client.feedback import (
    fetch_feedback,
    parse_feedback,
    summarise,
    with_feedback,
)


def label(name, label_id="1", count=100, agree=0, disagree=0, idk=0, feedbacks=()):
    return {
        "__typename": "Label", "feedbacks": list(feedbacks), "id": label_id,
        "name": name,
        "scores": {"__typename": "LabelScores",
                   "agree": agree, "disagree": disagree, "idk": idk},
        "count": count,
    }


def entry(kind, user="A. Curator", **data):
    return {
        "__typename": "LabelFeedback", "createdAt": "2026-10-08T09:00:00.000Z",
        "user": {"__typename": "CapUser", "uid": "u1", "displayName": user,
                 "orcidId": "0000-0002-1825-0097", "institution": "Somewhere",
                 "email": "should.not.appear@example.org"},
        "explanation": {"__typename": "LabelFeedbackExplanation",
                        "type": kind, "data": {"__typename": "D", **data}},
    }


def page(labelset_name, *labels):
    """A feedback page as CAP serves it: JSON inside a JS string literal."""
    body = (f'{{"__typename":"Labelset","name":"{labelset_name}","labels":['
            + ",".join(json.dumps(lb, separators=(",", ":")) for lb in labels)
            + "]}")
    return ('<html><script>self.__next_f.push([1,"'
            + body.replace("\\", "\\\\").replace('"', '\\"')
            + '"])</script></html>')


def test_parses_labels_with_and_without_feedback():
    got = parse_feedback(page("author_cell_type",
                              label("Quiet", label_id="1"),
                              label("Noisy", label_id="2", disagree=1,
                                    feedbacks=[entry("disagree", comment="Wrong branch.")])))
    assert [lb["label"] for lb in got] == ["Quiet", "Noisy"]
    assert all(lb["labelset"] == "author_cell_type" for lb in got)
    assert got[0]["feedbacks"] == []
    assert got[1]["feedbacks"][0]["comment"] == "Wrong branch."


def test_email_is_never_passed_through():
    got = parse_feedback(page("ls", label("X", feedbacks=[entry("agree")])))
    user = got[0]["feedbacks"][0]["user"]
    assert user["displayName"] == "A. Curator"
    assert user["orcidId"] == "0000-0002-1825-0097"
    assert "email" not in user
    assert "example.org" not in json.dumps(got)


def test_refine_keeps_before_and_after():
    fb = entry("refine", changes=[
        {"attribute": "ontologyTermId", "originalValue": "CL:0000057",
         "newValue": "CL:7770003"}])
    got = parse_feedback(page("ls", label("BeamA", feedbacks=[fb])))
    assert got[0]["feedbacks"][0]["changes"] == [
        {"attribute": "ontologyTermId", "from": "CL:0000057", "to": "CL:7770003"}]


def test_split_keeps_proposed_labels():
    fb = entry("split", labels=[{"name": "Sub A", "markerGenes": ["AAA", "BBB"]}])
    got = parse_feedback(page("ls", label("Broad", feedbacks=[fb])))
    assert got[0]["feedbacks"][0]["proposed_labels"] == [
        {"name": "Sub A", "marker_genes": ["AAA", "BBB"]}]


def test_pointer_strings_do_not_crash_the_parse():
    """Flight payloads dedupe repeated objects into '$...' pointers."""
    fb = {"__typename": "LabelFeedback", "createdAt": "2026-10-08T09:00:00.000Z",
          "user": "$12:props:user",
          "explanation": {"type": "agree", "data": {"comment": "Fine."}}}
    got = parse_feedback(page("ls", label("X", feedbacks=[fb])))
    assert got[0]["feedbacks"][0]["user"] is None
    assert got[0]["feedbacks"][0]["comment"] == "Fine."


def test_scores_are_independent_of_explanations():
    """A refine carries no score, so a corrected label still reads 0/0/0.
    Never rank labels by score alone."""
    got = parse_feedback(page("ls", label("X", feedbacks=[entry("refine")])))
    lb = got[0]
    assert (lb["agree"], lb["disagree"], lb["idk"]) == (0, 0, 0)
    assert with_feedback(got) == [lb]          # still selected, via feedbacks


def test_with_feedback_filters_but_parse_does_not():
    got = parse_feedback(page("ls", label("Quiet"),
                              label("Scored", label_id="2", agree=2)))
    assert len(got) == 2
    assert [lb["label"] for lb in with_feedback(got)] == ["Scored"]


def test_empty_parse_raises_rather_than_reporting_no_feedback():
    """The failure this guards: CAP serves the shell without its payload, and a
    silent empty result is indistinguishable from a dataset with no feedback."""
    with pytest.raises(CapError, match="No labels parsed"):
        fetch_feedback("1", "3400", fetch_page=lambda url: "<html></html>", attempts=1)


def test_empty_parse_is_retried_before_giving_up():
    calls = []

    def flaky(url):
        calls.append(url)
        return "<html></html>" if len(calls) < 3 else page("ls", label("X"))

    got = fetch_feedback("1", "3400", fetch_page=flaky, attempts=3, sleep=lambda s: None)
    assert [lb["label"] for lb in got] == ["X"]
    assert len(calls) == 3


def test_fetch_requests_the_feedback_tab():
    seen = {}

    def spy(url):
        seen["url"] = url
        return page("ls", label("X"))

    fetch_feedback("1030", "3400", fetch_page=spy)
    assert seen["url"] == "https://celltype.info/project/1030/dataset/3400/feedback"


def test_summarise_is_flat_and_names_contributors():
    got = parse_feedback(page("ls", label("X", count=42, disagree=1,
                                          feedbacks=[entry("disagree", comment="No.")])))
    row, = summarise(got, "3400")
    assert row["dataset_id"] == "3400"
    assert row["label"] == "X"
    assert row["count"] == 42
    assert row["types"] == "disagree"
    assert row["users"] == "A. Curator"
