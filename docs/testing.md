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

Record exact command/results, test scope and skips in the current roadmap. Keep
long logs and historical milestone records under dated evidence. Existing financial
parity contracts and synthetic fixtures remain the regression basis for engines.
The [earlier verification ledger](history/verification-through-2026-10.md) retains
historical migration, source-import and browser results.
