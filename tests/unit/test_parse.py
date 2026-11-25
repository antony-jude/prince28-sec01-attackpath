from pathlib import Path

import pymupdf
import pytest

from attackpath.ingest.parse import (
    ParseError,
    clean_text,
    drop_repeated_lines,
    headings_in,
    markup_to_markdown,
    parse_file,
    parse_pdf_pymupdf,
    parse_pdf_pypdf,
    split_pages,
    with_heading_paths,
)


def pdf_file(tmp_path: Path, pages: list[str]) -> Path:
    path = tmp_path / "guide.pdf"
    doc = pymupdf.open()
    for value in pages:
        page = doc.new_page()
        page.insert_text((72, 72), value)
    doc.save(path)
    return path


def test_clean_text_normalizes_unicode_and_soft_hyphen():
    assert clean_text("ﬁeld-\u00ad\nwork") == "fieldwork"


def test_clean_text_collapses_excess_blank_lines():
    assert clean_text("a\n\n\n\nb") == "a\n\nb"


def test_headings_skip_fenced_code():
    found, _ = headings_in("# Real\n```\n# Code\n```\n## Child")
    assert found == [(1, "Real"), (2, "Child")]


def test_heading_paths_continue_between_pages():
    pages = with_heading_paths(["# Fever\nintro", "details\n## Dengue", "more"])
    assert pages[0].headings == []
    assert pages[1].headings == ["Fever"]
    assert pages[2].headings == ["Fever", "Dengue"]


def test_split_pages_respects_paragraph_boundaries():
    assert len(split_pages("a\n\nb\n\nc", size=1)) == 3


def test_markup_to_markdown_converts_adoc():
    assert markup_to_markdown("= Title\ntext", ".adoc") == "# Title\ntext"


def test_markup_to_markdown_converts_rst():
    assert markup_to_markdown("Title\n=====\ntext", ".rst") == "# Title\ntext"


def test_drop_repeated_lines_removes_headers():
    pages = [f"Guide\nbody {i}\nPage {i}" for i in range(5)]
    result = drop_repeated_lines(pages)
    assert all("Guide" not in page for page in result)


def test_pymupdf_extracts_pdf_pages_and_headings(tmp_path):
    path = pdf_file(tmp_path, ["Guide\nThis is enough text " * 5, "More text " * 20])
    doc = parse_pdf_pymupdf(path)
    assert doc.parser == "pymupdf"
    assert len(doc.pages) == 2


def test_pypdf_extracts_pdf(tmp_path):
    path = pdf_file(tmp_path, ["A useful document " * 10])
    assert parse_pdf_pypdf(path).parser == "pypdf"


def test_pdf_with_no_text_layer_is_reported(tmp_path):
    path = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(path)
    with pytest.raises(ParseError, match="no_text_layer"):
        parse_file(path)


def test_corrupt_pdf_is_reported(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(ParseError, match="corrupt"):
        parse_file(path)


def test_parse_text_has_pages(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# Notes\n\nhello", encoding="utf-8")
    doc = parse_file(path)
    assert doc.pages[0].text.startswith("# Notes")


def test_parse_json_is_data(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    assert parse_file(path).kind == "data"


def test_unsupported_type(tmp_path):
    path = tmp_path / "archive.zip"
    path.write_bytes(b"PK")
    with pytest.raises(ParseError, match="unsupported_type"):
        parse_file(path)


def test_empty_html_is_reported(tmp_path):
    path = tmp_path / "empty.html"
    path.write_text("<html><script>x</script></html>", encoding="utf-8")
    with pytest.raises(ParseError, match="empty"):
        parse_file(path)


def test_pdf_parser_choice_is_explicit(tmp_path):
    path = pdf_file(tmp_path, ["Readable PDF " * 10])
    assert parse_file(path, "pypdf").parser == "pypdf"
