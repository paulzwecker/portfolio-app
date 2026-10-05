"""FastAPI entry point. Startup never creates or upgrades database objects."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request, Response
from sqlalchemy.engine import Engine

from portfolio_api.database import create_database_engine
from portfolio_api.domain.routes import router
from portfolio_api.health import HealthResponse, LivenessResponse, check_readiness
from portfolio_api.migrations import expected_heads
from portfolio_api.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(settings if settings is not None else Settings())
        application.state.database_engine = engine
        application.state.migration_heads = expected_heads()
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    application = FastAPI(
        title="Portfolio Research API",
        version="0.1.0",
        description=(
            "Identity, explicit lifecycle, scores, auditable ranking snapshots, "
            "observed holdings, strategic targets, imported model outputs and the "
            "versioned deterministic UFCF DCF model domain."
        ),
        lifespan=lifespan,
    )
    application.include_router(router)

    @application.get("/health/live", response_model=LivenessResponse, tags=["health"])
    def liveness() -> LivenessResponse:
        return LivenessResponse()

    @application.get(
        "/health/ready",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse, "description": "Database or schema not ready"}},
        tags=["health"],
    )
    def readiness(request: Request, response: Response) -> HealthResponse:
        engine = cast(Engine | None, request.app.state.database_engine)
        heads = cast(set[str], request.app.state.migration_heads)
        result = check_readiness(engine, heads)
        response.status_code = 200 if result.status == "ok" else 503
        response.headers["Cache-Control"] = "no-store"
        return result

    return application


app = create_app()
