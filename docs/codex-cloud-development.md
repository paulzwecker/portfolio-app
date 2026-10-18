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
TEST_DATABASE_URL='postgresql+psycopg://portfolio_app:<password>@<host>:5432/portfolio_app_test' \
  npm run test:e2e:api

npm run test:e2e
```

Browser tests are intentionally an operator or release check rather than a
required cloud-initialization step because they need a running API and a
Playwright browser installation.

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
