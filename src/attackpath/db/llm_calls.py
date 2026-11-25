from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from attackpath.db.models import LlmCall


async def record_call(session: AsyncSession, row: dict) -> None:
    session.add(LlmCall(**row))
    await session.commit()


class UsageRepository:
    def __init__(self, session):
        self.session = session

    async def by_day(self, days: int = 7) -> list[dict]:
        since = datetime.now(UTC) - timedelta(days=days)
        day = func.date(LlmCall.created_at).label("day")
        stmt = (
            select(
                day,
                func.count().label("calls"),
                func.sum(LlmCall.tokens_in).label("tokens_in"),
                func.sum(LlmCall.tokens_out).label("tokens_out"),
                func.sum(LlmCall.cost_inr).label("cost_inr"),
                func.sum((LlmCall.status == "error").cast(__import__("sqlalchemy").Integer)).label(
                    "errors"
                ),
                func.sum(LlmCall.fallback_used.cast(__import__("sqlalchemy").Integer)).label(
                    "fallbacks"
                ),
            )
            .where(LlmCall.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "day": str(r.day),
                "calls": r.calls,
                "errors": r.errors or 0,
                "fallbacks": r.fallbacks or 0,
                "tokens_in": r.tokens_in or 0,
                "tokens_out": r.tokens_out or 0,
                "cost_inr": float(r.cost_inr or Decimal("0")),
            }
            for r in rows
        ]
