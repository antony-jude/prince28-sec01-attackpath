from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from attackpath.api.deps import check_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(database_ready: bool = Depends(check_db)) -> JSONResponse:
    status_code = 200 if database_ready else 503
    return JSONResponse(
        {
            "status": "ready" if database_ready else "not_ready",
            "checks": {"database": database_ready},
        },
        status_code=status_code,
    )
