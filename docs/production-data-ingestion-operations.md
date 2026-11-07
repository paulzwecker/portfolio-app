# Controlled production market and SEC ingestion

## Status

**Market preview verified on 2026-11-07; production execution remains gated.**
The market-data and SEC bootstrap commands use the shared database write-target
guard. The canonical portfolio baseline is applied and reconciled. No production
provider requests or database writes were made during this readiness assessment.
Previews used the local candidate checkout against production read-only; hosted
services were unchanged.

Real ingestion remains blocked until all of the following are true:

1. The canonical portfolio bootstrap has been applied and reconciled with status
   `MATCHED` on the exact production database.
2. The production schema is at the reviewed Alembic head. Read-only verification
   found `9f2a6d4c81b7`, matching the repository head on 2026-11-07. The older R8
   and workbook-sync migrations are ancestors of this head. Reverify before a run.
3. The exact target, direct TLS connection, Neon project/primary branch/endpoint,
   database privileges, production-write authorization and interactive target
   confirmation all pass the existing guard.
4. The required source identity mappings and exact-listing crosswalks are reviewed.
5. A verified recovery point protects the current accepted portfolio state, with
   sufficient retention for execution and reconciliation. The original empty
   pre-import recovery branch does not protect the imported holdings and targets.
6. An operator separately approves the bounded production run, including its
   exact target, mappings, date window, request limits and recovery procedure.

This document is an operating procedure, not authorization. Do not enable
recurring operations, Sheets polling, FMP, decision recomputation, model changes,
or portfolio changes as part of data ingestion.

## Current coverage and next approval

The read-only production assessment found all 22 held listings matched the
reviewed Yahoo crosswalk, with no unresolved identity or FX mapping. Required
pairs are DKK/EUR and USD/EUR. A deliberately bounded example window of
2025-11-07 through 2026-11-06 produces 24 logical provider scopes (22 listings
and two FX pairs). This is a planning window, not approved historical coverage
or proof that a provider has observations for every session. Retries and future
requests remain subject to the existing per-invocation budgets.

Production contained zero price, FX, corporate-action, reported-fundamental and
source-document observations at verification. SEC preview is blocked by
`NO_REVIEWED_SEC_CIK_MAPPINGS`; no company identity is inferred from a ticker.
There are no explicit Portfolio/Watchlist lifecycle records in this minimal
baseline. Market selection still includes all held listings. Zero unmapped
_active_ SEC companies therefore does not establish issuer coverage.

Full target, inventory, recovery metadata and preview reports remain in the
private `%LOCALAPPDATA%\PortfolioResearch\private-reports\c2-market-readiness`
directory. Re-run previews before seeking execution approval. The immediate
operator decisions are a current-state recovery point and a bounded first market
batch. Reviewed CIK mappings are a separate prerequisite for SEC ingestion.

On this Windows checkout, libpq could not locate a root certificate file. The
assessment selected the installed trusted `certifi` bundle through
`PGSSLROOTCERT` in the child process only, retaining `sslmode=verify-full`.
No `.env` or hosted setting was changed. For the commands below, use an existing
trusted CA configuration. If it is absent, select and verify the installed CA
bundle in the operator process, and restore its previous setting afterward.
Never substitute `require` or disable hostname verification. See the
[PostgreSQL TLS configuration](https://www.postgresql.org/docs/18/libpq-ssl.html).

## Guard and run semantics

For both CLIs, `preview`, `status` and `reconcile` use a read-only database
connection and read-only target verification. They do not call an external
provider. `prepare`, `run` and `resume` use the shared writer guard with operation
kind `bootstrap`. The guard requires the exact configured production identity,
separate production-write authorization, appropriate privileges, and the exact
interactive confirmation. Do not pipe or automate the confirmation.

Preparation writes only a frozen run scope and checkpoint ledger; it does not
call Yahoo or SEC. A production run is blocked before provider access unless the
newest canonical bootstrap receipt is `APPLIED` or `APPLIED_WITH_GAPS`, has a
persisted `MATCHED` reconciliation, and was recorded no later than the ingestion
run's preparation time. If the canonical import is applied after a provider run
was prepared, prepare a new run; do not resume the earlier scope.

The full-workbook receipt records reconciliation at its report root. The minimal
Sheets v1 receipt records it under `legacy_import`. The shared readiness adapter
recognizes only the exact minimal versions and verifies source IDs, raw hashes,
the derived source digest, input digest, matching immutable legacy batch and
complete zero-difference domain reconciliation. Missing, conflicting or malformed
evidence remains blocked. It reads the original receipts without rewriting them.
This validates the historical baseline; it does not freeze later legitimate
holdings changes or grant production write permission.

Provider checkpoints commit independently under the existing advisory lock.
Repeated completed runs do not re-fetch data. Retry only failed/retryable
checkpoints through the existing `resume` command. Keep every report outside the
repository and cloud-synced folders. Reports can contain company identities,
coverage and source data; do not attach them to public issues or CI artifacts.

## Market data: bounded initial and incremental runs

The preview reads canonical listings, the reviewed Yahoo crosswalk, exact held
listing identities and portfolio currency requirements. The prepared manifest
orders held listings first, then other Portfolio listings, then Watchlist
listings; the required FX pairs follow listing requests. `--company-id` can
restrict preview/preparation to one canonical company. The maximum history
window is ten years. A current quote is not imported as a daily historical close.
Yahoo corporate-action records remain unverified unless the existing verification
process supplies evidence; unverified actions are surfaced as a partial run.

Run from an interactive, private Windows PowerShell session after target
configuration and approvals have been reviewed. The dates and UUID below are
operator-supplied values, not defaults:

```powershell
$env:DATABASE_TARGET_ENVIRONMENT = 'production'
$startDate = 'REPLACE_WITH_REVIEWED_START_DATE'
$endDate = 'REPLACE_WITH_REVIEWED_END_DATE'
$privateDir = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\private-reports'
New-Item -ItemType Directory -Force -Path $privateDir | Out-Null
$previewPath = Join-Path $privateDir ('market-preview-' + [guid]::NewGuid().ToString('N') + '.json')
npm run db:bootstrap-market-data -- preview `
  --target-environment production `
  --start-date $startDate `
  --end-date $endDate `
  --report $previewPath
if ($LASTEXITCODE -ne 0) { throw 'Market-data preview is blocked.' }
```

Review the complete private preview: canonical-import readiness, listing identity
matches, priority counts, FX pairs, date window and all blockers. A `READY`
preview is only an input check; it does not prove price availability or authorize
ingestion. Stop on unresolved identity, currency, FX or source-quality states.

After the canonical import and separate explicit run approval, enable production
write authorization only in this PowerShell process. Prepare a fresh frozen run,
then process small batches. A single checkpoint per call is the safest first live
request; increase only after observing provider and database behavior.

```powershell
$env:DATABASE_PRODUCTION_WRITES_AUTHORIZED = 'true'
$preparedPath = Join-Path $privateDir ('market-prepared-' + [guid]::NewGuid().ToString('N') + '.json')
npm run db:bootstrap-market-data -- prepare `
  --target-environment production `
  --start-date $startDate `
  --end-date $endDate `
  --report $preparedPath
if ($LASTEXITCODE -ne 0) { throw 'Market-data preparation is blocked.' }
$runId = (Get-Content -Raw $preparedPath | ConvertFrom-Json).run_id
$runPath = Join-Path $privateDir ('market-run-' + [guid]::NewGuid().ToString('N') + '.json')
npm run db:bootstrap-market-data -- run `
  --target-environment production `
  --run-id $runId `
  --max-checkpoints 1 `
  --report $runPath
```

For an explicitly reviewed retryable checkpoint, use the same run ID and a new
private report path:

```powershell
$resumePath = Join-Path $privateDir ('market-resume-' + [guid]::NewGuid().ToString('N') + '.json')
npm run db:bootstrap-market-data -- resume `
  --target-environment production `
  --run-id $runId `
  --max-checkpoints 1 `
  --report $resumePath
```

Review each attempt and checkpoint before resuming. Use `status --run-id` to
inspect a frozen run and `reconcile --run-id` to compare saved provider receipts
with canonical rows. Both commands require the same explicit target selection,
but are read-only:

```powershell
npm run db:bootstrap-market-data -- status `
  --target-environment production `
  --run-id $runId
npm run db:bootstrap-market-data -- reconcile `
  --target-environment production `
  --run-id $runId
```

After completion, confirm reconciliation and partial/unavailable coverage; a
matched receipt is not a claim of complete universe coverage. Clear the
process-level write authorization when finished.

For incremental refreshes, choose a bounded overlap window that matches the
provider's correction behavior and current source calendar. The same commands
and guard apply. Do not create a recurring request as part of this procedure.

## SEC filings and reported fundamentals: bounded runs

The SEC preview uses only reviewed CIK-to-company identities in PostgreSQL. It
reports unmapped active companies and does not make requests. The production SEC
adapter preserves response payload provenance, accession/filing identity,
publication metadata, fiscal periods, units, and existing correction/restatement
quality states. It imports supported filing metadata and Company Facts; filing
bodies are not downloaded. SEC `429` and transient network failures remain
retryable checkpoint states. `SEC_USER_AGENT` must name the application and a
monitored contact email; provide it securely in the local process, never in source
code or a report.

```powershell
$env:DATABASE_TARGET_ENVIRONMENT = 'production'
$privateDir = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\private-reports'
New-Item -ItemType Directory -Force -Path $privateDir | Out-Null
$previewPath = Join-Path $privateDir ('sec-preview-' + [guid]::NewGuid().ToString('N') + '.json')
npm run db:bootstrap-fundamentals -- preview `
  --target-environment production `
  --report $previewPath
if ($LASTEXITCODE -ne 0) { throw 'SEC preview is blocked.' }
```

Review all CIKs, company labels, evidence references and active unmapped companies.
Do not assign a CIK from ticker similarity or use a parent/subsidiary issuer as a
substitute. After separate approval and only after the canonical import has been
reconciled, the bounded writer flow is:

```powershell
$env:SEC_USER_AGENT = 'Portfolio Research Platform <monitored-contact-email>'
$env:DATABASE_PRODUCTION_WRITES_AUTHORIZED = 'true'
$preparedPath = Join-Path $privateDir ('sec-prepared-' + [guid]::NewGuid().ToString('N') + '.json')
npm run db:bootstrap-fundamentals -- prepare `
  --target-environment production `
  --report $preparedPath
if ($LASTEXITCODE -ne 0) { throw 'SEC preparation is blocked.' }
$runId = (Get-Content -Raw $preparedPath | ConvertFrom-Json).run_id
$runPath = Join-Path $privateDir ('sec-run-' + [guid]::NewGuid().ToString('N') + '.json')
npm run db:bootstrap-fundamentals -- run `
  --target-environment production `
  --run-id $runId `
  --max-checkpoints 1 `
  --report $runPath
```

For an explicitly reviewed retryable SEC checkpoint, use `resume` with the same
run ID and another private report path:

```powershell
$resumePath = Join-Path $privateDir ('sec-resume-' + [guid]::NewGuid().ToString('N') + '.json')
npm run db:bootstrap-fundamentals -- resume `
  --target-environment production `
  --run-id $runId `
  --max-checkpoints 1 `
  --report $resumePath
```

Inspect status and the provider-request count after each call. Use `resume` for a
retryable failed checkpoint only after reviewing its failure. Reconcile when all
checkpoints are terminal. Consensus ingestion is explicitly excluded: FMP remains
disabled unless the organization separately resolves licensing and approves it.
For example, read status and reconcile using:

```powershell
npm run db:bootstrap-fundamentals -- status `
  --target-environment production `
  --run-id $runId
npm run db:bootstrap-fundamentals -- reconcile `
  --target-environment production `
  --run-id $runId
```

## Historical coverage evidence and estimates

No current production coverage count is available because the R7 canonical
portfolio import has not been applied and reconciled. Do not treat historical
local PostgreSQL receipts as Neon production evidence.

The latest local reports provide planning estimates only:

- A bounded market refresh report dated 2026-10-16 had fresh quotes and at least
  252 sessions for 22/22 Portfolio listings and 61/71 then-mapped Watchlist
  listings. It had nine relevant EUR FX pairs; 10 Watchlist identities were then
  unmapped, and 29 corporate-action observations were still unverified.
- The later identity review dated 2026-10-16 resolved the ten listing identities;
  it did not establish that those newly resolved listings have canonical price
  history or fresh quotes.
- The SEC identity/fundamentals report dated 2026-10-16 had 27 reviewed CIKs
  (20 Portfolio, 7 Watchlist), facts for 20/21 Portfolio and 7/71 Watchlist
  companies, and 26,808 observations. Adyen remained intentionally unresolved;
  64 Watchlist companies lacked a reviewed SEC CIK. These local counts are not a
  current production baseline.

After R7, use the production previews to establish exact selected scope, then use
run/reconcile reports for actual post-ingestion counts. Market coverage is bounded
by reviewed exact-listing crosswalks, supported FX pairs and verified action
semantics. SEC coverage is bounded by reviewed registrant identity, SEC
applicability and the canonical concept/document allowlists. Missing domains stay
unavailable. Do not infer data from a listing, provider mapping, or a current
observation.

## Safe stop conditions

Stop before `run`/`resume` if any of these conditions occurs:

- the source or target identity differs from the reviewed preview;
- Alembic head or the verified Neon target changes;
- the newest canonical import is missing, not matched, or recorded after the
  provider run was prepared;
- a listing/CIK mapping is absent, ambiguous, changed, or unsupported;
- currencies, FX pairs, SEC fiscal/period metadata, or provider provenance fail
  validation;
- the provider returns an identity mismatch, normalization rejection, repeated
  rate limiting, or unexplained duplicate/conflicting facts;
- the approved request count or date window would be exceeded.

Correct the source/mapping and prepare a new run where required. Keep existing
accepted holdings, targets, models, scores, ranks and execution history unchanged.
