# Testing and verification

## Commands and isolation

`npm run check` covers lint/format, frontend and strict backend types, unit tests,
repository/source-data policy, generated contracts and the Next.js production
build. It runs independently of production database access.

`npm run test:integration` uses only `TEST_DATABASE_URL` ending in `_test`. The
fixture creates and removes random migrated schemas. Use an explicitly verified,
disposable target. Tests requiring extra local tools/privileges may skip. Record
those skips and their reasons in milestone evidence.

`npm run test:e2e` uses Chromium desktop and mobile projects. Database-backed browser
fixtures use test-owned schemas. Fixture browser evidence and live production
verification have separate scopes. Keep private source files and credentials
outside CI and browser artifacts.

`npm run docs:check` verifies repository Markdown links. It reports files absent
from deliberate sparse checkouts, so the normal full-repository documentation
check belongs in the operator/developer checkout. CI keeps its source-data policy.

## Local Playwright server modes

Playwright starts the development frontend by default. On Windows hosts with
restricted worker creation, build and start the production frontend in one terminal.

```powershell
npm run build
$env:E2E_WEB_PORT = "3000"
npm run start:web
```

In another terminal set `$env:E2E_USE_PRODUCTION_SERVER = "1"` and run
`npm run test:e2e -- --workers=1`. This reuses the running frontend.

## Managed authenticated production-browser fixtures

For synthetic access/proxy verification, the existing driver can build and launch
its own production frontend and loopback HTTPS source.

```powershell
npm run test:e2e -- --managed-production production-access.spec.ts research.spec.ts --grep "production access|DCF sensitivity" --workers=1
```

The driver uses the normal production build including type checks. It generates
fresh process-only Basic Auth and API credentials, plus a short-lived loopback
certificate signed by an ephemeral test CA. Child Node processes trust that CA
through `NODE_EXTRA_CA_CERTS` while certificate and hostname verification remain
enabled. Temporary certificate/key files are removed on normal command completion
and failures. Managed traces are disabled to keep test credentials out of artifacts.

Managed mode pins both servers to loopback, refuses existing servers, redirects
the API to its read-only synthetic HTTPS fixture and disables existing live/write
test opt-ins and background controls. It uses the existing locked Python toolchain
and cryptography dependency. Default ports are 3108 and 3109; optional
`E2E_WEB_PORT` / `E2E_FIXTURE_API_PORT` overrides require distinct unprivileged ports.

The existing development mode stays the default. For an explicitly operator-started
production frontend, `E2E_USE_PRODUCTION_SERVER=1` retains server reuse. Supply both
`E2E_WEB_ACCESS_USERNAME` and `E2E_WEB_ACCESS_PASSWORD` explicitly for that server.
Browser credentials are restricted to the exact local frontend origin. This fixture
verification establishes local auth/proxy behavior; hosted verification and real
financial data retain their separate evidence and authorization requirements.

## Evidence maintenance

### Complete SEC refresh rehearsal (no provider network)

Use an existing disposable native PostgreSQL database ending `_test` on loopback;
Docker is not required. The browser server verifies the connected identity and
creates its own migrated random schema. With `TEST_DATABASE_URL` set to that exact
local target and `BROWSER_API_PORT=8011`, start:

```sh
node scripts/uv.mjs run --locked --project apps/api python apps/api/tests/browser_server.py --scenario sec-refresh-workflow --lifetime-seconds 600
```

In a second terminal set `API_BASE_URL=http://127.0.0.1:8011`,
`BROWSER_API_PORT=8011`, `E2E_SEC_REFRESH_API=1`, and a free `E2E_WEB_PORT` (3120
was verified). Run:

```sh
node node_modules/@playwright/test/cli.js test --config apps/web/playwright.config.ts financial-refresh.spec.ts --project desktop --workers 1 --timeout 180000
```

Repeat with a **fresh fixture server/schema** for `--project mobile`. Do not point
this scenario at an existing application or use the managed synthetic API mode.

This scenario alone permits the two SEC request types and test-only clock/provider
controls. It runs the real queue, SEC adapters, normalization, raw receipts and
financial APIs against fixed [fictional responses](../apps/api/tests/recorded/sec-refresh/README.md).
It proves navigation/reload recovery, automatic UI invalidation, the Operations
two-domain batch, one coalesced missed-run cycle, duplicate-free replay, retained
facts during outage, partial coverage and separate currencies. Every table outside
the SEC ingestion/job scope is content-hashed before and after. Existing read-only
browser scenarios keep their original restrictions. No real SEC request, recurring
schedule registration, production write or activation is part of this rehearsal.

### Recorded official SEC responses through the investor UI

The `sec-real-refresh` scenario reuses the same queue, worker, adapters and bounded
test database. It requires a private `sec-real-recording-v1` manifest containing
the exact issuer/listing evidence, original capture times, official source URLs,
file lengths/SHA-256 hashes, all indexed history pages (at most five), and independently
checked expected values. `expected.statement_samples` pins each metric's view,
economic start/end, value, unit/currency, fiscal label, cell status and selected
accession/concept/source URL; `annual_samples` also carries explicit fiscal labels.
Optional `missing_metrics` pins unavailable metric/period cells. Never generate
these expectations from the API being tested. No raw response or private manifest belongs in Git.
The loader validates the complete bundle before seeding its random test schema.
It never downloads a missing file or substitutes a fictional response.

Set `TEST_DATABASE_URL` to the verified loopback `_test` target and
`BROWSER_SEC_RECORDING_MANIFEST` to that private rehearsal manifest. With
`BROWSER_API_PORT=8017`, start:

```sh
node scripts/uv.mjs run --locked --project apps/api python apps/api/tests/browser_server.py --scenario sec-real-refresh --lifetime-seconds 600
```

Set `API_BASE_URL=http://127.0.0.1:8017`, `BROWSER_API_PORT=8017`,
`E2E_REAL_SEC_REFRESH_API=1`, and a free `E2E_WEB_PORT` in another terminal:

```sh
node node_modules/@playwright/test/cli.js test --config apps/web/playwright.config.ts real-sec-refresh.spec.ts --project desktop --workers 1
```

Repeat mobile with a fresh fixture/schema. The frontend must also use loopback.
This is real source data replayed offline in a fictional portfolio, not production
or an additional live provider request. Original `retrieved_at`/`observed_at`
remain the capture times; jobs and database recording have their later execution
times. The scheduled-clock check replays identical bytes: it proves idempotence
and missed-run handling, not a new filing or financial period.

The November 14 UTC MSCI capture used three public SEC requests and the existing
configured contact. Independent raw-source counts were 1,596 supported facts and
310 supported filings. Rehearsal checks annual/quarterly values, fiscal labels,
selected filing evidence, genuine PARTIAL coverage, refreshed tables/charts,
internal table scrolling and unchanged protected state. Source gaps, restatements
and unlinked amendments remain visible. The ordinary fictional scenario separately
tests new-period updates, outages and synthetic conflicts.

The November 15 Berlin-time extension adds Microsoft, with six official requests:
four JSON responses plus the latest 10-K/10-Q filing HTML for independent review.
Only the four JSON responses enter the replay manifest; filing bodies remain
private comparison evidence and are not imported as canonical document content.
Reconciliation retains 1,909 facts and 428 filing references. Fourteen filing-checked
annual/quarterly samples cover revenue, gross profit, operating/net income, cash,
operating cash flow and capex. The June annual period is FY2026; September 2026 is
FY2027 Q1. Source capex keeps its positive XBRL sign; no FCF is synthesized.
The same test switches existing Income Statement, Cash Flow and Balance Sheet
views, verifies source drawers, and reruns MSCI without new source requests.
The opt-in backend check also proves that a knowledge cutoff before capture cannot
expose observations recorded later during replay. Private mapping proposals remain
unapproved; isolated success is not a production mapping or activation receipt.

For the opt-in backend replay, set `BROWSER_SEC_RECORDING_MANIFEST` to the same file
and select `test_real_sec_recording_manual_scheduled_api_reconciliation` in
`apps/api/tests/test_refresh_rehearsal.py`. It carries `source_data` and integration
markers; ordinary CI never opens private captures. Bundle validation has ordinary
synthetic guard tests that run without source access.

Record exact command/results, test scope and skips in the current roadmap. Keep
long logs and historical milestone records under dated evidence. Existing financial
parity contracts and synthetic fixtures remain the regression basis for engines.
The [earlier verification ledger](history/verification-through-2026-10.md) retains
historical migration, source-import and browser results.

## Database test classification

Ordinary tests that consume the shared `postgres_engine` fixture require
`@pytest.mark.integration`, including indirect consumers through other fixtures.
The CI unit job deliberately has no database; its marker expression excludes these
cases. The PostgreSQL job selects `integration and not source_data` and provides
an isolated PostgreSQL service. An unmarked database case would otherwise skip in
the unit job and be omitted from the PostgreSQL job.

Collection fails early for an unclassified ordinary `postgres_engine` consumer,
including dependencies exposed through another fixture. The fixture also checks
runtime requests before its missing-database skip, covering dynamic
`request.getfixturevalue` calls. Marker inheritance at module/class/function level
is supported. Diagnostics identify each function once and omit parameter values.

Keep `source_data` on tests requiring operator portfolio files or private model
fixtures. Those cases retain explicit operator execution and remain excluded from
ordinary CI. Preserve all source-data checkout and credential restrictions.

Current integration status and preserved branch evidence are in the
[active workstream](ACTIVE_WORKSTREAM.md).

## Private public-market source rehearsal

`test_real_public_market.py` requires off-repository `BROWSER_PUBLIC_MARKET_MANIFEST`
with version `private-public-market-v1`. The manifest binds original EODHD metadata,
history and official ECB CSV URLs, hashes and capture timestamps. All referenced
files stay within its private bundle; missing responses never trigger network fetches.
Two explicit captured windows (`initial`, `incremental`) are replayed unchanged.
Independent source values determine expected counts and EUR values for fictional
quantities/cash. No source value is checked into CI.

Against the existing loopback `_test` target, run:

```powershell
node scripts/uv.mjs run --locked --project apps/api pytest apps/api/tests/test_real_public_market.py -q
```

`browser_server.py --scenario public-market-refresh --lifetime-seconds 600` serves
the same fixture for `public-market-refresh.spec.ts`. Its opt-in environment guards
require private screenshot output. Initial stale history, queued manual work,
scheduled increment, unchanged protected hashes and same-day reuse are verified.
Review desktop/mobile and light/dark themes. Real screenshots/readbacks remain private;
default CI uses synthetic data and skips this recording. Freshness assertions require
a contemporaneous recording bundle; never alter original capture timestamps to make
old provider data appear current.

## Private consensus source rehearsal

Set `TEST_DATABASE_URL` to the existing disposable loopback PostgreSQL `_test`
database and `BROWSER_CONSENSUS_RECEIPT` to the off-repository capture receipt.
The receipt binds the fixed EODHD AMZN demo URL, original retrieval timestamp,
payload path and SHA256. Source files must remain inside the private bundle.
Missing evidence fails; this test never fetches a replacement from the network.

```powershell
node scripts/uv.mjs run --locked --project apps/api pytest apps/api/tests/test_real_consensus.py -q
```

The source-data test seeds fictional isolated research context, then exercises the
existing durable ingestion service, same-day reuse and a later scheduled replay.
It independently compares raw forward-period means, ranges and analyst counts
against canonical PostgreSQL and both consensus/financial-statement APIs. It checks
the pre-capture knowledge cutoff and hashes all unrelated tables before/after.
The delayed replay preserves original source time and proves idempotence, not a
second real snapshot or newly changed forecasts. Ordinary CI excludes this test.

For browser review set a free `BROWSER_API_PORT` and start:

```powershell
node scripts/uv.mjs run --locked --project apps/api python apps/api/tests/browser_server.py --scenario real-consensus --lifetime-seconds 600
```

In another terminal set matching loopback `API_BASE_URL`, `BROWSER_API_PORT`, a free
`E2E_WEB_PORT`, `E2E_REAL_CONSENSUS_API=1`, and `CONSENSUS_ARTIFACT_DIR` to a private
off-repository directory. Run the existing harness:

```powershell
node node_modules/@playwright/test/cli.js test --config apps/web/playwright.config.ts real-consensus.spec.ts --project desktop --workers 1
```

Repeat mobile with a fresh fixture. The test checks annual/quarterly revenue,
source ranges/counts, explicit uncertain EPS, reload persistence, light/dark themes,
no browser writes and unchanged protected state. Source screenshots remain private.
The local fixture cleans up its own schema on normal shutdown. Use a contemporaneous
recording for freshness checks; never rewrite capture timestamps to keep it fresh.
