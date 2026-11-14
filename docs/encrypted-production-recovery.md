# Encrypted production recovery and first ingestion

Scope frozen 2026-11-14: export the existing application database with the native
PostgreSQL toolkit, encrypt it with age, and rehearse restoration into an empty,
isolated database. No production restore, new service, migration, scheduler or
provider change. This procedure is prepared; **no production backup exists from
this work**. The owner must authorize the actual destination and rehearsal target.

## Current evidence and gates

Read-only verification on November 14 resolved project `blue-pond-96398788`, primary
branch `br-square-butterfly-bacw0rn5`, endpoint `ep-floral-cake-bae16liy`, database
`neondb`, schema `public`, revision `b59f16c8a203`. The direct endpoint uses
`verify-full`. No additional user schemas, large objects or enabled RLS were found.
The market preview is READY for 22 reviewed Yahoo listings, DKK/EUR and USD/EUR,
2025-11-10 through 2026-11-09 inclusive: 24 planned requests, zero actual requests
and zero writes. The canonical receipt passed the existing readiness guard.
SEC preview is BLOCKED: `NO_REVIEWED_SEC_CIK_MAPPINGS`.

The November 8 recovery branch expires **2026-11-15 14:18 CET** and predates the
current schema. Do not rely on it as durable protection. Actual production backup,
decryption from an off-device copy, restore reconciliation and application readback
remain mandatory before ingestion. Live Render/Vercel commit identities and release
controls also require verification; matching schema alone does not prove a release.

## Minimal affordable design

Use existing workstation storage plus an existing owner-controlled removable drive
stored separately. No hosting subscription. The working disk must be encrypted
(for example BitLocker), nonsynced and restricted to the operator and SYSTEM. Keep
the final `.age` file off-device; keep the private age identity and a tested second
key copy separately from both archives. An unencrypted staging disk is a NO-GO:
temporary plaintext is removed normally, not securely erased from SSD media.

The bundle contains a custom-format `pg_dump`, its versioned integrity/reconciliation
manifest and `access.json`. It reuses the existing exported repeatable-read snapshot,
schema/table/sequence fingerprints, archive validation and atomic restore. Only
transient worker heartbeat rows are excluded; their table schema is retained.
Owners, role memberships and grants are recorded without passwords, **not replayed**.
The current single-database scope is `neondb`; catalog entries for `postgres` and
templates do not imply those databases were backed up. Confirm no other application
database needs recovery. This follows [PostgreSQL's single-database dump contract](https://www.postgresql.org/docs/18/app-pgdump.html)
and [Neon's pg_dump guidance](https://neon.com/docs/manage/backup-pg-dump).

Proposed retention for owner approval: snapshot immediately before first ingestion;
retain it through reconciliation and for 30 days afterward. Once daily ingestion is
approved, retain seven daily and four weekly encrypted copies, with at least one
off-device. Proposed RPO is 24 hours after automation, zero accepted changes between
the initial snapshot and ingestion. Measure restore time during rehearsal before
promising an RTO. Never prune the last successfully rehearsed recovery point.

## Operator procedure

1. Approve exact source, backup destination, encrypted staging path, key custodians,
   retention and exact isolated restore target. Confirm all application writers are
   stopped, including manual requests, workers, Sheets and administrative changes.
   Keep them stopped through snapshot/rehearsal or recapture after intervening changes.
   This document does not authorize cloud configuration changes or new expenditure.
2. Install PostgreSQL 18 client tools and the official [age CLI](https://github.com/FiloSottile/age)
   on the operator workstation; validate the release checksum. Local verification
   used age 1.3.2. Run from the reviewed repository checkout after normal setup.
   Add both tools to this shell's PATH. `age-keygen -o <new-private-key-path>` creates
   the identity; `age-keygen -y <private-key-path>` prints only the public recipient.
   Do not print/copy the private identity into logs or Git. Verify key recovery from
   its separate copy. Commands below use operator-selected paths, never credentials.
3. Securely load the existing production read-target environment: `DATABASE_URL`
   (direct `postgresql+psycopg`, `sslmode=verify-full`), `DATABASE_TARGET_ENVIRONMENT=production`,
   `DATABASE_TARGET_DATABASE=neondb`, exact `NEON_PROJECT_ID`, `NEON_BRANCH_ID`,
   `NEON_ENDPOINT_ID`, and a metadata-read `NEON_API_KEY`. Retain a trusted
   `PGSSLROOTCERT` when necessary. Keep `DATABASE_PRODUCTION_WRITES_AUTHORIZED=false`.
   This command uses only the current shell environment, not `.env` fallbacks.

   ```powershell
   $python = Join-Path $PWD 'apps\api\.venv\Scripts\python.exe'
   $privateDir = 'REPLACE_WITH_EXISTING_ENCRYPTED_PRIVATE_DIRECTORY'
   $backupDir = 'REPLACE_WITH_APPROVED_OFF_PROVIDER_DESTINATION'
   $identityPath = 'REPLACE_WITH_PRIVATE_AGE_IDENTITY_PATH'
   $recipient = (& age-keygen -y $identityPath).Trim()
   if ($LASTEXITCODE -ne 0) { throw 'Key unavailable.' }
   $stamp = [guid]::NewGuid().ToString('N')
   $bundle = Join-Path $backupDir ("portfolio-$stamp.age")
   & $python -m portfolio_api.recovery_bundle preflight --source production `
     --report (Join-Path $privateDir "inventory-$stamp.json")
   if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; stop.' }
   ```

   Review the private inventory, actual schema/rows, extensions, roles/grants and
   canonical receipt against the approved target. RLS, unknown objects, extra
   schemas, large objects, schema drift, unreadable rows or access drift block export.

4. **Only after explicit backup approval**, run interactively:

   ```powershell
   & $python -m portfolio_api.recovery_bundle backup --source production --output $bundle `
     --staging-root $privateDir --recipient $recipient
   if ($LASTEXITCODE -ne 0) { throw 'Backup failed; do not ingest.' }
   ```

   Type the displayed `BACKUP host/database` yourself after checking the paths.
   No piped confirmation. `ENCRYPTED_EXPORT_CREATED` is not recovery verification.
   Record the ciphertext SHA256 privately. If the first destination is local,
   copy to the approved off-device destination and verify the same hash there.
   Rehearse from **that copy** and the recovered key, not just the staging files.
   age protects ciphertext integrity; it is not a signature of the producer.
   Accept only operator-custodied bundles, never untrusted archives.

5. On the approved rehearsal machine, decrypt into a new encrypted private directory:

   ```powershell
   $rehearsalDir = Join-Path $privateDir ("rehearsal-$stamp")
   & $python -m portfolio_api.recovery_bundle decrypt --bundle $bundle `
     --identity $identityPath --destination $rehearsalDir
   if ($LASTEXITCODE -ne 0) { throw 'Decrypt/integrity check failed; stop.' }
   $archive = Join-Path $rehearsalDir 'database.dump'
   ```

   For an approved Neon target, the existing [restore wrapper](postgresql-migration.md)
   prompts privately for credentials and exact target confirmation:
   `.\scripts\postgres-migration.ps1 -Operation restore -Archive $archive -Report <new-private-report>`.
   It requires an empty `_migration` database on a verified nonprimary child branch.
   It rejects populated targets and the Neon primary; it never uses `--clean`.

   The no-cloud alternative is an approved isolated loopback PostgreSQL 18 database
   ending in `_test`. Securely load its `MIGRATION_TARGET_URL` into this shell
   (never in a command line), then use the same guarded restore engine directly:

   ```powershell
   $env:MIGRATION_ALLOW_TEST_TARGET = '1'
   $env:MIGRATION_EXPECTED_TARGET_HOST = '127.0.0.1'
   $env:MIGRATION_EXPECTED_TARGET_DATABASE = 'REPLACE_WITH_APPROVED_EMPTY_DATABASE_test'
   $confirmation = Read-Host "Type RESTORE $($env:MIGRATION_EXPECTED_TARGET_HOST)/$($env:MIGRATION_EXPECTED_TARGET_DATABASE)"
   & $python -m portfolio_api.postgres_migration restore --archive $archive `
     --confirm-target $confirmation --report (Join-Path $privateDir "restore-$stamp.json")
   if ($LASTEXITCODE -ne 0) { throw 'Restore failed; do not ingest.' }
   Remove-Item Env:\MIGRATION_TARGET_URL, Env:\MIGRATION_ALLOW_TEST_TARGET
   ```

   Type that confirmation yourself. Never pipe it or reuse production credentials.
   Match source encoding, locale provider/version, collation and extensions exactly.
   Production currently reports `C.UTF-8`, builtin locale provider `b`, version `1`.
   A default Windows cluster may differ: use a matching isolated PostgreSQL 18
   environment, not a manifest edit. Provisioning a new cloud target needs approval.

6. Require `RESTORED_AND_RECONCILED`, zero schema/table/sequence differences and
   accepted holdings/cash/targets/receipt fingerprints. Review `access.json` and
   recreate only approved application roles and privileges on the isolated target;
   never replay provider-managed roles or copy production passwords. Verify the
   intended API role can read the restored portfolio and cannot perform forbidden
   writes. Start the API against **only that isolated target**, with workers and
   integrations disabled; verify holdings, cash, targets and source availability
   through API and UI. Record restore duration and evidence privately.
   Dispose of decrypted artifacts only after evidence and encrypted copies are
   verified. A real production restore or reroute requires separate authorization.

## Bounded activation sequence

1. Complete recovery above and resolve [provider access](financial-data-provider-decision.md).
   Rerun the [existing market preview and guarded procedure](production-data-ingestion-operations.md)
   with dates `2025-11-10` / `2026-11-09`. Require exactly 22 reviewed held listings,
   no extra lifecycle subjects, DKK/EUR + USD/EUR, the frozen crosswalk and canonical
   receipt. The approved conceptual scope is already recorded; do not ask for it again.
2. Prepare that immutable 24-checkpoint run using the existing operator write guard.
   Execute `--max-checkpoints 1`; inspect raw response identity, currency, UTC/local
   session date, raw versus adjusted close and FX direction. Reconcile that checkpoint
   before continuing one at a time. Budget: 24 logical requests; the Yahoo transport
   allows one initial HTTP request plus three retries per checkpoint invocation
   (four for the first checkpoint, up to 96 for a first pass). The checkpoint ledger
   permits three attempts, making 288 the worst-case transport ceiling across the
   full scope. Review failures before any resume; that ceiling is not permission
   for a blind retry loop. Calls are serial with bounded transport backoff and at
   least one second between checkpoints. Stop on entitlement,
   identity, unexpected currency, exhausted budget, unreconciled rows or protected-state
   differences. Partial coverage stays partial; no filling missing observations.
3. Read back actual price/FX counts, first/last dates, currencies, duplicate/conflict
   counts and the untouched holdings/cash/targets fingerprints. Verify historical
   company charts and EUR portfolio valuation using stored rates in the authenticated
   deployed UI. Distinguish price history from portfolio performance. Corporate actions
   remain unverified and never become inferred ledger transactions.
4. Execute one controlled incremental overlap only after the initial reconciliation;
   record its exact approved end date and request budget. Reuse the existing ingestion
   services, durable requests, locks, deduplication, retries and status. First prove
   the manual request path end to end. Daily scheduling remains conditional.
   The checked-in Render plan is free, starts only Uvicorn, and can [sleep after 15
   idle minutes](https://render.com/docs/free); an in-process timer is not reliable.
   Lowest-cost proposal: an owner-operated always-on machine runs the existing
   recurring worker with `--once` daily at 02:00 UTC Tuesday-Saturday, five calendar
   days of overlap, market jobs only. Verify actual deployed configuration, credential
   storage, missed-run recovery and monitoring before approving this activation.
   No new cron service, worker rewrite or broad operation enablement is part of this PR.
5. SEC proceeds independently of market entitlement once recovery is ready. Review
   the existing private issuer evidence, choose **one exact held company UUID/CIK**,
   and approve its mapping write separately. Provide a monitored `SEC_USER_AGENT`.
   Run `db:bootstrap-fundamentals -- preview --target-environment production --company-id <UUID>`;
   require exactly one reviewed mapping. Prepare with the same company filter.
   Run one checkpoint and reconcile before the second stage (filings, then facts).
   A filing checkpoint allows the submissions index plus at most five history files;
   facts uses one Company Facts request. More filing pages need another bounded review;
   do not equate two stages with complete filing history. Minimum interval is 0.15s,
   maximum three failures per checkpoint. Retain accession, units, fiscal dates,
   corrections and raw evidence. No filing-body downloads or accepted-model changes.
   No verified company selection means NO-GO, not inferred identity. The current
   missing production mappings are an exact blocker, not a reason to build a new adapter.

Consensus remains disabled until FMP entitlement, credentials and exact symbol,
currency, period and coverage checks pass. Deployments, schema changes, Sheets,
model acceptance and ledger ownership are outside this sequence.
