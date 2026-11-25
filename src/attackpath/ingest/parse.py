"""Turn one raw file into clean, citation-ready pages."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import trafilatura
from pypdf import PdfReader

TEXT_TYPES = {".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc", ".sgml", ".py"}
DATA_TYPES = {".json", ".yaml", ".yml", ".csv", ".xml"}
PAGE_CHARS = 3000
MIN_CHARS_PER_PAGE = 50
HEADING = re.compile(r"^(#{1,6}) +(.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass
class ParsedPage:
    page_no: int
    text: str
    headings: list[str] = field(default_factory=list)
    tables: int = 0


@dataclass
class ParsedDoc:
    parser: str
    kind: str
    title: str
    pages: list[ParsedPage]
    scanned_pages: list[int] = field(default_factory=list)


class ParseError(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail[:500]


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\x00", "").replace("­", "")
    text = re.sub(r"(?<=[a-z])-\n(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def drop_repeated_lines(pages: list[str]) -> list[str]:
    if len(pages) < 4:
        return pages

    def key(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip().lower())

    seen: Counter[str] = Counter()
    for page in pages:
        lines = [line for line in page.splitlines() if line.strip()]
        seen.update(key(line) for line in lines[:2] + lines[-2:] if not line.startswith("#"))
    repeated = {name for name, count in seen.items() if count >= 0.6 * len(pages)}
    result = []
    for page in pages:
        lines = page.splitlines()
        edge = {i for i, line in enumerate(lines) if line.strip()}
        edge = set(sorted(edge)[:2] + sorted(edge)[-2:])
        result.append(
            "\n".join(
                line for i, line in enumerate(lines) if not (i in edge and key(line) in repeated)
            )
        )
    return result


def heading_title(raw: str) -> str:
    return re.sub(r"\s*\{\s*[#.][^}]*\}\s*$", "", raw).strip()


def headings_in(text: str, in_code: bool = False) -> tuple[list[tuple[int, str]], bool]:
    found = []
    for line in text.splitlines():
        if FENCE.match(line):
            in_code = not in_code
        elif not in_code and (match := HEADING.match(line)):
            found.append((len(match.group(1)), heading_title(match.group(2))))
    return found, in_code


def with_heading_paths(texts: list[str]) -> list[ParsedPage]:
    pages, path, in_code = [], [], False
    for number, text in enumerate(texts, 1):
        pages.append(ParsedPage(number, text, list(path), text.count("\n|---")))
        found, in_code = headings_in(text, in_code)
        for level, title in found:
            path = path[: level - 1] + [title]
    return pages


def split_pages(text: str, size: int = PAGE_CHARS) -> list[str]:
    pages, current, length = [], [], 0
    for para in re.split(r"\n\s*\n", text):
        if current and length + len(para) > size:
            pages.append("\n\n".join(current))
            current, length = [], 0
        current.append(para)
        length += len(para)
    return pages + (["\n\n".join(current)] if current else [])


def finish(parser: str, kind: str, title: str, texts: list[str]) -> ParsedDoc:
    texts = [clean_text(t) for t in drop_repeated_lines(texts)]
    if not any(texts):
        raise ParseError("empty", "no text after cleaning")
    found, _ = headings_in("\n".join(texts))
    return ParsedDoc(parser, kind, found[0][1] if found else title, with_heading_paths(texts))


def _open_pdf(path: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc
    if doc.needs_pass:
        raise ParseError("encrypted", "the PDF needs a password")
    if doc.page_count == 0:
        raise ParseError("empty", "the PDF has no pages")
    return doc


def _body_size(doc: pymupdf.Document) -> float:
    sizes: Counter[float] = Counter()
    for page in list(doc)[:30]:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"])
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _heading_level(text: str, size: float, bold: bool, body: float) -> int:
    if not 2 < len(text) <= 120 or not any(char.isalpha() for char in text):
        return 0
    if size >= body * 1.6:
        return 1
    if size >= body * 1.3:
        return 2
    if size >= body * 1.12 or (bold and len(text) <= 80 and not text.endswith((".", ",", ";"))):
        return 3
    return 0


def parse_pdf_pymupdf(path: Path) -> ParsedDoc:
    doc, body, texts, chars, scanned = _open_pdf(path), 0.0, [], 0, []
    body = _body_size(doc)
    for page_no, page in enumerate(doc, 1):
        tables = list(page.find_tables().tables) if len(page.get_cdrawings()) >= 4 else []
        used, out = set(), []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            rect = pymupdf.Rect(block["bbox"])
            inside = next(
                (i for i, table in enumerate(tables) if rect.intersects(table.bbox)), None
            )
            if inside is not None:
                if inside not in used:
                    used.add(inside)
                    out.append("\n" + tables[inside].to_markdown().strip() + "\n")
                continue
            for line in block["lines"]:
                value = "".join(span["text"] for span in line["spans"]).strip()
                if not value:
                    continue
                size = max(span["size"] for span in line["spans"])
                bold = all(span["flags"] & 16 for span in line["spans"])
                level = _heading_level(value, size, bold, body)
                out.append(f"{'#' * level} {value}" if level else value)
                chars += len(value)
            out.append("")
        page_chars = sum(
            len("".join(span["text"] for span in line["spans"]))
            for block in page.get_text("dict")["blocks"]
            if block["type"] == 0
            for line in block["lines"]
        )
        if page_chars < MIN_CHARS_PER_PAGE:
            scanned.append(page_no)
        texts.append("\n".join(out))
    if scanned and len(scanned) == len(texts):
        raise ParseError("no_text_layer", f"all {len(texts)} pages need OCR")
    result = finish("pymupdf", "pdf", (doc.metadata or {}).get("title") or "", texts)
    result.scanned_pages = scanned
    return result


def parse_pdf_ocr(path: Path, language: str = "eng") -> ParsedDoc:
    doc = _open_pdf(path)
    try:
        texts = [
            page.get_text(textpage=page.get_textpage_ocr(language=language, dpi=200, full=True))
            for page in doc
        ]
    except Exception as exc:
        raise ParseError("ocr_unavailable", str(exc)) from exc
    return finish(f"ocr-{language}", "pdf", "", texts)


def parse_pdf_pypdf(path: Path) -> ParsedDoc:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ParseError("encrypted", "the PDF needs a password")
        texts = [page.extract_text() or "" for page in reader.pages]
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc
    if not texts:
        raise ParseError("empty", "the PDF has no pages")
    if sum(len(text) for text in texts) < MIN_CHARS_PER_PAGE * len(texts):
        raise ParseError("no_text_layer", f"almost no text on {len(texts)} pages: needs OCR")
    return finish("pypdf", "pdf", "", texts)


def parse_html(path: Path) -> ParsedDoc:
    html = path.read_text(encoding="utf-8", errors="replace")
    markdown = trafilatura.extract(html, output_format="markdown", include_tables=True)
    if not markdown or len(markdown) < 40:
        raise ParseError("empty", "no main content found")
    meta = trafilatura.extract_metadata(html)
    title = (meta.title if meta else "") or path.stem
    return finish("trafilatura", "html", title, split_pages(f"# {title}\n\n{markdown}"))


RST_MARKS = {"=": 1, "-": 2, "~": 3, "^": 3, '"': 3}


def markup_to_markdown(text: str, suffix: str) -> str:
    lines = text.splitlines()
    if suffix == ".adoc":
        return "\n".join(
            re.sub(r"^(=+) ", lambda m: "#" * len(m.group(1)) + " ", line) for line in lines
        )
    if suffix not in {".rst", ".txt"}:
        return text
    out = []
    for i, line in enumerate(lines):
        under = lines[i + 1] if i + 1 < len(lines) else ""
        is_rule = len(under) >= 3 and len(set(under)) == 1 and under[0] in RST_MARKS
        if line.strip() and is_rule and len(under) >= len(line.rstrip()):
            out.append("#" * RST_MARKS[under[0]] + " " + line.strip())
        elif not (out and len(line) >= 3 and len(set(line)) == 1 and line[0] in RST_MARKS):
            out.append(line)
    return "\n".join(out)


def parse_text(path: Path) -> ParsedDoc:
    text = path.read_text(encoding="utf-8", errors="replace")
    kind = "data" if path.suffix.lower() in DATA_TYPES else "text"
    return finish(
        "plain",
        kind,
        path.stem if kind == "data" else "",
        split_pages(markup_to_markdown(text, path.suffix.lower())),
    )


PDF_PARSERS = {"pymupdf": parse_pdf_pymupdf, "pypdf": parse_pdf_pypdf}


def parse_file(path: Path, pdf_parser: str = "pymupdf") -> ParsedDoc:
    try:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return PDF_PARSERS[pdf_parser](path)
        if suffix in {".html", ".htm"}:
            return parse_html(path)
        if suffix in TEXT_TYPES | DATA_TYPES:
            return parse_text(path)
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("crash", f"{type(exc).__name__}: {exc}") from exc
    raise ParseError("unsupported_type", suffix or "no file extension")
