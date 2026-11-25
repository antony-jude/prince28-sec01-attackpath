from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from attackpath.db.llm_calls import UsageRepository
from attackpath.db.repository import DocumentRepository
from attackpath.llm.gateway import LLMGateway


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


async def check_db(request: Request) -> bool:
    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("select 1"))
        return True
    except Exception:
        return False


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_repository(session: SessionDependency) -> DocumentRepository:
    return DocumentRepository(session)


def get_gateway(request: Request) -> LLMGateway:
    return request.app.state.gateway


def get_usage_repository(session: SessionDependency) -> UsageRepository:
    return UsageRepository(session)


GatewayDep = Annotated[LLMGateway, Depends(get_gateway)]
UsageDep = Annotated[UsageRepository, Depends(get_usage_repository)]
