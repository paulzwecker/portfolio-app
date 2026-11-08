# Historical market-data bootstrap

## Scope and current status

This stage backfills historical daily prices and dated FX observations for exact
canonical listings, and records the provider's supported split and dividend
events as unverified source facts. It does not change holdings, targets, lifecycle,
accepted decisions, or model outputs. It does not run in the background or activate
a schedule.

The command reuses the reviewed Yahoo listing crosswalk, explicit FX allowlist,
normalizers, raw-payload storage, append-only observation tables, and supersession
rules from the existing market-data ingestion path. It stores raw provider payloads
separately from normalized observations. A current quote returned alongside a
historical chart is counted in the receipt and excluded from canonical writes.

Implemented functionality is available through `db:bootstrap-market-data`.
Synthetic PostgreSQL 18 integration tests cover preview, exact identity checks,
bounded resume after an interrupted checkpoint, provider gaps, idempotent replay,
and exact persisted-row reconciliation. No real Yahoo requests, real workbook
inputs, Neon database, or production data were used in those tests. Production is
an explicit target choice, but the live procedure remains inactive and unexecuted.
Production requests require a reconciled canonical portfolio bootstrap receipt.
See [the shared production ingestion runbook](production-data-ingestion-operations.md)
for target gating, bounded execution, reconciliation and historical coverage caveats.

## Frozen source and identity scope

The stage selects canonical listings whose company lifecycle is `PORTFOLIO` or
`WATCHLIST`, plus exact listings present in the latest holdings snapshot. Each
listing must match exactly one `VERIFIED` crosswalk entry by venue, ticker,
listing currency, and security type. If the crosswalk contains canonical company,
security, or listing IDs, each supplied ID must match the database. Ambiguous,
missing, or conflicting mappings block preparation before any provider call.

FX scope comes from currencies in the latest portfolio holdings and cash compared
with the portfolio base currency, plus active/watchlist listing currencies. Only
the explicit `FX_SYMBOLS` pairs are accepted. Any unsupported required pair blocks
the frozen run; do not add a pair by guessing a provider symbol or reversing a
rate. Review the existing FX allowlist and its documented inverse-pair rules in
`portfolio_api.yahoo_finance` before requesting a scope that needs a new pair.

The inclusive start and end dates are supplied by the operator. The end date
cannot be in the future, and a single run is limited to ten years. Split older
history into separate reviewed runs. Daily price and FX rows outside the requested
window are rejected. Corporate actions outside the window are rejected as well.
Yahoo's current quote is not a historical observation for this stage and is not
inserted.

`AVAILABLE` for a listing or FX pair means that at least one normalized historical
observation was returned. A `COMPLETE` run means its checkpoints completed; neither
proves that every expected trading or FX session in the requested window is covered.
Reports expose `history_window_coverage: NOT_ASSESSED` and per-checkpoint
`history_window_evidence` with distinct observed dates, their first and last dates,
and maximum calendar spacing. Spacing is descriptive: weekends, holidays, exchange
closures and provider conventions are not classified as missing sessions. Dates
refer to the normalized batch, not all observations already in the database.
Current quotes are excluded. No response has unknown date evidence; a returned
empty series has zero dates. Older checkpoint receipts without the new fields remain
`EVIDENCE_NOT_RECORDED`, not zero or complete. The observation span does not certify
usable price history, FX coverage, completeness or freshness. Review expected sessions
and source conventions separately before interpreting coverage or chart readiness.

Operations also offers an on-demand, read-only schedule review for the latest run.
It examines at most 30 listing checkpoints per page ordered by subject key and ID,
reporting remaining listings and FX checkpoints separately. Navigation pins the run
ID, but each page is an independent read, not a transactional snapshot. Offsets
are capped at 10,000; use a smaller scoped run if that limit is reached. Only completed checkpoints with matching
frozen listing identity, batch digest and provider, listing currency and eligible
same-provider/same-currency stored closes are considered. It compares both the
first-to-last eligible-close span and the requested window intersected with the
reviewed 2026 NYSE, NASDAQ or Xetra schedule and the knowledge cutoff. The displayed
window can exclude earlier, later or not-yet-closed dates. At least one eligible close
is required; an empty batch remains explicitly unassessed. These comparisons are not
raw-payload reconciliation, proof of actual trading, a
confirmed missing trade, an assessment of FX sessions or a modification of receipts.
Unavailable schedules, ambiguous identities and incomplete data stay explicit.
For unavailable, failed or blocked checkpoints, and completed checkpoints without
eligible closes, the panel separately shows bounded counts recorded in the receipt:
provider responses and failures, normalized rows, rejections and warnings. Missing
or malformed evidence remains “Not recorded”; these counts do not verify raw
payloads or establish why a listing did not trade. No retry is initiated.

The prepared run pins the provider/crosswalk hash, normalizer versions, exact
listing identities, required currency pairs, target environment, and date window.
Listings are ordered as held positions first, other Portfolio listings second, and
Watchlist listings third; FX pairs follow those listing checkpoints. A company
scope can be supplied for a bounded preview/preparation. Changing a listing
identity or crosswalk after preparation blocks the affected run; correct the
reviewed source and prepare a new run.

## Corporate actions and adjustment semantics

The existing normalizer supports Yahoo dividend and stock-split event payloads.
Those events are stored with provider IDs, effective dates, raw response batch
references, and retrieval-time provenance. They remain `verified = false`; this
stage does not independently confirm them with an issuer filing or use them to
rewrite historical prices. The price normalizer retains Yahoo's native close,
split-adjusted close, and adjusted total-return series as separate fields. It does
not infer missing prices or derive adjustment factors from these actions.

Check `unverified_corporate_actions` and each listing's `action_status` in the
coverage report. A run containing unverified actions is reported as `PARTIAL` even
when all requested observations were stored. Review those actions under a separate
verification process before using them as trusted canonical corporate-action
facts.

## Target and execution safety

Every command requires `--target-environment development`, `rehearsal`, or
`production`, and requires `DATABASE_TARGET_ENVIRONMENT` to match. `preview`,
`status`, and `reconcile` use a PostgreSQL read-only engine and the read-only target
verifier; they do not require production-write authorization. `prepare`, `run`, and
`resume` use the shared write-target guard and check the exact Alembic head before
writing or calling Yahoo. A production writer additionally requires the verified
Neon primary branch, exact project/branch/endpoint/database, direct
`sslmode=verify-full` connection, a non-superuser role,
`DATABASE_PRODUCTION_WRITES_AUTHORIZED=true`, and interactive confirmation of the
exact `BOOTSTRAP <project>/<branch>/<endpoint>/<database>` phrase. Production
provider requests also require a successfully reconciled canonical portfolio
bootstrap receipt. A branch label alone is insufficient.

Use a disposable local PostgreSQL database, an independently verified isolated
rehearsal target, or an explicitly authorized verified production primary. Keep
`DATABASE_URL` in the operator's approved secret store or untracked local
environment file. Do not paste it in commands, reports, tickets, or shell
transcripts. The command output is sanitized; a private report contains
canonical company/listing identifiers, coverage, provider receipt hashes, and
failure codes, but no connection URL or credential. Store reports outside the
repository and do not upload them to CI or a PR.

The runner makes at most ten listing/pair requests per invocation, defaults to
five, uses provider concurrency one, and asks the Yahoo adapter for at most three
bounded transport retries per request (four wire attempts maximum for one
checkpoint attempt). A checkpoint can be attempted at most three times across
resumptions. A persisted one-second minimum interval separates checkpoint requests
across invocations. Use `--max-checkpoints 1` for a slow, careful rehearsal. Each
checkpoint and its raw/canonical batch receipt commit atomically. If execution
stops, resume the same run; an uncommitted `RUNNING` checkpoint is recorded as
interrupted and retried within the three-attempt limit.

## Windows PowerShell 5.1 and PowerShell 7 procedure

Run from the repository root after the application schema has been migrated to
the current Alembic head. The target must be a disposable local database or an
isolated rehearsal database with provider/network access permitted by the
operator. The CLI itself verifies the configured target before provider access.

Configure `DATABASE_URL` using the approved local secret mechanism. In the current
PowerShell process, set the non-secret target selector:

```powershell
$ErrorActionPreference = 'Stop'
$env:DATABASE_TARGET_ENVIRONMENT = 'rehearsal'
```

Preview the exact scope. This performs target/schema verification and read-only
database inventory; it makes no provider request and no application-table write:

```powershell
npm run db:bootstrap-market-data -- preview `
  --target-environment rehearsal `
  --start-date 2016-10-01 `
  --end-date 2026-10-05
if ($LASTEXITCODE -ne 0) { throw 'Market-data preview was blocked.' }
```

Review `status`, selected listing count, unresolved listings, required/allowlisted
FX pairs, planned request count, and date window. Continue only when status is
`READY`, unresolved listings are empty, and unmapped FX pairs are empty.

Create a frozen run. Preparation writes only the run/checkpoint ledger; it does
not call the provider:

```powershell
npm run db:bootstrap-market-data -- prepare `
  --target-environment rehearsal `
  --start-date 2016-10-01 `
  --end-date 2026-10-05
if ($LASTEXITCODE -ne 0) { throw 'Market-data preparation was blocked.' }
```

Copy the `run_id` from the JSON summary. Then process a small batch and inspect the
reported status:

```powershell
$runId = '<run-id-from-prepare>'
npm run db:bootstrap-market-data -- run `
  --target-environment rehearsal `
  --run-id $runId `
  --max-checkpoints 1 `
  --report (Join-Path $env:TEMP "market-data-bootstrap-$runId.json")
$runExitCode = $LASTEXITCODE
if ($runExitCode -notin @(0, 2)) { throw 'Market-data command failed before reporting a run status.' }
```

`--report` uses create-only semantics. Choose a new file for each invocation, or
omit `--report` and keep the sanitized console summary. The detailed report stays
outside the repository.

Continue in bounded invocations with `resume` until there are no pending or
retryable checkpoints. If a command returns nonzero, inspect the per-subject
failure code and coverage report before resuming:

```powershell
npm run db:bootstrap-market-data -- resume `
  --target-environment rehearsal `
  --run-id $runId `
  --max-checkpoints 5
$resumeExitCode = $LASTEXITCODE
if ($resumeExitCode -notin @(0, 2)) { throw 'Market-data command failed before reporting a run status.' }
```

Check current status without provider calls, then reconcile stored rows and
fingerprints:

```powershell
npm run db:bootstrap-market-data -- status `
  --target-environment rehearsal `
  --run-id $runId
$statusExitCode = $LASTEXITCODE
if ($statusExitCode -notin @(0, 2)) { throw 'Market-data status command failed.' }

npm run db:bootstrap-market-data -- reconcile `
  --target-environment rehearsal `
  --run-id $runId
if ($LASTEXITCODE -ne 0) { throw 'Market-data reconciliation did not match.' }
```

`MATCHED` means the immutable provider batch receipts and the stored canonical row
counts/content fingerprints still agree. It does not mean every listing had
provider coverage. Review `unavailable_coverages`, `failed_checkpoints`,
`blocked_checkpoints`, each requested date range, and unverified corporate actions.
`UNAVAILABLE` is a valid provider gap; `FAILED` means a request or normalization
failure; `BLOCKED` means an identity, target, or allowlist gate stopped work. Do not
replace any missing observation with zero or carry-forward data. Exit code `2`
means the JSON summary reported a `PARTIAL`, `BLOCKED`, or nonmatching state. A
bounded invocation commonly returns `PARTIAL` while checkpoints remain; inspect
the summary and continue only when no checkpoint is blocked or terminally failed.

Normalization warnings, including provider rows with an invalid timestamp or without a positive close, are
retained per listing or FX pair and make the run `PARTIAL`. They identify provider
response issues, not a count of missing expected sessions. Older receipts may lack
FX warning evidence; `warning_evidence_unrecorded_checkpoints` distinguishes that
unknown state from a newly captured empty warning list. Warning-only completed
checkpoints are not silently retried; review their source evidence and scope.

Remove the non-secret target selector when finished:

```powershell
Remove-Item Env:DATABASE_TARGET_ENVIRONMENT -ErrorAction SilentlyContinue
```

The commands above use syntax supported by Windows PowerShell 5.1 and PowerShell 7. They check `$LASTEXITCODE` after each npm process instead of relying on the
different native-command error handling defaults in PowerShell 7.3+.

## Reconciliation and recovery

Each run has one checkpoint for every exact listing and required FX pair. The run
report summarizes status by company, listing, listing currency, FX pair, and
requested/effective date range. Every successful provider response is retained as
a compressed raw payload with provider ID, source-record ID, retrieval time, and
content hash. The canonical batch links the normalized price/action/FX rows to the
same response receipt.

Exact repeats use the provider response digest plus normalizer version. Existing
canonical business keys are not duplicated; changed observations use the existing
append-only supersession rules. Replaying a completed run performs no provider
request. Reconciliation hashes the persisted raw receipt metadata and every
canonical row belonging to each batch, including exact decimal and timestamp
values. A mismatch is reported explicitly; do not repair it with manual row edits.
Completed checkpoints must also retain a batch and raw source payload. Reconciliation
checks listing or FX-pair identity, the frozen date window, historical price kind,
cross-domain rows and price/FX observation times. Legitimate unavailable checkpoints
may have no batch. These checks do not establish that every expected trading session
or FX date is present; that coverage remains unassessed without a reviewed calendar.
For each retained source payload, reconciliation also verifies provider/domain and
the SHA-256 of the decoded bytes, including gzip integrity. Verification is bounded
to 64 MiB per encoded and decoded payload; a larger payload is reported as a
verification-limit mismatch, not as verified or as proven data corruption.

For a retryable network/HTTP failure, resume after the stored backoff. For
`NO_PROVIDER_DATA`, keep the `UNAVAILABLE` result and include the gap in the
coverage decision. For an identity or normalization failure, correct the reviewed
mapping or provider issue and prepare a new run. A changed crosswalk hash blocks a
prepared run. For `WORKER_INTERRUPTED`, resume the same run; the runner only
retries checkpoints whose attempt budget remains.

The existing Alembic migration adds `market_data_bootstrap_runs` and
`market_data_bootstrap_checkpoints`. These are operational ledgers in the
provider-payload/history migration group. Downgrade is destructive to those run
receipts; do not downgrade a rehearsal or production schema to clear a run.

## Guarded production procedure

This procedure is available only after the canonical portfolio bootstrap has a
persisted `APPLIED` or `APPLIED_WITH_GAPS` receipt whose reconciliation is
`MATCHED`. Production previews expose that prerequisite; provider execution
rechecks it before any Yahoo request. No recurring ingestion is enabled.

First run a read-only production preview with the exact reviewed scope. The CLI
verifies the Neon primary identity, database, TLS, privileges, and Alembic head
without production-write authorization:

```powershell
$env:DATABASE_TARGET_ENVIRONMENT = 'production'
$preview = Join-Path $env:USERPROFILE 'Documents\market-preview.json'
npm run db:bootstrap-market-data -- preview `
  --target-environment production `
  --start-date '<YYYY-MM-DD>' `
  --end-date '<YYYY-MM-DD>' `
  --report $preview
if ($LASTEXITCODE -ne 0) { throw 'Production market-data preview is blocked.' }
```

Review canonical-import readiness, provider crosswalk and held/Portfolio/Watchlist
listing tiers. Stop on any unresolved held-listing or required-FX mapping. Only
after a separate operation-specific approval, set authorization in this interactive
PowerShell process and prepare a bounded run:

```powershell
$env:DATABASE_PRODUCTION_WRITES_AUTHORIZED = 'true'
npm run db:bootstrap-market-data -- prepare `
  --target-environment production `
  --start-date '<YYYY-MM-DD>' `
  --end-date '<YYYY-MM-DD>'
```

The guard prompts for the exact target confirmation; commands must run in an
interactive terminal. Begin with `run --max-checkpoints 1`, review its private
report, then use `resume` on the same run with bounded batches. Run `status` and
`reconcile` using read-only target verification afterward. Clear both temporary
environment settings when finished. This document does not authorize any
production request.

## Verification status

- **Implemented:** bounded preview, frozen preparation, exact identity and FX
  gates, shared target preflight, raw response retention, daily price/FX and
  supported corporate-action normalization, resumable checkpoint ledger, reports,
  and exact reconciliation.
- **Tested:** synthetic provider responses, a disposable PostgreSQL 18 schema,
  target guard, exact decimal persistence, native listing currency/provider
  identity, current-quote exclusion, retry/unavailable classification, interrupted
  resume, rerun idempotency, production-target ordering and the canonical import
  prerequisite before a provider call.
- **Staged:** operator commands and report template in this document.
- **Executed:** no live Yahoo retrieval, real-source bootstrap, Neon rehearsal, or
  production write has been performed by Codex.
