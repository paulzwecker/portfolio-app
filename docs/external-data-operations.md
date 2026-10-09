# External-data ingestion operations

## Scope and daily schedule

The API has a one-shot worker around the existing canonical provider adapters. Run it once per day at **02:15 UTC** with cron or a systemd timer:

```cron
15 2 * * * cd /path/to/portfolio-app && npm run db:ingest-external-data -- run >> /var/log/portfolio-external-ingestion.log 2>&1
```

Before enabling the timer, apply the schema migration with `npm run db:migrate`,
configure `DATABASE_URL`, `SEC_USER_AGENT` (an application name and contact email)
and `FMP_API_KEY` through the deployment's secret/environment configuration, and
review the SEC CIK and FMP company mappings. Yahoo Finance uses the checked-in
listing and currency crosswalk and does not require credentials. The worker does
not infer missing mappings.

The worker is deliberately a single process, not a queue service. Its PostgreSQL run key makes the same provider/domain/scope idempotent within a UTC day. If the process is invoked again for a completed or failed key, it reports the stored result without fetching again. `PARTIAL` and `BLOCKED` return exit code 2; `FAILED` returns 1; a fully complete cycle returns 0.

Domains run in this order: reported fundamentals, filing metadata, consensus estimates, then Yahoo market data, corporate actions and FX. Market prices and actions share one chart cycle; FX has its own exact pair scope and date window. This prioritizes the biggest 6.1 source-data gaps and avoids duplicate listing-chart requests. Company-scoped SEC and FMP requests order Portfolio companies before Watchlist companies. No listing or provider identity is inferred.

## Provider and source policy

| Domain                              | Active adapter        | Operational behavior                                                                                                                                                                                                                                                                                                                                                                      |
| ----------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reported fundamentals               | SEC Company Facts     | Uses reviewed CIK mappings and the existing standard US-GAAP/IFRS concept allowlist. SEC facts are primary; normalized providers remain complementary under existing source priorities.                                                                                                                                                                                                   |
| Filings/source documents            | SEC EDGAR submissions | Stores dated filing metadata and SEC links. Filing bodies and exhibits stay at SEC. Already retained historical submission archives are not downloaded again; the current SEC submissions index is checked each run.                                                                                                                                                                      |
| Consensus estimates                 | FMP analyst estimates | Fetches annual and quarterly series only for reviewed FMP mappings. Each estimate retains its FMP mapping/provider identity, currency, snapshot and raw response. No values are combined across vendors.                                                                                                                                                                                  |
| FX                                  | Yahoo chart           | Uses only the explicit currency-pair symbols already in `yahoo_finance.py`, including TWD/EUR. Fetches dated rates after each pair's latest stored observation, or the configured historical lookback when no observation exists. TWD/EUR is explicitly polled because 6.1 found only two dated observations.                                                                             |
| Market prices and corporate actions | Yahoo chart           | Uses the reviewed listing crosswalk and the existing price/action normalizers. Daily listing requests recheck a 90-day overlap to catch recent backdated actions; unchanged prices/actions are deduplicated by their canonical source keys. Price and action observations retain their existing canonical quality and provenance. Actions remain unverified until independently reviewed. |

The adapters retain raw provider payloads separately from normalized domain observations. Domain-specific batch receipts and source-record fingerprints continue to control canonical idempotency and correction handling. A changed response is processed as new evidence under the existing append-only rules; it does not overwrite or blend another provider's observation.

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
npm run db:ingest-external-data -- run --domain FX --fx-pair TWD/EUR --start-date 2016-10-08 --end-date 2026-10-06
npm run db:ingest-external-data -- status
npm run db:ingest-external-data -- replay <run-uuid>
```

Use a deliberate historical FX window once during deployment to fill known history gaps such as the two-point TWD/EUR series in the 6.1 audit. The example window matches the ten-year default as of 2026-10-06; choose its start date to match the application's accepted history policy. `--fx-pair` scopes the historical request to that exact reviewed pair. An FX-only run does not fetch listing prices or actions. A market-data or corporate-action selection runs both chart domains because the same provider response contains both facts. Replay creates linked run records with the stored date window and subject scope. The adapters then re-fetch and normalize that scope: unchanged market, filing and fundamental payloads reuse existing receipts; changed source content follows the domain's append-only correction policy. An estimate re-fetch has a new observation timestamp by design, so it creates a new FMP point-in-time snapshot even if its values match the prior snapshot.

## Milestone 6.1 baseline and current coverage effect

The [Milestone 6.1 audit](operational-coverage-audit.md) measured 21 Portfolio and 71 Watchlist companies. It found 0 reviewed SEC CIK mappings, 0 reported-fundamental observations, 0 filing/source-document rows, 0 primary-provider estimate observations, 10 Watchlist listing identity gaps, and only two TWD/EUR observations. The prioritized ingestion domains therefore lacked recurring operational status.

Milestone 6.2 operationalizes all six provider/domain areas above and persists freshness and failures for each. It does **not** change the audit's canonical data counts by itself: mappings and credentials remain prerequisites, and no live database or SEC/FMP credentials were available in the Codex environment. The checked-in Yahoo crosswalk already explicitly maps TWD/EUR, so the daily worker can continue that series from the latest stored date when deployed. The 10 Watchlist identity gaps, unverified corporate actions, estimate currency/period checks, and non-comparable model returns remain visible issues rather than being auto-corrected.

## Verification limits

Provider transports and normalizers are fixture-testable. In this environment the application `DATABASE_URL` was configured but PostgreSQL was unreachable, `SEC_USER_AGENT` and `FMP_API_KEY` were absent, and `TEST_DATABASE_URL` was not configured. Live ingestion, PostgreSQL migration application and live provider responses therefore remain deployment checks; the implementation does not claim new source coverage until a scheduled run records it.
