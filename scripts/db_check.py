"""Check that the configured PostgreSQL database is reachable."""

import asyncio

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from attackpath.config import get_settings
from attackpath.db.session import make_engine


async def main() -> None:
    engine = make_engine(get_settings())
    try:
        async with engine.connect() as connection:
            row = await connection.execute(text("select current_database(), version()"))
            database_name, version = row.one()
    except SQLAlchemyError as exc:
        raise SystemExit(
            "Database connection failed. Add a valid DATABASE_URL to .env "
            "and verify the Neon network/SSL settings."
        ) from exc
    url = make_url(str(engine.url))
    print(f"Connected to database '{database_name}'")
    print(f"Database host: {url.host}")
    print(version)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
