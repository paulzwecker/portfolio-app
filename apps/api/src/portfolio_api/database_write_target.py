"""Fail-closed verification for database connections that can write application state."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import re
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.engine import URL, Connection, Engine

from portfolio_api.settings import Settings

logger = logging.getLogger("portfolio_api.database_write_target")

WriteOperationKind = Literal[
    "application", "import", "ingestion", "bootstrap", "seed", "schema_migration"
]
ConfirmationProvider = Callable[[str], str]
AuditSink = Callable[[Mapping[str, Any]], None]

_API_BASE = "https://console.neon.tech/api/v2"
_AUDIT_INFO_KEY = "portfolio_database_write_target_guard"
_OPERATION_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
_WRITE_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "COMMENT",
        "GRANT",
        "REVOKE",
        "CALL",
        "DO",
        "COPY",
        "VACUUM",
        "ANALYZE",
        "CHECKPOINT",
        "REFRESH",
        "REINDEX",
        "CLUSTER",
        "LOCK",
        "SET",
        "RESET",
    }
)
_MUTATING_FUNCTION_PATTERN = re.compile(
    r"\b(?:nextval|setval|set_config|pg_(?:try_)?advisory_(?:xact_)?(?:try_)?"
    r"(?:lock|unlock)(?:_shared)?|pg_advisory_unlock_all|pg_notify|"
    r"pg_(?:cancel_backend|terminate_backend|reload_conf)|"
    r"lo_(?:create|creat|put|unlink|import|export)|dblink_exec)\s*\(",
    re.IGNORECASE,
)


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Do not forward the Neon bearer token to a redirected host."""

    def redirect_request(
        self, request: Any, fp: Any, code: int, msg: str, headers: Any, new_url: str
    ) -> urllib.request.Request | None:
        return None


class DatabaseWriteTargetError(RuntimeError):
    """A sanitized, stable failure code for a rejected database write target."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True)
class NeonTargetMetadata:
    project_id: str
    branch_id: str
    branch_project_id: str | None
    branch_is_primary: bool
    primary_branch_id: str
    branch_parent_id: str | None
    branch_state: str
    endpoint_id: str
    endpoint_project_id: str | None
    endpoint_branch_id: str
    endpoint_host: str
    endpoint_type: str
    endpoint_state: str


@dataclass(frozen=True)
class LiveDatabaseIdentity:
    url_host: str
    driver_host: str
    driver_hostaddr: str | None
    url_port: int
    driver_port: int
    url_database: str
    driver_database: str
    server_database: str
    server_user: str
    server_address: str | None
    server_port: int | None
    server_version_num: int
    current_schema: str | None
    role_is_superuser: bool
    can_connect: bool
    can_use_schema: bool
    can_create_schema: bool
    missing_tables: tuple[str, ...] = ()
    missing_privileges: tuple[str, ...] = ()
    missing_owned_objects: tuple[str, ...] = ()


class NeonControlPlaneClient:
    """Minimal read-only Neon control-plane client. API response bodies are never logged."""

    def __init__(self, api_key: str, *, timeout_seconds: float = 8.0) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def _get_json(self, resource: str) -> Mapping[str, Any]:
        request = urllib.request.Request(
            f"{_API_BASE}{resource}",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
                "User-Agent": "portfolio-research-database-target-guard/1.0",
            },
            method="GET",
        )
        try:
            opener = urllib.request.build_opener(_RejectRedirects)
            with opener.open(request, timeout=self._timeout_seconds) as response:
                body = response.read(1_048_576)
            value = json.loads(body)
        except urllib.error.HTTPError as error:
            code = "neon_auth_rejected" if error.code in {401, 403} else "neon_api_rejected"
            raise DatabaseWriteTargetError(
                code, "The Neon control plane did not approve the configured target lookup."
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            raise DatabaseWriteTargetError(
                "neon_api_unavailable", "The Neon control plane could not verify the target."
            ) from None
        if not isinstance(value, Mapping):
            raise DatabaseWriteTargetError(
                "neon_metadata_invalid", "The Neon control plane returned invalid metadata."
            )
        return value

    def read_target(self, project_id: str, branch_id: str, endpoint_id: str) -> NeonTargetMetadata:
        project_path = urllib.parse.quote(project_id, safe="")
        branch_path = urllib.parse.quote(branch_id, safe="")
        endpoint_path = urllib.parse.quote(endpoint_id, safe="")
        branches_body = self._get_json(f"/projects/{project_path}/branches")
        branch_body = self._get_json(f"/projects/{project_path}/branches/{branch_path}")
        endpoint_body = self._get_json(f"/projects/{project_path}/endpoints/{endpoint_path}")
        branches_raw = branches_body.get("branches")
        branch_raw = branch_body.get("branch", branch_body)
        endpoint_raw = endpoint_body.get("endpoint", endpoint_body)
        if not isinstance(branches_raw, list) or not isinstance(branch_raw, Mapping):
            raise DatabaseWriteTargetError(
                "neon_metadata_invalid", "The Neon branch metadata is incomplete."
            )
        if not isinstance(endpoint_raw, Mapping):
            raise DatabaseWriteTargetError(
                "neon_metadata_invalid", "The Neon endpoint metadata is incomplete."
            )
        branches = [item for item in branches_raw if isinstance(item, Mapping)]
        primary = [item for item in branches if item.get("primary") is True]
        if len(primary) != 1 or not isinstance(primary[0].get("id"), str):
            raise DatabaseWriteTargetError(
                "neon_primary_branch_ambiguous",
                "The Neon project does not expose exactly one primary branch.",
            )

        branch_values = (
            branch_raw.get("id"),
            branch_raw.get("primary"),
            branch_raw.get("current_state"),
        )
        endpoint_values = (
            endpoint_raw.get("id"),
            endpoint_raw.get("branch_id"),
            endpoint_raw.get("host"),
            endpoint_raw.get("type"),
            endpoint_raw.get("current_state"),
        )
        if not all(isinstance(value, str) and value for value in branch_values[::2]):
            raise DatabaseWriteTargetError(
                "neon_metadata_invalid", "The Neon branch metadata is incomplete."
            )
        if not isinstance(branch_values[1], bool) or not all(
            isinstance(value, str) and value for value in endpoint_values
        ):
            raise DatabaseWriteTargetError(
                "neon_metadata_invalid", "The Neon endpoint metadata is incomplete."
            )
        branch_id_value = str(branch_raw["id"])
        endpoint_id_value = str(endpoint_raw["id"])
        if branch_id_value != branch_id or endpoint_id_value != endpoint_id:
            raise DatabaseWriteTargetError(
                "neon_configured_identity_mismatch",
                "The configured Neon branch or endpoint ID did not resolve exactly.",
            )
        branch_project = branch_raw.get("project_id")
        endpoint_project = endpoint_raw.get("project_id")
        if branch_project is not None and branch_project != project_id:
            raise DatabaseWriteTargetError(
                "neon_project_mismatch", "The resolved branch belongs to another project."
            )
        if endpoint_project is not None and endpoint_project != project_id:
            raise DatabaseWriteTargetError(
                "neon_project_mismatch", "The resolved endpoint belongs to another project."
            )
        return NeonTargetMetadata(
            project_id=project_id,
            branch_id=branch_id_value,
            branch_project_id=str(branch_project) if branch_project is not None else None,
            branch_is_primary=bool(branch_values[1]),
            primary_branch_id=str(primary[0]["id"]),
            branch_parent_id=(
                str(branch_raw["parent_id"]) if branch_raw.get("parent_id") is not None else None
            ),
            branch_state=str(branch_raw["current_state"]),
            endpoint_id=endpoint_id_value,
            endpoint_project_id=str(endpoint_project) if endpoint_project is not None else None,
            endpoint_branch_id=str(endpoint_raw["branch_id"]),
            endpoint_host=str(endpoint_raw["host"]),
            endpoint_type=str(endpoint_raw["type"]),
            endpoint_state=str(endpoint_raw["current_state"]),
        )


def _normalize_host(value: str) -> str:
    return value.rstrip(".").casefold()


def _is_loopback(host: str) -> bool:
    normalized = _normalize_host(host)
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _is_pooler(host: str, port: int) -> bool:
    return "-pooler." in _normalize_host(host) or port in {6432, 6543}


def _target_environment(settings: Settings) -> str:
    configured = settings.database_target_environment
    if configured is not None:
        if configured not in {"development", "rehearsal", "production"}:
            raise DatabaseWriteTargetError(
                "target_environment_invalid", "DATABASE_TARGET_ENVIRONMENT is invalid."
            )
        return configured
    raise DatabaseWriteTargetError(
        "target_environment_required",
        "Set DATABASE_TARGET_ENVIRONMENT explicitly for database writes.",
    )


def _target_database(settings: Settings, url: URL, environment: str) -> str:
    configured = settings.database_target_database
    if configured:
        if configured != url.database:
            raise DatabaseWriteTargetError(
                "database_name_mismatch",
                "DATABASE_TARGET_DATABASE does not match DATABASE_URL.",
            )
        return configured
    raise DatabaseWriteTargetError(
        "target_database_required",
        "Set DATABASE_TARGET_DATABASE to the exact intended database name.",
    )


def _bootstrap_confirmation_text(
    project_id: str, branch_id: str, endpoint_id: str, database: str
) -> str:
    return f"BOOTSTRAP {project_id}/{branch_id}/{endpoint_id}/{database}"


def _interactive_confirmation(expected: str) -> str:
    if not sys.stdin.isatty():
        raise DatabaseWriteTargetError(
            "production_bootstrap_confirmation_required",
            "Production bootstrap requires an interactive operator terminal.",
        )
    try:
        return input(f"Type '{expected}' to authorize the production bootstrap: ")
    except (EOFError, OSError):
        raise DatabaseWriteTargetError(
            "production_bootstrap_confirmation_required",
            "Production bootstrap confirmation could not be read.",
        ) from None


def validate_database_write_target(
    *,
    settings: Settings,
    url: URL,
    identity: LiveDatabaseIdentity,
    operation: str,
    operation_kind: WriteOperationKind,
    neon_target: NeonTargetMetadata | None,
    confirmation_provider: ConfirmationProvider | None = None,
) -> dict[str, Any]:
    """Validate configuration and live identities without opening a connection."""

    if not _OPERATION_PATTERN.fullmatch(operation):
        raise DatabaseWriteTargetError(
            "operation_name_invalid", "The database write operation name is invalid."
        )
    if operation_kind not in {
        "application",
        "import",
        "ingestion",
        "bootstrap",
        "seed",
        "schema_migration",
    }:
        raise DatabaseWriteTargetError(
            "operation_kind_invalid", "The database write operation kind is invalid."
        )
    if settings.app_env not in {"development", "preview", "production"}:
        raise DatabaseWriteTargetError("application_environment_invalid", "APP_ENV is invalid.")
    if url.host is None or url.database is None:
        raise DatabaseWriteTargetError(
            "connection_target_incomplete", "DATABASE_URL must identify a host and database."
        )
    environment = _target_environment(settings)
    target_database = _target_database(settings, url, environment)
    if settings.app_env == "production" and environment != "production":
        raise DatabaseWriteTargetError(
            "application_target_environment_mismatch",
            "A production application must target the verified production branch.",
        )
    if settings.app_env == "preview" and environment != "rehearsal":
        raise DatabaseWriteTargetError(
            "application_target_environment_mismatch",
            "A preview application must target an explicitly designated rehearsal branch.",
        )

    expected_host = _normalize_host(url.host)
    if (
        _normalize_host(identity.url_host) != expected_host
        or _normalize_host(identity.driver_host) != expected_host
        or identity.url_port != identity.driver_port
        or identity.url_database != url.database
        or identity.driver_database != url.database
        or identity.server_database != target_database
    ):
        raise DatabaseWriteTargetError(
            "live_connection_target_mismatch",
            "The live PostgreSQL connection does not match DATABASE_URL and the expected database.",
        )
    if not identity.can_connect or not identity.can_use_schema:
        raise DatabaseWriteTargetError(
            "insufficient_database_privileges",
            "The connected role lacks database CONNECT or current-schema USAGE privilege.",
        )
    if operation_kind == "schema_migration":
        if not identity.can_create_schema:
            raise DatabaseWriteTargetError(
                "insufficient_database_privileges",
                "The connected role lacks current-schema CREATE privilege for migrations.",
            )
        if identity.missing_owned_objects:
            raise DatabaseWriteTargetError(
                "insufficient_schema_ownership",
                "The connected role does not own all existing objects that migrations may alter.",
            )
    else:
        if identity.missing_tables:
            raise DatabaseWriteTargetError(
                "application_schema_incomplete",
                "One or more mapped application tables are absent from the selected schema.",
            )
        if identity.missing_privileges:
            raise DatabaseWriteTargetError(
                "insufficient_table_privileges",
                "The connected role lacks required SELECT/INSERT/UPDATE/DELETE privileges.",
            )

    local_test = (
        environment == "development"
        and settings.app_env == "development"
        and _is_loopback(url.host)
        and target_database.endswith("_test")
    )
    if local_test:
        if not settings.database_local_test_writes_authorized:
            raise DatabaseWriteTargetError(
                "local_test_write_not_authorized",
                "Set DATABASE_LOCAL_TEST_WRITES_AUTHORIZED=true for the explicit disposable "
                "test target.",
            )
        return _audit_record(
            operation,
            operation_kind,
            environment,
            target_database,
            identity,
            provider="local_postgresql",
        )

    if _is_loopback(url.host):
        if environment != "development" or settings.app_env != "development":
            raise DatabaseWriteTargetError(
                "local_target_environment_mismatch",
                "Loopback PostgreSQL is only allowed for isolated development targets.",
            )
        if not settings.database_local_writes_authorized:
            raise DatabaseWriteTargetError(
                "local_development_write_not_authorized",
                "Set DATABASE_LOCAL_WRITES_AUTHORIZED=true for an explicitly named local database.",
            )
        if settings.database_target_database is None:
            raise DatabaseWriteTargetError(
                "target_database_required",
                "Non-test local writes require an explicit DATABASE_TARGET_DATABASE.",
            )
        if neon_target is not None:
            raise DatabaseWriteTargetError(
                "unexpected_neon_metadata", "A local database cannot use Neon target metadata."
            )
        return _audit_record(
            operation,
            operation_kind,
            environment,
            target_database,
            identity,
            provider="local_postgresql",
        )

    if _is_pooler(url.host, identity.url_port):
        raise DatabaseWriteTargetError(
            "pooled_endpoint_not_supported",
            "Write verification requires a direct PostgreSQL endpoint, not a pooler.",
        )
    sslmode = url.query.get("sslmode")
    if sslmode != "verify-full":
        raise DatabaseWriteTargetError(
            "tls_hostname_verification_required",
            "Neon writes require sslmode=verify-full to bind TLS identity to the endpoint host.",
        )
    if identity.role_is_superuser:
        raise DatabaseWriteTargetError(
            "superuser_write_role_rejected",
            "Remote application writes must use a non-superuser database role.",
        )
    if identity.driver_hostaddr is None:
        raise DatabaseWriteTargetError(
            "resolved_endpoint_unavailable",
            "The active PostgreSQL connection did not expose its resolved endpoint address.",
        )
    try:
        resolved_addresses = {
            str(item[4][0]).split("%", maxsplit=1)[0]
            for item in socket.getaddrinfo(url.host, identity.url_port, type=socket.SOCK_STREAM)
        }
    except OSError:
        raise DatabaseWriteTargetError(
            "endpoint_resolution_failed", "The configured database endpoint did not resolve."
        ) from None
    resolved_address = identity.driver_hostaddr.split("%", maxsplit=1)[0]
    if resolved_address not in resolved_addresses:
        raise DatabaseWriteTargetError(
            "resolved_endpoint_mismatch",
            "The active PostgreSQL connection address is not a current resolution of DATABASE_URL.",
        )
    if neon_target is None:
        raise DatabaseWriteTargetError(
            "neon_target_metadata_required",
            "Remote writes require Neon project, branch, and endpoint verification.",
        )
    if not all(
        (
            settings.neon_project_id,
            settings.neon_branch_id,
            settings.neon_endpoint_id,
        )
    ):
        raise DatabaseWriteTargetError(
            "neon_target_configuration_incomplete",
            "Set NEON_PROJECT_ID, NEON_BRANCH_ID, and NEON_ENDPOINT_ID explicitly.",
        )
    if (
        neon_target.project_id != settings.neon_project_id
        or neon_target.branch_id != settings.neon_branch_id
        or neon_target.endpoint_id != settings.neon_endpoint_id
    ):
        raise DatabaseWriteTargetError(
            "neon_configured_identity_mismatch",
            "Neon control-plane IDs do not match the configured project, branch, and endpoint.",
        )
    if neon_target.branch_project_id not in {
        None,
        neon_target.project_id,
    } or neon_target.endpoint_project_id not in {None, neon_target.project_id}:
        raise DatabaseWriteTargetError(
            "neon_project_mismatch", "The Neon branch or endpoint belongs to another project."
        )
    if _normalize_host(neon_target.endpoint_host) != expected_host:
        raise DatabaseWriteTargetError(
            "endpoint_host_mismatch",
            "DATABASE_URL host does not match the configured Neon endpoint metadata.",
        )
    if neon_target.endpoint_branch_id != neon_target.branch_id:
        raise DatabaseWriteTargetError(
            "endpoint_branch_mismatch", "The configured endpoint is attached to another branch."
        )
    if neon_target.endpoint_type != "read_write" or neon_target.endpoint_state not in {
        "active",
        "idle",
    }:
        raise DatabaseWriteTargetError(
            "endpoint_not_writable",
            "The verified Neon endpoint is not an active read-write endpoint.",
        )
    if neon_target.branch_state != "ready":
        raise DatabaseWriteTargetError(
            "branch_not_ready", "The verified Neon branch is not in the ready state."
        )
    primary_by_id = neon_target.branch_id == neon_target.primary_branch_id
    if neon_target.branch_is_primary != primary_by_id:
        raise DatabaseWriteTargetError(
            "neon_primary_branch_ambiguous",
            "Neon branch primary metadata is inconsistent with the project branch list.",
        )
    if environment == "production":
        if not primary_by_id:
            raise DatabaseWriteTargetError(
                "production_requires_primary_branch",
                "Production writes must target the Neon project primary branch.",
            )
        if not settings.database_production_writes_authorized:
            raise DatabaseWriteTargetError(
                "production_write_not_authorized",
                "Set DATABASE_PRODUCTION_WRITES_AUTHORIZED=true after operator authorization.",
            )
    else:
        if primary_by_id:
            raise DatabaseWriteTargetError(
                "nonproduction_primary_branch_rejected",
                "Development and rehearsal writes cannot target the Neon primary branch.",
            )
        if environment == "rehearsal":
            if neon_target.branch_parent_id != neon_target.primary_branch_id:
                raise DatabaseWriteTargetError(
                    "rehearsal_branch_not_isolated",
                    "A rehearsal branch must be a direct child of the verified primary branch.",
                )
            if not settings.database_rehearsal_writes_authorized:
                raise DatabaseWriteTargetError(
                    "rehearsal_write_not_authorized",
                    "Set DATABASE_REHEARSAL_WRITES_AUTHORIZED=true for the approved rehearsal.",
                )
    if operation_kind == "seed" and environment != "development":
        raise DatabaseWriteTargetError(
            "seed_environment_rejected", "Demonstration seed data is restricted to development."
        )
    if environment == "production" and operation_kind == "bootstrap":
        if confirmation_provider is None:
            raise DatabaseWriteTargetError(
                "production_bootstrap_confirmation_required",
                "Production bootstrap requires explicit interactive operator confirmation.",
            )
        expected_confirmation = _bootstrap_confirmation_text(
            neon_target.project_id,
            neon_target.branch_id,
            neon_target.endpoint_id,
            target_database,
        )
        supplied_confirmation = confirmation_provider(expected_confirmation)
        if not hmac.compare_digest(supplied_confirmation.strip(), expected_confirmation):
            raise DatabaseWriteTargetError(
                "production_bootstrap_confirmation_mismatch",
                "The production bootstrap confirmation did not match the exact target identity.",
            )
    return _audit_record(
        operation,
        operation_kind,
        environment,
        target_database,
        identity,
        provider="neon",
        project_id=neon_target.project_id,
        branch_id=neon_target.branch_id,
        endpoint_id=neon_target.endpoint_id,
    )


def _audit_record(
    operation: str,
    operation_kind: WriteOperationKind,
    environment: str,
    database: str,
    identity: LiveDatabaseIdentity,
    *,
    provider: str,
    project_id: str | None = None,
    branch_id: str | None = None,
    endpoint_id: str | None = None,
) -> dict[str, Any]:
    endpoint_fingerprint = hashlib.sha256(
        f"{identity.url_host}:{identity.url_port}".encode()
    ).hexdigest()
    principal_fingerprint = hashlib.sha256(identity.server_user.encode("utf-8")).hexdigest()
    resolved_fingerprint = (
        hashlib.sha256(identity.driver_hostaddr.encode("utf-8")).hexdigest()
        if identity.driver_hostaddr
        else None
    )
    return {
        "event": "database_write_target_approved",
        "event_id": str(uuid4()),
        "verified_at": datetime.now(UTC).isoformat(),
        "operation": operation,
        "operation_kind": operation_kind,
        "environment": environment,
        "provider": provider,
        "project_id": project_id,
        "branch_id": branch_id,
        "endpoint_id": endpoint_id,
        "database": database,
        "endpoint_sha256": endpoint_fingerprint,
        "resolved_address_sha256": resolved_fingerprint,
        "principal_sha256": principal_fingerprint,
        "server_version_num": identity.server_version_num,
    }


def _application_table_names() -> tuple[str, ...]:
    # Late imports avoid a database.py -> guard -> database.py import cycle.
    from portfolio_api.database import Base
    from portfolio_api.domain import models as _models  # noqa: F401

    return tuple(sorted(Base.metadata.tables))


def _read_live_identity(
    connection: Connection, operation_kind: WriteOperationKind
) -> LiveDatabaseIdentity:
    url = connection.engine.url
    if url.host is None or url.database is None:
        raise DatabaseWriteTargetError(
            "connection_target_incomplete", "DATABASE_URL must identify a host and database."
        )
    try:
        driver_connection = connection.connection.driver_connection
        if driver_connection is None:
            raise AttributeError("driver connection is unavailable")
        info = driver_connection.info
        driver_host = str(info.host or "")
        driver_hostaddr_raw = getattr(info, "hostaddr", None)
        driver_hostaddr = str(driver_hostaddr_raw) if driver_hostaddr_raw else None
        driver_port = int(info.port)
        driver_database = str(info.dbname or "")
        cursor = driver_connection.cursor()
    except (AttributeError, TypeError, ValueError):
        raise DatabaseWriteTargetError(
            "live_connection_identity_unavailable",
            "The active PostgreSQL driver did not expose its resolved connection identity.",
        ) from None
    try:
        cursor.execute(
            """SELECT current_database(), current_user, inet_server_addr()::text,
                      inet_server_port(), current_setting('server_version_num')::integer,
                      current_schema(),
                      (SELECT rolsuper FROM pg_roles WHERE rolname = current_user),
                      has_database_privilege(current_user, current_database(), 'CONNECT'),
                      has_schema_privilege(current_user, current_schema(), 'USAGE'),
                      has_schema_privilege(current_user, current_schema(), 'CREATE')"""
        )
        row = cursor.fetchone()
        if row is None or len(row) != 10:
            raise DatabaseWriteTargetError(
                "live_connection_identity_unavailable",
                "PostgreSQL did not return complete live database identity metadata.",
            )
        (
            server_database,
            server_user,
            server_address,
            server_port,
            server_version_num,
            current_schema,
            role_is_superuser,
            can_connect,
            can_use_schema,
            can_create_schema,
        ) = row
        missing_tables: tuple[str, ...] = ()
        missing_privileges: tuple[str, ...] = ()
        missing_owned_objects: tuple[str, ...] = ()
        if operation_kind == "schema_migration":
            cursor.execute(
                """SELECT c.relname
                   FROM pg_class AS c
                   JOIN pg_namespace AS n ON n.oid = c.relnamespace
                   WHERE n.nspname = current_schema()
                     AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
                     AND NOT pg_has_role(current_user, c.relowner, 'USAGE')
                   ORDER BY c.relname"""
            )
            missing_owned_objects = tuple(str(row[0]) for row in cursor.fetchall())
        else:
            table_names = _application_table_names()
            cursor.execute(
                """WITH expected(table_name) AS (
                       SELECT unnest(%s::text[])
                   ), resolved AS (
                       SELECT table_name,
                              to_regclass(
                                  quote_ident(current_schema()) || '.' || quote_ident(table_name)
                              ) AS relation
                       FROM expected
                   )
                   SELECT table_name,
                          relation IS NOT NULL,
                          CASE WHEN relation IS NULL THEN false
                               ELSE has_table_privilege(current_user, relation, 'SELECT') END,
                          CASE WHEN relation IS NULL THEN false
                               ELSE has_table_privilege(current_user, relation, 'INSERT') END,
                          CASE WHEN relation IS NULL THEN false
                               ELSE has_table_privilege(current_user, relation, 'UPDATE') END,
                          CASE WHEN relation IS NULL THEN false
                               ELSE has_table_privilege(current_user, relation, 'DELETE') END
                   FROM resolved
                   ORDER BY table_name""",
                (list(table_names),),
            )
            absent: list[str] = []
            denied: list[str] = []
            for (
                table_name,
                exists,
                can_select,
                can_insert,
                can_update,
                can_delete,
            ) in cursor.fetchall():
                if not exists:
                    absent.append(str(table_name))
                    continue
                for privilege, allowed in (
                    ("SELECT", can_select),
                    ("INSERT", can_insert),
                    ("UPDATE", can_update),
                    ("DELETE", can_delete),
                ):
                    if not allowed:
                        denied.append(f"{table_name}:{privilege}")
            missing_tables = tuple(absent)
            missing_privileges = tuple(denied)
    except DatabaseWriteTargetError:
        raise
    except Exception:
        raise DatabaseWriteTargetError(
            "live_connection_identity_unavailable",
            "The active PostgreSQL connection could not be independently verified.",
        ) from None
    finally:
        cursor.close()
    return LiveDatabaseIdentity(
        url_host=str(url.host),
        driver_host=driver_host,
        driver_hostaddr=driver_hostaddr,
        url_port=int(url.port or 5432),
        driver_port=driver_port,
        url_database=str(url.database),
        driver_database=driver_database,
        server_database=str(server_database),
        server_user=str(server_user),
        server_address=str(server_address) if server_address is not None else None,
        server_port=int(server_port) if server_port is not None else None,
        server_version_num=int(server_version_num),
        current_schema=str(current_schema) if current_schema is not None else None,
        role_is_superuser=bool(role_is_superuser),
        can_connect=bool(can_connect),
        can_use_schema=bool(can_use_schema),
        can_create_schema=bool(can_create_schema),
        missing_tables=missing_tables,
        missing_privileges=missing_privileges,
        missing_owned_objects=missing_owned_objects,
    )


class DatabaseWriteTargetGuard:
    """SQLAlchemy engine hook that checks the exact connection before its first write."""

    def __init__(
        self,
        settings: Settings,
        *,
        operation: str,
        operation_kind: WriteOperationKind,
        audit_sink: AuditSink | None = None,
    ) -> None:
        if not _OPERATION_PATTERN.fullmatch(operation):
            raise DatabaseWriteTargetError(
                "operation_name_invalid", "The database write operation name is invalid."
            )
        self.settings = settings
        self.operation = operation
        self.operation_kind = operation_kind
        self.neon_client: NeonControlPlaneClient | None = None
        self.audit_sink = audit_sink
        self._bootstrap_confirmed = False
        self._lock = threading.Lock()
        self._guard_id = str(uuid4())

    def verify_connection(self, connection: Connection, *, phase: str = "before_write") -> None:
        if connection.info.get(_AUDIT_INFO_KEY) == self._guard_id:
            return
        try:
            identity = _read_live_identity(connection, self.operation_kind)
            url = connection.engine.url
            neon_target: NeonTargetMetadata | None = None
            if url.host is not None and not _is_loopback(url.host):
                if self.neon_client is None:
                    api_key = self.settings.neon_api_key
                    project_id = self.settings.neon_project_id
                    branch_id = self.settings.neon_branch_id
                    endpoint_id = self.settings.neon_endpoint_id
                    if api_key is None or not all((project_id, branch_id, endpoint_id)):
                        raise DatabaseWriteTargetError(
                            "neon_target_configuration_incomplete",
                            "Remote writes require NEON_API_KEY and explicit project, branch, "
                            "and endpoint IDs.",
                        )
                    self.neon_client = NeonControlPlaneClient(api_key.get_secret_value())
                project_id = self.settings.neon_project_id
                branch_id = self.settings.neon_branch_id
                endpoint_id = self.settings.neon_endpoint_id
                if not all((project_id, branch_id, endpoint_id)):
                    raise DatabaseWriteTargetError(
                        "neon_target_configuration_incomplete",
                        "Set NEON_PROJECT_ID, NEON_BRANCH_ID, and NEON_ENDPOINT_ID explicitly.",
                    )
                neon_target = self.neon_client.read_target(
                    str(project_id), str(branch_id), str(endpoint_id)
                )
            confirmation_provider = None
            with self._lock:
                if not self._bootstrap_confirmed and self.operation_kind == "bootstrap":
                    confirmation_provider = _interactive_confirmation
                audit = validate_database_write_target(
                    settings=self.settings,
                    url=connection.engine.url,
                    identity=identity,
                    operation=self.operation,
                    operation_kind=self.operation_kind,
                    neon_target=neon_target,
                    confirmation_provider=confirmation_provider,
                )
                if self.operation_kind == "bootstrap" and audit["environment"] == "production":
                    self._bootstrap_confirmed = True
            audit["phase"] = phase
            self._emit_audit(audit)
            if phase == "before_write":
                connection.info[_AUDIT_INFO_KEY] = self._guard_id
        except DatabaseWriteTargetError as error:
            logger.warning(
                "database_write_target_rejected %s",
                json.dumps(
                    {
                        "event": "database_write_target_rejected",
                        "operation": self.operation,
                        "operation_kind": self.operation_kind,
                        "reason_code": error.code,
                    },
                    sort_keys=True,
                ),
            )
            raise

    def _emit_audit(self, record: Mapping[str, Any]) -> None:
        try:
            if self.audit_sink is not None:
                self.audit_sink(record)
            else:
                logger.info("database_write_target_approved %s", json.dumps(record, sort_keys=True))
        except Exception:
            raise DatabaseWriteTargetError(
                "write_audit_record_failed",
                "The approved database operation could not be written to the redacted audit log.",
            ) from None

    def before_cursor_execute(
        self,
        connection: Connection,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        if _statement_may_write(statement, context):
            self.verify_connection(connection)


def _statement_may_write(statement: str, context: Any) -> bool:
    if any(
        bool(getattr(context, attribute, False))
        for attribute in ("isinsert", "isupdate", "isdelete", "isddl")
    ):
        return True
    sanitized = re.sub(r"/\*.*?\*/|--[^\n]*", " ", statement, flags=re.DOTALL).lstrip()
    if ";" in sanitized:
        # Multiple raw statements must not hide a later mutation behind a read-only prefix.
        return True
    keyword_match = re.match(r"([A-Za-z]+)", sanitized)
    if keyword_match is None:
        return False
    keyword = keyword_match.group(1).upper()
    if keyword in _WRITE_KEYWORDS:
        return True
    if _MUTATING_FUNCTION_PATTERN.search(sanitized):
        return True
    if keyword == "WITH" and re.search(
        r"\b(?:INSERT|UPDATE|DELETE|MERGE|CALL|DO)\b", sanitized, re.IGNORECASE
    ):
        return True
    if keyword == "EXPLAIN" and re.search(r"\bANALYZE\b", sanitized, re.IGNORECASE):
        return bool(
            re.search(r"\b(?:INSERT|UPDATE|DELETE|MERGE|CALL|DO)\b", sanitized, re.IGNORECASE)
        )
    return False


def install_database_write_target_guard(
    engine: Engine,
    settings: Settings,
    *,
    operation: str,
    operation_kind: WriteOperationKind = "application",
    audit_sink: AuditSink | None = None,
) -> DatabaseWriteTargetGuard:
    """Protect one SQLAlchemy engine, checking the same DBAPI connection that writes."""

    existing = getattr(engine, "_portfolio_database_write_target_guard", None)
    if existing is not None:
        if not isinstance(existing, DatabaseWriteTargetGuard):
            raise DatabaseWriteTargetError(
                "write_guard_already_configured",
                "The SQLAlchemy engine already has an incompatible write guard.",
            )
        if existing.operation != operation or existing.operation_kind != operation_kind:
            raise DatabaseWriteTargetError(
                "write_guard_already_configured",
                "A SQLAlchemy engine cannot be reused for a different write operation.",
            )
        return existing
    guard = DatabaseWriteTargetGuard(
        settings,
        operation=operation,
        operation_kind=operation_kind,
        audit_sink=audit_sink,
    )
    event.listen(engine, "before_cursor_execute", guard.before_cursor_execute)
    engine._portfolio_database_write_target_guard = guard  # type: ignore[attr-defined]
    return guard


def verify_database_write_target(engine: Engine) -> None:
    """Preflight a configured engine before expensive imports or provider calls.

    The engine hook verifies each later physical writer connection again, so this
    early check is not used as a substitute for binding to the actual writer.
    """

    guard = getattr(engine, "_portfolio_database_write_target_guard", None)
    if not isinstance(guard, DatabaseWriteTargetGuard):
        raise DatabaseWriteTargetError(
            "write_guard_not_installed", "Install the database write-target guard first."
        )
    try:
        with engine.connect() as connection:
            guard.verify_connection(connection, phase="preflight")
            connection.rollback()
    except DatabaseWriteTargetError:
        raise
    except Exception:
        raise DatabaseWriteTargetError(
            "target_preflight_failed", "The database write-target preflight failed."
        ) from None
