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

## Evidence maintenance

Record exact command/results, test scope and skips in the current roadmap. Keep
long logs and historical milestone records under dated evidence. Existing financial
parity contracts and synthetic fixtures remain the regression basis for engines.
The [earlier verification ledger](history/verification-through-2026-10.md) retains
historical migration, source-import and browser results.
