"""Readiness verifies a real query and the installed Alembic revision."""

from datetime import UTC, datetime
from typing import Literal

from alembic.runtime.migration import MigrationContext
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    database: Literal["connected", "unavailable"]
    schema_status: Literal["current", "outdated", "unavailable"] = Field(alias="schema")
    checked_at: datetime


def check_readiness(engine: Engine | None, heads: set[str]) -> HealthResponse:
    result = HealthResponse(
        status="error",
        database="unavailable",
        schema="unavailable",
        checked_at=datetime.now(UTC),
    )
    if engine is None:
        return result
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            result.database = "connected"
            current_heads = set(MigrationContext.configure(connection).get_current_heads())
            result.schema_status = "current" if current_heads == heads else "outdated"
            if result.schema_status == "current":
                result.status = "ok"
    except SQLAlchemyError:
        # Connection strings, driver messages, and credentials never reach a client.
        pass
    return result
