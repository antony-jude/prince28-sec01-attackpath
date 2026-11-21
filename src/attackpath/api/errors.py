import logging
from http import HTTPStatus
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _problem(
    request: Request,
    status_code: int,
    detail: str,
    *,
    errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    try:
        title = HTTPStatus(status_code).phrase
    except ValueError:
        title = "Internal Server Error"
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", ""),
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(
        body,
        status_code=status_code,
        media_type="application/problem+json",
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return _problem(request, exc.status_code, detail)


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return _problem(request, 422, "Request validation failed.", errors=errors)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled request error",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"request_id": getattr(request.state, "request_id", "")},
    )
    return _problem(request, 500, "An unexpected error occurred.")
