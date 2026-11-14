# Active workstream

## Encrypted recovery and bounded data activation — integration

Branch `codex/data-recovery-activation` starts from main `ddbacbc`, after owner-merged
PRs #34, #36 and #35. The owner checkout, ledger-income branch, stashes and private
artifacts are untouched. No replacement feature PRs or unrelated changes.

Frozen acceptance: reuse native snapshot/dump/restore reconciliation; add an
operator-only encrypted bundle and production read-target verification; prove
recovery on disposable PostgreSQL; provide precise recovery, provider and ingestion
choices. No new service, schema, worker or production activation.

Implemented: production-read-guarded preflight/export, age encryption of the native
archive/manifest and password-free access inventory, fixed-member decryption,
no-overwrite behavior and interactive backup confirmation. Existing restoration
still rejects production/populated targets and reconciles exact data and schema.
A real production backup is NOT STARTED. Native migration source restrictions are
unchanged; only the explicit recovery export role uses the existing production read guard.

Verification: 174 recovery/migration/production-target/market/SEC tests passed on a
disposable native PostgreSQL 18 cluster, including encrypted round trip, wrong key,
truncation, overwrite, noninteractive rejection and RLS rejection. Ruff and mypy
passed; OpenAPI/TypeScript contracts match; 22 deployment/documentation tests and
both offline schema gates passed. No frontend change requires a new visual review;
no live chart or UI data-readback claim is made. CI installs age only in its isolated
PostgreSQL test job; no application dependency or deployment image changes.

Current read-only production evidence (2026-11-14): exact Neon primary identity and
`neondb.public` revision `b59f16c8a203` matched. No extra user schemas, large objects
or RLS. One accepted snapshot / 22 positions / two cash rows / one target revision.
Prices 0, FX 0, facts 0, filing records 0, consensus observations 0. Market preview
READY: approved 2025-11-10–2026-11-09 window, 22/22 Yahoo listing mappings, two FX
pairs, 24 logical requests, zero provider requests/writes. SEC preview BLOCKED:
no reviewed production CIK mappings. Private target-bound reports and the exact
single-issuer proposal are in `%LOCALAPPDATA%\PortfolioResearch\private-reports`.
The existing isolated SEC source-backed evidence is not production ingestion.

Engineering package is [PR #37](https://github.com/paulzwecker/portfolio-app/pull/37).
Local checks pass; verify the latest-head remote checks before owner merge.
Release classification: CONFIGURATION_REQUIRED; deployment controls/live hosted
SHAs are unverified, and no deployment is authorized. No migrations. Production
data activation remains BLOCKED on an approved encrypted destination/key custody
and isolated current-state restore rehearsal, plus Yahoo entitlement or an approved
alternative provider. The expiring November 8 Neon branch is not a durable backup.

Next exact action: owner names existing encrypted/off-device storage and a matching
isolated restore target, and approves backup/rehearsal. Then the operator runs the
interactive procedure and verifies recovered API/UI data before any ingestion.
Choose documented Yahoo permission or evaluate the EODHD Historian candidate under
separate subscription/provider approval. SEC can advance independently after recovery,
review of the exact source-backed issuer/CIK proposal and a monitored contact.

Canonical instructions: [recovery and activation](encrypted-production-recovery.md),
[provider matrix](financial-data-provider-decision.md), and
[guarded ingestion](production-data-ingestion-operations.md). Deferred: generic backup
services/PITR management, new provider adapters before selection, scheduler changes,
Sheets recovery and UI refactors. Manual/scheduled production refresh remains disabled.
Prior integration evidence remains in Git at main `ddbacbc` and the merged PRs;
production release must still verify the API-first dependency introduced by #35.
