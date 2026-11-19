import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from paw.api.catalog import router
from paw.api.limits import BodyLimits
from paw.api.runs import router as runs_router
from paw.config import Settings
from paw.domain.files import Catalog, InputError, NotFound
from paw.domain.ports import Readiness
from paw.domain.runs import IdempotencyConflict, RunRepository
from paw.infrastructure.db.catalog import PostgresCatalog
from paw.infrastructure.db.connection import DatabaseReadiness, make_engine
from paw.infrastructure.db.runs import PostgresRuns
from paw.infrastructure.logging import configure_logging
from paw.infrastructure.storage.local import LocalBlobStore


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["paw-api"] = "paw-api"


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: Literal["paw-api"] = "paw-api"
    code: Literal["database_unavailable"] | None = None


def create_app(
    readiness: Readiness | None = None,
    catalog: Catalog | None = None,
    runs: RunRepository | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        app.state.catalog = catalog
        app.state.runs = runs
        if readiness is not None:
            app.state.readiness = readiness
            yield
        else:
            settings = Settings()
            engine = make_engine(settings)
            app.state.readiness = DatabaseReadiness(engine)
            app.state.runs = PostgresRuns(engine)
            try:
                actual_catalog = PostgresCatalog(engine, LocalBlobStore(settings.storage_root))
                app.state.catalog = actual_catalog
                try:
                    actual_catalog.reconcile()
                except (SQLAlchemyError, OSError):
                    logging.getLogger("paw").warning("upload_reconciliation_deferred")
                yield
            finally:
                engine.dispose()

    app = FastAPI(title="Personal AI Workspace", version="0.1.0", lifespan=lifespan)

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/v1/ready", response_model=ReadyResponse, response_model_exclude_none=True)
    def ready(response: Response) -> ReadyResponse:
        if app.state.readiness.is_ready():
            return ReadyResponse(status="ready")
        response.status_code = 503
        return ReadyResponse(status="not_ready", code="database_unavailable")

    app.add_middleware(BodyLimits)
    app.include_router(router)
    app.include_router(runs_router)

    @app.exception_handler(IdempotencyConflict)
    async def conflict(request: Request, exc: IdempotencyConflict) -> JSONResponse:
        return JSONResponse({"code": "idempotency_conflict"}, 409)

    @app.exception_handler(InputError)
    async def input_error(request: Request, exc: InputError) -> JSONResponse:
        return JSONResponse({"code": exc.code}, 413 if exc.code == "file_too_large" else 422)

    @app.exception_handler(NotFound)
    async def not_found(request: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"code": "not_found"}, 404)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"code": "invalid_request"}, 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {
            400: "invalid_upload",
            404: "not_found",
            405: "method_not_allowed",
            413: "request_too_large",
            415: "unsupported_media_type",
            503: "service_unavailable",
        }
        return JSONResponse(
            {"code": codes.get(exc.status_code, "invalid_request")}, exc.status_code
        )

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(OSError)
    async def persistence_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("paw").error("storage_operation_failed")
        return JSONResponse({"code": "storage_unavailable"}, 503)

    return app
