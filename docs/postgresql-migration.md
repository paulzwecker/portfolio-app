# Canonical PostgreSQL migration preparation

This runbook prepares a local PostgreSQL 18 database for an operator-run migration into an isolated Neon database. It does not connect to Neon production, modify a database, perform a cutover, or copy portfolio data to Codex Cloud. The migration command is deliberately separate from application startup and Alembic; no background migration was added.

## Findings and restore design

The local application database is `portfolio_app`, the application schema is `public`, and the current Alembic head is `12a6f0d9c3e1`. The migration chain is pinned to PostgreSQL 18. The current schema contains 83 application tables plus `alembic_version`. The inventory command verifies the checked-in model table set and the single expected Alembic head before producing an archive.

The canonical data spans these related domains:

- Company, security, listing, provider identifiers, lifecycle events and current lifecycle state.
- Portfolios, dated holding snapshots, security quantities, cash balances and target-allocation revisions.
- Score assessments, ranking runs and entries, execution decisions, research priorities and candidate-pipeline decisions.
- Market-data batches, prices, corporate actions, FX, reported financials and consensus estimates.
- Financial-model identities, immutable revisions, revision evidence, DCF/owner-cash-flow/residual-income inputs, scenarios, projections and calculated outputs.
- Research, forecast, thesis and risk revisions; evidence links; source-document batches, document references and review outcomes.
- Provider payloads and ingestion, recurring-operation and operational-job histories.

The relationships include parent/child chains, self-references such as superseded observations and revision ancestry, and a circular dependency between `financial_models.current_revision_id` and `financial_model_revisions.model_id`. Lifecycle current state also references its lifecycle event. The histories and provenance rows are preserved. The three migration-seeded reference tables (`score_definitions`, `ranking_definitions`, and `return_methodology_definitions`) are included because the selected restore is a complete archive into an empty database. `alembic_version` is included and checked. `recurring_operations_worker_state` is the only table whose rows are excluded: it contains process-specific worker heartbeat/lease state. Its schema is restored empty.

The current schema is **not safe for a data-only restore**. PostgreSQL 18 reports circular foreign-key dependencies for self-referencing tables and the financial-model/revision pair. A data-only restore into the already migrated Neon schema would have to load rows while those immediate constraints are active. Disabling triggers is not a safe assumption for a Neon application role, and this tool never uses `--disable-triggers` or `session_replication_role`.

The toolkit therefore creates a PostgreSQL custom-format **full schema and data** archive, then restores it with `pg_restore --single-transaction --exit-on-error` into a newly created, empty database named with the `_migration` suffix on an isolated Neon branch. PostgreSQL creates the foreign keys after loading the rows. The existing application database on the branch is not a restore target. The restore never uses `--clean`, never drops objects, and refuses any target whose `public` schema already contains objects.

Source and target must both be PostgreSQL 18 and have matching encoding, collation, locale provider/version, and extension inventory. Those differences can change index ordering or restore behavior, so the tool blocks instead of guessing. The archive omits source ownership and ACLs; restored objects belong to the explicitly selected migration role. It preserves application DDL, indexes, validated constraints, data and sequence state. A source with unvalidated foreign keys is blocked until its referential integrity is reviewed. Unknown objects, extra schemas, archive TOC entries, or large objects are refused rather than silently omitted. Large objects are counted during inventory; if any exist, backup stops until a separately reviewed large-object reconciliation path is available.

The generated archive and its JSON manifest contain the full portfolio dataset and must remain on the operator’s encrypted local workstation. Reports contain endpoint/database identity, counts, sizes, schema metadata, hashes and difference counts, but no URLs, passwords, row values or raw source documents. Table keys in difference samples are hashed. Database URLs are prompted as hidden PowerShell input and are passed to the process environment only for that command. Never paste credentials into command arguments, issue text, logs, Git, CI, PRs, or support transcripts.

## Windows operator setup

Run these commands from the repository root in Windows PowerShell 5.1 or PowerShell 7. Keep the archive directory on a BitLocker-encrypted local disk with a restricted ACL; avoid OneDrive, synced folders and network shares. The examples use `%LOCALAPPDATA%` so the default path is not a synced Documents directory:

```powershell
$migrationFolder = Join-Path $env:LOCALAPPDATA "PortfolioMigration"
New-Item -ItemType Directory -Force -Path $migrationFolder | Out-Null
icacls.exe $migrationFolder /inheritance:r /grant:r `
  "$($env:USERDOMAIN)\$($env:USERNAME):(OI)(CI)F" `
  "SYSTEM:(OI)(CI)F"

$pg18Bin = Join-Path $env:ProgramFiles "PostgreSQL\18\bin"
$env:Path = "$pg18Bin;$env:Path"
& "$pg18Bin\pg_dump.exe" --version
& "$pg18Bin\pg_restore.exe" --version
```

Both version commands must report PostgreSQL 18. The application’s normal setup must already be complete (`npm ci` and `npm run setup`). The migration script does not read `.env` or fall back to `DATABASE_URL`.

Use the script entry point below; no source or script edits are needed. Connection URLs are requested with hidden input. For the source, paste the local `portfolio_app` PostgreSQL 18 connection URL. For the target, use the **direct** endpoint and database URL from the isolated Neon branch; pooled endpoints containing `-pooler.` are rejected. Set the expected target hostname and database name exactly, and enter the protected production hostname as host-only text. The target database name must end in `_migration`, and the operator must type an additional `RESTORE host/database` confirmation before restore starts.

```powershell
pwsh -NoProfile -File .\scripts\postgres-migration.ps1 -Operation inventory
pwsh -NoProfile -File .\scripts\postgres-migration.ps1 -Operation capacity
pwsh -NoProfile -File .\scripts\postgres-migration.ps1 -Operation schema-check
```

For Windows PowerShell 5.1, use `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\postgres-migration.ps1` in place of `pwsh -NoProfile -File .\scripts\postgres-migration.ps1`; the bypass applies only to that process. `inventory` is read-only and lists all recognized tables, row counts, table/index sizes, schema identity, migration heads, foreign-key cycles and large-object count. `capacity` reports source database size and can optionally inspect an explicitly selected isolated target. Provider storage quotas are not exposed by PostgreSQL; check the Neon project storage and branch limits in the provider console and leave headroom for the full restore, indexes and WAL.

Create a fresh archive path for each attempt. The path must be outside the repository and must not already exist:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archive = Join-Path $migrationFolder "portfolio-$stamp.dump"
pwsh -NoProfile -File .\scripts\postgres-migration.ps1 `
  -Operation backup `
  -Output $archive `
  -Report "$archive.backup-report.json"

pwsh -NoProfile -File .\scripts\postgres-migration.ps1 `
  -Operation verify-backup `
  -Archive $archive
```

Expected statuses are `BACKUP_CREATED` and then `VALID`. Backup uses a repeatable-read exported PostgreSQL snapshot, captures table hashes and sequence state from that snapshot, decodes the complete archive, verifies its allowlisted TOC and writes a SHA-256 manifest. It does not pause writers; before any future production cutover, the operator must separately freeze writes and make a final backup. If a sequence changes while the backup is running, the backup fails and must be repeated after writers are stopped.

The migration target is a new empty database, for example `portfolio_migration`, on a separately identified Neon migration branch. Do not select the production branch’s existing database, even though it already has the application schema. `schema-check` reports `EMPTY_TARGET_COMPATIBLE_FOR_FULL_RESTORE` when the empty target’s PostgreSQL version, locale, extension set and privileges match. The `data_only_restore_compatible: false` result is expected for this schema and documents why full restore is used.

After an authorized operator creates that isolated branch/database and reviews the exact endpoint, perform the restore and checks from the same local workstation:

```powershell
pwsh -NoProfile -File .\scripts\postgres-migration.ps1 -Operation schema-check
pwsh -NoProfile -File .\scripts\postgres-migration.ps1 `
  -Operation restore `
  -Archive $archive `
  -Report "$archive.restore-report.json"
pwsh -NoProfile -File .\scripts\postgres-migration.ps1 -Operation reconcile
pwsh -NoProfile -File .\scripts\postgres-migration.ps1 `
  -Operation cutover-preflight `
  -Archive $archive `
  -Report "$archive.preflight-report.json"
```

Expected restore status is `RESTORED_AND_RECONCILED`; reconciliation must say `MATCH`. A preflight result of `READY_FOR_SEPARATE_PRODUCTION_REVIEW` only means the local source, verified archive and isolated migration database match and no active operations were found. The command confirms in its report that it accessed or modified no production database. It does **not** authorize or perform cutover.

Keep the original local database intact. If restore is interrupted or a restore statement fails, `pg_restore` is stopped and its one transaction rolls back. The target is deliberately disposable: if a post-restore check fails or the target is no longer empty, do not retry into that database. Create a new empty `_migration` database and repeat from the unchanged local source and a verified archive. A backup/manifest pair is never overwritten; choose a new timestamped name.

## Report template

Use [the JSON template](templates/postgresql-migration-report.template.json) for a manually retained operator summary. The generated JSON reports are more detailed and contain no row contents or credentials. Store all reports beside the archive on the restricted local disk; do not attach either to GitHub or upload them to Codex Cloud.

## Production cutover and rollback plan (future, separate authorization)

This milestone stops after the isolated restore and review. A future cutover requires its own explicit authorization and a reviewed production change window.

1. Freeze all write paths: put the API in maintenance/read-only mode, pause Render workers and scheduled jobs, stop local import/ingestion jobs, and prevent new portfolio/research edits from the frontend or spreadsheet workflows.
2. Run a new source inventory and backup after the freeze. Verify target identity again, restore to a fresh isolated migration database, and require exact table/sequence reconciliation plus no running/queued operations.
3. Review the cutover report and the Neon branch/database identity with a second operator. Confirm the existing production endpoint and current Render/Vercel configuration are recorded privately for rollback.
4. In the separately approved deployment step, change the Render API’s `DATABASE_URL` to the reviewed target endpoint, restart the API/workers, and validate readiness, portfolio counts, holdings/cash, expected IRR and weighted fair value in read-only checks before reopening writes.
5. Keep the original local PostgreSQL database and its backup unchanged. If validation fails before any new target writes, restore the previous Render endpoint and restart the previous service configuration. If target writes have started, do not simply switch back: freeze writes again, capture the target delta, reconcile it, and choose a reviewed forward-recovery or rollback that preserves those writes.

Neon endpoint/branch promotion, Render/Vercel settings, deployment, schema downgrade, source deletion and production traffic changes are all outside this toolkit. The scripts have no command that connects to production or changes application deployment settings.

## CI and known limits

The integration CI job uses its disposable PostgreSQL 18 service as the native PostgreSQL client-tools container. Its only database password is the throwaway service password. CI sets no migration URLs, Neon credentials, Google service-account credentials or workbook secrets. The migration tests create randomly named `_test` databases only on loopback, apply migrations to a synthetic source database, exercise archive integrity, schema mismatch, exact financial decimals, a circular model/revision reference, failed-restore transaction rollback and end-to-end reconciliation, then drop only those generated test databases.

The toolkit requires PostgreSQL 18 `pg_dump`/`pg_restore`, a local `portfolio_app` source, a clean database with the same locale/extension profile for restore, and a Neon role that can create objects in the new database’s `public` schema. It refuses extra source schema objects, user-defined archive objects outside `public`, unclassified tables/TOC entries and PostgreSQL large objects. It does not copy files between machines; the operator runs backup, verification and restore on the local workstation so the dump never enters Codex Cloud.
