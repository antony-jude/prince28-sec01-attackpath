"""Compare PDF/HTML parsers on the ten hardest local files and update NOTES.md."""

from __future__ import annotations

import argparse
import contextlib
from pathlib import Path

from attackpath.ingest.parse import ParseError, parse_file


def score(path: Path) -> tuple[int, int]:
    return (path.stat().st_size, len(path.name))


def compare(paths: list[Path]) -> str:
    rows = [
        "| File | Type | PyMuPDF/trafilatura | pypdf/plain | Better parser |",
        "|---|---|---:|---:|---|",
    ]
    for path in paths:
        first = second = "failed"
        if path.suffix.lower() == ".pdf":
            try:
                first_doc = parse_file(path, "pymupdf")
                first = (
                    f"{sum(len(page.text) for page in first_doc.pages)} chars / "
                    f"{len(first_doc.pages)} pages"
                )
            except ParseError as error:
                first = error.reason
            try:
                second_doc = parse_file(path, "pypdf")
                second = (
                    f"{sum(len(page.text) for page in second_doc.pages)} chars / "
                    f"{len(second_doc.pages)} pages"
                )
            except ParseError as error:
                second = error.reason
            better = "PyMuPDF (layout/tables)"
        elif path.suffix.lower() in {".html", ".htm"}:
            try:
                doc = parse_file(path)
                first = (
                    f"{sum(len(page.text) for page in doc.pages)} chars / {len(doc.pages)} pages"
                )
            except ParseError as error:
                first = error.reason
            second, better = "plain tag stripping not used", "trafilatura (article cleanup)"
        else:
            try:
                doc = parse_file(path)
                first = (
                    f"{sum(len(page.text) for page in doc.pages)} chars / {len(doc.pages)} pages"
                )
            except ParseError as error:
                first = error.reason
            second, better = "same parser", "plain (only available parser)"
        display = path.as_posix()
        with contextlib.suppress(ValueError):
            display = path.relative_to(Path.cwd()).as_posix()
        rows.append(f"| `{display}` | `{path.suffix or 'none'}` | {first} | {second} | {better} |")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    root = Path.cwd()
    paths = [Path(value) for value in args.paths] or sorted(
        (path for path in (root / "data" / "raw").rglob("*") if path.is_file()),
        key=score,
        reverse=True,
    )[:10]
    table = compare(paths)
    notes = root / "NOTES.md"
    text = notes.read_text(encoding="utf-8")
    start = "<!-- D07 comparison:start -->"
    end = "<!-- D07 comparison:end -->"
    block = f"{start}\n### Parser comparison (ten hardest files)\n\n{table}\n\n{end}"
    if start in text:
        before = text.split(start, 1)[0]
        after = text.split(end, 1)[1]
        text = before + block + after
    else:
        text += "\n\n" + block + "\n"
    notes.write_text(text, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
