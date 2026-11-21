import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from attackpath.api.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from attackpath.api.middleware import install_request_middleware
from attackpath.api.routes.documents import router as documents_router
from attackpath.api.routes.health import router as health_router
from attackpath.config import Settings, get_settings
from attackpath.logging_setup import configure_logging
from attackpath.store import load_records

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            records = load_records(app_settings.data_file)
        except (OSError, ValueError) as exc:
            app.state.records = None
            logger.error("could not load records", extra={"error": str(exc)})
        else:
            app.state.records = records
            logger.info("records loaded", extra={"records": len(records)})
        yield

    configure_logging(app_settings.log_level)
    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.records = None
    app.state.settings = app_settings
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    install_request_middleware(app)
    app.include_router(health_router)
    app.include_router(documents_router)
    return app
