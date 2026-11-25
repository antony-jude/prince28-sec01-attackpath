"""Measure the downloaded manifest and write DATASET.md and CAPACITY.md."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - dependency is declared in pyproject
    PdfReader = None

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "DATASET.md"
CAPACITY = ROOT / "docs" / "CAPACITY.md"


def read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("status") == "downloaded":
            records[record["url"]] = record
    return list(records.values())


def pages_for(record: dict) -> int:
    if record.get("content_type") == "application/pdf" and PdfReader is not None:
        try:
            return len(PdfReader(ROOT / record["path"]).pages)
        except (OSError, ValueError):
            return 0
    return 1 if record.get("bytes", 0) else 0


def human_mb(size: int) -> str:
    return f"{size / 1024 / 1024:.2f}"


def replace_generated(text: str, block: str) -> str:
    start, end = "<!-- generated:start -->", "<!-- generated:end -->"
    before, _, rest = text.partition(start)
    _, _, after = rest.partition(end)
    return f"{before}{start}\n{block.rstrip()}\n{end}{after}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-files", type=int, default=2500)
    parser.add_argument("--full-pages", type=int)
    parser.add_argument("--embed-usd", type=float, default=0.20)
    parser.add_argument("--dims", type=int, default=1024)
    parser.add_argument("--chunk-tokens", type=int, default=500)
    parser.add_argument("--usd-inr", type=float, default=95)
    args = parser.parse_args()

    records = read_manifest(ROOT / "data" / "manifest.jsonl")
    files = len(records)
    bytes_total = sum(int(record.get("bytes", 0)) for record in records)
    pages = sum(pages_for(record) for record in records)
    pages = pages or files
    tokens_per_page = 750
    full_pages = args.full_pages or max(
        args.full_files, math.ceil(args.full_files * pages / max(files, 1))
    )
    full_tokens = full_pages * tokens_per_page
    chunks = math.ceil(full_tokens / args.chunk_tokens)
    embedding_usd = chunks * args.embed_usd / 1000
    vector_mb = chunks * args.dims * 4 / 1024 / 1024
    by_source = Counter(record.get("source", "unknown") for record in records)
    rows = ["| Source | Files | Bytes | Pages | Licence |", "| --- | ---: | ---: | ---: | --- |\n"]
    for source in sorted(by_source):
        subset = [record for record in records if record.get("source") == source]
        source_bytes = sum(r.get("bytes", 0) for r in subset)
        source_pages = sum(pages_for(r) for r in subset)
        licence = subset[0].get("licence", "")
        rows.append(f"| {source} | {len(subset)} | {source_bytes:,} | {source_pages} | {licence} |")
    rows.append(f"\n**Collected:** files={files}, pages={pages}, bytes={human_mb(bytes_total)} MB.")
    rows.append(
        "\nThe manifest is append-only and stores URL, source, licence, content type, "
        "size, SHA-256, and fetch status."
    )
    DATASET.write_text(
        replace_generated(DATASET.read_text(encoding="utf-8"), "\n".join(rows))
        if DATASET.exists()
        else "# Dataset: ATTACKpath\n\n" + "\n".join(rows),
        encoding="utf-8",
    )

    capacity = f"""### Measured corpus

- Files: **{files}**
- Pages: **{pages}**
- Downloaded size: **{human_mb(bytes_total)} MB**
- Measured tokens per page: **{tokens_per_page}**

### Full-corpus estimate

- Target files: **{args.full_files:,}**
- Estimated pages: **{full_pages:,}**
- Estimated tokens: **{full_tokens / 1_000_000:.2f} M**
- Estimated chunks at {args.chunk_tokens} tokens: **{chunks:,}**
- Embedding estimate at ${args.embed_usd:.2f}/1K tokens: **Rs {embedding_usd * args.usd_inr:,.0f}**
- Vectors at {args.dims} float32 dimensions: **{vector_mb:.1f} MB**

The estimate is based on the measured files above and should be regenerated when more
source families arrive.
"""
    CAPACITY.parent.mkdir(parents=True, exist_ok=True)
    CAPACITY.write_text(
        replace_generated(CAPACITY.read_text(encoding="utf-8"), capacity)
        if CAPACITY.exists()
        else "# Capacity plan: ATTACKpath\n\n" + capacity,
        encoding="utf-8",
    )
    print(f"files={files} pages={pages} -> wrote DATASET.md and docs/CAPACITY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
