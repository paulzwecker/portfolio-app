# R10 — Application Readiness and Cloud Synchronization Release Candidate

- **Assessment date:** 2026-10-26
- **Release-candidate status:** CONDITIONALLY READY FOR REVIEW
- **Production operating status:** NOT READY
- **Production writes, imports, providers, polling, schedules and deployments:** not run or enabled

## Scope and evidence boundary

This assessment uses the local checkout, synthetic fixtures and the isolated loopback
PostgreSQL test database `portfolio_app_test`. It does not connect to Neon or Google
Drive, read current production records, or establish that the production database has
been bootstrapped. Earlier operational documentation says the canonical R7 import was
not reconciled. No separate Task 8 findings report or Task 9 completion report was
present in the checkout. Task 9 implementation is present as local changes and was
reviewed and tested where possible; it is not live-cloud verification.

The active branch is `codex/task-8-readiness-test-isolation`. The worktree contains
substantial pre-existing R8/Task 9 changes. They were preserved. This assessment added
the missing semantic fields to the synthetic workbook-sync manifest helper and applied
formatting to two Markdown documents. No broad staging or commit was performed.

## Synchronization release candidate

The existing implementation is a bounded, manual Google Drive → canonical PostgreSQL
workflow. It reuses the reviewed `source:workbook` acquisition and canonical importers.
It is not a Sheets polling service and is not enabled by default.

1. Acquire the explicitly configured source read-only, verify stable Drive revision
   metadata, export/freeze the XLSX and retain its raw SHA-256 in the private
   content-addressed artifact store.
2. Record source identity hash, source revision/checksum where supplied, acquisition
   time, contract/schema/header identity and the versioned semantic fingerprint over
   importer-relevant values. Recompute the semantic fingerprint from frozen bytes
   before parsing; incomplete or changed manifests fail closed.
3. Stage a durable sync run and append-only preview. Resolve exact company, security,
   listing, currency and fiscal mappings. Compare source projection hashes with
   canonical state and report blockers, warnings and missing rows. Absence is not a
   deletion instruction.
4. Require explicit schema review and a separate source-state preview. An apply must
   reference the reviewed artifact hash, be unblocked, and still match the current
   target-state hash. A transaction advisory lock and transaction-scoped reconciliation
   prevent overlapping apply and roll back mismatched projections.
5. Store a durable operational request/attempt and run/preview receipt. Exact replay
   is idempotent; the same projection is reported as `NO_CHANGES`. Accepted application
   model/research revisions, provider facts, holdings confirmation, target decisions,
   ranking runs and execution history are not overwritten. Source-owned records can
   be updated only under the ownership matrix in
   [workbook-sync-ownership.md](../workbook-sync-ownership.md).

The manual API path requires the server-side access token in remote environments and
the explicit manual/workbook feature flags. The shared production write-target guard
still governs mutations. A one-shot allowlisted runner supports an operator-created
durable request followed by one explicit `--confirm-run`; it is preferable to opening
public production writes. Public job requests remain disabled with current production
write authorization off. There is no arbitrary command, URL, workbook-ID or provider
input in the job contract.

One material limitation remains: `reviewer` is audit text, not an identity established
by an individual authentication system. The API access token is shared service
authentication. Before routine multi-user production reviews, bind review actions to
an authenticated human identity and role policy. This is not a reason to weaken the
current disabled-by-default guard.

## Domain readiness scorecard

“Synthetic verified” means deterministic fixtures and isolated local tests only. It is
not evidence that the same coverage exists in Neon.

| Area             | Local implementation/test evidence                                                                                                                    | Real-data state                                                                                                                    | Production prerequisites                                                                                                                                                    |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Portfolio        | Valuation, holdings, cash and allocation APIs have unit/fixture coverage; synthetic canonical bootstrap and workbook-sync apply/replay are exercised. | Unknown in this task; no current production query. Do not present historical local counts as Neon coverage.                        | **R7** canonical portfolio baseline; **R8** exact-listing prices/FX for current valuation; **R9** model/analytics outputs for investment context.                           |
| Universe         | Identity/lifecycle, score, rank and eligibility domains pass the local unit suite; workbook ownership/import mapping is explicit.                     | No reconciled R7 universe was verified.                                                                                            | **R7** identities/lifecycle/scores; **R8** supported factual observations; **R9** model outputs and valid decision inputs.                                                  |
| Company Explorer | Financials, market history, model, thesis, research and source views are covered by API/UI tests and the production web build.                        | Actual company coverage and sparse/missing states in Neon were not inspected.                                                      | **R7** company/listing baseline; **R8** prices, FX, fundamentals and filings; **R9** native model state/outputs.                                                            |
| Models           | Deterministic methods, revisions, interoperability and normalized-output contracts are present; model/domain tests pass.                              | No R9 production bootstrap/reconciliation verified here.                                                                           | **R7** canonical identities and workbook source baseline; **R9** parity-backed model import/compute.                                                                        |
| Decisions        | Rank, return comparability, attribution and execution fixtures pass; no decision rules were relaxed.                                                  | No fresh production rank/execution runs or coverage counts were generated.                                                         | **R7** holdings and targets; **R8** current factual inputs; **R9** eligible model outputs. Human target decisions remain investor-owned.                                    |
| Operations       | Manual job request/attempt ledger, allowlisted one-shot runner, disabled-by-default flags, runbook and synthetic replay/conflict tests exist.         | No live Google Drive, Neon, Render or provider operation was exercised. Current production migrations were not checked or changed. | Deploy reviewed schema migrations; verify exact target; R7 source baseline; explicit one-off authorization. **R8/R9** are needed only for their respective data/model jobs. |

Current production record counts, market/fundamental coverage, native-model coverage,
ranking availability, and Execution Pace availability are **unverified**, not zero.

## Deployment, resource, retention and rollback review

- **Render:** checked-in configuration uses a Python web service, `$PORT`, Frankfurt,
  a liveness endpoint, and disables ingestion/recurring operations/Sheets polling.
  No Render configuration or service was changed. Render Free does not provide the
  documented one-off job capability; manual cloud execution requires an operator-run
  compatible one-off environment or a separately approved runner plan.
- **Vercel:** checked-in monorepo install/build commands are compatible with the
  frontend workspace. No deployment or environment settings were changed.
- **Neon:** the write-target code uses direct endpoint/project/branch/database
  verification and TLS policy; no live Neon identity or readiness check was performed
  during R10. Local Alembic head is `c17a0b9d4e62`; the prior production record was at
  `6c2eaf0b8147`. The new workbook-sync/bootstrap migrations therefore require a
  separately reviewed and authorized production schema-upgrade procedure before this
  workflow can operate there.
- **Scheduling:** no schedule is configured or enabled. Vercel is not used as the
  Python/PostgreSQL importer runtime. Recurring operations stay disabled.
- **Storage/retention:** frozen artifacts are append-only and capped at 32 MiB each.
  The runbook estimates that 32 maximum-sized artifacts would consume 1 GiB before
  indexes/metadata. There is no automatic pruning. Measure storage, set an explicit
  archive/retention policy, and stop new unique snapshots before approaching the plan
  limit; never silently delete audit artifacts.
- **Rollback:** restore from a verified pre-import database recovery point when needed.
  For a mistaken source projection, use a reviewed compensating sync from a prior
  approved snapshot and retain both receipts. Apply is transactional and reconciliation
  mismatch rolls back. Do not edit production rows or delete historical receipts by
  hand.
- **Cost:** the existing runbook records the Free-plan limitations and paid one-off
  runner trade-off. No service was provisioned. Confirm current vendor plan pricing
  before approving an operating budget.

## Verification results

| Check                            | Result  | Qualification                                                                                                                                                                                                                                                                                                                                         |
| -------------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ESLint + Ruff                    | PASS    | `npm run lint` passed after the fixture correction.                                                                                                                                                                                                                                                                                                   |
| Prettier + Ruff format           | PASS    | `npm run format:check`; 213 files.                                                                                                                                                                                                                                                                                                                    |
| Web TypeScript + API mypy        | PASS    | API mypy: 155 source files.                                                                                                                                                                                                                                                                                                                           |
| Web unit tests                   | PASS    | 163 passed in the full unit run.                                                                                                                                                                                                                                                                                                                      |
| API unit tests                   | PASS    | 464 passed, 2 skipped; 146 deselected by the unit marker in the full unit run.                                                                                                                                                                                                                                                                        |
| Contract check                   | PASS    | OpenAPI and TypeScript contracts current.                                                                                                                                                                                                                                                                                                             |
| Next.js production build         | PASS    | Build and static page generation completed.                                                                                                                                                                                                                                                                                                           |
| CI source-data policy assertions | PASS    | 3/3 pass when the test module is run directly. `npm run test:repo-policy` cannot start Node's test worker in this Windows sandbox (`spawn EPERM`); assertions themselves pass without reducing coverage.                                                                                                                                              |
| PostgreSQL integration suite     | PARTIAL | Full run: 120 passed, 5 failed, 2 errors. Two failures require local `CREATEROLE`; two setup errors require `pg_dump`/`pg_restore` or the configured tools container. Three workbook-sync failures were incomplete synthetic manifests; the helper was corrected without weakening validation, and all 5 workbook-sync integration tests then passed. |
| Production/browser smoke         | NOT RUN | No live Neon, Google Drive, Render/Vercel deployment, or desktop/mobile real-data walkthrough was performed.                                                                                                                                                                                                                                          |

The full `npm run check` is therefore not green as a single command: its repository
policy test runner hits the Windows `spawn EPERM`. Its preceding checks passed, the
policy assertions pass by direct invocation, and contracts/build were run independently.

## Exact production checks still dependent on R7/R8/R9

- **R7 must execute and reconcile** the approved canonical company/listing/portfolio
  workbook baseline. Without it, production source synchronization has no canonical
  target state and portfolio/universe real-data checks cannot be claimed.
- **R8 must execute its separately authorized, bounded ingestion** to establish real
  prices, FX, filings and fundamentals, then reconcile exact listings, provenance and
  freshness. Synthetic provider fixtures do not establish production coverage.
- **R9 must execute its separately authorized model bootstrap/compute** for eligible
  companies and reconcile methodology-specific projections/outputs. No model output
  or decision coverage should be inferred from the local test database.
- After those tasks, read-only production verification must rerun current valuation,
  return comparability, rank/Execution Pace previews and UI/API workflows against the
  exact deployed schema. Never auto-create decision runs to improve coverage.
- Production schema upgrade for migrations after `6c2eaf0b8147`, a fresh restore point,
  and an explicit operator approval remain separate gates. R10 did none of them.

## Operator actions

1. Preserve and review the current local changes; do not deploy the dirty worktree.
2. For complete local integration coverage, use a disposable PostgreSQL 18 test role
   permitted to create/drop isolated test databases and roles, or run only the required
   tests as a local PostgreSQL administrator. Never grant these privileges to the
   production application role.
3. Install PostgreSQL 18 client utilities (`pg_dump`, `pg_restore`) on the test PATH,
   or configure the already-supported migration tools container for local tests.
4. Resolve the shared-reviewer identity limitation before exposing review/apply
   operations to multiple production users.
5. Complete R7, R8 and R9 under their own approval gates; then produce a new
   production reconciliation report. Keep all recurring flags off until separately
   approved.
