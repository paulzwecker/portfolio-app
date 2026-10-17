# Local development handover and state reconciliation — 2026-10-09

This is the verified local baseline after reconciling Milestone 6.3d with the
checked-in `main` state. It records the local database work performed during
handover and supersedes the earlier **offline-only** result in
[`postgresql-state-reconciliation-2026-10-07.md`](postgresql-state-reconciliation-2026-10-07.md).
It does not start Milestone 6.4 or change model methodology.

## Repository and runtime

- Branch `main` and fetched `origin/main` both resolve to
  `d9e72249d4b168c283a14618200087943fa8fd88`; ahead/behind is `0/0`.
- Node.js `24.14.0`, npm `11.9.0`, Python `3.12.3`, PostgreSQL `18.3`.
- The Windows PostgreSQL service `postgresql-x64-18` is running. The ignored
  local `.env` configures `DATABASE_URL` for `portfolio_app` and
  `TEST_DATABASE_URL` for the separate `portfolio_app_test` database on
  loopback port 5432. Values and credentials are intentionally not recorded.
- The existing local application responds through the Next.js health proxy with
  database connected and schema current. Start both development servers with
  `npm run dev`; check schema with `npm run db:check` and apply pending
  migrations with `npm run db:migrate`.
- The application role does not have `CREATEDB`. No manual system change was
  needed for this handover; the configured test database supports the
  PostgreSQL integration suite.
- `SEC_USER_AGENT` and `FMP_API_KEY` are not configured. SEC filing/reported
  fundamental ingestion and FMP consensus refresh therefore remain unavailable
  until locally configured, as described in
  [`external-data-operations.md`](../external-data-operations.md). No schedule
  was created.

## Database safety and migrations

Before migrating or importing, a complete PostgreSQL custom-format dump was
written to the ignored local file
`.cache/handover/portfolio_app_before_6e6c2d4e8a19_20261009.dump` (30,981,430
bytes; SHA-256
`EDBAECFF09527553CE4363E16C567522778BA863DEBDA11D0EB6D8F994BE90C3`).
`pg_restore --list` read all 365 archive entries. The dump was restored into a
new isolated PostgreSQL 18.3 cluster; row counts matched the source across all
52 pre-migration tables. The temporary cluster was shut down and removed. Keep
the dump outside Git; it contains the local database and should be handled as a
backup, not shared as a fixture.

The application database was at `8f96876cc9e9` and the repository had one head,
`6e6c2d4e8a19`. After the verified backup, `npm run db:migrate` applied the
additive external-ingestion operations migration. `npm run db:check` now reports
no new upgrade operations and Alembic reports `6e6c2d4e8a19 (head)`. The current
database has 54 tables.

## Canonical local state

Counts below were queried from the application database after migration,
market-data smoke, native-model import and idempotent replay. Missing lifecycle
rows remain missing; lifecycle was not inferred or edited.

| Domain                                                     |                                            Local state |
| ---------------------------------------------------------- | -----------------------------------------------------: |
| Companies / securities / listings                          |                                        219 / 100 / 100 |
| Current lifecycle rows                                     | 214: Portfolio 21, Watchlist 71, Candidate 96, Drop 26 |
| Companies without current lifecycle                        |                                                      5 |
| Holdings / cash positions / target allocations             |                                            22 / 2 / 16 |
| Score definitions / assessments                            |                                                4 / 506 |
| Price observations / FX observations / corporate actions   |                                 284,876 / 20,830 / 880 |
| Model-output snapshots                                     |                                                    344 |
| Native models / accepted revisions / migration assessments |                                              7 / 7 / 7 |
| Ranking definitions / runs / entries                       |                                          7 / 7 / 1,533 |
| Execution Pace runs / decisions                            |                                                  0 / 0 |
| Consensus observations                                     |                                                     67 |
| Reported fundamentals / source documents                   |                                                  0 / 0 |
| Research-priority inputs                                   |                                                     98 |
| External-ingestion runs / attempts                         |                                                  1 / 1 |

The seven native model/revision/assessment records are all revision 1 and
currently report `PARITY_PASS`: GOOGL, ASML, ISRG, CPRT, MA and UBER in
Portfolio, and TOST in Watchlist. This is 6/21 Portfolio (28.6%) and 1/71
Watchlist (1.4%) by current lifecycle membership. The existing accepted ISRG
and MA models were already in the canonical database before this handover; they
were not duplicated.

The bounded importer dry-run and replay left GOOGL/TOST as already imported.
CPRT and UBER each passed the exact NASDAQ/NYSE USD listing identity check,
30/30 projection comparisons and 22/22 normalized-output/return-stream
comparisons. Their accepted revisions retain the legacy enterprise-UFCF return
definition and are explicitly marked **not comparable** to canonical
shareholder-cash-flow IRR. Repeating the import inserted zero revisions and
reported four already-imported mappings.

ASML's current accepted revision was preserved. The latest dry-run reports
`DATA_CHECK`: 30/30 projection checks passed, but 20/22 output checks passed;
`P-ASML!N202` (Bull FV) and `P-ASML!AO7` (Weighted FV) exceed the existing
`1e-7` tolerance. The dry-run also left ISRG and MA `BLOCKED` because existing
models for their exact listing/method do not carry the newer immutable source
revision ID. No existing accepted revision was overwritten to make those
reports pass. The next native-model batch should resolve those mapping/parity
questions before import.

## Bounded Milestone 6.2 smoke

Yahoo Finance was used only through the existing provider adapter and exact
listing identities. A dry-run, then a bounded apply, requested CPRT (NASDAQ)
and UBER (NYSE) from October 6–9, 2026. It added eight price observations, ten
FX observations and four raw provider payloads; current quotes for both exact
listings are marked fresh as of October 9. A separate worker smoke requested
only `TWD/EUR` for the same dates and completed one ingestion run/attempt with
two observations. Replaying the identical request reused the completed run and
inserted no duplicates. No full-universe backfill, scheduler or alternate
listing substitution was used.

Detailed ignored local run reports remain under `.cache/handover/`, including
`market-smoke-applied-20261009.json`,
`native-model-applied-20261009.json`, and
`native-model-replay-20261009.json`. The local backup and those reports are
operational artifacts and are not committed.

## Verification and known gaps

- `npm run check` passed: ESLint/Ruff, Prettier/Ruff formatting, TypeScript and
  mypy, Vitest (86), pytest (212), generated API contracts, and optimized web
  production build.
- `npm run test:integration` passed: 43 PostgreSQL integration tests.
- `npm run db:check` passed after migration with no schema drift.
- Playwright ran against a fresh production server on port 3001: 16 passed, 10
  explicitly skipped, and 8 failed. The failures reproduce against the fresh
  build: responsive horizontal overflow in several Research/Company views,
  desktop overflow and a mobile interaction timeout in the Sheets model flow,
  the mobile workspace retry timing out, and a mobile Portfolio interaction
  blocked by an overlapping card.
  The live-database E2E cases were skipped by their explicit opt-in gates. The
  pre-existing server on port 3000 was left running and untouched.
- Full financial-model native coverage remains limited to seven models; ASML's
  new source comparison is a data check, and newer ISRG/MA mapping revisions
  remain blocked. Reported-fundamental and filing history is empty, consensus
  history has 67 rows, and Execution Pace history is empty. SEC/FMP credentials
  are the external-ingestion prerequisites still missing.

The only tracked implementation adjustment from the verification run is a
`session.flush()` in the external-ingestion persistence test fixture so its
parent run row is inserted before the foreign-key dependent attempt row. It
does not change production behavior.
