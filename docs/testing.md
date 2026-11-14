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

## Return hurdle investor journey (fictional data)

The opt-in `return-hurdle-api.spec.ts` journey uses the real Next.js proxy,
FastAPI native engines and a disposable PostgreSQL schema. It creates explicitly
fictional accepted DCF, owner-cash-flow and residual-income models, then serves
them through a database connection with `default_transaction_read_only=on`.
There are no provider requests. Accepted revisions and the portfolio fingerprint
must remain unchanged after the browser explores all three models and returns
to Holdings.

In one terminal, set `TEST_DATABASE_URL` to an operator-verified loopback
PostgreSQL database ending `_test` (never production), then run:

```powershell
$env:BROWSER_API_PORT = "8014"
node scripts/uv.mjs run --locked --project apps/api python apps/api/tests/browser_server.py --scenario return-hurdle --lifetime-seconds 600
```

After the fixture is ready, in another terminal:

```powershell
$env:BROWSER_API_PORT = "8014"
$env:API_BASE_URL = "http://127.0.0.1:8014"
$env:E2E_RETURN_HURDLE_API = "1"
$env:E2E_WEB_PORT = "3122"
npm run test:e2e -- return-hurdle-api.spec.ts --workers=1
```

Repeat with `--scenario return-hurdle-unpriced` after normal fixture shutdown to
verify hypothetical analysis without any price observations. The server removes
its own random schema at normal shutdown. Both Chromium projects cover the full
journey, light/dark themes, stale input suppression, source details and screenshots.
The ordinary `research.spec.ts` suite separately exercises stale revisions,
mismatched identity, an older API and delayed responses with labeled fixtures.
The managed production-browser mode skips the opt-in database journey; its broader
auth/proxy checks remain separate from these real local API checks.

## Evidence maintenance

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
