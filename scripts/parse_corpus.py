"""Parse data/raw into Postgres, recording every failure and supporting resume."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from sqlalchemy import select

from attackpath.config import get_settings
from attackpath.db.models import Document, ParseFailure
from attackpath.db.session import make_engine, make_sessionmaker
from attackpath.ingest.parse import ParseError, parse_file, parse_pdf_ocr
from attackpath.ingest.store import manifest_rows, save_failure, save_parsed


async def run(
    limit: int | None, retry_failed: bool, ocr: str | None, reparse: bool
) -> dict[str, int]:
    settings = get_settings()
    root = Path.cwd()
    raw = root / "data" / "raw"
    rows = manifest_rows(root)
    paths = sorted(
        path for path in raw.rglob("*") if path.is_file() and not path.name.endswith(".part")
    )
    engine = make_engine(settings)
    factory = make_sessionmaker(engine)
    counts = {
        "files": len(paths),
        "parsed": 0,
        "failed": 0,
        "pages": 0,
        "already_parsed": 0,
        "failed_before": 0,
    }
    async with factory() as session:
        parsed_paths = {
            value
            for value in await session.scalars(select(Document.metadata_["path"].as_string()))
            if value
        }
        failures = {value for value in await session.scalars(select(ParseFailure.path))}
        todo = [
            path
            for path in paths
            if reparse or path.relative_to(root).as_posix() not in parsed_paths
        ]
        if retry_failed:
            todo = [path for path in paths if path.relative_to(root).as_posix() in failures]
        counts["already_parsed"] = len(paths) - len(todo)
        counts["failed_before"] = len(failures)
        if limit:
            todo = todo[:limit]
        for index, path in enumerate(todo, 1):
            relative = path.relative_to(root).as_posix()
            try:
                doc = parse_file(path)
                if ocr and doc.scanned_pages and path.suffix.lower() == ".pdf":
                    doc = parse_pdf_ocr(path, language=ocr)
                async with session.begin_nested():
                    await save_parsed(session, path, doc, root=root, source=rows.get(relative))
                counts["parsed"] += 1
                counts["pages"] += len(doc.pages)
            except ParseError as error:
                async with session.begin_nested():
                    await save_failure(session, path, error, root=root, source=rows.get(relative))
                counts["failed"] += 1
            if index % 50 == 0:
                print(
                    f"processed={index} parsed={counts['parsed']} failed={counts['failed']}",
                    flush=True,
                )
        await session.commit()
    await engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--ocr", help="Tesseract language(s), e.g. eng or eng+tam")
    parser.add_argument("--reparse", action="store_true", help="Rebuild pages for every raw file")
    args = parser.parse_args()
    started = time.perf_counter()
    result = asyncio.run(run(args.limit, args.retry_failed, args.ocr, args.reparse))
    print(json.dumps({**result, "seconds": round(time.perf_counter() - started, 1)}))


if __name__ == "__main__":
    main()
