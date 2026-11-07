# Portfolio Research Platform

A private equity-research and portfolio application built with Next.js, FastAPI
and PostgreSQL. Finance agents maintain models in Google Sheets and explicitly
publish versioned proposals. The application validates and presents accepted
models, independent valuation methods, research and portfolio decisions.

Start with the [documentation index](docs/README.md),
[product vision](docs/PRODUCT_VISION.md) and [current roadmap](ROADMAP.md).
The [canonical production baseline](docs/production-canonical-baseline.md) records
verified holdings restoration and its enrichment exclusions.

## Development setup

Pinned tool versions are in `.node-version`, `.python-version` and `package.json`.
From the repository root run the dependency-only setup.

```sh
npm ci
npm run check:environment
npm run setup
```

Configure secrets in the ignored root `.env`. Verify the effective database target
using [database-write-targets.md](docs/database-write-targets.md) before running
any database command. Configure a separate disposable `TEST_DATABASE_URL` for
integration tests. The [development guide](docs/codex-cloud-development.md) covers
Linux, local setup and isolated database provisioning.

Start the local API and frontend independently when background workers should
remain disabled.

```sh
npm run dev:api
npm run dev:web
```

The web application uses `http://127.0.0.1:3000`, the API uses port 8000 and exposes
`/docs`, `/health/live` and `/health/ready`. `npm run dev` also starts the existing
market-data and recurring-operation workers according to their configured flags.
See [recurring operations](docs/recurring-operations.md) before enabling them.
Schema changes follow the [deployment/migration runbook](docs/deployment-and-migrations.md),
with separate owner authorization for production.

## Verification

```sh
npm run check
npm run test:integration
npm run test:e2e
npm run docs:check
```

`npm run check` runs static checks, unit tests, API contract checks and the production
build. Integration tests require the explicitly configured disposable database.
[Testing](docs/testing.md) covers isolation, browser modes and skipped-test evidence.

## Repository ownership

| Area                  | Owner                                                                    |
| --------------------- | ------------------------------------------------------------------------ |
| `apps/api`            | Native financial engines, validation, domain operations, source adapters |
| `apps/web`            | Accessible presentation and interaction using typed API responses        |
| `packages/contracts`  | Generated API/client contracts                                           |
| `tools/google-sheets` | Explicit publication and source-authoring adapter                        |
| `docs`                | Product, architecture, domain references, runbooks and dated evidence    |

Pydantic owns API schemas. Use `npm run contracts:generate` after API contract
changes and `npm run contracts:check` to verify committed client artifacts.

Accepted financial state and source provenance follow the domain contracts linked
from the index. Development fixtures belong in disposable test infrastructure.
Private snapshots, credentials and financial review packages stay outside Git.
