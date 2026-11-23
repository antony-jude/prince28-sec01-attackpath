from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("select 1"))
        database_ready = True
    except Exception:
        database_ready = False
    status_code = 200 if database_ready else 503
    return JSONResponse(
        {
            "status": "ready" if database_ready else "not_ready",
            "checks": {"database": database_ready},
        },
        status_code=status_code,
    )
