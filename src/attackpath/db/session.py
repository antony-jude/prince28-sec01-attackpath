"""SQLAlchemy async engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from attackpath.config import Settings
from attackpath.db.url import to_asyncpg_url


def make_engine(settings: Settings):
    return create_async_engine(to_asyncpg_url(settings.database_url), pool_pre_ping=True)


def make_sessionmaker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
