# PostgreSQL development targets

For Linux or remote workspace setup use [cloud development](codex-cloud-development.md).
For every database operation use the [write-target contract](database-write-targets.md).
Integration tests use the isolated `TEST_DATABASE_URL` target described in
[testing.md](testing.md). Use the existing canonical Neon database only through
its verified read-only or separately authorized production workflows.

Remote PostgreSQL connections require certificate and hostname verification with
`sslmode=verify-full`, a trusted CA and direct endpoints where session locks are
required. Keep secrets in the ignored environment or approved secret store.

Production schema changes follow [deployment and migrations](deployment-and-migrations.md).
The [canonical baseline](production-canonical-baseline.md) records the last verified
production scope. Reverify live identity and schema before any privileged operation.

The [2026-10-07 environment record](history/remote-postgresql-2026-10-07.md)
preserves the older unavailable-local-database investigation and import sequence.
