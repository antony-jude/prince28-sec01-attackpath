from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    records = getattr(request.app.state, "records", None)
    is_loaded = records is not None
    status_code = 200 if is_loaded else 503
    return JSONResponse(
        {
            "status": "ready" if is_loaded else "not_ready",
            "checks": {
                "records_loaded": is_loaded,
                "records_count": len(records) if is_loaded else 0,
            },
        },
        status_code=status_code,
    )
