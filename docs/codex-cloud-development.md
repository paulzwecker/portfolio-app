# Codex Cloud development runbook

This repository is designed to develop from a clean Linux checkout. Codex Cloud
does not need the original Windows machine, a production database, or a cloud
deployment during environment initialization.

## Supported toolchain

The repository pins the development toolchain to:

| Tool    | Version | Source                          |
| ------- | ------- | ------------------------------- |
| Node.js | 24.14.0 | `.node-version`                 |
| npm     | 11.9.0  | `package.json` `packageManager` |
| Python  | 3.12.3  | `.python-version`               |
| uv      | 0.12.23 | installed by `npm run setup`    |

JavaScript packages are installed from the committed `package-lock.json`. Python
packages are resolved from the committed `apps/api/uv.lock`. `npm run
check:environment` fails early if the Node, npm or Python versions differ from
the pinned values.

## Clean checkout

Run these commands from the repository root:

```sh
npm ci
npm run check:environment
npm run setup
```

`npm run setup` creates the ignored `.tools/venv`, installs the pinned uv
version, runs `uv sync --locked`, and creates an ignored `.env` from
`.env.example` if one does not exist. It never runs Alembic, starts a worker,
connects to Neon, deploys a service, seeds data, or imports workbook state.

The normal database-independent verification path is:

```sh
npm run check
```

This runs frontend/API lint, formatting checks, TypeScript and mypy, frontend
unit tests, backend tests explicitly selected with `-m "not integration"`,
OpenAPI contract checks, and the Next.js production build. It does not require
`DATABASE_URL`, `TEST_DATABASE_URL` or production Neon access. Run
`npm run test` only when you intentionally want the complete backend collection;
use `npm run test:integration` for the PostgreSQL subset.

## PostgreSQL-dependent tests

Integration tests are marked `integration` and require an explicitly dedicated
PostgreSQL database whose name ends in `_test`. The fixture creates a random
schema, applies the Alembic chain inside that schema, yields it to the test and
drops it afterward. It never uses the application database.

Set only the test URL in the Codex session or CI job:

```sh
export TEST_DATABASE_URL='postgresql+psycopg://portfolio_app:<password>@<host>:5432/portfolio_app_test?sslmode=require'
npm run test:integration
```

The URL must use the `postgresql+psycopg` driver and a database name ending in
`_test`. Do not point it at the application or production database. The GitHub
Actions `integration` job uses an ephemeral PostgreSQL 18 service and the same
isolated-schema fixture.

Browser tests that need seeded API state use the same test database. Start the
fixture API in one terminal, then run the web suite in another:

```sh
TEST_DATABASE_URL='postgresql+psycopg://portfolio_app:<password>@127.0.0.1:5432/portfolio_app_test' \
  npm run test:e2e:api

npm run test:e2e
```

Browser tests are intentionally an operator or release check rather than a
required cloud-initialization step because they need a running API and a
Playwright browser installation.

### Portfolio data rehearsal

The browser fixture requires a loopback PostgreSQL `_test` database and verifies
its live identity before creating a random test-owned schema. Portfolio scenarios
use synthetic provider payloads through the real importer. FastAPI serves those
records with PostgreSQL read-only transactions, the existing SQL write guard and
GET/HEAD-only HTTP access. Operator application settings and credentials are isolated.

In a dedicated PowerShell terminal with `TEST_DATABASE_URL` configured securely,
run the fixture from the repository root. Select `unpriced`, `fx-outage` or `valued`.

```powershell
$env:BROWSER_API_PORT='8011'
npm run test:e2e:api -- --scenario valued --lifetime-seconds 120
```

Run the focused desktop/mobile journey from a second dedicated terminal.

```powershell
$env:E2E_WEB_PORT='3110'
$env:BROWSER_API_PORT='8011'
$env:E2E_REAL_API='1'
$env:API_BASE_URL='http://127.0.0.1:8011'
$env:API_ACCESS_TOKEN=''
$env:APP_ENV='development'
$env:WEB_ACCESS_USERNAME=''
$env:WEB_ACCESS_PASSWORD=''
node scripts/browser.mjs test portfolio-live-data.spec.ts --workers=1
```

The test checks the fixture identity, exact decimal readback, proxy routing,
Portfolio → Operations investigation and unchanged holdings/targets/table counts.
It rejects API errors and browser write requests. Screenshots remain in ignored
`apps/web/test-results`. This test is skipped without `E2E_REAL_API=1`.

Wait for normal fixture shutdown and `Removed the test-owned browser schema.`
The lifetime defaults to 120 seconds for portfolio scenarios and is capped at 600.
Forced termination of the Windows wrapper can interrupt cleanup. Existing schemas
remain untouched. Each scenario needs its own fixture invocation. These checks
establish local integration using synthetic facts. Hosted provider cycles and
production activation retain their separate review and authorization gates.

### Company SEC coverage rehearsal

Use the same isolated test database and loopback web/API environment above. Start
one fixture at a time. The existing bootstrap advisory lock spans test schemas.
Choose `sec-covered`, `sec-outage`, `sec-unmapped`, `sec-refresh-partial` or
`sec-refresh-outage`. The incremental scenarios cover differing batch/issuer
outcomes and transport failures after retained evidence. Their SEC responses are
synthetic and pass through the existing real ingestion services.

```powershell
npm run test:e2e:api -- --scenario sec-outage --lifetime-seconds 180
```

In the second terminal, keep the matching `BROWSER_API_PORT` and `API_BASE_URL`.
Start the browser check promptly after the API reports readiness.

```powershell
$env:E2E_SEC_API='1'
$env:E2E_REAL_API='0'
node scripts/browser.mjs test company-sec-data.spec.ts --workers=1
```

This exercises the real scoped SEC importer with synthetic payloads, coverage and
provenance drawers, historical-cutoff separation, query/tab navigation and focused
Operations on desktop/mobile. It checks API errors, browser writes and unchanged
portfolio/table fingerprints. Wait for normal schema cleanup. A timed-out fixture
requires a fresh invocation before another browser run.

## Environment variables and database boundaries

Keep secrets in the Codex environment or an ignored `.env`; never commit them.
For database-independent work, leave `DATABASE_URL` and provider credentials
unset. The API can be imported and tested without creating an engine when no
database URL is configured.

The runtime variables have these boundaries:

| Variable                                                                                | Used by                                                 | Cloud-development guidance                                                                                 |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                                                                          | API runtime, Alembic and import commands                | Leave unset for initialization; use only a disposable development database for explicit database work.     |
| `TEST_DATABASE_URL`                                                                     | Integration tests and the seeded browser fixture server | Set only to a dedicated database ending in `_test`; never use the application or Neon production database. |
| `APP_ENV`, `API_ACCESS_TOKEN`                                                           | Preview/production API validation                       | Not needed for local checks; keep remote secrets in the hosting provider.                                  |
| `API_BASE_URL`, `WEB_ACCESS_USERNAME`, `WEB_ACCESS_PASSWORD`                            | Remote Next.js proxy and access gate                    | Not needed for local checks; use isolated preview values when deploying.                                   |
| `SEC_USER_AGENT`, `FMP_API_KEY`, `GOOGLE_SHEETS_*`                                      | Optional external-data and Sheets workers               | Leave unset unless the provider, source permissions and credentials are explicitly approved.               |
| `CLOUD_INGESTION_ENABLED`, `RECURRING_OPERATIONS_ENABLED`, `GOOGLE_SHEETS_POLL_SECONDS` | Background workers                                      | Keep disabled/zero in cloud development; do not start unattended jobs.                                     |
| `PORTFOLIO_PYTHON`                                                                      | Local setup/toolchain override                          | Optional path to the pinned Python 3.12.3 executable.                                                      |

When database-backed work is explicitly needed, use a disposable or dedicated
development database and apply migrations manually:

```sh
DATABASE_URL='postgresql+psycopg://portfolio_app:<password>@<host>:5432/portfolio_app_dev?sslmode=require' \
  npm run db:migrate
DATABASE_URL='postgresql+psycopg://portfolio_app:<password>@<host>:5432/portfolio_app_dev?sslmode=require' \
  npm run db:check
```

Do not run these commands during Codex Cloud initialization. Do not connect a
Codex development checkout to the production Neon branch, import personal
portfolio state, seed a real database, or start recurring ingestion workers
without an explicit task.

## GitHub branch and pull-request workflow

`main` is the deployable integration branch. Work starts from the latest `main`
in a short-lived branch named `codex/<topic>` (or another clearly scoped branch
when a hosting system requires it). Push the branch and open a pull request;
do not develop directly on `main`.

Every pull request must pass the `CI` workflow:

- **Quality, contracts and build**: database-independent checks and production
  build.
- **PostgreSQL integration tests**: isolated PostgreSQL 18 service and random
  test schemas.

Review migration files and contract changes in the pull request. A migration
PR must explain its rollback/reconciliation plan and must not apply itself to a
shared or production database. Merge only after the checks pass and the change
has an explicit reviewer. Keep deployment configuration changes separate from
personal-data migration and provider credential changes.

Configure GitHub branch protection separately to require pull requests, at least
one review and the `Quality, contracts and build` and `PostgreSQL integration
tests` checks before merging `main`. The repository workflow cannot change those
repository settings.

## Cloud publishing

Cloud deployment is a separate operator action. Use
[`docs/cloud-deployment.md`](cloud-deployment.md) for Render, Vercel and Neon
configuration. Codex Cloud initialization ends after dependency installation
and database-independent verification; it does not run deployment commands.

If a cloud build fails, reproduce it with the pinned Node/Python versions and
`npm ci` before changing application code. Keep local `.env`, Neon connection
strings, API tokens, Sheets credentials and provider keys outside GitHub.

## Known limitations

- A remote PostgreSQL service is still required for integration tests outside
  the GitHub Actions service container.
- E2E tests require a running fixture API and Playwright Chromium.
- Provider-backed ingestion remains opt-in and requires separately reviewed
  credentials and source permissions.
- Render/Vercel deployment and Neon data transfer are not part of cloud
  environment initialization.
