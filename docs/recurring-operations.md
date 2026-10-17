# Recurring Data & Research Operations

## Worker boundary

`npm run dev` starts the existing bounded market-data worker and a separate
`portfolio_api.recurring_operations` process beside FastAPI and Next.js. The
operations worker performs no network work during API import or request
startup. It waits until PostgreSQL and all Alembic heads are ready, checks due
times in PostgreSQL, and acquires a PostgreSQL advisory lock before running a
cycle. Repeated development-server starts and multiple worker processes cannot
run the same cycle concurrently.

The worker checks due jobs every 60 seconds. It records attempts, completion,
failure, retry time and result summaries in `recurring_operation_runs`; the
singleton worker heartbeat is in `recurring_operations_worker_state`. Existing
provider ingestion runs, Sheets poll records and agent delivery receipts remain
the detailed domain histories.

User-initiated refreshes use this same worker. The API stores an allowlisted
request in `operational_job_requests`; the worker claims at most one queued
request per cycle and records each dependency step in
`operational_job_attempts`. HTTP requests only enqueue or inspect work; they do
not wait for provider or Google API calls to finish. Requests survive worker
restarts. A request stuck running for more than two hours is marked interrupted
and replayed through existing idempotent services.

When the worker detects the known development proxy at loopback port 9, it adds
only the SEC and Google API hosts it uses to its own `NO_PROXY` variables. Other
proxy configurations are untouched. This keeps worker routing local to its
process and avoids changing machine-wide proxy settings.

## Jobs and cadence

| Job                         | Default cadence  | Behavior                                                                                                                                                                                        |
| --------------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SEC reported fundamentals   | 24 hours         | Uses exact reviewed CIK mappings and the existing Company Facts adapter.                                                                                                                        |
| SEC filings                 | 24 hours         | Uses exact reviewed CIK mappings and existing EDGAR submissions metadata; source bodies remain at SEC.                                                                                          |
| FMP consensus               | 24 hours, opt-in | Runs only when `FMP_CONSENSUS_INGESTION_ENABLED=true` and a key is configured. Keep disabled until raw storage and display rights are confirmed.                                                |
| Sheets discovery            | 1 hour           | Reads only the configured model, research, risk and acknowledgment inboxes. Set `GOOGLE_SHEETS_POLL_SECONDS=0` to disable polling; nonzero values must be at least 60 seconds.                  |
| Research triggers and queue | 1 hour           | Reuses the deterministic 30-day trigger scan and current research-queue derivation. Identical source events remain idempotent.                                                                  |
| Agent work feed             | 1 hour           | Publishes up to ten current work items per role into the fixed application-owned work-feed tab. Exact replays add no rows; each write is read-back verified.                                    |
| Decision snapshots          | 1 hour           | Reuses canonical Portfolio/Watchlist/Research Rank and Execution Pace services. It appends a run only when its complete status, reason, position and input snapshot differ from the latest run. |

The existing `market_data_startup` worker continues to own market prices and
FX. It retains its exact-listing refresh checks, correction overlap, bounded
backfill and separate advisory lock. The recurring scheduler does not duplicate
its regular fetch. Explicit market refresh requests use the same adapter while
acquiring the same advisory lock first.

The recurring worker claims at most one eligible manual request before its
scheduled work, so user-initiated jobs do not wait behind a full scheduled
cycle. It then runs SEC facts and filing metadata, optional licensed consensus,
Sheets discovery, trigger/queue refresh, agent work-feed publication, and
decision recomputation. Sheets proposal discovery captures
and validates candidate revisions only. No proposal is accepted automatically;
no target, holding, lifecycle, model assumption or trade is changed by the
worker.

## Manual refresh interface

The Operations workspace queues fixed operations through
`POST /v1/operations/job-requests` and reads them from
`GET /v1/operations/job-requests` or
`GET /v1/operations/job-requests/{request_id}`. A safe retry is an explicit
`POST /v1/operations/job-requests/{request_id}/retry`; it creates a linked
request and preserves the first attempt.

| Request            | Scope                                                      | Existing service                                                                           |
| ------------------ | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `MARKET_DATA`      | Active universe or one current Portfolio/Watchlist company | Yahoo market ingestion and corporate actions from the same chart response                  |
| `FX`               | Active universe or one current Portfolio/Watchlist company | Existing Yahoo FX ingestion and required canonical currency pairs                          |
| `MARKET_AND_FX`    | Active universe or one current Portfolio/Watchlist company | Market and FX ingestion under the startup market worker's advisory lock                    |
| `SEC_FUNDAMENTALS` | Active universe or one current Portfolio/Watchlist company | Reviewed SEC CIK mappings and Company Facts normalization                                  |
| `SEC_FILINGS`      | Active universe or one current Portfolio/Watchlist company | Reviewed SEC CIK mappings and EDGAR filing metadata                                        |
| `SHEETS_DISCOVERY` | Active universe only                                       | Model, research and risk inbox checks plus acknowledgment reconciliation                   |
| `RESEARCH_REFRESH` | Active universe or one current Portfolio/Watchlist company | Deterministic trigger scan and current queue derivation                                    |
| `AGENT_WORK_FEED`  | Active universe only                                       | Existing fixed-tab work-feed publication with read-back verification                       |
| `COMPANY_REFRESH`  | One current Portfolio/Watchlist company                    | Market/FX, SEC facts/filings and company-scoped research refresh                           |
| `REFRESH_ALL`      | Active universe only                                       | Market/FX, SEC facts/filings, Sheets discovery, research refresh and work-feed publication |

Company scope resolves through canonical company identity and its active exact
listings; the provider still validates its reviewed venue, ticker and currency
mapping. SEC work remains limited to reviewed CIKs. Candidate, dropped and
unassigned companies are rejected. Sheets discovery and agent-feed publication
remain universe-wide because their workbook interfaces are shared.
Company-scoped market diagnostics include only the requested company's listing
coverage; an unrelated active company with an unresolved listing does not make a
single-company refresh appear partial.

`REFRESH_ALL` follows the dependency order and excludes licensed FMP consensus,
ranking/execution recomputation, proposal acceptance and all portfolio-state
actions. It checks proposal and acknowledgment inboxes and publishes current
agent work items to the configured workbook; this is stated beside the UI
action. Company refresh does not write to Sheets. Refreshed facts become
available to normal analytics, while decision snapshots remain governed by the
separate decision workflow.

Requests use per-operation cooldowns of three to fifteen minutes and a
transaction-scoped PostgreSQL lock for identical scopes. Repeated clicks return
the existing request during cooldown. Manual market refresh uses a 90-calendar-
day correction overlap after the exact listings have at least 252 daily
observations. When an included listing lacks initial history, the existing
bounded ten-year backfill is used. Market refreshes share the dedicated market
worker's advisory lock and defer safely while it is active. Provider retry,
idempotence, identity checks and partial-success reporting remain owned by the
existing adapters.

Only terminal `FAILED`, `PARTIAL` and `BLOCKED` requests can be retried. No
command, provider URL, arbitrary date range or provider option is accepted.
Manual Sheets discovery is available when scheduled polling is disabled, but
still requires the configured workbook and credentials. Configuration blockers
remain visible in the request result and can be retried after correction.

## Retry, interruption and missing configuration

Provider adapters retain their existing bounded per-run retry policy. Retryable
SEC failures may be replayed at most twice per UTC day, using the stored source
scope. The recurring job schedules a retryable partial result after 15 minutes
while replay capacity remains; once a same-day completed/partial external run is
available, the next operation pass reuses its stored report without refetching.
Scheduled job failures use 15-minute exponential backoff capped at six hours. Missing credentials or disabled policy are recorded as blockers and
rechecked after six hours, or immediately when the relevant missing setting is
added. Successful and partial jobs use their configured cadence.

Transient provider or Google API failures do not prevent the other jobs from
running. A stopped process marks its heartbeat on SIGINT/SIGTERM. If a process
crashes during a job, a `RUNNING` record older than two hours is marked
`WORKER_INTERRUPTED` and retried after backoff. Database advisory locks are
released automatically if a process or connection exits unexpectedly.

Unavailable identities are not inferred. SEC ingestion requires
`SEC_USER_AGENT`; filings and facts remain partial when authoritative issuer
mappings are absent. FMP estimates remain disabled by default due to provider
terms. Google Sheets polling and work-feed publication require the explicit
workbook ID and external service-account credential file. Polling does not
accept proposals, and external ChatGPT automation schedules remain managed
outside the application.

## Operations and review

The live status endpoint is `GET /v1/recurring-operations/status`. The Sheets
Model Sync page displays worker heartbeat, market-data state, per-job cadence,
last attempt, last success, next attempt, failures and blockers. Existing
`/model-sync`, Research Queue, provider-run and agent-event views remain the
domain-specific review surfaces.

Manual request records and step outcomes appear on the Operations page. The
Company Explorer offers only its relevant company-scoped refresh. A successful
or partial company request signals open frontend data hooks to refetch; provider
outages do not erase previously stored observations.
When `RECURRING_OPERATIONS_ENABLED=false`, Operations displays the disabled
worker state, refresh controls are disabled and the API rejects new requests
with `503` instead of persisting work that cannot run.

The development API and web server bind to loopback by default. Operational
request endpoints follow the application's local-only trust boundary and do
not authenticate individual users. Before binding beyond localhost or putting
the app behind a shared reverse proxy, add authentication, authorization for
provider/workbook operations and CSRF protections; do not expose this API
directly to a network.

Local development starts the workers with:

```sh
npm run db:migrate
npm run dev
```

To inspect status or run one bounded diagnostic cycle without leaving a worker
process running:

```sh
npm run db:ingest-external-data -- status
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.recurring_operations --once
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.market_data_startup --once
```

In a deployed environment, run `portfolio_api.recurring_operations` and the
existing `portfolio_api.market_data_startup` as separate supervised worker
processes, each with the same migrated PostgreSQL database and secret-backed
environment. Do not also install an overlapping cron for the same domains.
The external-data one-shot CLI remains available for operator-requested runs
and replay; its provider/domain idempotency and run ledger are unchanged.

The user-managed ChatGPT schedules are not created, edited or activated by the
application. Feed publication is a delivery receipt, not proof an agent
processed its work. A reviewer still explicitly accepts or rejects proposals
and completes research-queue items.

## Bounded live verification (2026-10-16)

The local worker completed real cycles against PostgreSQL, SEC EDGAR and the configured Google
workbook. A first sandboxed attempt inherited the known loopback port-9 proxy and recorded
SEC/Google network failures. A bounded retry with process-local `NO_PROXY` exclusions reached
both services. The recurring worker now applies those same narrow exclusions when its runtime
detects that exact proxy; the authorized live recheck ran in a direct-network environment, so the
branch itself is covered by deterministic tests.

SEC EDGAR submissions imported 3,122 filing records and reused 2,599 existing records. The result
was `PARTIAL`: 14 documents were marked `DATA_CHECK`, 12 CIK responses did not match the reviewed
issuer mapping, and 14 amendment relationships remain unlinked. SEC Company Facts normalized
13,382 supported facts on replay; 408 retain data-check status, and 12 issuer-name mapping failures
remain explicit. A single mismatched issuer no longer rolls back valid facts for other mapped
companies. Missing identities, unsupported forms/concepts and quality checks remain visible in
the run report.

Google Sheets model inbox discovery was `PARTIAL`: two model contracts were unchanged, with one
existing `CONFLICT`; the research, risk and acknowledgment checks succeeded or replayed without
new submissions. The three role work feeds were published and read-back verified (6, 10 and 10
items). An idempotent later check added one new Data & Universe Steward row after factual state
changed; the other two role feeds were unchanged. Research trigger scanning created 4 records and
replayed 15 unchanged events. Ranking and Execution Pace services ran through existing domain
operations, but inputs still yielded zero Portfolio/Watchlist ranked entries and zero available
Execution Pace decisions. FMP remained disabled because provider storage/display rights and
credentials are not configured. No model revision was added and no model, research, risk or
portfolio proposal was accepted by the worker.

The `--once` process exited cleanly and recorded its stopped heartbeat. A subsequent same-day run
uses the persisted due times and the advisory lock to avoid duplicate provider calls and work-feed
rows. For continuous local operation, `npm run dev` starts the supervised worker process alongside
the existing market-data worker.
