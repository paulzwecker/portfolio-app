# Verified database write targets

## Purpose and scope

`portfolio_api.database_write_target` is the common fail-closed gate for database
writes made through the application's SQLAlchemy engine. `create_database_engine`
installs it automatically. It checks the same physical PostgreSQL connection that
will execute the first write, then caches approval only for that checked connection.
Read-only statements do not require write authorization. Every approved writer
connection emits a redacted structured audit record before the statement runs.

This protects the FastAPI database, importer commands, provider ingestion commands,
scheduled workers, demo seed command, and online Alembic command that use the shared
engine factory. The dedicated `postgres_migration` restore utility uses direct
psycopg/`pg_restore` and keeps its separate, stricter child-branch and explicit-target
gate. Do not bypass either gate with a raw driver connection.

The guard does not create or migrate a database, schedule work, or turn on ingestion.
The cloud-native bootstrap readiness plan remains a reviewed set of existing
domain-specific commands; a future bootstrap command must integrate the guard as
described below.

## Environment policy

| Target                       | Permitted identity                                                                                                | Additional authorization                                                                                                               |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Local disposable development | Loopback PostgreSQL database ending `_test`; `APP_ENV=development`; explicit target environment and database name | `DATABASE_LOCAL_TEST_WRITES_AUTHORIZED=true`. No Neon credentials. The live schema and application table privileges are still checked. |
| Other local development      | Loopback PostgreSQL, exact `DATABASE_TARGET_DATABASE`                                                             | `DATABASE_LOCAL_WRITES_AUTHORIZED=true` and `DATABASE_TARGET_ENVIRONMENT=development`                                                  |
| Remote development           | Verified direct Neon endpoint on a non-primary branch                                                             | Exact Neon project, branch and endpoint IDs; `DATABASE_TARGET_ENVIRONMENT=development`                                                 |
| Rehearsal                    | Verified direct Neon endpoint on a ready, non-primary branch whose parent is the verified primary branch          | Exact Neon IDs and `DATABASE_REHEARSAL_WRITES_AUTHORIZED=true`                                                                         |
| Production                   | Verified direct Neon endpoint on the project's primary branch                                                     | Exact Neon IDs and `DATABASE_PRODUCTION_WRITES_AUTHORIZED=true`                                                                        |

Production bootstrap has an extra interactive gate. Its operator must set production
authorization and type the exact phrase printed by the command:

```text
BOOTSTRAP <project-id>/<primary-branch-id>/<direct-endpoint-id>/<database-name>
```

The phrase is checked against the verified live target. It is not accepted in
non-interactive mode. This confirmation does not replace the authorization setting,
Neon metadata verification, or database privileges. Seed/demo writes are limited to
development.

For remote writes the guard also requires TLS hostname verification
(`sslmode=verify-full`), a direct endpoint rather than a pooler, an exact match among
the configured URL and live driver/database identity, and a non-superuser database
role. Application operations require the mapped schema tables and SELECT/INSERT/
UPDATE/DELETE privileges. Online migrations additionally require schema CREATE
privilege and ownership of existing schema objects they may alter. A deployment's
`APP_ENV` cannot silently lower its target environment:
production services must target production and preview services must target rehearsal.

## Neon metadata and connection binding

Remote settings must provide:

- `DATABASE_TARGET_ENVIRONMENT`
- `DATABASE_TARGET_DATABASE` (the exact PostgreSQL database name)
- `NEON_API_KEY`
- `NEON_PROJECT_ID`
- `NEON_BRANCH_ID`
- `NEON_ENDPOINT_ID`
- The environment-specific authorization flag shown above

The Neon API key is used only for read-only project branch and endpoint lookups. Give
it the narrowest Neon permissions that can read those resources. The guard resolves
the configured project, branch, primary branch, and endpoint metadata and compares
the exact IDs, host, endpoint type/state, branch relationship/state, and primary
identity with the live psycopg connection. It also confirms that the active resolved
address is currently returned for the configured hostname. API redirects are
rejected so the bearer token is not forwarded to a different host. A missing API
response, ambiguous primary branch, DNS failure, pooler, ID/host mismatch, or
unverified TLS setting blocks writes.

Do not put credentials in command arguments, source files, CI, reports, or shell
transcripts. Supply them through the operator's secret store or process environment.
Never print `DATABASE_URL` or `NEON_API_KEY`. The GitHub integration job uses only its
local disposable PostgreSQL 18 service and synthetic unit-test metadata; it has no
Neon credentials.

## Integrating a future import or bootstrap command

Use the shared factory and set a stable operation label plus the correct operation
kind. For a canonical bootstrap, run the explicit preflight before reading source
files or calling providers; the SQLAlchemy write hook verifies the exact connection
again at the first mutation:

```python
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import verify_database_write_target

engine = create_database_engine(
    settings,
    write_operation="canonical_bootstrap",
    write_operation_kind="bootstrap",
)
if engine is None:
    raise RuntimeError("DATABASE_URL is required")
try:
    verify_database_write_target(engine)
    # Perform bounded, domain-specific work using this engine.
finally:
    engine.dispose()
```

Use `import`, `ingestion`, `bootstrap`, `seed`, or `schema_migration` to describe the
operation. Do not create a second unguarded engine in the same command. A command
that uses direct psycopg or another database client must add an equivalent guard
that binds verification to that client's actual connection before it can write; do
not assume the SQLAlchemy hook covers it.

## Write coverage and audit

The SQLAlchemy hook detects DML, DDL, CTE writes, `EXPLAIN ANALYZE` writes, and known
mutating PostgreSQL functions such as sequence changes, advisory locks, notifications,
large-object changes, and backend control calls. SQL functions with undocumented or
custom side effects should not be invoked through a read-only statement. Add a
classifier case and regression test when introducing a new mutating function.

The approved audit record includes operation, operation kind, target environment,
provider, database, verified Neon IDs when applicable, timestamp, server version, and
one-way hashes for endpoint, resolved address, and role name. It does not include the
connection URL, hostname, resolved IP, role name, password, API key, SQL parameters,
or row contents. Rejections log only operation labels and stable reason codes. If
the audit sink fails, the write is rejected.

Common sanitized rejection codes include `target_environment_required`,
`database_name_mismatch`, `live_connection_target_mismatch`,
`neon_target_metadata_required`, `neon_configured_identity_mismatch`,
`endpoint_branch_mismatch`, `production_requires_primary_branch`,
`rehearsal_branch_not_isolated`, `pooled_endpoint_not_supported`,
`insufficient_database_privileges`, and `write_audit_record_failed`.

## Operator procedure

1. Review the command's dry-run/reconciliation output and identify its exact target
   database. For local test writes, set `DATABASE_TARGET_ENVIRONMENT=development`,
   `DATABASE_TARGET_DATABASE` to the exact local `_test` database, and
   `DATABASE_LOCAL_TEST_WRITES_AUTHORIZED=true`. Do not use the production database
   for rehearsal.
2. Obtain the Neon project, isolated branch, direct endpoint, and database names from
   the Neon control plane. Independently verify that the rehearsal branch is not
   primary and is a direct child of the primary branch.
3. Set the operator process environment without echoing secret values. Set
   `DATABASE_TARGET_ENVIRONMENT=rehearsal`, the exact database name, Neon IDs/API
   key, and `DATABASE_REHEARSAL_WRITES_AUTHORIZED=true`. Use a direct endpoint URL
   with `sslmode=verify-full` and a non-superuser application role.
4. Run the command's explicit target preflight. A rejection is a hard stop: correct
   the target and rerun the full read-only review. Do not edit or skip a guard.
5. Run one bounded domain operation. Inspect its domain reconciliation and the
   redacted `database_write_target_approved` audit record. A failed command may have
   committed domain-specific transactions; follow that command's recovery procedure
   before retrying.
6. For production bootstrap, use the primary branch only after separate operator
   authorization. Set `DATABASE_TARGET_ENVIRONMENT=production` and
   `DATABASE_PRODUCTION_WRITES_AUTHORIZED=true`; the command must be interactive and
   require the exact target phrase. This document does not authorize a production
   operation or change any deployment configuration.

## Verification and limits

Pure regression tests exercise the target policy with synthetic Neon metadata and
IDs. PostgreSQL integration tests use only the explicit database ending `_test`,
exercise guarded DDL/DML on the verified connection, and prove that a wrong target
and insufficient table privileges are rejected before a write. They do not connect
to Neon or use portfolio data.

The control-plane key and Neon target have not been exercised against an actual Neon
branch in CI. The application has no production bootstrap orchestrator. Each future
command must use the shared factory, add its own bounded/idempotent transaction and
reconciliation behavior, and keep production disabled until separately authorized.
