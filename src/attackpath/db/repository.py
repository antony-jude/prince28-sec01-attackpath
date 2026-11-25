"""All SQL for documents lives here. Endpoints never write SQL themselves."""

import re
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from attackpath.db.models import Document, Page

FILTER_KEY = re.compile(r"^[a-z_][a-z0-9_]{0,40}$")


def to_dict(doc: Document) -> dict[str, Any]:
    return {
        "id": doc.external_id,
        **doc.metadata_,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "source_url": doc.source_url,
        "licence": doc.licence,
        "published_on": doc.published_on.isoformat() if doc.published_on else None,
    }


def _value_candidates(value: str) -> list[Any]:
    out: list[Any] = [value, [value]]
    lowered = value.lower()
    if lowered in ("true", "false"):
        out.append(lowered == "true")
    elif re.fullmatch(r"-?\d+", value):
        out.append(int(value))
    elif re.fullmatch(r"-?\d+\.\d+", value):
        out.append(float(value))
    return out


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        q: str | None,
        filters: dict[str, str],
        limit: int,
        offset: int,
        sort: str = "external_id",
    ) -> tuple[int, list[dict[str, Any]]]:
        stmt = select(Document)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(Document.title.ilike(like), cast(Document.metadata_, Text).ilike(like))
            )
        for key, value in filters.items():
            if key == "technique_id":
                stmt = stmt.where(Document.technique_id == value)
            else:
                stmt = stmt.where(
                    or_(
                        *(
                            Document.metadata_.contains({key: candidate})
                            for candidate in _value_candidates(value)
                        )
                    )
                )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        descending = sort.startswith("-")
        sort_field = sort.removeprefix("-")
        sort_columns = {
            "title": Document.title,
            "published_on": Document.published_on,
            "external_id": Document.external_id,
        }
        column = sort_columns.get(sort_field)
        if column is not None:
            stmt = stmt.order_by(column.desc() if descending else column.asc())
        else:
            stmt = stmt.order_by(Document.external_id.asc())
        rows = await self.session.scalars(stmt.limit(limit).offset(offset))
        return total or 0, [to_dict(doc) for doc in rows]

    async def get(self, external_id: str) -> dict[str, Any] | None:
        doc = await self.session.scalar(select(Document).where(Document.external_id == external_id))
        return to_dict(doc) if doc else None

    async def get_page(self, external_id: str, page_no: int) -> dict[str, Any] | None:
        document = await self.session.scalar(
            select(Document).where(Document.external_id == external_id)
        )
        if document is None:
            return None
        page = await self.session.scalar(
            select(Page).where(Page.document_id == document.id, Page.page_no == page_no)
        )
        if page is None:
            return None
        return {
            "document_id": external_id,
            "page_no": page.page_no,
            "headings": page.headings,
            "text": page.text,
        }
