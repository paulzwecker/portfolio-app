# Workbook Sync Operations

## Purpose and activation boundary

This runbook describes manual synchronization of the configured portfolio/watchlist
Google workbook into the canonical PostgreSQL application. Google Drive is read-only;
the app never writes to the portfolio source workbook. The sync stages a frozen source
revision, creates a validation/reconciliation preview, and applies only after explicit
operator review. It does not run financial models, refresh market or SEC data, create
current ranking/execution runs, confirm holdings, alter targets, accept research, or
trade.

The feature is implemented but deliberately disabled by default. There is no scheduled
portfolio workbook poll and this change does not create or change a Render/Vercel
service. Do not interpret this runbook as authorization to write to production.

## Data ownership and import policy

See [Workbook Source Ownership](workbook-sync-ownership.md) for the complete field
matrix. In brief, the approved workbook owns source company/lifecycle inputs, holdings
and cash snapshots, strategic target inputs, the four workbook quality scores,
research-priority inputs, and published legacy model-output snapshots. Provider
observations, application-accepted models/research/theses/risks, holdings confirmations,
current ranking runs, execution runs, review decisions, and operational history remain
application-owned. Cached workbook ranks remain source snapshot observations; they do
not become current canonical ranking runs.

The importer uses the reviewed canonical listing crosswalk. Ticker similarity does not
create a listing, venue, currency, security, or company mapping. An unresolved exact
identity blocks the affected preview. A missing source row is reported as
`SOURCE_ROWS_ABSENT_NOT_DELETED`; it is not a delete, liquidation, zero, lifecycle
change, or target change. Existing holdings and target guards additionally block
unsafe reductions/removals without explicit reviewed semantics. Source-owned accepted
state is updated only by the import workflow; application-owned append-only records are
not overwritten.

Market/FX, SEC fundamentals/filings, other provider ingestion, model recalculation and
decision recomputation stay on their existing separate operations. `REFRESH_ALL` does
not run this workbook sync.

## Snapshot and run ledger

The sync reuses `source:workbook`'s exact-file Google Drive reader and XLSX validation.
It checks file metadata around acquisition and rejects a workbook that changes while
being downloaded/exported. The resulting bytes are frozen before parsing and stored in
`workbook_sync_artifacts`, keyed by SHA-256. XLSX payloads are capped at 32 MiB. The
manifest records source identity as a one-way hash, Drive revision/checksum/MIME type
where provided, acquisition/recorded time, workbook contract version, schema/header
fingerprints, raw artifact hash, and the versioned semantic fingerprint over
importer-relevant values. The raw Drive file ID is not returned by the run API or CLI
summary. The sync recomputes the semantic fingerprint from the frozen bytes before parsing;
missing or changed semantic metadata fails closed. Reacquire snapshots created before
`portfolio-import-values-v2` before staging them with the current sync implementation.

`workbook_sync_runs` records the acquisition, source projection, importer version,
preview/apply status, errors, reviewer and timestamps. `workbook_sync_previews` is
append-only, so refreshed previews retain their old outcomes. Schema approval binds a
reviewer and rationale to the exact source identity, contract, schema/header
fingerprints and reviewed artifact hash. The existing `operational_job_requests` and
`operational_job_attempts` record a requested one-shot stage and its outcome.

An unchanged source-content idempotency key reuses its existing run/artifact. An exact
apply replay returns `ALREADY_APPLIED`; a separately acquired revision with the same
projection is recorded as `NO_CHANGES`. A new content hash creates a new immutable
artifact/run. No cleanup job deletes historical artifacts; plan storage capacity
before regular synchronization. On a Neon Free project, the current documented limit
is 1 GB of database storage. At the code's 32 MiB per-artifact maximum, 32 unique maximum
size snapshots alone would consume 1 GiB before database/index overhead. Actual source
snapshots are often smaller, but measure them. Stop if storage is approaching limits and
design a separately reviewed archive/retention policy; do not prune audit history
silently.

## Review workflow

1. Confirm the exact source ID and service-account permission out of band. The service
   account needs Viewer access to the explicitly configured portfolio file. The reader
   uses the existing Google Drive read-only scope; no editor access is required.
2. Enable only the manual operation and workbook staging flags in the approved
   operator environment. Leave `RECURRING_OPERATIONS_ENABLED=false` and
   `GOOGLE_SHEETS_POLL_SECONDS=0`. Never set `WORKBOOK_SYNC_ENABLED` as a way to turn on
   polling: the flag only permits an explicitly requested `WORKBOOK_SYNC` job.
3. Queue `WORKBOOK_SYNC` for `ACTIVE_UNIVERSE` in Operations. The equivalent API
   request is `POST /v1/operations/job-requests` with
   `{"job_name":"WORKBOOK_SYNC","scope_kind":"ACTIVE_UNIVERSE"}`. The request contains no
   arbitrary file ID, URL, date range, provider, or command. A durable job request and
   attempt record are created. If the cloud service has no continuously running manual
   worker, the request stays queued until an operator invokes the exact-ID one-shot
   runner described below.
4. Inspect the run by ID. A new/changed schema yields
   `SCHEMA_REVIEW_REQUIRED`; the XLSX is frozen but not parsed into domain rows until
   the exact schema fingerprint is approved. Review the data-free structural contract
   and the private source snapshot through the approved local/private review process.
5. Approve a schema only when the headers, required tabs, source cells and importer
   meaning are understood. Approval is reviewer-, rationale-, artifact-hash- and
   fingerprint-bound. It does not approve financial or portfolio decisions.
6. Review the generated preview. Resolve exact listing/currency mappings, invalid rows,
   target/holdings changes, app-owned conflicts and warnings. If canonical state changes
   after preview, apply is rejected; refresh the preview and review the new diff.
7. Apply only an unblocked `PREVIEWED` artifact hash after separate production write
   authorization and the production procedure below. Apply is a single database
   transaction and runs source reconciliation before commit. A mismatch rolls back.
8. Inspect the receipt and compare record counts/domain digests. Keep source and app
   decisions separate: applying workbook rows is not a substitute for an investor's
   holdings confirmation, an accepted native model revision, or a decision run.

## Local operator commands

All commands below use the repository's guarded SQLAlchemy engine. Use an isolated
development or rehearsal target for execution testing. Do not put credentials in the
command line. The request ID and artifact hash are non-secret identifiers, but keep
private workbook contents and financial reports out of Git, CI, and shared logs.

For local manual processing, set the required flags only in the operator process and
queue the job in Operations. Then run the exact queued request once:

```powershell
$env:MANUAL_OPERATIONS_ENABLED = "true"
$env:WORKBOOK_SYNC_ENABLED = "true"
npm run operations:run-manual -- <request-uuid> --confirm-run
```

For a private operator process that should not rely on the public API queue, the runner
can create a durable allowlisted request and run that exact request once:

```powershell
$env:MANUAL_OPERATIONS_ENABLED = "true"
$env:WORKBOOK_SYNC_ENABLED = "true"
npm run operations:run-manual -- --job-name WORKBOOK_SYNC --scope-kind ACTIVE_UNIVERSE --confirm-run
```

Read a sanitized run summary (no database writes):

```powershell
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.workbook_sync show <run-uuid>
```

After exact source/schema review, refresh a preview if canonical state changed:

```powershell
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.workbook_sync refresh-preview <run-uuid> --expected-artifact-sha256 <sha256>
```

Schema approval and apply are separate guarded writes. They require the exact artifact
hash, reviewer, schema rationale where applicable, and database write-target
authorization:

```powershell
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.workbook_sync approve-schema <run-uuid> --expected-artifact-sha256 <sha256> --reviewer <reviewer-id> --rationale "<schema review rationale>"
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.workbook_sync apply <run-uuid> --expected-artifact-sha256 <sha256> --reviewer <reviewer-id> --confirm-apply
```

For local test/rehearsal use the correct isolated target flags and validate target
identity before the command. Do not copy production credentials into tests. A
production apply additionally requires the existing Neon project/primary branch/direct
endpoint verification, `sslmode=verify-full`, exact database identity, operator
authorization, and a recoverable backup/restore point. Production `apply` is out of
scope here and was not run.

## Render cloud execution

The sync runs as a short-lived one-shot process, not inside FastAPI import/startup and
not in the Vercel request path. Render Free web services spin down and do not support
shell/SSH or one-off jobs. A compatible paid Render service can be the base service for
an operator-created Render One-Off Job; it receives that service's environment snapshot
and exits after the allowlisted Python command finishes. The preferred operator flow
creates one durable request inside the one-shot process and immediately runs only that
request. This avoids enabling manual-write endpoints on the public API. The CLI accepts
only the existing `OperationalJobRequest` allowlist and exact scope types; it accepts no
provider URL, arbitrary command or workbook ID. For an already queued request, pass its
exact UUID positionally instead.

```sh
MANUAL_OPERATIONS_ENABLED=true WORKBOOK_SYNC_ENABLED=true \
DATABASE_PRODUCTION_WRITES_AUTHORIZED=true \
uv run --locked --no-dev python -m portfolio_api.manual_job_runner \
  --job-name WORKBOOK_SYNC --scope-kind ACTIVE_UNIVERSE --confirm-run
```

The production write flag above is a per-process command environment override; it does
not change the base service's environment. It is a broad write authorization enforced by
the existing target guard, so use it only after separate operator authorization and
exact-target verification. No production request was run for this milestone. Keep the
public API's production write flag off; its job-request endpoint stays disabled until a
separate authentication/security decision authorizes it.

Render's One-Off Job API needs a Render API credential held by the operator, not by the
application. One-off jobs use the base service's latest successful build and configured
environment; verify that the required Python dependencies and secret files are present
in that artifact/environment before use. The command exits on completion and does not
poll. Render documents one-off jobs as per-second billed, and Free services do not
support shell or one-off execution. Do not expose a Render API token to the browser or
store it in this repository.

The Render worker process requires the exact production `DATABASE_URL`, target database
and Neon project/branch/endpoint IDs, read-only Neon API key for target verification,
Google service-account secret file path, and explicit per-process production-write
authorization. `MANUAL_OPERATIONS_ENABLED=true` and `WORKBOOK_SYNC_ENABLED=true` must be
set for an operator run; recurring jobs and Sheets polling stay off. The preferred
one-shot CLI path creates its request internally, so the public API does not need to
accept manual write requests. The Operations UI queue remains unavailable while the
production API write guard is off. The existing production write flag authorizes a broad
class of application database writes, not only this job. Do not enable it on the public
API service without a separate security review and operator approval. This milestone
does not change Render configuration or enable that flag.

Future options, not activated here:

- Render Cron can be manually triggered from its Runs page, but creating a Cron service
  also establishes a schedule. Render currently documents a $1/month minimum per Cron
  service plus active compute time, so create one only after schedule approval.
- Vercel Hobby Cron is limited to one invocation per day with hourly timing precision;
  it invokes a Vercel Function and is not a suitable place for this bounded Python/Postgres
  importer. It is not configured here.
- GitHub Actions is not used because source credentials and private workbook-derived
  state must not transit CI.

The least-cost presently safe production posture is to keep scheduling disabled and
operate from a compatible, explicitly launched Render one-off environment only after
the authorization/security blockers are resolved. If the current deployment remains on
Render Free, cloud manual execution is unavailable there; use a vetted external operator
environment or approve a compatible paid one-off runner. Do not fall back to a long-lived
web request.

Provider documentation used for the cost/plan comparison: [Render One-Off Jobs](https://render.com/docs/one-off-jobs),
[Render Cron Jobs](https://render.com/docs/cronjobs), [Render Free service limits](https://render.com/docs/free),
[Render shell access](https://render.com/docs/ssh), [Vercel Cron pricing/limits](https://vercel.com/docs/cron-jobs/usage-and-pricing),
and [Neon Free storage update](https://neon.com/blog/neon-free-plan-1-gb-per-project).

## Environment matrix

Values shown are names/policies, not production values. Store secrets in Render secret
environment/secret files and Vercel environment settings, never Git or CI.

| Runtime         | Required settings                                                                                                                                                                                                                                      | Required safe posture                                                                                                                                                                         |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API service     | `APP_ENV=production`, direct Neon `DATABASE_URL` with TLS hostname validation, `DATABASE_TARGET_ENVIRONMENT=production`, exact `DATABASE_TARGET_DATABASE`, `NEON_API_KEY`, `NEON_PROJECT_ID`, `NEON_BRANCH_ID`, `NEON_ENDPOINT_ID`, `API_ACCESS_TOKEN` | `RECURRING_OPERATIONS_ENABLED=false`, `GOOGLE_SHEETS_POLL_SECONDS=0`; manual flags remain false until separately approved. Keep `DATABASE_PRODUCTION_WRITES_AUTHORIZED=false` by default.     |
| One-shot runner | Same exact guarded Neon target and read-only Neon metadata key; `GOOGLE_DRIVE_PORTFOLIO_WORKBOOK_FILE_ID` (or explicitly approved `GOOGLE_SHEETS_SPREADSHEET_ID` fallback); service-account secret file and `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` path  | For one explicitly authorized request only, set `MANUAL_OPERATIONS_ENABLED=true`, `WORKBOOK_SYNC_ENABLED=true`, and production write authorization in that process. Do not attach a schedule. |
| Vercel web      | `API_BASE_URL`, `API_ACCESS_TOKEN`, existing access-gate credentials                                                                                                                                                                                   | No Google credentials, Neon URL, Render API token, workbook file, or job execution code.                                                                                                      |

`GOOGLE_DRIVE_MARKET_DATA_WORKBOOK_FILE_ID` belongs to the separate market-workbook
acquisition/bootstrap workflow; it is not read by this portfolio synchronization job.

The direct API access token and Vercel shared login are not per-reviewer identities.
Before routine production use, document who may queue, schema-approve, and apply, and
ensure review actions are attributable to that person. The reviewer string is audit
metadata, not authentication by itself.

## Failure, retry, and recovery

| Failure                                  | Expected behavior                                                                                                  | Operator action                                                                                                                          |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Drive timeout/permission/metadata error  | Failed request/run with a sanitized code; no partial XLSX is parsed                                                | Check exact configured file ID, service-account Viewer share, Google API enablement and egress; fix then explicitly retry.               |
| Workbook changes during download/export  | Acquisition rejects unstable revision; no apply                                                                    | Retry after workbook editing settles; compare source revision metadata.                                                                  |
| New schema/header fingerprint            | Frozen artifact retained as `SCHEMA_REVIEW_REQUIRED`; no row parsing/apply                                         | Review exact contract and artifact hash; approve only the fingerprint and version you reviewed.                                          |
| Missing exact canonical listing/currency | Preview blocked, mapping is not guessed                                                                            | Add/review canonical identity crosswalk separately, then refresh preview.                                                                |
| Source row absent                        | Preview warning `SOURCE_ROWS_ABSENT_NOT_DELETED`; no row is deleted or converted to zero                           | Compare frozen snapshots and determine whether absence is intentional; do not treat it as liquidation without explicit source semantics. |
| App-owned data changed after preview     | Apply rejected by target-state hash/conflict checks                                                                | Refresh and review a new preview. Resolve app-owned conflicts through their native workflow.                                             |
| Transient failure/worker interruption    | Durable request/run/attempt state; transactions roll back; stale request can be retried using existing queue rules | Inspect status, ensure prior process stopped, then explicitly retry the same failed request through Operations. Exact replay is safe.    |
| Reconciliation mismatch                  | Entire apply transaction rolls back; run remains unapplied/blocked                                                 | Preserve evidence, correct the mapping/contract, regenerate preview; do not edit database records manually.                              |
| Database nearing storage limit           | No automatic artifact deletion                                                                                     | Stop new acquisitions and design an approved archive/retention policy before more unique snapshots.                                      |

## Verification status and limitations

The staging workflow is covered by synthetic PostgreSQL integration tests: exact
artifact freezing and replay, schema approval, a synthetic bootstrap → sync apply →
replay, app-owned holdings change conflict, append-only preview history, removed-row
warnings, and exact-request one-shot worker behavior. Provider/network credentials and
the real configured Google workbook are not used by these tests. No live Google Drive
acquisition, Neon staging import, production apply, Render one-off job, or recurring
schedule was executed for this milestone. The current live workbook access/setup remains
an operator prerequisite; see [Workbook Source Acquisition](workbook-source-acquisition.md).
