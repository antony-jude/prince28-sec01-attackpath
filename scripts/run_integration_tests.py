"""Reset the local test database, migrate it, and run PostgreSQL integration tests."""

import asyncio
import os
import subprocess
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url

ROOT = Path(__file__).parents[1]
# pragma: allowlist nextline secret
DEFAULT_TEST_DATABASE_URL = "postgresql://app:app@localhost:5433/attackpath_test"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


async def recreate_database(database_url: str) -> None:
    test_url = make_url(database_url)
    if test_url.host not in LOCAL_HOSTS or test_url.database != "attackpath_test":
        raise ValueError(
            "Integration tests may only recreate the local attackpath_test database "
            "(localhost:5433 by default)."
        )

    admin_url = test_url.set(database="postgres", drivername="postgresql")
    connection = await asyncpg.connect(admin_url.render_as_string(hide_password=False))
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            test_url.database,
        )
        await connection.execute('DROP DATABASE IF EXISTS "attackpath_test"')
        await connection.execute('CREATE DATABASE "attackpath_test"')
    finally:
        await connection.close()


def main() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    asyncio.run(recreate_database(database_url))

    environment = os.environ.copy()
    environment.update(
        APP_ENV="ci",
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
    )
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    subprocess.run(
        ["uv", "run", "python", "scripts/load_db.py"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    subprocess.run(
        ["uv", "run", "pytest", "-m", "integration"],
        cwd=ROOT,
        env=environment,
        check=True,
    )


if __name__ == "__main__":
    main()
