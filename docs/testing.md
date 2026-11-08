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

## Current BUILD checkpoint

Branch `codex/ci-database-test-coverage` starts from main `395f842`. Completed PRs
[#25](https://github.com/paulzwecker/portfolio-app/pull/25) and
[#26](https://github.com/paulzwecker/portfolio-app/pull/26) remain stable for owner
review. This independent C5.2 scope restores CI coverage without runtime changes.

C5.2 is LOCAL_VERIFIED. Thirty-two previously unmarked PostgreSQL cases across ten
modules now select into the database job and pass against fresh random schemas on
independently verified loopback PostgreSQL 18.3, including a repeat with the guard.
Seventy-one focused unit checks pass with TEST_DATABASE_URL removed and an unusable
synthetic default database URL. Six real pytest-subprocess policy cases cover
indirect/dynamic requests, inherited marks, both CI selectors and source opt-in.
Collection selects 649 unit cases with zero PostgreSQL consumers and 178 integration
cases. Existing test bodies and financial assertions match main. Strict mypy,
focused Ruff/format, three source-policy checks, docs links and whitespace pass.

Next integrate this independent correction after the pending owner-reviewed PRs
merge, preserve both sets of roadmap/handoff evidence, then run comprehensive
checks once at that integration gate. Remote CI for this BUILD branch and its
combined baseline remain unverified. Runtime behavior, production operations and
financial acceptance retain their existing contracts and approval gates.
