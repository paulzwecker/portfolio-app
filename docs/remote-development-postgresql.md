# Persistent PostgreSQL for remote development

PostgreSQL is the canonical application database. The API and Alembic already use
the same `DATABASE_URL`; no database host or credentials belong in application
code. This runbook covers a persistent PostgreSQL service reachable from a remote
development environment.

## Required service and network access

Use a provider-managed, persistent PostgreSQL service. PostgreSQL 18 is the major
version verified by this repository's historical setup; choosing the same major
avoids relying on unverified compatibility. The database must survive remote
workspace restarts and should have the provider's normal backup and restore
protection enabled.

Create the application and test databases using the names and ownership model in
[`infra/create-local-db.sql`](../infra/create-local-db.sql): `portfolio_app` and
`portfolio_app_test`, both owned by a non-superuser `portfolio_app` login. The
application login needs the DDL privileges Alembic uses in `portfolio_app`; the
test database must allow the integration-test role to create and drop its own
random schemas. The administrator is used only to provision the role and
databases, never in either application connection URL.

The remote environment needs a private route or narrowly scoped TCP access to the
database endpoint on port 5432, working DNS, and provider-required TLS. Use
certificate verification (`sslmode=verify-full`) when the provider supplies a CA
bundle; otherwise follow its documented secure connection parameters. Do not open
broad network access to make the database reachable.

As observed on 2026-10-07, this workspace's ignored root `.env` has application
and test URLs aimed at a loopback PostgreSQL listener, but both connections fail
with `OperationalError`. The managed cloud environment has no database secret or
runtime-variable binding and no TCP database domains or IP ranges configured.
There is no persistent PostgreSQL service reachable from this workspace yet.

## Configure connection secrets

Set these variables through the remote environment's secret configuration. Keep
the ignored local `.env` for local development only; do not commit credentials.
URL-encode special characters in passwords. Replace the placeholders with the
provider's endpoint and credentials:

```text
DATABASE_URL=postgresql+psycopg://portfolio_app:<URL-ENCODED-PASSWORD>@<postgres-host>:5432/portfolio_app?sslmode=require
TEST_DATABASE_URL=postgresql+psycopg://portfolio_app:<URL-ENCODED-PASSWORD>@<postgres-host>:5432/portfolio_app_test?sslmode=require
```

If the provider requires certificate verification, use its CA and the corresponding
`sslmode=verify-full` connection parameters instead. `TEST_DATABASE_URL` must be a
separate dedicated database whose name ends in `_test`; integration tests create
and drop only randomly named schemas inside that database. The application setting
requires the `postgresql+psycopg` driver and a database name.

The minimum external setup for this workspace is therefore:

1. Provision the persistent PostgreSQL service and the two databases above.
2. Configure a private route or narrowly scoped TCP access from the remote runtime
   to its endpoint on port 5432, including TLS and DNS.
3. Bind `DATABASE_URL` and `TEST_DATABASE_URL` as remote runtime secrets, not
   checked-in files or source code.

No PostgreSQL provisioning or remote environment configuration tool is available
in this workspace. After the external setup, the application can use the service
without code changes.

## Apply schema and reconstruct application state

From the repository root, first apply and check the full Alembic chain:

```sh
npm run db:migrate
npm run db:check
npm run test:integration
```

The current repository has one Alembic head, `6e6c2d4e8a19`. Keep the test URL
separate from the application URL; integration tests do not use the application
database.

On an empty application database, rebuild state through the source-owned import
workflows. Run each command once without `--apply`, review its report, then repeat
with `--apply`. Use new dated paths for replay receipts so existing reference
evidence is not overwritten.

```sh
npm run db:import-workbook -- --report /tmp/workbook-reconcile.json
npm run db:import-workbook -- --apply --report /tmp/workbook-reconcile.json

npm run db:import-consensus-estimates -- --report /tmp/consensus-reconcile.json
npm run db:import-consensus-estimates -- --apply --report /tmp/consensus-reconcile.json

npm run db:import-market-data -- --report /tmp/market-data-reconcile.json
npm run db:import-market-data -- --apply --report /tmp/market-data-reconcile.json

npm run db:import-model-outputs -- --report /tmp/model-output-reconcile.json
npm run db:import-model-outputs -- --apply --report /tmp/model-output-reconcile.json

npm run db:import-native-models -- --output /tmp/native-model-reconcile.json
npm run db:import-native-models -- --apply --output /tmp/native-model-reconcile.json
```

The workbook workflow owns universe identity and lifecycle, holdings, targets,
scores, and cached rank observations. Separate workflows import legacy estimate
observations, dated market facts, published model outputs/history, and parity-
approved native revisions. They are idempotent under their existing source hashes,
revision IDs, and input digests. The native-model apply step still enforces exact
company, security, listing, currency, and current-price checks; a source parity pass
alone is not enough to accept a revision.

Do not use `--replace-demo` for a real or unknown database. It is only valid when
the workbook importer verifies that the existing contents are exclusively the
explicit fictional development seed. If the service may contain real application
records, reconcile its existing state first and never populate it with ad-hoc SQL.

Provider-backed facts are a separate step after mappings and credentials are
reviewed. Configure `SEC_USER_AGENT` and `FMP_API_KEY` through the same secret
mechanism, review provider identity mappings, then use the existing operational
worker:

```sh
npm run db:ingest-external-data -- run
npm run db:ingest-external-data -- status
```

Missing mappings or credentials remain blocked or partial in the canonical
operational records; do not treat an unsuccessful run as data coverage. See
[external-data operations](external-data-operations.md) for provider policy and
retry semantics.

The Milestone 6.1 `coverage_audit` command reads committed receipts and workbook
evidence; it does not query PostgreSQL. It must not be presented as a current
database count. Record actual company, holding, target, market-data, output, and
native-revision counts only after reading the configured application database.

## Reconciliation evidence in this workspace

The current run could not apply migrations or replay imports because the configured
loopback PostgreSQL listener is unavailable. No application rows were written.
See the [2026-10-07 reconciliation record](reconciliation/postgresql-state-reconciliation-2026-10-07.md)
for the exact distinction between tracked application receipts, the 6.3 parity-only
worktree receipt, and current database state.
