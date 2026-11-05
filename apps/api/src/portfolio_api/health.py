"""Readiness verifies a real query and the installed Alembic revision."""

import json
import logging
import re
import socket
import ssl
from datetime import UTC, datetime
from typing import Literal

from alembic.runtime.migration import MigrationContext
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _safe_database_error(error: SQLAlchemyError) -> dict[str, str | None]:
    """Classify locally; never return driver messages or connection details."""
    original = getattr(error, "orig", error)
    message = str(original).lower()
    sqlstate = getattr(original, "sqlstate", None)
    safe_state = (
        sqlstate if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate) else None
    )
    name = type(original).__name__
    safe_name = name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "Unknown"
    if isinstance(original, ssl.SSLCertVerificationError) or any(
        s in message
        for s in (
            "certificate verify failed",
            "certificate verification failed",
            "root certificate file",
            "certificate has expired",
            "certificate does not match",
        )
    ):
        category = "tls_certificate"
    elif (
        safe_state
        and safe_state.startswith("28")
        or any(
            s in message
            for s in (
                "password authentication failed",
                "no password supplied",
                "authentication failed",
            )
        )
    ):
        category = "authentication"
    elif isinstance(original, socket.gaierror) or any(
        s in message
        for s in (
            "could not translate host name",
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname provided",
        )
    ):
        category = "dns"
    elif isinstance(original, TimeoutError) or any(
        s in message for s in ("timed out", "timeout expired", "connection timeout")
    ):
        category = "timeout"
    else:
        category = "other"
    return {"category": category, "exception_class": safe_name, "sqlstate": safe_state}


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
            else:
                try:
                    database, schema = connection.execute(
                        text("SELECT current_database(), current_schema()")
                    ).one()
                except SQLAlchemyError:
                    database, schema = None, None
                logger.warning(
                    "readiness_schema_mismatch %s",
                    json.dumps(
                        {
                            "expected_revisions": sorted(heads),
                            "observed_revisions": sorted(current_heads),
                            "database": database,
                            "schema": schema,
                        },
                        sort_keys=True,
                    ),
                )
    except SQLAlchemyError as error:
        diagnostic = _safe_database_error(error)
        diagnostic["phase"] = "schema_query" if result.database == "connected" else "connection"
        logger.warning("readiness_database_error %s", json.dumps(diagnostic, sort_keys=True))
    return result
