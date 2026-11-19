from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response
from pydantic import BaseModel

from paw.config import Settings
from paw.domain.ports import Readiness
from paw.infrastructure.db.connection import DatabaseReadiness, make_engine
from paw.infrastructure.logging import configure_logging


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["paw-api"] = "paw-api"


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: Literal["paw-api"] = "paw-api"
    code: Literal["database_unavailable"] | None = None


def create_app(readiness: Readiness | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        if readiness is not None:
            app.state.readiness = readiness
            yield
        else:
            engine = make_engine(Settings())
            app.state.readiness = DatabaseReadiness(engine)
            try:
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

    return app
