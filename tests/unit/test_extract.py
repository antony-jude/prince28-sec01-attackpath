import pytest
from pydantic import ValidationError

from attackpath.llm.doc_meta import DocMeta
from attackpath.llm.extract import parse_json


def test_parse_json_accepts_fenced_reply():
    assert parse_json('```json {"x": 1} ```') == {"x": 1}


def test_parse_json_rejects_non_object():
    with pytest.raises(ValueError):
        parse_json("[1, 2]")


def test_doc_meta_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        DocMeta(
            doc_kind="other",
            language="en",
            summary="A sufficiently long summary here.",
            topics=["x"],
            unknown="x",
        )


def test_doc_meta_normalizes_topics():
    item = DocMeta(
        doc_kind="guideline",
        language="en",
        summary="A sufficiently long summary here.",
        topics=["ATT&CK", "att&ck"],
    )
    assert item.topics == ["att&ck"]


def test_doc_meta_limits_lists():
    with pytest.raises(ValidationError):
        DocMeta(
            doc_kind="other",
            language="en",
            summary="A sufficiently long summary here.",
            topics=["x"],
            name=[str(i) for i in range(9)],
        )


def test_doc_meta_year_range():
    with pytest.raises(ValidationError):
        DocMeta(
            doc_kind="other",
            language="en",
            summary="A sufficiently long summary here.",
            topics=["x"],
            year=1900,
        )


def test_doc_meta_requires_topic():
    with pytest.raises(ValidationError):
        DocMeta(
            doc_kind="other", language="en", summary="A sufficiently long summary here.", topics=[]
        )


def test_doc_meta_valid_record():
    item = DocMeta(
        doc_kind="reference",
        language="en",
        summary="A sufficiently long summary here.",
        topics=["attack"],
    )
    assert item.technique_id == []
