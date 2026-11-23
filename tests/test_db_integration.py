import asyncio
import os

import pytest
from sqlalchemy import text

from attackpath.config import Settings
from attackpath.db.repository import DocumentRepository
from attackpath.db.session import make_engine, make_sessionmaker

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not configured",
)


def run_db_query(operation):
    settings = Settings(
        app_env="ci",
        database_url=TEST_DATABASE_URL or "",
        _env_file=None,
    )
    engine = make_engine(settings)
    factory = make_sessionmaker(engine)

    async def run():
        async with factory() as session:
            result = await operation(session)
        await engine.dispose()
        return result

    return asyncio.run(run())


def test_real_database_connects() -> None:
    async def operation(session):
        row = await session.execute(text("select 1"))
        return row.scalar_one()

    assert run_db_query(operation) == 1


def test_real_document_tables_exist() -> None:
    async def operation(session):
        row = await session.execute(
            text(
                "select count(*) from information_schema.tables "
                "where table_schema = 'public' "
                "and table_name in ('documents', 'pages')"
            )
        )
        return row.scalar_one()

    assert run_db_query(operation) == 2


def test_real_repository_filters_metadata() -> None:
    async def operation(session):
        repository = DocumentRepository(session)
        return await repository.list(
            q=None,
            filters={"technique_id": "T1059.001"},
            limit=20,
            offset=0,
        )

    total, items = run_db_query(operation)
    assert total == 1
    assert items[0]["technique_id"] == "T1059.001"
