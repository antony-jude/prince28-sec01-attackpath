"""Print parsed corpus counts for the Day 7 evidence log."""

import asyncio

from sqlalchemy import func, select

from attackpath.config import get_settings
from attackpath.db.models import Document, Page, ParseFailure
from attackpath.db.session import make_engine, make_sessionmaker


async def main() -> None:
    engine = make_engine(get_settings())
    factory = make_sessionmaker(engine)
    async with factory() as session:
        documents = await session.scalar(
            select(func.count()).select_from(Document).where(Document.doc_type == "parsed")
        )
        pages = await session.scalar(
            select(func.count())
            .select_from(Page)
            .join(Document)
            .where(Document.doc_type == "parsed")
        )
        failures = await session.scalar(select(func.count()).select_from(ParseFailure))
        reasons = await session.execute(
            select(ParseFailure.reason, func.count()).group_by(ParseFailure.reason)
        )
        print({"documents": documents, "pages": pages, "failures": failures})
        print({reason: count for reason, count in reasons})
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
