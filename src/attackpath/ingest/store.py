"""Persist parsed documents and parser failures in one transaction per file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from attackpath.db.models import Document, Page, ParseFailure
from attackpath.ingest.parse import ParsedDoc, ParseError


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_rows(root: Path) -> dict[str, dict[str, Any]]:
    manifest = root / "data" / "manifest.jsonl"
    if not manifest.exists():
        return {}
    rows = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["path"]] = row
    return rows


async def save_parsed(
    session: AsyncSession,
    path: Path,
    doc: ParsedDoc,
    *,
    root: Path,
    source: dict[str, Any] | None = None,
) -> Document:
    relative = path.relative_to(root).as_posix()
    digest = file_sha256(path)
    external_id = "parsed-" + digest[:32]
    metadata = {
        "parser": doc.parser,
        "kind": doc.kind,
        "pages": len(doc.pages),
        "tables": sum(page.tables for page in doc.pages),
        "scanned_pages": doc.scanned_pages,
        "path": relative,
    }
    existing = await session.scalar(select(Document).where(Document.external_id == external_id))
    if existing:
        await session.execute(delete(Page).where(Page.document_id == existing.id))
        existing.title = doc.title or path.stem
        existing.metadata_ = metadata
        existing.sha256 = digest
        document = existing
    else:
        document = Document(
            external_id=external_id,
            title=doc.title or path.stem,
            source_url=(source or {}).get("url"),
            licence=(source or {}).get("licence"),
            doc_type="parsed",
            sha256=digest,
            metadata_=metadata,
        )
        session.add(document)
        await session.flush()
    session.add_all(
        Page(document_id=document.id, page_no=page.page_no, text=page.text, headings=page.headings)
        for page in doc.pages
    )
    await session.execute(delete(ParseFailure).where(ParseFailure.path == relative))
    return document


async def save_failure(
    session: AsyncSession,
    path: Path,
    error: ParseError,
    *,
    root: Path,
    source: dict[str, Any] | None = None,
) -> ParseFailure:
    relative = path.relative_to(root).as_posix()
    digest = file_sha256(path)
    failure = await session.scalar(select(ParseFailure).where(ParseFailure.path == relative))
    if failure:
        failure.sha256 = digest
        failure.source_url = (source or {}).get("url")
        failure.reason = error.reason
        failure.detail = error.detail
        failure.attempts += 1
    else:
        failure = ParseFailure(
            path=relative,
            sha256=digest,
            source_url=(source or {}).get("url"),
            reason=error.reason,
            detail=error.detail,
        )
        session.add(failure)
    return failure
