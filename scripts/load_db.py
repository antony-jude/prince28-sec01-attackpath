"""Load data/sample_records.json into Postgres.

Safe to run repeatedly: unchanged records are skipped and changed records are updated.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import date

from sqlalchemy import delete, select, update

from attackpath.config import get_settings
from attackpath.db.models import Document
from attackpath.db.session import make_engine, make_sessionmaker

TITLE_FIELD = "name"
KNOWN = {"id", "title", "source_url", "licence", "doc_type", "published_on"}


def fingerprint(record: dict) -> str:
    canonical = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_row(record: dict) -> dict:
    published = record.get("published_on")
    return {
        "external_id": str(record["id"]),
        "title": str(record.get("title") or record.get(TITLE_FIELD) or record["id"]),
        "technique_id": record.get("technique_id"),
        "source_url": record.get("source_url"),
        "licence": record.get("licence"),
        "doc_type": record.get("doc_type") or "record",
        "published_on": date.fromisoformat(published) if published else None,
        "sha256": fingerprint(record),
        "metadata_": {k: v for k, v in record.items() if k not in KNOWN},
    }


def stale_document_ids(source_records: list[dict], database_ids: set[str]) -> list[str]:
    source_ids = {str(record["id"]) for record in source_records}
    return sorted(database_ids - source_ids)


async def main(prune: bool = False) -> None:
    settings = get_settings()
    records = json.loads(settings.data_file.read_text(encoding="utf-8"))
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)
    inserted = updated = unchanged = deleted = 0
    async with session_factory() as session, session.begin():
        rows = await session.execute(select(Document.external_id, Document.sha256, Document.title))
        existing = {
            external_id: {"sha256": sha256, "title": title}
            for external_id, sha256, title in rows.all()
        }
        for record in records:
            row = to_row(record)
            old = existing.get(row["external_id"])
            if old is None:
                session.add(Document(**row))
                inserted += 1
            elif old["sha256"] != row["sha256"] or old["title"] != row["title"]:
                await session.execute(
                    update(Document).where(Document.external_id == row["external_id"]).values(**row)
                )
                updated += 1
            else:
                unchanged += 1
        if prune:
            stale_ids = stale_document_ids(records, set(existing))
            if stale_ids:
                await session.execute(delete(Document).where(Document.external_id.in_(stale_ids)))
                deleted = len(stale_ids)
    await engine.dispose()
    print(
        f"records={len(records)} inserted={inserted} updated={updated} "
        f"unchanged={unchanged} deleted={deleted}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete database documents absent from the JSON file",
    )
    args = parser.parse_args()
    asyncio.run(main(prune=args.prune))
