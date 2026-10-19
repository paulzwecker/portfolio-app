"""Fail-closed tooling for preparing a local PostgreSQL data migration.

This module deliberately has no fallback to ``DATABASE_URL``. Source and target
connections must be selected independently through the migration-only environment
variables documented in ``docs/postgresql-migration.md``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from portfolio_api.database import Base
from portfolio_api.domain import models  # noqa: F401 -- register mapped tables
from portfolio_api.migrations import expected_heads

FORMAT_VERSION = 1
EXPECTED_POSTGRES_MAJOR = 18
APP_SCHEMA = "public"
ALLOWED_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# These immutable definitions are seeded by Alembic and must already match on
# the isolated Neon target. Copying them from a data archive would collide with
# their migration-created primary keys.
MIGRATION_SEEDED_TABLES = frozenset(
    {"score_definitions", "ranking_definitions", "return_methodology_definitions"}
)

# Worker heartbeat/lease state is tied to one running process and is never moved.
# alembic_version is checked independently and is never part of a data archive.
TRANSIENT_TABLES = frozenset({"recurring_operations_worker_state"})
METADATA_TABLES = frozenset({"alembic_version"})
EXCLUDED_ARCHIVE_TABLES = TRANSIENT_TABLES

TABLE_GROUPS: dict[str, tuple[str, ...]] = {
    "identity_and_lifecycle": (
        "companies",
        "securities",
        "listings",
        "company_provider_identifiers",
        "lifecycle_events",
        "company_lifecycle_current",
    ),
    "portfolio_state": (
        "portfolios",
        "holding_snapshots",
        "holding_positions",
        "holding_cash_positions",
        "target_allocation_revisions",
        "target_allocations",
    ),
    "scores_rankings_and_execution": (
        "score_definitions",
        "score_assessments",
        "ranking_definitions",
        "ranking_runs",
        "ranking_entries",
        "research_priority_inputs",
        "execution_pace_runs",
        "execution_pace_decisions",
        "candidate_pipeline_revisions",
        "candidate_pipeline_gate_assessments",
        "candidate_pipeline_evidence",
    ),
    "market_and_fundamental_observations": (
        "market_data_batches",
        "price_observations",
        "corporate_actions",
        "price_regime_snapshots",
        "fx_observations",
        "reported_fundamental_batches",
        "reported_fundamental_observations",
        "consensus_estimate_provider_mappings",
        "consensus_estimate_batches",
        "consensus_estimate_observations",
    ),
    "financial_models_and_outputs": (
        "return_methodology_definitions",
        "model_output_import_batches",
        "model_output_snapshots",
        "financial_models",
        "financial_model_revisions",
        "financial_model_revision_evidence",
        "financial_model_outputs",
        "financial_model_migration_assessments",
        "dcf_model_assumptions",
        "dcf_scenario_assumptions",
        "dcf_year_assumptions",
        "dcf_tail_growth_assumptions",
        "dcf_projections",
        "owner_cash_flow_assumptions",
        "owner_cash_flow_scenarios",
        "owner_cash_flow_year_assumptions",
        "owner_cash_flow_projections",
        "residual_income_assumptions",
        "residual_income_scenarios",
        "residual_income_projections",
        "google_sheets_sync_runs",
        "google_sheets_sync_candidates",
    ),
    "research_thesis_risk_and_evidence": (
        "source_document_batches",
        "source_documents",
        "research_revisions",
        "research_forecasts",
        "research_assessments",
        "research_evidence",
        "research_queue_completions",
        "research_triggers",
        "research_trigger_publication_links",
        "research_agent_work_events",
        "investment_thesis_revisions",
        "investment_thesis_claims",
        "investment_thesis_evidence",
        "risk_assessment_revisions",
        "risk_assessment_findings",
        "risk_assessment_evidence",
        "google_sheets_research_sync_runs",
        "google_sheets_research_sync_candidates",
        "google_sheets_risk_sync_runs",
        "google_sheets_risk_sync_candidates",
    ),
    "provider_payloads_and_operational_history": (
        "external_raw_payloads",
        "external_ingestion_runs",
        "external_ingestion_attempts",
        "legacy_import_batches",
        "canonical_bootstrap_runs",
        "market_data_bootstrap_runs",
        "market_data_bootstrap_checkpoints",
        "fundamentals_bootstrap_runs",
        "fundamentals_bootstrap_checkpoints",
        "recurring_operation_runs",
        "recurring_operations_worker_state",
        "operational_job_requests",
        "operational_job_attempts",
    ),
}
TABLE_GROUP_BY_NAME = {
    table_name: group_name
    for group_name, table_names in TABLE_GROUPS.items()
    for table_name in table_names
}


class MigrationToolError(Exception):
    """Expected, safe-to-display migration-tool failure."""


@dataclass(frozen=True)
class DatabaseEndpoint:
    role: str
    url: URL = field(repr=False)
    host: str
    port: int
    database: str
    username: str
    schema: str
    test_target: bool = False
    neon_environment: dict[str, str] | None = field(default=None, repr=False, compare=False)

    @property
    def password(self) -> str | None:
        return self.url.password

    @property
    def sslmode(self) -> str | None:
        value = self.url.query.get("sslmode")
        return str(value) if value is not None else None


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MigrationToolError(f"Set {name}; the migration tool has no database default.")
    return value


def _neon_api_json(path: str, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://console.neon.tech/api/v2/{path.lstrip('/')}",
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"},
        method="GET",
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(
            self, req: Any, fp: Any, code: int, msg: str, headers: Any, new_url: str
        ) -> None:
            return None

    try:
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(request, timeout=15) as response:
            if not response.geturl().startswith("https://console.neon.tech/"):
                raise MigrationToolError(
                    "Neon control-plane identity verification redirected to an unexpected host."
                )
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise MigrationToolError(
            f"Neon control-plane identity verification failed (HTTP {error.code})."
        ) from None
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        raise MigrationToolError(
            "Neon control-plane identity verification failed; the target identity is unproven."
        ) from None
    except MigrationToolError:
        raise
    except Exception:
        raise MigrationToolError(
            "Neon control-plane identity verification failed; the target identity is unproven."
        ) from None
    if not isinstance(payload, dict):
        raise MigrationToolError("Neon control-plane returned an invalid identity response.")
    return payload


def _neon_api_list(resource: str, project_id: str, api_key: str) -> list[dict[str, Any]]:
    encoded_project = urllib.parse.quote(project_id, safe="")
    cursor: str | None = None
    seen_cursors: set[str] = set()
    results: list[dict[str, Any]] = []
    for _ in range(20):
        query = {"limit": "100"}
        if cursor is not None:
            query["cursor"] = cursor
        payload = _neon_api_json(
            f"projects/{encoded_project}/{resource}?{urllib.parse.urlencode(query)}", api_key
        )
        items = payload.get(resource)
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise MigrationToolError(
                f"Neon control-plane returned an invalid {resource} identity list."
            )
        results.extend(items)
        pagination = payload.get("pagination")
        next_cursor = pagination.get("cursor") if isinstance(pagination, dict) else None
        if next_cursor is None:
            if len(items) == 100:
                raise MigrationToolError(
                    "Neon control-plane identity results may be truncated; "
                    "target isolation is unproven."
                )
            return results
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
            raise MigrationToolError("Neon control-plane pagination could not be verified.")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    raise MigrationToolError("Neon control-plane identity list exceeded the safe pagination limit.")


def _verify_neon_target_identity(endpoint: DatabaseEndpoint) -> dict[str, str]:
    """Prove the entered endpoint belongs to a non-primary Neon child branch."""
    api_key = _required_environment("MIGRATION_NEON_API_KEY")
    project_id = _required_environment("MIGRATION_NEON_PROJECT_ID")
    target_branch_id = _required_environment("MIGRATION_NEON_TARGET_BRANCH_ID")
    target_endpoint_id = _required_environment("MIGRATION_NEON_TARGET_ENDPOINT_ID")
    for value in (project_id, target_branch_id, target_endpoint_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,128}", value):
            raise MigrationToolError("Neon project, branch and endpoint IDs must be plain IDs.")

    branches = _neon_api_list("branches", project_id, api_key)
    endpoints = _neon_api_list("endpoints", project_id, api_key)
    primary_branches = [branch for branch in branches if branch.get("primary") is True]
    if len(primary_branches) != 1:
        raise MigrationToolError(
            "Neon did not identify exactly one primary branch; target isolation is unproven."
        )
    primary_branch = primary_branches[0]
    primary_branch_id = primary_branch.get("id")
    if not isinstance(primary_branch_id, str) or not primary_branch_id:
        raise MigrationToolError(
            "Neon did not return the primary branch ID; target isolation is unproven."
        )
    target_branches = [branch for branch in branches if branch.get("id") == target_branch_id]
    target_endpoints = [
        endpoint_data
        for endpoint_data in endpoints
        if endpoint_data.get("id") == target_endpoint_id
    ]
    if len(target_branches) != 1 or len(target_endpoints) != 1:
        raise MigrationToolError(
            "The Neon project does not resolve the selected branch and endpoint IDs uniquely."
        )
    target_branch = target_branches[0]
    target_endpoint = target_endpoints[0]
    if target_branch.get("primary") is True or target_branch_id == primary_branch_id:
        raise MigrationToolError("The selected Neon branch is the primary production branch.")
    if target_branch.get("parent_id") != primary_branch_id:
        raise MigrationToolError(
            "The selected Neon branch is not a direct child of the verified primary branch."
        )
    if target_endpoint.get("branch_id") != target_branch_id:
        raise MigrationToolError(
            "The selected Neon endpoint is not attached to the verified migration branch."
        )
    endpoint_host = str(target_endpoint.get("host", "")).rstrip(".").lower()
    if endpoint_host != endpoint.host:
        raise MigrationToolError(
            "The PostgreSQL hostname does not match the verified Neon endpoint identity."
        )
    if target_endpoint.get("type") != "read_write":
        raise MigrationToolError("The verified Neon endpoint is not a read-write endpoint.")
    if target_branch.get("project_id") not in {None, project_id}:
        raise MigrationToolError("The selected Neon branch belongs to another project.")
    if target_endpoint.get("project_id") not in {None, project_id}:
        raise MigrationToolError("The selected Neon endpoint belongs to another project.")
    return {
        "project_id": project_id,
        "production_branch_id": str(primary_branch_id),
        "branch_id": target_branch_id,
        "endpoint_id": target_endpoint_id,
        "parent_branch_id": str(primary_branch_id),
        "verified_by": "neon_control_plane_api_v2",
    }


def _required_row(row: tuple[Any, ...] | None, message: str) -> tuple[Any, ...]:
    if row is None:
        raise MigrationToolError(message)
    return row


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_schema_name(name: str) -> str:
    if not ALLOWED_SCHEMA_NAME.fullmatch(name):
        raise MigrationToolError("Database schema name is invalid.")
    return name


def endpoint_from_environment(role: str) -> DatabaseEndpoint:
    if role not in {"source", "target"}:
        raise MigrationToolError("Database role must be source or target.")
    url_name = f"MIGRATION_{role.upper()}_URL"
    raw_url = _required_environment(url_name)
    try:
        url = make_url(raw_url)
    except (ArgumentError, ValueError):
        raise MigrationToolError(f"{url_name} is not a valid PostgreSQL URL.") from None
    if url.drivername not in {"postgresql+psycopg", "postgresql"}:
        raise MigrationToolError(f"{url_name} must use PostgreSQL with the psycopg driver.")
    if not url.host or not url.database or not url.username:
        raise MigrationToolError(f"{url_name} must include an explicit host, database, and role.")
    host = url.host.rstrip(".").lower()
    database = url.database
    username = url.username
    schema = _validate_schema_name(
        os.environ.get(f"MIGRATION_{role.upper()}_SCHEMA", APP_SCHEMA).strip()
    )
    endpoint = DatabaseEndpoint(
        role=role,
        url=url,
        host=host,
        port=url.port or 5432,
        database=database,
        username=username,
        schema=schema,
        test_target=False,
    )

    test_mode = os.environ.get("MIGRATION_ALLOW_TEST_TARGET") == "1"
    if role == "source":
        if not _is_loopback(host):
            raise MigrationToolError(
                "The source must be a loopback PostgreSQL endpoint on the developer workstation."
            )
        if database != "portfolio_app" and not (test_mode and database.endswith("_test")):
            raise MigrationToolError(
                "Source must be portfolio_app or a test-only database ending in _test."
            )
        if test_mode:
            return DatabaseEndpoint(
                role=role,
                url=url,
                host=endpoint.host,
                port=endpoint.port,
                database=database,
                username=username,
                schema=schema,
                test_target=True,
            )
        return endpoint

    expected_host = _required_environment("MIGRATION_EXPECTED_TARGET_HOST").rstrip(".").lower()
    expected_database = _required_environment("MIGRATION_EXPECTED_TARGET_DATABASE")
    if "/" in expected_host or ":" in expected_host or "@" in expected_host:
        raise MigrationToolError("MIGRATION_EXPECTED_TARGET_HOST must be a hostname only.")
    if host != expected_host:
        raise MigrationToolError(
            "Resolved target endpoint does not match the explicitly expected host."
        )
    if database != expected_database:
        raise MigrationToolError(
            "Connected target database does not match the explicitly expected name."
        )
    if "-pooler." in host:
        raise MigrationToolError(
            "The target must use the direct PostgreSQL endpoint, not a pooler."
        )
    if not _is_loopback(host) and endpoint.sslmode not in {"require", "verify-ca", "verify-full"}:
        raise MigrationToolError(
            "A remote target must require TLS with sslmode=require or stronger."
        )
    if test_mode:
        if not _is_loopback(host) or not database.endswith("_test"):
            raise MigrationToolError(
                "Test-target mode is restricted to loopback databases whose name ends in _test."
            )
        endpoint = DatabaseEndpoint(
            role=role,
            url=url,
            host=host,
            port=endpoint.port,
            database=database,
            username=username,
            schema=schema,
            test_target=True,
        )
    elif not host.endswith(".neon.tech"):
        raise MigrationToolError("A migration target must be an explicit Neon direct endpoint.")
    elif not database.endswith("_migration"):
        raise MigrationToolError("An isolated Neon restore database name must end in _migration.")
    elif endpoint.port != 5432:
        raise MigrationToolError(
            "A direct Neon migration endpoint must use the PostgreSQL port 5432."
        )
    else:
        endpoint = DatabaseEndpoint(
            role=endpoint.role,
            url=endpoint.url,
            host=endpoint.host,
            port=endpoint.port,
            database=endpoint.database,
            username=endpoint.username,
            schema=endpoint.schema,
            test_target=False,
            neon_environment=_verify_neon_target_identity(endpoint),
        )
    return endpoint


def _connection_options(endpoint: DatabaseEndpoint, *, read_only: bool) -> str:
    values = [
        f"-c search_path={endpoint.schema}",
        "-c timezone=UTC",
        "-c statement_timeout=0",
    ]
    if read_only:
        values.append("-c default_transaction_read_only=on")
    return " ".join(values)


def connect_read_only(endpoint: DatabaseEndpoint) -> psycopg.Connection[Any]:
    try:
        connection = psycopg.connect(
            host=endpoint.host,
            port=endpoint.port,
            dbname=endpoint.database,
            user=endpoint.username,
            password=endpoint.password,
            connect_timeout=10,
            application_name=f"portfolio-migration-{endpoint.role}-readonly",
            options=_connection_options(endpoint, read_only=True),
            **dict[str, Any](_ssl_options(endpoint)),
        )
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return connection
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        raise MigrationToolError(
            f"Could not open the {endpoint.role} database as a read-only transaction{detail}."
        ) from None


def _ssl_options(endpoint: DatabaseEndpoint) -> dict[str, str]:
    allowed = {"sslmode", "sslrootcert", "sslcert", "sslkey"}
    return {
        key: str(value)
        for key, value in endpoint.url.query.items()
        if key in allowed and value is not None
    }


def connection_identity(
    connection: psycopg.Connection[Any],
    endpoint: DatabaseEndpoint,
    *,
    require_supported: bool = True,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT current_database(), current_schema(), inet_server_addr()::text,
               current_setting('server_version_num')::integer,
               current_setting('server_encoding'), current_setting('TimeZone'),
               d.datcollate, d.datctype, d.datlocprovider::text, d.datcollversion
          FROM pg_database AS d
         WHERE d.datname = current_database()
        """
    ).fetchone()
    if row is None:
        raise MigrationToolError("PostgreSQL did not return a database identity.")
    (
        database,
        schema,
        server_address,
        version_num,
        encoding,
        timezone_name,
        collate,
        ctype,
        provider,
        collversion,
    ) = row
    if database != endpoint.database or schema != endpoint.schema:
        raise MigrationToolError(
            "Connected database identity does not match the explicit target identity."
        )
    major = int(version_num) // 10000
    if require_supported and major != EXPECTED_POSTGRES_MAJOR:
        raise MigrationToolError(
            f"PostgreSQL {major} is unsupported; this migration chain requires "
            f"PostgreSQL {EXPECTED_POSTGRES_MAJOR}."
        )
    try:
        addresses = sorted(
            {
                str(item[4][0])
                for item in socket.getaddrinfo(
                    endpoint.host, endpoint.port, type=socket.SOCK_STREAM
                )
            }
        )
    except OSError:
        raise MigrationToolError(
            "The explicitly selected database hostname did not resolve."
        ) from None
    if not addresses:
        raise MigrationToolError(
            "The explicitly selected database hostname resolved to no addresses."
        )
    if (
        endpoint.role == "source"
        and not endpoint.test_target
        and (server_address is None or not ipaddress.ip_interface(server_address).ip.is_loopback)
    ):
        raise MigrationToolError("The source server did not resolve to a loopback address.")
    identity = {
        "role": endpoint.role,
        "endpoint_host": endpoint.host,
        "resolved_address_count": len(addresses),
        "resolved_addresses_sha256": hashlib.sha256(
            "\n".join(addresses).encode("utf-8")
        ).hexdigest(),
        "database": database,
        "schema": schema,
        "server_address": server_address,
        "server_version_num": int(version_num),
        "postgres_major": major,
        "server_encoding": encoding,
        "timezone": timezone_name,
        "database_collation": collate,
        "database_ctype": ctype,
        "locale_provider": provider,
        "collation_version": collversion,
    }
    if endpoint.neon_environment is not None:
        identity["neon_environment"] = dict(endpoint.neon_environment)
    return identity


def _schema_tables(connection: psycopg.Connection[Any], schema: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT table_name
          FROM information_schema.tables
         WHERE table_schema = %s AND table_type = 'BASE TABLE'
         ORDER BY table_name
        """,
        (schema,),
    ).fetchall()
    tables = [str(row[0]) for row in rows]
    unknown = sorted(set(tables) - set(TABLE_GROUP_BY_NAME) - METADATA_TABLES)
    if unknown:
        raise MigrationToolError(
            "The schema contains unclassified tables; review the inventory before migration."
        )
    missing = sorted(set(TABLE_GROUP_BY_NAME) - set(tables))
    if missing:
        raise MigrationToolError("The schema is missing tables from the current Alembic head.")
    return tables


def _primary_key_columns(connection: psycopg.Connection[Any], schema: str, table: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT kcu.column_name
          FROM information_schema.table_constraints AS tc
          JOIN information_schema.key_column_usage AS kcu
            ON kcu.constraint_catalog = tc.constraint_catalog
           AND kcu.constraint_schema = tc.constraint_schema
           AND kcu.constraint_name = tc.constraint_name
           AND kcu.table_schema = tc.table_schema
           AND kcu.table_name = tc.table_name
         WHERE tc.constraint_type = 'PRIMARY KEY'
           AND tc.table_schema = %s AND tc.table_name = %s
         ORDER BY kcu.ordinal_position
        """,
        (schema, table),
    ).fetchall()
    columns = [str(row[0]) for row in rows]
    if not columns:
        raise MigrationToolError("A database table has no primary key; reconciliation is unsafe.")
    return columns


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        normalized = value.astimezone(UTC) if value.tzinfo else value
        return {"$datetime": normalized.isoformat()}
    if isinstance(value, date) and not isinstance(value, datetime):
        return {"$date": value.isoformat()}
    if isinstance(value, time):
        return {"$time": value.isoformat()}
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"$bytes": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, float):
        return {"$float64": value.hex()}
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _json_from_postgres(value: str) -> Any:
    return json.loads(value, parse_float=Decimal, parse_int=int)


def _row_stream(
    connection: psycopg.Connection[Any], schema: str, table: str
) -> Iterator[tuple[tuple[Any, ...], bytes]]:
    pk = _primary_key_columns(connection, schema, table)
    selection = [sql.Identifier(column) for column in pk]
    query = sql.SQL(
        "SELECT {}, to_jsonb(row_value)::text FROM {}.{} AS row_value ORDER BY {}"
    ).format(
        sql.SQL(", ").join(selection),
        sql.Identifier(schema),
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in pk),
    )
    cursor_name = "migration_" + hashlib.sha256(f"{schema}.{table}".encode()).hexdigest()[:16]
    with connection.cursor(name=cursor_name) as cursor:
        cursor.execute(query)
        while rows := cursor.fetchmany(500):
            for row in rows:
                keys = tuple(row[:-1])
                payload = _canonical_json(_json_from_postgres(row[-1]))
                yield keys, payload


def _key_fingerprint(key: tuple[Any, ...]) -> str:
    return hashlib.sha256(_canonical_json(key)).hexdigest()


def table_fingerprint(
    connection: psycopg.Connection[Any], schema: str, table: str
) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for _, payload in _row_stream(connection, schema, table):
        digest.update(payload)
        digest.update(b"\n")
        count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def _sequence_states(connection: psycopg.Connection[Any], schema: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT sequencename
          FROM pg_sequences
         WHERE schemaname = %s
         ORDER BY sequencename
        """,
        (schema,),
    ).fetchall()
    states: dict[str, Any] = {}
    for (sequence_name,) in rows:
        statement = sql.SQL("SELECT last_value, is_called FROM {}.{}").format(
            sql.Identifier(schema), sql.Identifier(sequence_name)
        )
        try:
            last_value, is_called = _required_row(
                connection.execute(statement).fetchone(),
                "Sequence metadata is missing.",
            )
        except Exception:
            raise MigrationToolError(
                "Could not read a sequence state with the selected database role."
            ) from None
        states[str(sequence_name)] = {"last_value": int(last_value), "is_called": bool(is_called)}
    return states


def _normalize_constraint_definition(value: str) -> str:
    # PostgreSQL's deparser may expand varchar-array casts on a full dump/restore
    # round trip even though the check expression remains equivalent.
    normalized = value.replace("::character varying::text", "::text")
    normalized = normalized.replace("::character varying", "::text")
    return re.sub(r"\]\s*::text\[\]", "]", normalized)


def schema_descriptor(connection: psycopg.Connection[Any], schema: str) -> dict[str, Any]:
    tables = connection.execute(
        """
        SELECT c.relname, c.relkind::text, c.relpersistence::text
          FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND c.relkind IN ('r','p','v','m','f')
         ORDER BY c.relname
        """,
        (schema,),
    ).fetchall()
    columns = connection.execute(
        """
        SELECT c.relname, a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod),
               a.attnotnull, pg_catalog.pg_get_expr(d.adbin, d.adrelid),
               a.attidentity::text, a.attgenerated::text, coll.collname
          FROM pg_attribute AS a
          JOIN pg_class AS c ON c.oid = a.attrelid
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
          LEFT JOIN pg_attrdef AS d ON d.adrelid = c.oid AND d.adnum = a.attnum
          LEFT JOIN pg_collation AS coll ON coll.oid = a.attcollation
         WHERE n.nspname = %s AND c.relkind IN ('r','p','v','m')
           AND a.attnum > 0 AND NOT a.attisdropped
         ORDER BY c.relname, a.attnum
        """,
        (schema,),
    ).fetchall()
    constraints = connection.execute(
        """
        SELECT c.relname, con.conname, con.contype::text, con.convalidated,
               con.condeferrable, con.condeferred,
               pg_catalog.pg_get_constraintdef(con.oid, true)
          FROM pg_constraint AS con
          JOIN pg_class AS c ON c.oid = con.conrelid
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = %s
         ORDER BY c.relname, con.conname
        """,
        (schema,),
    ).fetchall()
    normalized_constraints = [
        (*row[:6], _normalize_constraint_definition(str(row[6]))) for row in constraints
    ]
    indexes = connection.execute(
        """
        SELECT tablename, indexname, indexdef FROM pg_indexes
         WHERE schemaname = %s ORDER BY tablename, indexname
        """,
        (schema,),
    ).fetchall()
    sequences = connection.execute(
        """
        SELECT sequence.relname, pg_catalog.format_type(seq.seqtypid, NULL),
               seq.seqstart, seq.seqmin, seq.seqmax, seq.seqincrement,
               seq.seqcycle, seq.seqcache, owner.relname, owner_column.attname
          FROM pg_class AS sequence
          JOIN pg_namespace AS n ON n.oid = sequence.relnamespace
          JOIN pg_sequence AS seq ON seq.seqrelid = sequence.oid
          LEFT JOIN pg_depend AS dependency
            ON dependency.classid = 'pg_class'::regclass
           AND dependency.objid = sequence.oid
           AND dependency.refclassid = 'pg_class'::regclass
           AND dependency.deptype IN ('a','i')
          LEFT JOIN pg_class AS owner ON owner.oid = dependency.refobjid
          LEFT JOIN pg_attribute AS owner_column
            ON owner_column.attrelid = owner.oid
           AND owner_column.attnum = dependency.refobjsubid
         WHERE n.nspname = %s AND sequence.relkind = 'S'
         ORDER BY sequence.relname
        """,
        (schema,),
    ).fetchall()
    types = connection.execute(
        """
        SELECT t.typname, t.typtype::text, format_type(t.oid, NULL),
               COALESCE(array_agg(e.enumlabel ORDER BY e.enumsortorder)
                        FILTER (WHERE e.enumlabel IS NOT NULL), ARRAY[]::text[])
          FROM pg_type AS t
          JOIN pg_namespace AS n ON n.oid = t.typnamespace
          LEFT JOIN pg_enum AS e ON e.enumtypid = t.oid
         WHERE n.nspname = %s AND t.typtype IN ('e','d','r')
         GROUP BY t.oid, t.typname, t.typtype
         ORDER BY t.typname
        """,
        (schema,),
    ).fetchall()
    triggers = connection.execute(
        """
        SELECT c.relname, t.tgname, pg_catalog.pg_get_triggerdef(t.oid, true)
          FROM pg_trigger AS t
          JOIN pg_class AS c ON c.oid = t.tgrelid
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND NOT t.tgisinternal
         ORDER BY c.relname, t.tgname
        """,
        (schema,),
    ).fetchall()
    extensions = connection.execute(
        """
        SELECT e.extname, e.extversion, n.nspname
          FROM pg_extension AS e JOIN pg_namespace AS n ON n.oid = e.extnamespace
         ORDER BY e.extname
        """
    ).fetchall()
    views = connection.execute(
        """
        SELECT c.relname, pg_catalog.pg_get_viewdef(c.oid, true)
          FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND c.relkind IN ('v','m')
         ORDER BY c.relname
        """,
        (schema,),
    ).fetchall()
    return {
        "tables": tables,
        "columns": columns,
        "constraints": normalized_constraints,
        "indexes": indexes,
        "sequences": sequences,
        "types": types,
        "triggers": triggers,
        "extensions": extensions,
        "views": views,
    }


def schema_fingerprint(connection: psycopg.Connection[Any], schema: str) -> str:
    descriptor = schema_descriptor(connection, schema)
    return hashlib.sha256(_canonical_json(descriptor)).hexdigest()


def extension_inventory(connection: psycopg.Connection[Any]) -> list[list[str]]:
    return [
        [str(value) for value in row]
        for row in connection.execute(
            """
            SELECT e.extname, e.extversion, n.nspname
              FROM pg_extension AS e JOIN pg_namespace AS n ON n.oid = e.extnamespace
             ORDER BY e.extname
            """
        ).fetchall()
    ]


def _additional_user_schemas(
    connection: psycopg.Connection[Any], selected_schema: str
) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            """
            SELECT nspname FROM pg_namespace
             WHERE nspname <> %s
               AND nspname NOT IN ('pg_catalog', 'information_schema')
               AND left(nspname, 3) <> 'pg_'
             ORDER BY nspname
            """,
            (selected_schema,),
        ).fetchall()
    ]


def alembic_heads(connection: psycopg.Connection[Any], schema: str) -> list[str]:
    try:
        rows = connection.execute(
            sql.SQL("SELECT version_num FROM {}.alembic_version ORDER BY version_num").format(
                sql.Identifier(schema)
            )
        ).fetchall()
    except Exception:
        raise MigrationToolError("Alembic version metadata is missing or unreadable.") from None
    return sorted(str(row[0]) for row in rows)


def _exact_expected_heads() -> list[str]:
    return sorted(expected_heads())


def _foreign_key_status(connection: psycopg.Connection[Any], schema: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT count(*) FILTER (WHERE NOT con.convalidated)::integer,
               count(*)::integer
          FROM pg_constraint AS con
          JOIN pg_class AS c ON c.oid = con.conrelid
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND con.contype = 'f'
        """,
        (schema,),
    ).fetchone()
    rows = _required_row(rows, "Foreign-key metadata is unavailable.")
    return {"unvalidated": int(rows[0]), "total": int(rows[1])}


def _foreign_key_cycles(connection: psycopg.Connection[Any], schema: str) -> list[list[str]]:
    rows = connection.execute(
        """
        SELECT source.relname, target.relname
          FROM pg_constraint AS con
          JOIN pg_class AS source ON source.oid = con.conrelid
          JOIN pg_namespace AS source_schema ON source_schema.oid = source.relnamespace
          JOIN pg_class AS target ON target.oid = con.confrelid
          JOIN pg_namespace AS target_schema ON target_schema.oid = target.relnamespace
         WHERE con.contype = 'f'
           AND source_schema.nspname = %s AND target_schema.nspname = %s
        """,
        (schema, schema),
    ).fetchall()
    graph: dict[str, set[str]] = {}
    for source, target in rows:
        graph.setdefault(str(source), set()).add(str(target))
        graph.setdefault(str(target), set())

    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []
    next_index = 0

    def visit(node: str) -> None:
        nonlocal next_index
        indexes[node] = next_index
        lowlinks[node] = next_index
        next_index += 1
        stack.append(node)
        on_stack.add(node)
        for neighbor in sorted(graph[node]):
            if neighbor not in indexes:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[neighbor])
        if lowlinks[node] == indexes[node]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1 or node in graph[node]:
                cycles.append(sorted(component))

    for node in sorted(graph):
        if node not in indexes:
            visit(node)
    return sorted(cycles)


def _database_privileges(connection: psycopg.Connection[Any], schema: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT c.relname, c.relkind::text,
               CASE WHEN c.relkind = 'S'
                    THEN has_sequence_privilege(current_user, c.oid, 'UPDATE')
                    ELSE has_table_privilege(current_user, c.oid, 'INSERT') END AS can_restore
          FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND c.relkind IN ('r','p','S')
         ORDER BY c.relname
        """,
        (schema,),
    ).fetchall()
    missing = [str(row[0]) for row in rows if not row[2]]
    privilege_row = connection.execute(
        """
        SELECT has_schema_privilege(current_user, %s, 'USAGE'),
               has_schema_privilege(current_user, %s, 'CREATE')
        """,
        (schema, schema),
    ).fetchone()
    schema_usage, schema_create = _required_row(
        privilege_row, "Schema privilege metadata is unavailable."
    )
    return {
        "schema_usage": bool(schema_usage),
        "schema_create": bool(schema_create),
        "tables_without_insert_or_sequence_update": missing,
    }


def _public_object_count(connection: psycopg.Connection[Any], schema: str) -> int:
    row = connection.execute(
        """
            SELECT
                (SELECT count(*) FROM pg_class AS c
                  JOIN pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = %s AND c.relkind IN ('r','p','v','m','S','f'))
              + (SELECT count(*) FROM pg_type AS t
                  JOIN pg_namespace AS n ON n.oid = t.typnamespace
                 WHERE n.nspname = %s
                   AND (t.typtype IN ('e','d','r') OR (t.typtype = 'c' AND t.typrelid = 0)))
              + (SELECT count(*) FROM pg_proc AS p
                  JOIN pg_namespace AS n ON n.oid = p.pronamespace
                 WHERE n.nspname = %s)
              + (SELECT count(*) FROM pg_operator AS o
                  JOIN pg_namespace AS n ON n.oid = o.oprnamespace
                 WHERE n.nspname = %s)
              + (SELECT count(*) FROM pg_collation AS c
                  JOIN pg_namespace AS n ON n.oid = c.collnamespace
                 WHERE n.nspname = %s)
        """,
        (schema, schema, schema, schema, schema),
    ).fetchone()
    return int(_required_row(row, "Public schema inventory is unavailable.")[0])


def _table_size(connection: psycopg.Connection[Any], schema: str, table: str) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT pg_table_size(c.oid)::bigint,
               pg_indexes_size(c.oid)::bigint,
               pg_total_relation_size(c.oid)::bigint
          FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND c.relname = %s
        """,
        (schema, table),
    ).fetchone()
    if row is None:
        raise MigrationToolError("Could not measure a database relation.")
    return {
        "table_and_toast_bytes": int(row[0]),
        "index_bytes": int(row[1]),
        "total_bytes": int(row[2]),
    }


def _table_report(
    connection: psycopg.Connection[Any], schema: str, *, with_fingerprints: bool
) -> dict[str, Any]:
    tables = _schema_tables(connection, schema)
    report: dict[str, Any] = {}
    for table in tables:
        row = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        ).fetchone()
        row_count = int(_required_row(row, "Could not count a database table.")[0])
        entry: dict[str, Any] = {
            "group": TABLE_GROUP_BY_NAME.get(table, "migration_metadata"),
            "classification": _table_classification(table),
            "rows": row_count,
            **_table_size(connection, schema, table),
        }
        if with_fingerprints and table not in TRANSIENT_TABLES:
            entry.update(table_fingerprint(connection, schema, table))
        report[table] = entry
    return report


def _table_classification(table: str) -> str:
    if table in METADATA_TABLES:
        return "alembic_metadata_included_and_checked"
    if table in MIGRATION_SEEDED_TABLES:
        return "migration_seeded_reference_data_included"
    if table in TRANSIENT_TABLES:
        return "transient_runtime_state_excluded"
    return "canonical_or_append_only_data"


def _identity_and_schema(
    connection: psycopg.Connection[Any], endpoint: DatabaseEndpoint, *, strict_head: bool
) -> dict[str, Any]:
    identity = connection_identity(connection, endpoint)
    if endpoint.schema != APP_SCHEMA and not endpoint.test_target:
        raise MigrationToolError(
            "Production migration operations are restricted to the public schema."
        )
    heads = alembic_heads(connection, endpoint.schema)
    foreign_key_cycles = _foreign_key_cycles(connection, endpoint.schema)
    if strict_head and heads != _exact_expected_heads():
        raise MigrationToolError(
            "Database Alembic revision does not match the checked-in migration head."
        )
    tables = _schema_tables(connection, endpoint.schema)
    if not set(Base.metadata.tables).issubset(set(tables)):
        raise MigrationToolError("Database tables do not match the application model registry.")
    large_object_count = int(
        _required_row(
            connection.execute("SELECT count(*) FROM pg_largeobject_metadata").fetchone(),
            "Could not count PostgreSQL large objects.",
        )[0]
    )
    identity.update(
        {
            "alembic_heads": heads,
            "expected_alembic_heads": _exact_expected_heads(),
            "table_count": len(tables),
            "schema_fingerprint": schema_fingerprint(connection, endpoint.schema),
            "extensions": extension_inventory(connection),
            "additional_user_schemas": _additional_user_schemas(connection, endpoint.schema),
            "foreign_keys": _foreign_key_status(connection, endpoint.schema),
            "foreign_key_cycles": foreign_key_cycles,
            "data_only_restore_compatible": not foreign_key_cycles,
            "large_object_count": large_object_count,
            "restore_privileges": _database_privileges(connection, endpoint.schema),
        }
    )
    return identity


def inventory(endpoint: DatabaseEndpoint, *, with_fingerprints: bool = False) -> dict[str, Any]:
    try:
        with connect_read_only(endpoint) as connection:
            identity = _identity_and_schema(connection, endpoint, strict_head=True)
            tables = _table_report(connection, endpoint.schema, with_fingerprints=with_fingerprints)
            db_size = int(
                _required_row(
                    connection.execute(
                        "SELECT pg_database_size(current_database())::bigint"
                    ).fetchone(),
                    "Could not read database size.",
                )[0]
            )
            sequences = _sequence_states(connection, endpoint.schema)
            return {
                "identity": identity,
                "database_bytes": db_size,
                "table_and_toast_bytes": sum(v["table_and_toast_bytes"] for v in tables.values()),
                "index_bytes": sum(v["index_bytes"] for v in tables.values()),
                "relations_bytes": sum(v["total_bytes"] for v in tables.values()),
                "sequences": sequences,
                "tables": tables,
            }
    except MigrationToolError:
        raise
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        raise MigrationToolError(f"Read-only inventory failed{detail}.") from None


def capacity(endpoint: DatabaseEndpoint) -> dict[str, Any]:
    try:
        with connect_read_only(endpoint) as connection:
            identity = connection_identity(connection, endpoint)
            return {
                "identity": identity,
                "database_bytes": int(
                    _required_row(
                        connection.execute(
                            "SELECT pg_database_size(current_database())::bigint"
                        ).fetchone(),
                        "Could not read database size.",
                    )[0]
                ),
                "public_object_count": _public_object_count(connection, endpoint.schema),
                "database_quota_bytes": None,
                "quota_note": "Check provider console for project quota and branch limits.",
            }
    except MigrationToolError:
        raise
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        raise MigrationToolError(f"Read-only capacity report failed{detail}.") from None


def schema_check(source: DatabaseEndpoint, target: DatabaseEndpoint) -> dict[str, Any]:
    _source_target_distinct(source, target)
    try:
        with (
            connect_read_only(source) as source_connection,
            connect_read_only(target) as target_connection,
        ):
            source_identity = _identity_and_schema(source_connection, source, strict_head=True)
            target_identity = connection_identity(
                target_connection, target, require_supported=False
            )
            target_objects = _public_object_count(target_connection, target.schema)
            privileges = _database_privileges(target_connection, target.schema)
            target_extensions = extension_inventory(target_connection)
            target_extra_schemas = _additional_user_schemas(target_connection, target.schema)
            target_identity.update(
                {
                    "public_object_count": target_objects,
                    "restore_privileges": privileges,
                    "extensions": target_extensions,
                    "additional_user_schemas": target_extra_schemas,
                }
            )
            blockers: list[dict[str, Any]] = []
            for field_name in (
                "postgres_major",
                "server_encoding",
                "database_collation",
                "database_ctype",
                "locale_provider",
                "collation_version",
                "extensions",
            ):
                if source_identity[field_name] != target_identity[field_name]:
                    blockers.append(
                        {
                            "code": f"{field_name}_differs",
                            "source": source_identity[field_name],
                            "target": target_identity[field_name],
                        }
                    )
            if source_identity["foreign_keys"]["unvalidated"]:
                blockers.append(
                    {
                        "code": "source_has_unvalidated_foreign_keys",
                        "count": source_identity["foreign_keys"]["unvalidated"],
                    }
                )
            if source_identity["additional_user_schemas"]:
                blockers.append(
                    {
                        "code": "source_has_additional_user_schemas",
                        "schemas": source_identity["additional_user_schemas"],
                    }
                )
            if target_extra_schemas:
                blockers.append(
                    {
                        "code": "target_has_additional_user_schemas",
                        "schemas": target_extra_schemas,
                    }
                )
            if target_objects == 0:
                if not privileges["schema_usage"] or not privileges["schema_create"]:
                    blockers.append(
                        {
                            "code": "target_schema_restore_privileges_missing",
                            "required": ["USAGE", "CREATE"],
                            "actual": privileges,
                        }
                    )
                return {
                    "status": "BLOCKED" if blockers else "EMPTY_TARGET_COMPATIBLE_FOR_FULL_RESTORE",
                    "restore_format": "postgres-custom-full-schema-and-data",
                    "blockers": blockers,
                    "source": source_identity,
                    "target": target_identity,
                    "data_only_restore_compatible": source_identity["data_only_restore_compatible"],
                }
            source_descriptor = schema_descriptor(source_connection, source.schema)
            target_descriptor = schema_descriptor(target_connection, target.schema)
            source_fingerprint = hashlib.sha256(_canonical_json(source_descriptor)).hexdigest()
            target_fingerprint = hashlib.sha256(_canonical_json(target_descriptor)).hexdigest()
            target_identity["schema_fingerprint"] = target_fingerprint
            target_identity["alembic_heads"] = _schema_alembic_heads(
                target_connection, target.schema
            )
            target_identity["foreign_keys"] = _foreign_key_status(target_connection, target.schema)
            target_identity["additional_user_schemas"] = _additional_user_schemas(
                target_connection, target.schema
            )
            target_identity["table_count"] = len(
                target_connection.execute(
                    """
                    SELECT table_name FROM information_schema.tables
                     WHERE table_schema = %s AND table_type = 'BASE TABLE'
                    """,
                    (target.schema,),
                ).fetchall()
            )
            if source_fingerprint != target_fingerprint:
                blockers.append(
                    {
                        "code": "schema_definitions_differ",
                        "source_fingerprint": source_fingerprint,
                        "target_fingerprint": target_fingerprint,
                        "objects": _schema_difference_summary(source_descriptor, target_descriptor),
                    }
                )
            if source_identity["alembic_heads"] != target_identity["alembic_heads"]:
                blockers.append(
                    {
                        "code": "alembic_revisions_differ",
                        "source": source_identity["alembic_heads"],
                        "target": target_identity["alembic_heads"],
                    }
                )
            if target_identity["foreign_keys"]["unvalidated"]:
                blockers.append(
                    {
                        "code": "target_has_unvalidated_foreign_keys",
                        "count": target_identity["foreign_keys"]["unvalidated"],
                    }
                )
            if privileges["tables_without_insert_or_sequence_update"]:
                blockers.append(
                    {
                        "code": "target_table_or_sequence_restore_privileges_missing",
                        "objects": privileges["tables_without_insert_or_sequence_update"],
                    }
                )
            if not privileges["schema_usage"] or not privileges["schema_create"]:
                blockers.append(
                    {
                        "code": "target_schema_restore_privileges_missing",
                        "required": ["USAGE", "CREATE"],
                        "actual": privileges,
                    }
                )
            return {
                "status": "BLOCKED" if blockers else "SCHEMAS_MATCH",
                "blockers": blockers,
                "source": source_identity,
                "target": target_identity,
                "data_only_restore_compatible": source_identity["data_only_restore_compatible"],
            }
    except MigrationToolError:
        raise
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        traceback = error.__traceback__
        tool_frame = None
        while traceback is not None:
            if traceback.tb_frame.f_code.co_filename.endswith("postgres_migration.py"):
                tool_frame = traceback
            traceback = traceback.tb_next
        location = (
            f" at {tool_frame.tb_frame.f_code.co_name}:{tool_frame.tb_lineno}"
            if tool_frame is not None
            else ""
        )
        raise MigrationToolError(
            f"Schema compatibility check failed ({type(error).__name__}){detail}{location}."
        ) from None


def _schema_alembic_heads(connection: psycopg.Connection[Any], schema: str) -> list[str]:
    row = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
             WHERE table_schema = %s AND table_name = 'alembic_version'
        )
        """,
        (schema,),
    ).fetchone()
    if not _required_row(row, "Could not inspect target migration metadata.")[0]:
        return []
    return alembic_heads(connection, schema)


def _schema_difference_summary(
    source: dict[str, Any], target: dict[str, Any], *, limit: int = 50
) -> dict[str, Any]:
    """Show changed schema object names without exposing definitions or row data."""
    identity_functions: dict[str, Callable[[Any], str]] = {
        "tables": lambda row: str(row[0]),
        "columns": lambda row: f"{row[0]}.{row[1]}",
        "constraints": lambda row: f"{row[0]}.{row[1]}",
        "indexes": lambda row: f"{row[0]}.{row[1]}",
        "sequences": lambda row: str(row[0]),
        "types": lambda row: str(row[0]),
        "triggers": lambda row: f"{row[0]}.{row[1]}",
        "extensions": lambda row: str(row[0]),
        "views": lambda row: str(row[0]),
    }
    field_names = {
        "tables": {1: "relation_kind", 2: "persistence"},
        "columns": {
            2: "data_type",
            3: "not_null",
            4: "default_changed",
            5: "identity",
            6: "generated",
            7: "collation",
        },
        "constraints": {
            2: "constraint_type",
            3: "validated",
            4: "deferrable",
            5: "initially_deferred",
            6: "definition_changed",
        },
        "indexes": {2: "definition_changed"},
        "sequences": {
            1: "sequence_type",
            2: "start",
            3: "minimum",
            4: "maximum",
            5: "increment",
            6: "cycle",
            7: "cache",
            8: "owner_changed",
            9: "owner_column_changed",
        },
        "types": {1: "type_kind", 2: "type_definition", 3: "labels_changed"},
        "triggers": {2: "definition_changed"},
        "extensions": {1: "version", 2: "schema"},
        "views": {1: "definition_changed"},
    }
    summary: dict[str, Any] = {}
    for section, identity_of in identity_functions.items():
        source_items = {identity_of(row): row for row in source.get(section, [])}
        target_items = {identity_of(row): row for row in target.get(section, [])}
        source_keys = set(source_items)
        target_keys = set(target_items)
        added = sorted(target_keys - source_keys)
        removed = sorted(source_keys - target_keys)
        changed = []
        for key in sorted(source_keys & target_keys):
            source_row = source_items[key]
            target_row = target_items[key]
            if source_row != target_row:
                fields = field_names[section]
                changed.append(
                    {
                        "name": key,
                        "fields": [
                            fields[index]
                            for index, (source_value, target_value) in enumerate(
                                zip(source_row, target_row, strict=True)
                            )
                            if source_value != target_value
                        ],
                    }
                )
        if added or removed or changed:
            summary[section] = {
                "added": added[:limit],
                "added_count": len(added),
                "removed": removed[:limit],
                "removed_count": len(removed),
                "changed": changed[:limit],
                "changed_count": len(changed),
                "truncated": len(added) > limit or len(removed) > limit or len(changed) > limit,
            }
    return summary


def _source_target_distinct(source: DatabaseEndpoint, target: DatabaseEndpoint) -> None:
    if (source.host, source.port, source.database, source.schema) == (
        target.host,
        target.port,
        target.database,
        target.schema,
    ):
        raise MigrationToolError("Source and target resolve to the same database identity.")


def _assert_target_schema_matches_source(
    source_connection: psycopg.Connection[Any],
    target_connection: psycopg.Connection[Any],
    source: DatabaseEndpoint,
    target: DatabaseEndpoint,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_identity = _identity_and_schema(source_connection, source, strict_head=True)
    target_identity = _identity_and_schema(target_connection, target, strict_head=True)
    for field_name in (
        "postgres_major",
        "server_encoding",
        "database_collation",
        "database_ctype",
        "locale_provider",
        "collation_version",
        "extensions",
    ):
        if source_identity[field_name] != target_identity[field_name]:
            raise MigrationToolError(f"Source and target {field_name} values are incompatible.")
    if source_identity["schema_fingerprint"] != target_identity["schema_fingerprint"]:
        raise MigrationToolError("Source and target schema definitions do not match exactly.")
    if source_identity["alembic_heads"] != target_identity["alembic_heads"]:
        raise MigrationToolError("Source and target Alembic revisions do not match.")
    if (
        source_identity["foreign_keys"]["unvalidated"]
        or target_identity["foreign_keys"]["unvalidated"]
    ):
        raise MigrationToolError("Source or target contains an unvalidated foreign key.")
    if target_identity["restore_privileges"]["tables_without_insert_or_sequence_update"]:
        raise MigrationToolError(
            "The target role lacks privileges required to restore all tables/sequences."
        )
    if not target_identity["restore_privileges"]["schema_usage"]:
        raise MigrationToolError("The target role lacks USAGE on the selected schema.")
    if not target_identity["restore_privileges"]["schema_create"]:
        raise MigrationToolError("The target role lacks CREATE on the selected schema.")
    return source_identity, target_identity


def compare_table(
    source_connection: psycopg.Connection[Any],
    target_connection: psycopg.Connection[Any],
    source_schema: str,
    target_schema: str,
    table: str,
    *,
    sample_limit: int = 20,
) -> dict[str, Any]:
    source_rows = iter(_row_stream(source_connection, source_schema, table))
    target_rows = iter(_row_stream(target_connection, target_schema, table))
    source_item = next(source_rows, None)
    target_item = next(target_rows, None)
    result: dict[str, Any] = {
        "table": table,
        "source_rows": 0,
        "target_rows": 0,
        "source_sha256": hashlib.sha256(),
        "target_sha256": hashlib.sha256(),
        "missing_in_target": 0,
        "extra_in_target": 0,
        "changed_rows": 0,
        "difference_key_sha256": [],
    }

    def record(digest: Any, item: tuple[tuple[Any, ...], bytes], count_key: str) -> None:
        digest.update(item[1])
        digest.update(b"\n")
        result[count_key] += 1

    while source_item is not None or target_item is not None:
        if target_item is None or (source_item is not None and source_item[0] < target_item[0]):
            assert source_item is not None
            record(result["source_sha256"], source_item, "source_rows")
            result["missing_in_target"] += 1
            if len(result["difference_key_sha256"]) < sample_limit:
                result["difference_key_sha256"].append(_key_fingerprint(source_item[0]))
            source_item = next(source_rows, None)
            continue
        if source_item is None or target_item[0] < source_item[0]:
            assert target_item is not None
            record(result["target_sha256"], target_item, "target_rows")
            result["extra_in_target"] += 1
            if len(result["difference_key_sha256"]) < sample_limit:
                result["difference_key_sha256"].append(_key_fingerprint(target_item[0]))
            target_item = next(target_rows, None)
            continue

        assert source_item is not None and target_item is not None
        record(result["source_sha256"], source_item, "source_rows")
        record(result["target_sha256"], target_item, "target_rows")
        if source_item[1] != target_item[1]:
            result["changed_rows"] += 1
            if len(result["difference_key_sha256"]) < sample_limit:
                result["difference_key_sha256"].append(_key_fingerprint(source_item[0]))
        source_item = next(source_rows, None)
        target_item = next(target_rows, None)

    result["source_sha256"] = result["source_sha256"].hexdigest()
    result["target_sha256"] = result["target_sha256"].hexdigest()
    result["matches"] = not (
        result["missing_in_target"] or result["extra_in_target"] or result["changed_rows"]
    )
    return result


def _sequence_state_diff(
    source_connection: psycopg.Connection[Any],
    target_connection: psycopg.Connection[Any],
    source: DatabaseEndpoint,
    target: DatabaseEndpoint,
) -> dict[str, Any]:
    source_states = _sequence_states(source_connection, source.schema)
    target_states = _sequence_states(target_connection, target.schema)
    return {
        name: {"source": source_states.get(name), "target": target_states.get(name)}
        for name in sorted(set(source_states) | set(target_states))
        if source_states.get(name) != target_states.get(name)
    }


def reconcile(source: DatabaseEndpoint, target: DatabaseEndpoint) -> dict[str, Any]:
    _source_target_distinct(source, target)
    try:
        with (
            connect_read_only(source) as source_connection,
            connect_read_only(target) as target_connection,
        ):
            source_identity, target_identity = _assert_target_schema_matches_source(
                source_connection, target_connection, source, target
            )
            source_tables = _schema_tables(source_connection, source.schema)
            target_tables = _schema_tables(target_connection, target.schema)
            if source_tables != target_tables:
                raise MigrationToolError("Source and target table inventories do not match.")
            tables: dict[str, Any] = {}
            for table in source_tables:
                if table in TRANSIENT_TABLES:
                    continue
                tables[table] = compare_table(
                    source_connection, target_connection, source.schema, target.schema, table
                )
            sequence_differences = _sequence_state_diff(
                source_connection, target_connection, source, target
            )
            differences = [name for name, value in tables.items() if not value["matches"]]
            return {
                "status": "MATCH"
                if not differences and not sequence_differences
                else "DIFFERENCES_FOUND",
                "source": source_identity,
                "target": target_identity,
                "table_differences": differences,
                "sequence_differences": sequence_differences,
                "tables": tables,
            }
    except MigrationToolError:
        raise
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        raise MigrationToolError(f"Source-to-target reconciliation failed{detail}.") from None


def _safe_output_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[4]
    if path == repository_root or path.is_relative_to(repository_root):
        raise MigrationToolError(
            "Migration artifacts and reports must be stored outside the repository."
        )
    return path


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as archive:
        while chunk := archive.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _native_tool_environment(
    endpoint: DatabaseEndpoint, *, application_name: str | None = None
) -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if (
            name.startswith(("MIGRATION_", "NEON_"))
            or name == "DATABASE_URL"
            or name.endswith("_DATABASE_URL")
        ):
            environment.pop(name, None)
    for name in (
        "PGHOST",
        "PGPORT",
        "PGUSER",
        "PGPASSWORD",
        "PGDATABASE",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSSLMODE",
        "PGSSLROOTCERT",
        "PGSSLCERT",
        "PGSSLKEY",
        "PGOPTIONS",
        "PGCONNECT_TIMEOUT",
        "PGAPPNAME",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "PGHOST": endpoint.host,
            "PGPORT": str(endpoint.port),
            "PGUSER": endpoint.username,
            "PGDATABASE": endpoint.database,
            "PGAPPNAME": application_name or f"portfolio-migration-{endpoint.role}",
            "PGOPTIONS": _connection_options(endpoint, read_only=endpoint.role == "source"),
            "PGCONNECT_TIMEOUT": "10",
        }
    )
    if endpoint.password is not None:
        environment["PGPASSWORD"] = endpoint.password
    if endpoint.sslmode:
        environment["PGSSLMODE"] = endpoint.sslmode
    for key, env_name in (
        ("sslrootcert", "PGSSLROOTCERT"),
        ("sslcert", "PGSSLCERT"),
        ("sslkey", "PGSSLKEY"),
    ):
        value = endpoint.url.query.get(key)
        if value is not None:
            environment[env_name] = str(value)
    return environment


def _container_tool_prefix(
    endpoint: DatabaseEndpoint, container: str, *, application_name: str | None = None
) -> list[str]:
    if not endpoint.test_target and not (
        _is_loopback(endpoint.host) and endpoint.database.endswith("_test")
    ):
        raise MigrationToolError(
            "A PostgreSQL tools container may be used only with a disposable _test database."
        )
    if not _is_loopback(endpoint.host) or not endpoint.database.endswith("_test"):
        raise MigrationToolError(
            "Containerized PostgreSQL tools require a loopback _test database."
        )
    docker = shutil.which("docker")
    if not docker:
        raise MigrationToolError(
            "Docker is required for the configured disposable PostgreSQL tools container."
        )
    return [
        docker,
        "exec",
        "--interactive",
        "--env",
        "PGHOST=127.0.0.1",
        "--env",
        "PGPORT=5432",
        "--env",
        f"PGUSER={endpoint.username}",
        "--env",
        f"PGDATABASE={endpoint.database}",
        "--env",
        f"PGAPPNAME={application_name or f'portfolio-migration-{endpoint.role}'}",
        "--env",
        _container_pgoptions(endpoint),
        "--env",
        "PGCONNECT_TIMEOUT=10",
        *(["--env", f"PGPASSWORD={endpoint.password}"] if endpoint.password is not None else []),
        *(["--env", f"PGSSLMODE={endpoint.sslmode}"] if endpoint.sslmode else []),
        container,
    ]


def _container_pgoptions(endpoint: DatabaseEndpoint) -> str:
    return "PGOPTIONS=" + _connection_options(endpoint, read_only=endpoint.role == "source")


def _tool_prefix(
    endpoint: DatabaseEndpoint, tool_name: str, *, application_name: str | None = None
) -> tuple[list[str], dict[str, str] | None]:
    container = os.environ.get("MIGRATION_PG_TOOLS_CONTAINER", "").strip()
    if container:
        return [
            *_container_tool_prefix(endpoint, container, application_name=application_name),
            tool_name,
        ], None
    executable = shutil.which(tool_name)
    if not executable:
        raise MigrationToolError(
            f"{tool_name} is required. Install PostgreSQL 18 client tools or use the "
            "CI-only _test container setting."
        )
    return [executable], _native_tool_environment(endpoint, application_name=application_name)


def _tool_major(endpoint: DatabaseEndpoint, tool_name: str) -> int:
    prefix, environment = _tool_prefix(endpoint, tool_name)
    try:
        result = subprocess.run(
            [*prefix, "--version"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except Exception:
        raise MigrationToolError(f"Could not execute {tool_name}.") from None
    if result.returncode != 0:
        raise MigrationToolError(f"Could not read the installed {tool_name} version.")
    match = re.search(r"\b(?:pg_dump|pg_restore)\s+\(PostgreSQL\)\s+(\d+)", result.stdout)
    if not match:
        raise MigrationToolError(f"Could not parse the installed {tool_name} version.")
    major = int(match.group(1))
    if major != EXPECTED_POSTGRES_MAJOR:
        raise MigrationToolError(
            f"{tool_name} major version {major} does not match "
            f"PostgreSQL {EXPECTED_POSTGRES_MAJOR}."
        )
    return major


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


def _cancel_restore_backend(endpoint: DatabaseEndpoint, application_name: str) -> None:
    """Terminate and confirm the unique pg_restore session after local interruption."""
    try:
        with psycopg.connect(
            host=endpoint.host,
            port=endpoint.port,
            dbname=endpoint.database,
            user=endpoint.username,
            password=endpoint.password,
            connect_timeout=10,
            application_name="portfolio-migration-interrupt-cleanup",
            **dict[str, Any](_ssl_options(endpoint)),
        ) as connection:
            connection.autocommit = True
            for _ in range(30):
                rows = connection.execute(
                    """
                    SELECT pid
                      FROM pg_stat_activity
                     WHERE datname = %s AND usename = %s AND application_name = %s
                       AND pid <> pg_backend_pid()
                    """,
                    (endpoint.database, endpoint.username, application_name),
                ).fetchall()
                if not rows:
                    return
                for (pid,) in rows:
                    connection.execute("SELECT pg_terminate_backend(%s)", (int(pid),))
                time_module.sleep(0.1)
    except Exception:
        raise MigrationToolError(
            "Restore interruption could not confirm termination of the target session; "
            "discard the target database."
        ) from None
    raise MigrationToolError(
        "Restore interruption left a target session active; discard the target database."
    )


def _run_tool_capture(
    endpoint: DatabaseEndpoint,
    tool_name: str,
    arguments: Sequence[str],
    *,
    stdin_file: Path | None = None,
    timeout: int = 1800,
) -> bytes:
    prefix, environment = _tool_prefix(endpoint, tool_name)
    command = [*prefix, *arguments]
    try:
        with stdin_file.open("rb") if stdin_file else open(os.devnull, "rb") as standard_input:
            process = subprocess.Popen(
                command,
                stdin=standard_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
            )
            try:
                stdout, _ = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _stop_process(process)
                raise MigrationToolError(
                    f"{tool_name} exceeded the configured time limit."
                ) from None
            except KeyboardInterrupt:
                _stop_process(process)
                raise MigrationToolError(
                    f"{tool_name} interrupted; the child process was stopped."
                ) from None
    except subprocess.TimeoutExpired:
        raise MigrationToolError(f"{tool_name} exceeded the configured time limit.") from None
    except MigrationToolError:
        raise
    except Exception:
        raise MigrationToolError(f"Could not execute {tool_name}.") from None
    if process.returncode:
        raise MigrationToolError(
            f"{tool_name} failed with exit code {process.returncode}; tool details were withheld."
        )
    return stdout


def _run_pg_dump_to_file(
    endpoint: DatabaseEndpoint,
    snapshot: str,
    schema: str,
    output: Path,
) -> None:
    prefix, environment = _tool_prefix(endpoint, "pg_dump")
    excluded = [
        f"--exclude-table-data={schema}.{table}" for table in sorted(EXCLUDED_ARCHIVE_TABLES)
    ]
    arguments = [
        "--no-password",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--no-comments",
        "--snapshot",
        snapshot,
        *excluded,
        "--dbname",
        endpoint.database,
    ]
    try:
        with output.open("wb") as target:
            if os.environ.get("MIGRATION_PG_TOOLS_CONTAINER", "").strip():
                process = subprocess.Popen(
                    [*prefix, *arguments],
                    stdin=subprocess.DEVNULL,
                    stdout=target,
                    stderr=subprocess.PIPE,
                    env=environment,
                )
            else:
                process = subprocess.Popen(
                    [*prefix, "--file", str(output), *arguments],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    env=environment,
                )
            try:
                process.communicate(timeout=3600)
            except subprocess.TimeoutExpired:
                _stop_process(process)
                raise MigrationToolError("pg_dump exceeded the configured time limit.") from None
            except KeyboardInterrupt:
                _stop_process(process)
                raise MigrationToolError(
                    "pg_dump interrupted; the temporary archive will be removed."
                ) from None
    except subprocess.TimeoutExpired:
        raise MigrationToolError("pg_dump exceeded the configured time limit.") from None
    except MigrationToolError:
        raise
    except Exception:
        raise MigrationToolError("Could not execute pg_dump.") from None
    if process.returncode:
        raise MigrationToolError(
            f"pg_dump failed with exit code {process.returncode}; tool details were withheld."
        )


def _archive_toc(
    endpoint: DatabaseEndpoint,
    archive: Path,
    *,
    expected_schema_tables: set[str],
    expected_data_tables: set[str],
    expected_sequences: set[str],
) -> dict[str, Any]:
    toc = _run_tool_capture(endpoint, "pg_restore", ["--list"], stdin_file=archive)
    allowed_kinds = {
        "TABLE",
        "TABLE DATA",
        "SEQUENCE",
        "SEQUENCE OWNED BY",
        "SEQUENCE SET",
        "CONSTRAINT",
        "INDEX",
        "FK CONSTRAINT",
    }
    kinds: list[str] = []
    schema_tables: set[str] = set()
    data_tables: set[str] = set()
    sequences: set[str] = set()
    for raw_line in toc.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if ";" not in line:
            raise MigrationToolError("Backup archive has an unrecognized table-of-contents entry.")
        words = line.split(";", 1)[1].strip().split()
        if len(words) < 5:
            raise MigrationToolError("Backup archive has an incomplete table-of-contents entry.")
        kind = str(words[2])
        if kind == "TABLE" and len(words) > 3 and words[3] == "DATA":
            kind = "TABLE DATA"
        elif kind == "FK" and len(words) > 3 and words[3] == "CONSTRAINT":
            kind = "FK CONSTRAINT"
        elif kind == "SEQUENCE" and len(words) > 3:
            if words[3] == "SET":
                kind = "SEQUENCE SET"
            elif len(words) > 4 and words[3] == "OWNED" and words[4] == "BY":
                kind = "SEQUENCE OWNED BY"
        if kind not in allowed_kinds:
            raise MigrationToolError(
                f"Backup archive contains an unclassified object kind: {kind}."
            )
        if kind in {"TABLE DATA", "FK CONSTRAINT"}:
            object_schema, relation_name = words[4], words[5]
            if kind == "TABLE DATA":
                data_tables.add(str(relation_name))
        elif kind == "SEQUENCE SET":
            object_schema, relation_name = words[4], words[5]
            sequences.add(str(relation_name))
        elif kind == "SEQUENCE OWNED BY":
            if len(words) < 7:
                raise MigrationToolError(
                    "Backup archive has an incomplete sequence ownership entry."
                )
            object_schema, relation_name = words[5], words[6]
            sequences.add(str(relation_name))
        elif kind == "SEQUENCE":
            object_schema, relation_name = words[3], words[4]
            sequences.add(str(relation_name))
        else:
            object_schema, relation_name = words[3], words[4]
            if kind == "TABLE":
                schema_tables.add(str(relation_name))
        if object_schema != endpoint.schema:
            raise MigrationToolError(
                f"Backup object {kind} is outside the selected schema: {object_schema}."
            )
        kinds.append(kind)
    if not schema_tables or not data_tables:
        raise MigrationToolError("Backup archive is missing its schema or data entries.")
    if schema_tables != expected_schema_tables:
        raise MigrationToolError("Backup archive table definitions do not match its manifest.")
    if data_tables != expected_data_tables:
        raise MigrationToolError("Backup archive table data does not match its manifest.")
    if sequences != expected_sequences:
        raise MigrationToolError("Backup archive sequences do not match its manifest.")
    return {
        "kinds": kinds,
        "schema_tables": sorted(schema_tables),
        "data_tables": sorted(data_tables),
        "sequences": sorted(sequences),
    }


def _verify_archive_bytes(
    endpoint: DatabaseEndpoint,
    archive: Path,
    *,
    expected_schema_tables: set[str],
    expected_data_tables: set[str],
    expected_sequences: set[str],
) -> dict[str, Any]:
    if not archive.is_file():
        raise MigrationToolError("Backup archive does not exist or is not a file.")
    toc = _archive_toc(
        endpoint,
        archive,
        expected_schema_tables=expected_schema_tables,
        expected_data_tables=expected_data_tables,
        expected_sequences=expected_sequences,
    )
    # pg_restore --list validates the header/TOC; decoding the complete data stream
    # forces compressed custom-format blocks to be read without executing SQL.
    null_output = os.devnull
    _run_tool_capture(
        endpoint,
        "pg_restore",
        ["--file", null_output],
        stdin_file=archive,
        timeout=3600,
    )
    digest, size = _sha256_file(archive)
    return {
        "archive_sha256": digest,
        "archive_bytes": size,
        "toc_entries": len(toc["kinds"]),
        "schema_table_count": len(toc["schema_tables"]),
        "data_table_count": len(toc["data_tables"]),
        "sequence_count": len(toc["sequences"]),
    }


def verify_backup(archive_value: str | Path) -> dict[str, Any]:
    archive = _safe_output_path(archive_value)
    manifest_path = Path(str(archive) + ".manifest.json")
    if not manifest_path.is_file():
        raise MigrationToolError("Backup manifest is missing; the archive cannot be trusted.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        raise MigrationToolError("Backup manifest is unreadable or invalid JSON.") from None
    if not isinstance(manifest, dict):
        raise MigrationToolError("Backup manifest is unreadable or invalid JSON.")
    if (
        manifest.get("format_version") != FORMAT_VERSION
        or manifest.get("backup_format") != "postgres-custom-full-schema-and-data"
    ):
        raise MigrationToolError("Backup manifest format is unsupported.")
    if (
        not isinstance(manifest.get("schema_tables"), list)
        or not isinstance(manifest.get("data_tables"), dict)
        or not isinstance(manifest.get("sequence_names"), list)
    ):
        raise MigrationToolError("Backup manifest table inventory is invalid.")
    digest, size = _sha256_file(archive)
    if digest != manifest.get("archive_sha256") or size != manifest.get("archive_bytes"):
        raise MigrationToolError("Backup archive hash or size does not match its manifest.")
    tool_endpoint = _endpoint_for_archive_tool(manifest)
    schema_tables = set(manifest.get("schema_tables", []))
    data_tables = set(manifest.get("data_tables", {}))
    details = _verify_archive_bytes(
        tool_endpoint,
        archive,
        expected_schema_tables=schema_tables,
        expected_data_tables=data_tables,
        expected_sequences=set(manifest["sequence_names"]),
    )
    if details["archive_sha256"] != manifest["archive_sha256"]:
        raise MigrationToolError("Backup archive changed while it was being verified.")
    return {"status": "VALID", "manifest": _public_manifest(manifest), "archive": details}


def _endpoint_for_archive_tool(manifest: dict[str, Any]) -> DatabaseEndpoint:
    """Build a non-connecting tool endpoint from non-secret manifest metadata."""
    source = manifest.get("source", {})
    host = str(source.get("endpoint_host", ""))
    database = str(source.get("database", ""))
    schema = _validate_schema_name(str(source.get("schema", "")))
    test = bool(source.get("test_target"))
    if not host or not database:
        raise MigrationToolError("Backup manifest is missing its source identity.")
    url = URL.create("postgresql+psycopg", username="archive-check", host=host, database=database)
    return DatabaseEndpoint(
        "source", url, host, int(source.get("port", 5432)), database, "archive-check", schema, test
    )


def _public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    # The manifest is created by this tool and intentionally contains no URL,
    # password, username, source rows, or source field values.
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"credential", "password", "database_url", "url", "username"}
    }


def backup(output_value: str | Path, source: DatabaseEndpoint) -> dict[str, Any]:
    output = _safe_output_path(output_value)
    manifest_path = Path(str(output) + ".manifest.json")
    if output.exists() or manifest_path.exists():
        raise MigrationToolError(
            "Backup or manifest path already exists; refusing to overwrite it."
        )
    if not output.parent.is_dir():
        raise MigrationToolError(
            "Backup directory must already exist and be outside the repository."
        )
    _tool_major(source, "pg_dump")
    _tool_major(source, "pg_restore")
    temporary_path: Path | None = None
    try:
        with connect_read_only(source) as connection:
            identity = _identity_and_schema(connection, source, strict_head=True)
            if identity["foreign_keys"]["unvalidated"]:
                raise MigrationToolError(
                    "The source has unvalidated foreign keys; backup is blocked "
                    "until they are reviewed."
                )
            if identity["additional_user_schemas"]:
                raise MigrationToolError(
                    "The source database has additional user schemas; inventory and review "
                    "them before backup."
                )
            if identity["large_object_count"]:
                raise MigrationToolError(
                    "The source contains PostgreSQL large objects. This toolkit refuses "
                    "backups without large-object reconciliation."
                )
            snapshot = str(
                _required_row(
                    connection.execute("SELECT pg_export_snapshot()").fetchone(),
                    "PostgreSQL did not export a repeatable-read snapshot.",
                )[0]
            )
            table_report = _table_report(connection, source.schema, with_fingerprints=True)
            schema_tables = set(table_report)
            data_tables = schema_tables - set(TRANSIENT_TABLES)
            sequence_states_before = _sequence_states(connection, source.schema)
            handle, temporary_name = tempfile.mkstemp(
                prefix=".portfolio-migration-", dir=output.parent
            )
            os.close(handle)
            temporary_path = Path(temporary_name)
            _run_pg_dump_to_file(source, snapshot, source.schema, temporary_path)
            sequence_states_after = _sequence_states(connection, source.schema)
            if sequence_states_before != sequence_states_after:
                raise MigrationToolError(
                    "A sequence changed during backup; stop writers and create a new backup."
                )
            details = _verify_archive_bytes(
                source,
                temporary_path,
                expected_schema_tables=schema_tables,
                expected_data_tables=data_tables,
                expected_sequences=set(sequence_states_before),
            )
            os.link(temporary_path, output)
            temporary_path.unlink()
            temporary_path = None
            manifest = {
                "format_version": FORMAT_VERSION,
                "backup_format": "postgres-custom-full-schema-and-data",
                "created_at_utc": datetime.now(UTC).isoformat(),
                "snapshot_exported": True,
                "source": {
                    "endpoint_host": identity["endpoint_host"],
                    "port": source.port,
                    "database": identity["database"],
                    "schema": identity["schema"],
                    "test_target": source.test_target,
                    "postgres_major": identity["postgres_major"],
                    "alembic_heads": identity["alembic_heads"],
                    "schema_fingerprint": identity["schema_fingerprint"],
                    "server_encoding": identity["server_encoding"],
                    "database_collation": identity["database_collation"],
                    "database_ctype": identity["database_ctype"],
                    "locale_provider": identity["locale_provider"],
                    "collation_version": identity["collation_version"],
                    "extensions": identity["extensions"],
                    "data_only_restore_compatible": identity["data_only_restore_compatible"],
                    "foreign_key_cycles": identity["foreign_key_cycles"],
                    "foreign_keys": identity["foreign_keys"],
                    "large_object_count": identity["large_object_count"],
                },
                "archive_sha256": details["archive_sha256"],
                "archive_bytes": details["archive_bytes"],
                "schema_tables": sorted(schema_tables),
                "data_tables": {
                    name: value
                    for name, value in table_report.items()
                    if name not in EXCLUDED_ARCHIVE_TABLES
                },
                "excluded_transient_tables": {
                    name: table_report[name] for name in sorted(TRANSIENT_TABLES)
                },
                "sequence_names": sorted(sequence_states_before),
                "sequence_states": sequence_states_before,
            }
            _write_json_exclusive(manifest_path, manifest)
            return {"status": "BACKUP_CREATED", "manifest": _public_manifest(manifest)}
    except MigrationToolError:
        output.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        output.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise MigrationToolError(f"Consistent PostgreSQL backup failed{detail}.") from None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            descriptor = None
            json.dump(value, output, indent=2, ensure_ascii=False, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        raise MigrationToolError("Report path already exists; refusing to overwrite it.") from None
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise


def _manifest_for_archive(archive: Path) -> dict[str, Any]:
    manifest_path = Path(str(archive) + ".manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        raise MigrationToolError("Backup manifest is missing or invalid.") from None
    if not isinstance(manifest, dict):
        raise MigrationToolError("Backup manifest is missing or invalid.")
    verification = verify_backup(archive)
    if verification["status"] != "VALID":
        raise MigrationToolError("Backup verification failed.")
    return manifest


def _assert_target_isolated(target: DatabaseEndpoint) -> dict[str, Any]:
    if target.schema != APP_SCHEMA and not target.test_target:
        raise MigrationToolError(
            "Production migration operations are restricted to the public schema."
        )
    if not target.test_target and target.neon_environment is None:
        raise MigrationToolError(
            "Neon branch and endpoint identity were not verified against the control plane."
        )
    try:
        with connect_read_only(target) as connection:
            identity = connection_identity(connection, target)
            object_count = _public_object_count(connection, target.schema)
            privileges = _database_privileges(connection, target.schema)
            extra_schemas = _additional_user_schemas(connection, target.schema)
            if object_count:
                raise MigrationToolError(
                    "The selected migration database is not empty; restore requires a new database."
                )
            if extra_schemas:
                raise MigrationToolError(
                    "The selected migration database has additional user schemas; "
                    "restore requires a new database."
                )
            if not privileges["schema_usage"] or not privileges["schema_create"]:
                raise MigrationToolError(
                    "The selected role needs USAGE and CREATE on the empty target schema."
                )
            identity["public_object_count"] = object_count
            identity["restore_privileges"] = privileges
            identity["extensions"] = extension_inventory(connection)
            return identity
    except MigrationToolError:
        raise
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        raise MigrationToolError(f"Isolated target identity check failed{detail}.") from None


def _pg_restore(
    endpoint: DatabaseEndpoint,
    archive: Path,
    *,
    restore: bool,
) -> None:
    restore_application_name = f"portfolio-restore-{uuid4().hex}"
    prefix, environment = _tool_prefix(
        endpoint, "pg_restore", application_name=restore_application_name
    )
    arguments = ["--no-password", "--no-owner", "--no-acl", "--exit-on-error"]
    if restore:
        arguments.extend(["--single-transaction", "--dbname", endpoint.database])
    else:
        arguments.extend(["--file", os.devnull])
    command = [*prefix, *arguments]
    try:
        with archive.open("rb") as standard_input:
            process = subprocess.Popen(
                command,
                stdin=standard_input,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=environment,
            )
            try:
                process.communicate(timeout=3600)
            except KeyboardInterrupt:
                _stop_process(process)
                if restore:
                    _cancel_restore_backend(endpoint, restore_application_name)
                    message = (
                        "Restore interrupted; its PostgreSQL session was terminated and the "
                        "single-transaction restore was rolled back. Discard the target database."
                    )
                else:
                    message = "Backup archive validation was interrupted; no result is valid."
                raise MigrationToolError(message) from None
            except subprocess.TimeoutExpired:
                _stop_process(process)
                if restore:
                    _cancel_restore_backend(endpoint, restore_application_name)
                    message = (
                        "pg_restore exceeded the configured time limit; its PostgreSQL session "
                        "was terminated and transaction rolled back. Discard the target database."
                    )
                else:
                    message = (
                        "Backup archive validation exceeded its time limit; no result is valid."
                    )
                raise MigrationToolError(message) from None
    except MigrationToolError:
        raise
    except KeyboardInterrupt:
        raise MigrationToolError(
            "Restore interrupted before pg_restore completed; do not treat the target as migrated."
        ) from None
    except subprocess.TimeoutExpired:
        raise MigrationToolError(
            "pg_restore exceeded the configured time limit; do not treat the target as migrated."
        ) from None
    except Exception:
        raise MigrationToolError("Could not execute pg_restore.") from None
    if process.returncode:
        raise MigrationToolError(
            f"pg_restore failed with exit code {process.returncode}; its transaction "
            "was rolled back."
        )


def _manifest_data_reconcile(
    manifest: dict[str, Any], connection: psycopg.Connection[Any], target: DatabaseEndpoint
) -> dict[str, Any]:
    differences: dict[str, Any] = {}
    expected_tables = manifest.get("data_tables", {})
    for table in sorted(expected_tables):
        actual = table_fingerprint(connection, target.schema, table)
        expected = expected_tables[table]
        if actual != {"rows": expected.get("rows"), "sha256": expected.get("sha256")}:
            differences[table] = {"expected": expected, "target": actual}
    actual_sequences = _sequence_states(connection, target.schema)
    expected_sequences = manifest.get("sequence_states", {})
    sequence_differences = {
        name: {"expected": expected_sequences.get(name), "target": actual_sequences.get(name)}
        for name in sorted(set(expected_sequences) | set(actual_sequences))
        if expected_sequences.get(name) != actual_sequences.get(name)
    }
    return {"table_differences": differences, "sequence_differences": sequence_differences}


def _manifest_source_reconcile(
    manifest: dict[str, Any], connection: psycopg.Connection[Any], source: DatabaseEndpoint
) -> dict[str, Any]:
    differences: dict[str, Any] = {}
    expected_tables = manifest.get("data_tables", {})
    current_tables = set(_schema_tables(connection, source.schema)) - set(TRANSIENT_TABLES)
    if set(expected_tables) != current_tables:
        raise MigrationToolError("Backup and current source table inventories do not match.")
    for table in sorted(expected_tables):
        actual = table_fingerprint(connection, source.schema, table)
        expected = expected_tables[table]
        if actual != {"rows": expected.get("rows"), "sha256": expected.get("sha256")}:
            differences[table] = {"backup": expected, "source": actual}
    actual_sequences = _sequence_states(connection, source.schema)
    expected_sequences = manifest.get("sequence_states", {})
    sequence_differences = {
        name: {"backup": expected_sequences.get(name), "source": actual_sequences.get(name)}
        for name in sorted(set(expected_sequences) | set(actual_sequences))
        if expected_sequences.get(name) != actual_sequences.get(name)
    }
    return {"table_differences": differences, "sequence_differences": sequence_differences}


def restore(
    archive_value: str | Path, target: DatabaseEndpoint, *, confirmation: str
) -> dict[str, Any]:
    archive = _safe_output_path(archive_value)
    manifest = _manifest_for_archive(archive)
    source_identity = manifest.get("source", {})
    if target.schema != str(source_identity.get("schema", "")):
        raise MigrationToolError(
            "Archive schema name does not match the explicitly selected target schema."
        )
    expected_confirmation = f"RESTORE {target.host}/{target.database}"
    if confirmation != expected_confirmation:
        raise MigrationToolError(
            "Restore confirmation did not match the live target endpoint and database."
        )
    target_identity = _assert_target_isolated(target)
    if target_identity["postgres_major"] != source_identity.get("postgres_major"):
        raise MigrationToolError("Archive and target PostgreSQL major versions differ.")
    for field_name in (
        "server_encoding",
        "database_collation",
        "database_ctype",
        "locale_provider",
        "collation_version",
        "extensions",
    ):
        if target_identity[field_name] != source_identity.get(field_name):
            raise MigrationToolError(f"Backup and target {field_name} values are incompatible.")
    if source_identity.get("large_object_count"):
        raise MigrationToolError(
            "The source backup contains unsupported large objects; restore is blocked."
        )
    if source_identity.get("foreign_keys", {}).get("unvalidated", 0):
        raise MigrationToolError(
            "The source backup has unvalidated foreign keys; restore is blocked."
        )
    _tool_major(target, "pg_restore")
    _pg_restore(target, archive, restore=True)
    try:
        with connect_read_only(target) as connection:
            restored_identity = _identity_and_schema(connection, target, strict_head=True)
            if restored_identity["schema_fingerprint"] != source_identity.get("schema_fingerprint"):
                raise MigrationToolError(
                    "Restore completed but the resulting schema fingerprint differs "
                    "from the backup."
                )
            if restored_identity["alembic_heads"] != source_identity.get("alembic_heads"):
                raise MigrationToolError(
                    "Restore completed but the Alembic revision differs from the backup."
                )
            differences = _manifest_data_reconcile(manifest, connection, target)
            if differences["table_differences"] or differences["sequence_differences"]:
                raise MigrationToolError(
                    "Restore completed but exact data reconciliation found differences."
                )
            return {
                "status": "RESTORED_AND_RECONCILED",
                "target_use": "isolated_rehearsal_only",
                "target": restored_identity,
                "table_count": len(manifest["data_tables"]),
                "archive_sha256": manifest["archive_sha256"],
                "data_differences": differences,
            }
    except MigrationToolError:
        raise
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        raise MigrationToolError(f"Post-restore reconciliation failed{detail}.") from None


def _active_operations(connection: psycopg.Connection[Any], schema: str) -> dict[str, int]:
    conditions = {
        "recurring_operation_runs": "status = 'RUNNING'",
        "external_ingestion_runs": "status = 'RUNNING'",
        "operational_job_requests": "status IN ('QUEUED','RUNNING')",
        "operational_job_attempts": "status = 'RUNNING'",
        "recurring_operations_worker_state": "status IN ('STARTING','RUNNING')",
    }
    active: dict[str, int] = {}
    for table, condition in conditions.items():
        row = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.{} WHERE ").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
            + sql.SQL(condition)
        ).fetchone()
        count = int(_required_row(row, "Could not count active database operations.")[0])
        if count:
            active[table] = count
    return active


def cutover_preflight(
    source: DatabaseEndpoint, target: DatabaseEndpoint, archive_value: str | Path
) -> dict[str, Any]:
    archive = _safe_output_path(archive_value)
    manifest = _manifest_for_archive(archive)
    _source_target_distinct(source, target)
    try:
        with (
            connect_read_only(source) as source_connection,
            connect_read_only(target) as target_connection,
        ):
            source_identity, target_identity = _assert_target_schema_matches_source(
                source_connection, target_connection, source, target
            )
            source_size = int(
                _required_row(
                    source_connection.execute(
                        "SELECT pg_database_size(current_database())"
                    ).fetchone(),
                    "Could not read source database size.",
                )[0]
            )
            target_size = int(
                _required_row(
                    target_connection.execute(
                        "SELECT pg_database_size(current_database())"
                    ).fetchone(),
                    "Could not read isolated target database size.",
                )[0]
            )
            report = reconcile(source, target)
            backup_source_reconciliation = _manifest_source_reconcile(
                manifest, source_connection, source
            )
            source_active = _active_operations(source_connection, source.schema)
            target_active = _active_operations(target_connection, target.schema)
            backup_fresh = (
                manifest.get("source", {}).get("endpoint_host") == source.host
                and manifest.get("source", {}).get("database") == source.database
                and manifest.get("source", {}).get("port") == source.port
                and manifest.get("source", {}).get("schema") == source.schema
                and manifest.get("source", {}).get("schema_fingerprint")
                == source_identity["schema_fingerprint"]
                and manifest.get("source", {}).get("alembic_heads")
                == source_identity["alembic_heads"]
                and manifest.get("source", {}).get("postgres_major")
                == source_identity["postgres_major"]
            )
            blockers: list[str] = []
            if not backup_fresh:
                blockers.append("backup_identity_or_schema_changed")
            if (
                backup_source_reconciliation["table_differences"]
                or backup_source_reconciliation["sequence_differences"]
            ):
                blockers.append("backup_differs_from_current_source")
            if report["status"] != "MATCH":
                blockers.append("source_target_data_differences")
            if source_active:
                blockers.append("source_has_active_operations")
            if target_active:
                blockers.append("target_has_active_operations")
            if source_identity["database_collation"] != target_identity["database_collation"]:
                blockers.append("database_collation_differs")
            return {
                "status": (
                    "REHEARSAL_READY_FOR_SEPARATE_PRODUCTION_REVIEW" if not blockers else "BLOCKED"
                ),
                "review_scope": "isolated_rehearsal_only",
                "final_canonical_database_certified": False,
                "production_accessed": False,
                "production_modified": False,
                "blockers": blockers,
                "source": source_identity,
                "isolated_target": target_identity,
                "source_database_bytes": source_size,
                "isolated_target_database_bytes": target_size,
                "backup_sha256": manifest.get("archive_sha256"),
                "backup_source_reconciliation": backup_source_reconciliation,
                "source_active_operations": source_active,
                "target_active_operations": target_active,
                "source_target_reconciliation": report,
            }
    except MigrationToolError:
        raise
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if code else ""
        raise MigrationToolError(f"Cutover preflight failed{detail}.") from None


def _write_report(path_value: str | None, report: dict[str, Any]) -> None:
    if path_value is None:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        return
    path = _safe_output_path(path_value)
    if path.exists():
        raise MigrationToolError("Report path already exists; refusing to overwrite it.")
    if not path.parent.is_dir():
        raise MigrationToolError(
            "Report directory must already exist and be outside the repository."
        )
    _write_json_exclusive(path, report)
    print(json.dumps({"status": "REPORT_WRITTEN", "report_path": str(path)}, indent=2))


def _cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio-postgres-migration",
        description="Read-only discovery and explicitly isolated PostgreSQL migration preparation.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "capacity", "schema-check", "reconcile"):
        commands.add_parser(name).add_argument("--report")
    backup_parser = commands.add_parser("backup")
    backup_parser.add_argument("--output", required=True)
    backup_parser.add_argument("--report")
    verify_parser = commands.add_parser("verify-backup")
    verify_parser.add_argument("--archive", required=True)
    verify_parser.add_argument("--report")
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--archive", required=True)
    restore_parser.add_argument("--confirm-target", required=True)
    restore_parser.add_argument("--report")
    preflight_parser = commands.add_parser("cutover-preflight")
    preflight_parser.add_argument("--archive", required=True)
    preflight_parser.add_argument("--report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _cli_parser().parse_args(argv)
    try:
        if arguments.command == "inventory":
            report = {
                "status": "READ_ONLY_INVENTORY",
                **inventory(endpoint_from_environment("source")),
            }
        elif arguments.command == "capacity":
            source = inventory(endpoint_from_environment("source"))
            report = {"status": "CAPACITY_REPORT", "source": source}
            if os.environ.get("MIGRATION_TARGET_URL"):
                target = capacity(endpoint_from_environment("target"))
                report["isolated_target"] = target
        elif arguments.command == "backup":
            report = backup(arguments.output, endpoint_from_environment("source"))
        elif arguments.command == "verify-backup":
            report = verify_backup(arguments.archive)
        elif arguments.command == "schema-check":
            report = schema_check(
                endpoint_from_environment("source"), endpoint_from_environment("target")
            )
        elif arguments.command == "reconcile":
            report = reconcile(
                endpoint_from_environment("source"), endpoint_from_environment("target")
            )
        elif arguments.command == "restore":
            report = restore(
                arguments.archive,
                endpoint_from_environment("target"),
                confirmation=arguments.confirm_target,
            )
        elif arguments.command == "cutover-preflight":
            report = cutover_preflight(
                endpoint_from_environment("source"),
                endpoint_from_environment("target"),
                arguments.archive,
            )
        else:
            raise MigrationToolError("Unknown migration command.")
        _write_report(getattr(arguments, "report", None), report)
        return 2 if report.get("status") in {"BLOCKED", "DIFFERENCES_FOUND"} else 0
    except MigrationToolError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR: interrupted; no operation is considered successful.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
