# External-data ingestion operations

## Scope and daily schedule

The existing canonical provider adapters can run through the recurring local operations worker
started by `npm run dev`, or through the one-shot command below when an operator wants an external
scheduler. Do not enable both schedules for the same domain. The one-shot cron remains an
alternative for deployments that supervise scheduled commands directly:

```cron
15 2 * * * cd /path/to/portfolio-app && npm run db:ingest-external-data -- run >> /var/log/portfolio-external-ingestion.log 2>&1
```

Before enabling the timer, apply the schema migration with `npm run db:migrate`,
configure `DATABASE_URL`, `SEC_USER_AGENT` (an application name and contact email)
and `FMP_API_KEY` through the deployment's secret/environment configuration, and
review the SEC CIK and FMP company mappings. Yahoo Finance uses the checked-in
listing and currency crosswalk and does not require credentials. The worker does
not infer missing mappings.

For consensus, only configure `FMP_API_KEY` when the applicable FMP plan or a
written agreement permits the application's raw-data storage and display use.
FMP's published personal-use terms prohibit copying/downloading without prior
written approval and prohibit data display through internal or multi-user
applications without a specific agreement. A free personal key is not sufficient
authorization for canonical ingestion. See the [free-source feasibility report](reconciliation/consensus-free-source-feasibility-2026-10-11.md).

The worker is deliberately a single process, not a queue service. Its PostgreSQL run key makes the same provider/domain/scope idempotent within a UTC day. If the process is invoked again for a completed or failed key, it reports the stored result without fetching again. `PARTIAL` and `BLOCKED` return exit code 2; `FAILED` returns 1; a fully complete cycle returns 0.

Domains run in this order: reported fundamentals, filing metadata, consensus estimates, then Yahoo market data, corporate actions and FX. Market prices and actions share one chart cycle; FX has its own exact pair scope and date window. This prioritizes the biggest 6.1 source-data gaps and avoids duplicate listing-chart requests. Company-scoped SEC and FMP requests order Portfolio companies before Watchlist companies. No listing or provider identity is inferred.

## Provider and source policy

| Domain                              | Active adapter        | Operational behavior                                                                                                                                                                                                                                                                                                                                                                      |
| ----------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reported fundamentals               | SEC Company Facts     | Uses reviewed CIK mappings and the existing standard US-GAAP/IFRS concept allowlist. SEC facts are primary; normalized providers remain complementary under existing source priorities.                                                                                                                                                                                                   |
| Filings/source documents            | SEC EDGAR submissions | Stores dated filing metadata and SEC links. Filing bodies and exhibits stay at SEC. Already retained historical submission archives are not downloaded again; the current SEC submissions index is checked each run.                                                                                                                                                                      |
| Consensus estimates                 | FMP analyst estimates | The code path fetches annual and quarterly series only for reviewed FMP mappings. Enable it only when endpoint entitlement and an applicable agreement permit canonical raw-data storage and application display. Each estimate retains its FMP mapping/provider identity, currency, snapshot and raw response. No values are combined across vendors.                                    |
| FX                                  | Yahoo chart           | Uses only the explicit currency-pair symbols already in `yahoo_finance.py`, including the validated reciprocal source for canonical TWD/EUR. Fetches dated rates after each pair's latest stored observation, or the configured historical lookback when no observation exists. TWD/EUR remains explicitly polled to keep the recovered daily series current.                             |
| Market prices and corporate actions | Yahoo chart           | Uses the reviewed listing crosswalk and the existing price/action normalizers. Daily listing requests recheck a 90-day overlap to catch recent backdated actions; unchanged prices/actions are deduplicated by their canonical source keys. Price and action observations retain their existing canonical quality and provenance. Actions remain unverified until independently reviewed. |

The adapters retain raw provider payloads separately from normalized domain observations. Domain-specific batch receipts and source-record fingerprints continue to control canonical idempotency and correction handling. A changed response is processed as new evidence under the existing append-only rules; it does not overwrite or blend another provider's observation.

### Local proxy diagnosis for Yahoo chart requests

The Yahoo adapter honors the process's standard proxy environment variables. If
chart requests fail with Windows socket error `10061`, first inspect
`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` for an unreachable local
proxy. In the 2026-10-10 local recovery, the configured proxy was
`http://127.0.0.1:9`; requests through it were refused, while both Yahoo chart
hosts returned successfully when the request used the direct route. Keep the
adapter's normal proxy support. Correct the proxy listener/configuration or add
only the exact provider hosts to `NO_PROXY` for that ingestion process when
direct access is permitted; do not globally disable a required corporate proxy.

On PowerShell, a one-process verification can use:

```powershell
$env:NO_PROXY = "$env:NO_PROXY,query1.finance.yahoo.com,query2.finance.yahoo.com"
npm run db:sync-market-data -- --listing NASDAQ:GOOGL --end-date 2026-10-10 --apply
```

After confirming the active listing mappings, the same process-scoped setting
can be used for the bounded active-universe refresh:

```powershell
$env:NO_PROXY = "$env:NO_PROXY,query1.finance.yahoo.com,query2.finance.yahoo.com"
npm run db:sync-market-data -- --scope active --apply --report .cache/market-data-refresh.json
```

Use the repository's documented ingestion command and bounded listing scope for
actual refreshes. The environment override changes transport routing only; it
does not relax listing identity, provider response validation, data-quality,
freshness, or idempotency rules.

## Retry, failure and partial-success behavior

The worker records one `external_ingestion_runs` row per provider/domain/scope and one `external_ingestion_attempts` row per completed attempt. Run rows keep the current status and request scope; attempts keep outcome, bounded retry guidance, timestamps, diagnostics and data counts. These records are available for later Attention Center integration without adding an ingestion dashboard.

- Each provider/domain execution has at most **three** attempts. Network errors, HTTP 429 and provider 5xx responses can retry. HTTP 4xx, mapping/normalization errors and other validation failures do not retry.
- Retry delays start at 1 second, double between attempts and never exceed 30 seconds. A numeric provider `Retry-After` value is honored up to that cap.
- Yahoo already retries individual requests up to three times. SEC requests remain below the published 10 requests/second limit. FMP requests are spaced at five requests/second because account-specific limits vary.
- Missing credentials or reviewed identity mappings are stored as `BLOCKED`. A provider response with unresolved identities, rejected rows, source-quality checks or unmapped active companies is `PARTIAL` when other subjects succeeded. If none of the mapped subjects produces a usable observation, the domain is `FAILED`.
- A failure in one provider/domain does not roll back another domain's committed observations. Yahoo facts from one selected chart-import cycle share a canonical transaction while operational statuses stay separate; an FX-only backfill has its own query scope and transaction.
- Failed attempts, partial results and blocked prerequisites remain in PostgreSQL. Database error messages omit connection details, and FMP transport errors never store the API-key query URL.

An interrupted run remains visible as `RUNNING`. If it is still running after four hours, the next invocation records a `WORKER_INTERRUPTED` failure; use an explicit replay after checking the worker host. This prevents a stale process marker from being silently treated as a completed run.

## Freshness and commands

The daily polling cadence is considered fresh for 72 hours for fundamentals, source documents, consensus, FX and market prices. Corporate-action polling has a seven-day threshold because announcements are less frequent. Freshness measures the time since the last complete or partial provider run, not the age of a filing or the economics of the latest observation. Provider/source effective, publication, retrieval and recorded timestamps remain separate in canonical tables.

```sh
npm run db:ingest-external-data -- run
npm run db:ingest-external-data -- run --domain REPORTED_FUNDAMENTALS
npm run db:ingest-external-data -- run --domain FX --fx-pair TWD/EUR --start-date 2016-10-06 --end-date 2026-10-10
npm run db:ingest-external-data -- status
npm run db:ingest-external-data -- replay <run-uuid>
```

Use historical FX windows only for a documented gap and a reviewed pair. The TWD/EUR gap identified below was backfilled in Milestone 6.10 and should not be repeated routinely. `--fx-pair` scopes a historical request to that exact pair. An FX-only run does not fetch listing prices or actions. A market-data or corporate-action selection runs both chart domains because the same provider response contains both facts. Replay creates linked run records with the stored date window and subject scope. The adapters then re-fetch and normalize that scope: unchanged market, filing and fundamental payloads reuse existing receipts; changed source content follows the domain's append-only correction policy. An estimate re-fetch has a new observation timestamp by design, so it creates a new FMP point-in-time snapshot even if its values match the prior snapshot.

## Current live coverage (2026-10-10)

The [Milestone 6.1 audit](operational-coverage-audit.md) is a historical baseline, not the current database state. The [Milestone 6.10 operational report](reconciliation/operational-data-activation-2026-10-10.md) records the database read and bounded worker runs from that milestone only. At that read, all 21 Portfolio companies had fresh exact-listing quotes, as did 61/71 Watchlist companies with canonical listings. Ten Watchlist companies still lacked listing identities. The Yahoo worker had no provider fetch failures or normalization rejections for its 84 selected active/held listing responses; its market/action runs correctly remained partial because of the ten company identity gaps and unverified actions. See [Recurring Data & Research Operations](recurring-operations.md) for the current worker configuration and status endpoint.

The SEC crosswalk at that historical read contained 20 Portfolio and 7 Watchlist issuer identities. Four of the Watchlist CIK mappings also had canonical listings; three company-level mappings did not yet resolve listing identity. Fundamentals and source-document rows were zero at that time because `SEC_USER_AGENT` was not configured. FMP credentials and primary mappings were absent, so canonical estimate rows remained zero. Legacy workbook estimate values remained `DATA_CHECK` and were not counted as provider coverage or usable momentum history. TWD/EUR had 2,607 dated observations after a scoped reciprocal-series recovery. No unattended schedule was installed during Milestone 6.10; recurring operations were added later in Milestone 10E.

## Verification limits

The local PostgreSQL database was reachable and used for the coverage queries, mapping records, provider observations and operational run/attempt ledger. Yahoo live transport and normalization were exercised; the SEC and FMP adapters remain fixture-tested but could not be live-verified without local configuration. Set `SEC_USER_AGENT` to an application name plus a monitored contact email, and set `FMP_API_KEY` in the ignored local `.env` only if licensed FMP access is available. Do not place either value in tracked repository files. The current observed gaps and precise block reasons are in the linked Milestone 6.10 report.

## Local market-data startup worker

`npm run dev` launches `portfolio_api.market_data_startup` as a separate process
alongside FastAPI and Next.js. The worker waits for database and migration
readiness, checks active/held exact-listing coverage, current quotes, required
dated FX and corporate-action run age, then calls the existing Yahoo ingestion
domains only when refresh is due. It relies on existing bounded backfill and
incremental correction-overlap behavior and serializes concurrent starts with a
PostgreSQL advisory lock. No provider request occurs during FastAPI import or
module startup. `python -m portfolio_api.market_data_startup --once` is available
for one diagnostic run. The worker retries a database/schema readiness block
after one minute; after a completed, partial or failed provider attempt, its next
coverage check is on the next UTC day boundary. API and web servers remain usable
when Yahoo is unavailable. The web API `GET /v1/market-data/status` exposes the
latest run state and successful-update time, while per-listing APIs expose
availability and history-derived analytics.

In the local environment checked on 2026-10-16, Yahoo requests inherited a
loopback proxy at `127.0.0.1:9`, which refused connections. The startup worker
adds only `query1.finance.yahoo.com` and `query2.finance.yahoo.com` to
process-local `NO_PROXY`/`no_proxy` when that exact local port-9 proxy is
detected. It leaves other proxies unchanged. Operators can configure the
standard `NO_PROXY` variables directly if required; no global proxy settings are
changed by the application.

## Recurring SEC, Sheets and research operations

The separate `portfolio_api.recurring_operations` process starts with `npm run dev` when
`RECURRING_OPERATIONS_ENABLED=true`. It runs daily SEC Company Facts and EDGAR metadata jobs,
hourly Google Sheets inbox discovery, trigger/queue refresh, bounded work-feed publication, and
decision snapshots only when the canonical input signature changes. Google polling is controlled
by `GOOGLE_SHEETS_POLL_SECONDS` (default 3600; set to `0` to disable). FMP consensus stays disabled
unless provider rights and `FMP_CONSENSUS_INGESTION_ENABLED=true` are established.

The worker records job runs, last successes, retry times and blockers in PostgreSQL. Inspect
`GET /v1/recurring-operations/status` or the Operations card on `/model-sync`. It does not accept
research/model proposals or change holdings, targets, lifecycle, assumptions or trades. For the
schedule, backoff, shutdown and deployment requirements, see [recurring-operations.md](recurring-operations.md).
Do not add an overlapping cron while this worker is active.

In the local environment observed on 2026-10-16, SEC and Google APIs initially failed through
the dead loopback port-9 proxy. The recurring worker now adds only `www.sec.gov`, `data.sec.gov`
and Google API hosts to its process-local `NO_PROXY` entries when that exact proxy is detected.
It does not bypass another configured proxy. See the bounded live-cycle report in
[recurring-operations.md](recurring-operations.md) for current verification and the remaining
issuer-mapping checks.
