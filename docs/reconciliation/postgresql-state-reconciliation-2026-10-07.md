# PostgreSQL state reconciliation — 2026-10-07

## Current database access

The ignored root `.env` contains `DATABASE_URL` and `TEST_DATABASE_URL`, but both
are configured for a loopback PostgreSQL listener that is not running in this
workspace. A credential-safe SQLAlchemy probe returned `OperationalError` for both
connections. The remote cloud environment status also reports no database secret
or runtime-variable binding, and no TCP database domains or IP ranges. No
PostgreSQL service can be provisioned or reached through the tools available in
this environment.

The Alembic graph can be inspected without connecting: it has one head,
`6e6c2d4e8a19`, with `0001_platform_baseline` as its base. The database's current
revision is unknown. `alembic upgrade head`, `alembic check`, and `alembic current`
all stop at the unavailable connection; no migration was applied.

## Canonical state reconstruction

No canonical imports ran and no rows were inserted manually. The current
database-backed counts are therefore **unknown**, not zero:

| Requested count                       | Current database result |
| ------------------------------------- | ----------------------: |
| Portfolio companies                   |                 Unknown |
| Watchlist companies                   |                 Unknown |
| Holdings                              |                 Unknown |
| Targets                               |                 Unknown |
| Market-data observations and coverage |                 Unknown |
| Published model outputs               |                 Unknown |
| Accepted native Portfolio models      |                 Unknown |
| Accepted native Watchlist models      |                 Unknown |

The tracked historical receipts are useful replay evidence, not a current database
snapshot. They report the prior workbook import as 219 companies, 24 holdings, 16
targets, 506 score assessments, and 657 cached rank entries; the market-data
receipt reports 65,535 prices, 71 price-regime snapshots, and two corporate
actions; the model-output receipt reports 344 stored snapshots. None establishes
that those rows are present in the currently unreachable database.

## GitHub and canonical model evidence reconciliation

The earlier local inspection only saw commit `c028454` because it had not fetched
GitHub. The remote repository's `main` also contains commit
`aafef78ae461deaf68dd2760d2f778b3cabe82b1` (`advanced the data retrieval models`),
which commits the 2026-10-05 native-model import and replay receipts. The latest
2026-10-06 parity receipt is separate evidence: it records parity only and has no
canonical application query.

| Evidence                                                        | What it proves                                                                                                                                                                                                                                         | What it does not prove                                                                     |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| Native importer and canonical revision code                     | The deterministic workflow checks exact listing identity and stores append-only revisions and migration assessments.                                                                                                                                   | Code presence does not establish that a PostgreSQL revision exists.                        |
| `native-model-input-import-batch-2-2026-10-05.json` (`APPLIED`) | Three models were imported and two were already present: `P-ASML`, `P-ISRG`, and `P-MA` were newly imported; `P-GOOGL` and `W-TOST` were already present. The receipt therefore documents 4/21 Portfolio and 1/71 Watchlist native models at that run. | It does not establish that those rows remain in today's database.                          |
| `native-model-input-import-batch-2-replay-2026-10-05.json`      | Replay imported zero records and reported all five as already imported.                                                                                                                                                                                | It does not establish current database state.                                              |
| `native-model-input-import-2026-10-06.json` (`PARITY_ONLY`)     | Six fixture models pass source parity: `P-GOOGL`, `P-ISRG`, `P-MA`, `P-CPRT`, `P-UBER`, and `W-TOST`. The report records zero imported and zero already imported.                                                                                      | `canonical_application_state` is `NOT_QUERIED`; it is not application-acceptance evidence. |
| Current PostgreSQL query                                        | None; both configured local connections fail.                                                                                                                                                                                                          | Current accepted model count and IDs remain unknown.                                       |

The receipt-backed IDs for the five models in the applied batch are:

| Model     | Model ID                               | Revision ID                            | Receipt status   |
| --------- | -------------------------------------- | -------------------------------------- | ---------------- |
| `P-GOOGL` | `062694a6-2d4f-4170-8820-8872bcf42908` | `6bfae7e5-59d0-45ba-a193-79348e9f51ab` | Already imported |
| `W-TOST`  | `ef0631c9-a866-4fe4-ade9-7f03268010c0` | `020a4d36-4692-4e07-bfde-f957e2cfa0bc` | Already imported |
| `P-ASML`  | `40c89b0b-ca5f-4741-980c-3f5bb729efc7` | `3e5267fa-d7e8-4bc2-b19c-69eb46374f03` | Imported         |
| `P-ISRG`  | `5eb0ca86-e965-4e9a-91ac-287af09c338a` | `645b607a-4a07-48ee-8e72-e5662f19b9db` | Imported         |
| `P-MA`    | `c35c385e-c486-4581-af99-4b1c38f27fa9` | `e01d5779-e2d9-4b8a-9e80-ddd5c05f9abe` | Imported         |

This explains the old `1/21` versus later `4/21` Portfolio receipt counts: the
6.1 audit snapshot predates the 2026-10-05 17:36 UTC applied sub-batch. The
2026-10-06 parity receipt then passed `P-CPRT` and `P-UBER` in addition to
`P-ISRG` and `P-MA`, but it did not apply any revision. `P-ISRG` and `P-MA` already
have earlier accepted receipts. The latest receipt classifies `P-ASML` as
`DATA_CHECK`; that newer evidence does not delete or rewrite the historical
accepted revision.

The four new 6.3 Portfolio candidates in that parity receipt were **not applied**.
Without PostgreSQL, exact current identity checks, current-price validation,
persisted revisions, and idempotent database replay remain unverified. The
database-backed coverage before and after reconciliation is unknown; the latest
receipt-backed historical count is 4/21 Portfolio and 1/71 Watchlist.

## Required continuation after infrastructure setup

Provision the persistent PostgreSQL endpoint, network route, and secret bindings
described in [the remote database runbook](../remote-development-postgresql.md).
Then apply migrations and replay the documented canonical importers, starting
with their dry-run reports. Run native imports with `--apply` only after exact
identity and canonical-price checks pass. Store a new dated applied receipt and
capture the requested counts from PostgreSQL; do not treat the existing parity
receipt or source workbook counts as database state.

## Verification performed

- `alembic heads` and `alembic history` succeeded offline and show one head,
  `6e6c2d4e8a19`. `alembic current`, `alembic upgrade head`, and `alembic check`
  failed before schema access with `OperationalError`; no migration was applied.
- `npm run check` reached the API lint step after the web ESLint step passed, then
  stopped because `uv` could not fetch the uncached Hatchling build dependency
  from PyPI under the restricted network policy. API Ruff lint, Ruff formatting,
  strict mypy, and OpenAPI export checks passed when run directly with the existing
  project virtual environment.
- The complete backend pytest suite was attempted with the configured test URL.
  PostgreSQL-backed fixtures reported connection errors, and the run stalled at
  `test_health.py`; it was interrupted after a further 60 seconds without a final
  suite summary. The focused model-input parity, migration, and inventory tests
  completed with 10 passed and two database-dependent tests skipped.
- Web Vitest passed (66 tests), web typecheck passed, and the generated OpenAPI
  TypeScript contract matched. The production build's typecheck passed, but
  Turbopack could not spawn its CSS worker because local port binding returned
  `Operation not permitted`, including when retried outside the sandbox.
- Database import replay/idempotence, persisted counts, migration application,
  and live provider ingestion remain unverified. No tests or parity tolerances
  were changed to work around these limits.
