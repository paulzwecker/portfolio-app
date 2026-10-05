# Verification records

## Milestone 1A — 2026-10-04

Implemented and verified only Milestone 1A. The decisions in domain-model.md were
recorded before implementation. No workbook files were imported or reverse-engineered;
no score, ranking, price, financial-model or execution functionality was added.

The configured permanent local PostgreSQL service now works through the ignored
root `.env`. The application database was upgraded from the Milestone 0 baseline
and seeded with clearly marked fictional demonstrations. `TEST_DATABASE_URL` is
configured for the existing separate test database. No Docker is used.

| Check                                              | Result                                                                         |
| -------------------------------------------------- | ------------------------------------------------------------------------------ |
| Complete `npm run check`                           | Passed                                                                         |
| ESLint / Ruff, Prettier / Ruff formatting          | Passed                                                                         |
| TypeScript / strict mypy                           | Passed, including domain and test modules                                      |
| Vitest                                             | 39 passed                                                                      |
| pytest with real PostgreSQL integration            | 44 passed; no skips                                                            |
| Empty-schema Alembic upgrade → downgrade → upgrade | Passed with all 11 domain tables                                               |
| Application and fresh test database `db:check`     | No new upgrade operations                                                      |
| Generated OpenAPI / TypeScript consistency         | Passed                                                                         |
| Next.js production build                           | Passed, including all three research pages                                     |
| Chromium desktop and mobile with live fixture API  | 16 passed; no skips                                                            |
| Desktop/mobile portfolio and company screenshots   | Reviewed; no horizontal overflow                                               |
| Fresh source-only copy: `npm ci`, `npm run setup`  | Passed using committed lockfiles                                               |
| Fresh copy: `db:migrate`, `db:check`, `db:seed`    | Passed against an empty dedicated test database                                |
| Fresh copy: documented `npm run dev`               | Both reload servers started; pages and both frontend proxies returned HTTP 200 |

The npm production dependency audit reports zero vulnerabilities.

Backend integration tests use randomly named schemas in the explicit test database.
They verify atomic/stale/concurrent lifecycle transitions, restrictive historical
foreign keys, immutable snapshots and accepted targets, persisted target-total
revalidation, exact quantities/fractions, missing versus explicit zero, effective-time
snapshot selection, ADR identity boundaries, demo-seed idempotence/refusal, and REST
error behavior. Regression coverage includes fixed-notation decimal serialization.

Browser checks use `npm run test:e2e:api`, which migrates and seeds a test-owned
schema rather than using the application database. Coverage includes filtered universe
navigation, share-class/listing identity, lifecycle history, explicit lifecycle writes,
target independence, native cash, and loading/empty/error/retry states. The suite uses
two workers to avoid cold development compilation contention on this Windows machine.
Origin handling has a regression test for Next.js's internal localhost request URL.

There is still no `.git` metadata in the supplied workspace. Clean-install evidence
comes from a source-only copy excluding dependencies, virtual environments, caches,
credentials, generated build output and workbook artifacts. Its test fixtures are
disposable and distinct from the permanent application database.
Verification servers were stopped, owned browser schemas were removed, and the
fresh-install test database was returned to its original empty state. Temporary
verification credentials were removed; the configured local `.env` remains ignored.

Known limits: current market weights/gaps require later prices/FX; holdings and target
authoring currently use REST/Swagger. Administrator SQL can bypass ORM history guards.
The existing development dependency advisory remains (the clean npm install reports
five high-severity entries); no dependencies were added for Milestone 1A. See the
historical dependency note below. Workbook cutover and formula parity remain future
work. At the time of this historical Milestone 1A record, Milestone 1B had not yet
been implemented; the subsequent score and ranking verification follows below.

## Milestones 1B and 1C — 2026-10-04

Milestone 1B score definitions/assessments and Milestone 1C ranking definitions and
availability snapshots were verified together. The application PostgreSQL database
was upgraded through Alembic revision `f93584e17442`; `npm run db:check` reported no
schema drift, and the fictional development seed completed. No workbook scores or
numeric rankings were imported.

| Check                                                                                        | Result                                                              |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `npm run check` (lint, format, TS/mypy, unit/integration tests, contracts, production build) | Passed                                                              |
| Vitest                                                                                       | 40 passed                                                           |
| pytest with PostgreSQL integration                                                           | 54 passed; no skips                                                 |
| Empty-schema Alembic upgrade → downgrade → upgrade                                           | Passed in `test_migrations`                                         |
| Application `db:migrate` and `db:check`                                                      | Passed; no metadata drift                                           |
| Fictional score/ranking seed                                                                 | Passed; idempotent seed and one availability snapshot per rank type |
| OpenAPI / generated TypeScript contracts                                                     | Passed                                                              |
| Next.js optimized production build                                                           | Passed                                                              |
| Chromium browser suite, desktop and mobile                                                   | 18 passed; no skips                                                 |

Browser tests used a disposable PostgreSQL schema and verified the end-to-end API
path, explicit unavailable/not-migrated ranking states, ranking history in Company,
and responsive Universe/Company flows. Existing local services already occupied
ports 8000 and 3000, so the browser API and frontend used test ports 8100 and 3100;
the existing services were left running. The test schema was dropped when the
fixture server stopped.

The focused workbook inspection and three documented sort rules are recorded in
`workbook-map.md`. Portfolio Score, Expected IRR, Research Sort Key, market prices,
and FX remain unmigrated. Thus the tests verify safe auditable availability
snapshots, not workbook rank parity or numeric ranking calculations. The supplied
workspace still has no `.git` metadata.

## Controlled legacy workbook import - 2026-10-04

The scoped importer applied the committed `Portfolio_Watchlist.xlsx` and
`Market Data.xlsx` pair to the local application database. Source-pair digest:
`d0f8137ef9d7441fa78ec1eda4fae5603c255efe651f5f14cbd3042aedb3eac5`. The import
replaced only the fictional demo seed after the importer confirmed seed-only state.
Reapplying the same source pair is idempotent. The Portfolio and Universe UI now
read these imported PostgreSQL records.

| Domain                        | Imported and reconciled |
| ----------------------------- | ----------------------: |
| Companies                     |               219 / 219 |
| Securities and listings       |                 90 / 90 |
| Resolved lifecycle states     |               214 / 214 |
| Current holding and cash rows |                 24 / 24 |
| Company target allocations    |                 16 / 16 |
| Score assessments             |               506 / 506 |
| Cached ranking-run entries    |               657 / 657 |

Stored state matched all mapped source values: zero reconciliation mismatches and
`RECONCILED_WITH_SOURCE_GAPS`. The current holding snapshot is complete and company
target allocations sum to exactly 1.00. There are 48 unresolved source errors:
13 listing rows need status mapping, 11 READY listing rows are incomplete, five
lifecycle rows depend on blank cached allocation values, two rank cells are
malformed, and 17 rank-position groups contain duplicate ordinals. The latter
affect 35 rank entries, which remain unavailable rather than being renumbered.
Additional warnings identify ten exact-name fallbacks, four detailed score-row
choices, three portfolio-membership precedence cases, and the explicit zero reserve.
Blank score coverage is preserved as absence: six companies each have no Durability
or Compounder Quality source assessment, while 179 each have no Execution or Risk
source assessment.

| Check                                          | Result                                                                                   |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `npm run check`                                | Passed: lint, format, TypeScript/mypy, 40 Vitest, 57 pytest, contracts, production build |
| PostgreSQL integration/migration tests         | Passed, including empty-schema Alembic upgrade test                                      |
| `npm run db:migrate` and `npm run db:check`    | Passed; no metadata drift                                                                |
| Browser suite with live read-only imported API | 16 passed, 4 intentionally skipped, desktop and mobile                                   |
| Imported portfolio/universe live browser flow  | Passed on desktop and mobile                                                             |
| Final API state after browser checks           | 219 companies and one non-demo Imported Legacy Portfolio                                 |

Live browser checks separate read-only imported-data coverage from fictional-seed
and write-enabled checks. The two test-only companies created during an initial
unfiltered live run were removed together with their sole lifecycle projection and
event; final API counts and imported data reconciliation were then rechecked.

No model assumptions, valuation outputs, prices, FX, or expected returns were
imported. Company reporting currency remains unknown where the scoped workbook
does not establish it. Workbook effective dates are also unknown; importer-observed
time is not represented as the original economic observation date.

## Historical Milestone 0 verification

Recorded before Milestone 1A on 2026-10-04. At that point no Milestone 1 domain
functionality had been implemented. Its remaining local-database setup note is
superseded by the Milestone 1A record above.

### Environment and scope

Verified on Windows with Node.js 24.14.0, npm 11.9.0, Python 3.12.3, and PostgreSQL 18. The normal development setup uses the installed local PostgreSQL service via
the root `.env`; it requires no Docker installation.

The existing service on port 5432 requires administrator credentials that were not
provided. Its configuration and databases were not changed. For verification, the
installed PostgreSQL binaries initialized a separate temporary cluster under the
ignored `.cache/verification` directory on loopback port 15432, using generated
credentials and a non-superuser application role. These credentials are not
application defaults or committed artifacts.

### Checks completed

| Check                                                   | Result                                          |
| ------------------------------------------------------- | ----------------------------------------------- |
| ESLint and Ruff lint                                    | Passed                                          |
| Prettier and Ruff format checks                         | Passed                                          |
| TypeScript and strict mypy                              | Passed                                          |
| Vitest                                                  | 26 tests passed                                 |
| pytest, including real PostgreSQL integration           | 15 tests passed                                 |
| Alembic baseline upgrade on an empty database           | Passed                                          |
| Isolated-schema upgrade → downgrade → upgrade           | Passed                                          |
| Alembic metadata drift check                            | No new upgrade operations                       |
| Generated OpenAPI and TypeScript contract consistency   | Passed                                          |
| Next.js production build                                | Passed                                          |
| Chromium desktop and mobile browser cases               | 8 passed, including two live API/database cases |
| Desktop/mobile screenshots and keyboard skip navigation | Reviewed; no horizontal overflow                |
| npm production dependency audit                         | Zero reported vulnerabilities                   |

Browser coverage includes the empty workspace, pending connection, unavailable
API, retry recovery, outdated schema, and real browser → Next.js proxy → FastAPI →
PostgreSQL connectivity. Mocked health results exist only in tests. The running
application uses real API responses.

### Clean-install verification

This supplied workspace has no `.git` metadata, so verification uses a fresh
source-only copy rather than claiming a Git clone was tested. The copy excludes
installed dependencies, virtual environments, caches, `.env`, and workbook
artifacts. Workbook artifacts are unnecessary for Milestone 0 startup.

`npm ci` and `npm run setup` completed from that copy, including creation of a new
Python tooling environment, locked dependency installation, and `.env` creation.
After configuring temporary credentials, `npm run db:migrate` and
`npm run db:check` passed against a newly created database owned by the application
role. The committed lockfiles and repository-relative settings were used.

The full `npm run check` also passed in the fresh copy. `npm run dev` successfully
started both reload servers there; the application, API liveness/readiness, and
frontend health proxy returned HTTP 200, with database connected and schema
current. Ctrl+C stopped both development servers. The temporary PostgreSQL
instance is stopped after verification.

### Remaining local setup and dependency issue

To use the permanent local PostgreSQL service, run the exact one-time `psql`
command in the root README, set the application password in `.env`, then run
`npm run db:migrate` and `npm run dev`. The separate temporary verification cluster
does not configure your normal database credentials.

The complete npm audit reports five high-severity entries from one development
dependency chain: Next.js ESLint tooling → fast-glob → micromatch → braces. The
[braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) has no patched
compatible braces release available in the registry at verification time. The
production-only audit reports zero vulnerabilities. ESLint 9 also emits an
end-of-support notice; the current Next.js React lint plugin's peer range does not
yet accept ESLint 10. Keep these development dependencies under review when their
upstream compatible releases become available.

## Milestone 2A ? 2026-10-05

Canonical listing-specific market facts and factual portfolio valuation were
implemented and applied to the local PostgreSQL database. Alembic revision
`01773da3b70f` is current. The repeat import returned `ALREADY_APPLIED` for the same
workbook digest and did not duplicate observations.

| Check                                             | Result                                                                                                          |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Full `npm run check`                              | Passed: lint, formatting, TypeScript/mypy, Vitest, pytest, contract consistency and production build            |
| Vitest                                            | 39 passed                                                                                                       |
| pytest with dedicated PostgreSQL `_test` database | 62 passed; includes clean-schema migrations and import reconciliation                                           |
| Explicit integration selection                    | 24 passed; no skips                                                                                             |
| Browser E2E, desktop and mobile                   | 18 read-only/imported-data passed (4 write cases skipped); 4 demo/write cases passed on an isolated test schema |
| `npm run db:check` on application database        | No new upgrade operations                                                                                       |
| Live API read-only smoke                          | Ready/current schema; 219 universe companies and 89 listing-specific market views                               |
| Workbook metrics                                  | 852 numeric values and 142 trend/correction states reconciled with zero differences                             |
| Import repeatability                              | Second apply reported `ALREADY_APPLIED`; persisted counts remained unchanged                                    |

The import stored 65,535 daily observations, 71 price-regime snapshots and two
corporate actions across 88 matched listing identities. The machine-readable source
and persistence reconciliation is in
[`reconciliation/market-data-2026-10-05.json`](reconciliation/market-data-2026-10-05.json).
The legacy snapshot has 65,473 `PASS`, one `PASS_VERIFIED_FALLBACK` and 61
`UNSPECIFIED` accepted observations. It uses the historical Google Finance and Yahoo
Japan provider labels as provenance; the application does not depend on either at
runtime.

Live market views showed 71 fresh listing quotes at verification time. The imported
portfolio remains `INCOMPLETE_PRICE_COVERAGE` with 21 explicit coverage gaps; the
base-currency total and current weights remain unavailable. The Market Data workbook
has no dated FX series and does not cover two held listings, so this is the correct
missing-data result. A desktop/mobile browser check confirmed imported portfolio and
universe views, price history and the distinct unquoted TSM ADR listing. The four
demo-seed and explicit-write browser cases also passed against a disposable PostgreSQL
schema; that schema was removed when its fixture server stopped.

## Milestone 3A — Canonical UFCF DCF — 2026-10-05

The application now stores accepted, immutable revisions for the `P-GOOGL`
10-Year Secular Growth Fade UFCF DCF methodology. Its deterministic outputs and
representative projections reconcile to frozen workbook inputs/caches within
`1e-7`. A real current model was not seeded from the test fixture. The application
database was migrated to Alembic head; schema drift check reports no operations.

| Check                                       | Result                                                                                                                        |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Full `npm run check`                        | Passed: lint, formatting, TypeScript/mypy, Vitest, pytest, contract consistency and production build                          |
| Vitest                                      | 47 passed                                                                                                                     |
| pytest with PostgreSQL integration          | 73 passed; includes clean-schema Alembic upgrade/downgrade/upgrade                                                            |
| P-GOOGL DCF output/projection parity        | Passed at `1e-7` for Bear/Base/Bull, Weighted FV/Upside, Expected IRR, Hurdle, Expected Excess and representative UFCF values |
| Append-only model API integration           | Passed: 30 projections per revision, revision 2 appended, revision 1 unchanged, stale replay returns 409                      |
| Chromium desktop/mobile E2E                 | 16 passed; 10 live-database cases intentionally skipped                                                                       |
| OpenAPI / TypeScript contracts              | Current                                                                                                                       |
| Production build                            | Passed                                                                                                                        |
| `npm run db:migrate` and `npm run db:check` | Passed; no schema drift                                                                                                       |

The Company Explorer now separates native DCF state from imported model-output
snapshots and provides a basic revision form. Other workbook calculation methods,
including SOTP and financial-sector models, remain external or output-only. The
UFCF source's enterprise-cash-flow IRR semantics remain method-specific; see
[`financial-models.md`](financial-models.md) before adding another method.

## Milestone 3D — Heterogeneous native model archetypes — 2026-10-05

Native deterministic calculation and editing now cover three selected workbook
references: `P-GOOGL` UFCF DCF, `W-TOST` owner cash flow and `W-HDFC` residual
income. The two new methods reconcile normalized outputs and representative
projections from frozen workbook inputs/caches to `1e-7`. Their relational inputs
and projections remain method-specific while revision ancestry, provenance and
normalized output history are shared. These are parity fixtures, not migrated
production model assumptions.

The workbook population has 116 model tabs and the imported universe has 219
companies. The three parity references represent 3 tabs (2.6%) and 3 issuers
(1.4%). No legacy model inputs have been batch-imported into the native model
domain; these percentages describe fixture references, not migrated issuer coverage.

| Check                                | Result                                                                                                               |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| Full `npm run check`                 | Passed: lint, format, TypeScript/mypy, Vitest, pytest, contracts and production build                                |
| Vitest                               | 59 passed                                                                                                            |
| pytest with PostgreSQL integration   | 81 passed; fresh isolated schemas are upgraded to Alembic head                                                       |
| Workbook formula/output parity       | P-GOOGL, W-TOST and W-HDFC outputs plus representative projections pass `1e-7`                                       |
| Additional method revision/API tests | Creation, append-only history, missing-price nulls, v2 Sheets round trip, idempotence and stale-base conflict passed |
| Chromium desktop/mobile E2E          | 18 passed; 10 live-database cases skipped because they require an explicit imported/demo database                    |
| OpenAPI / TypeScript contracts       | Current                                                                                                              |

The build command runs frontend type generation and `tsc --noEmit` before the
production build. Next's duplicate process-based type worker is disabled for
restricted Windows environments; the full check still runs strict typechecking
separately before building. The build limits its static worker pool to one thread.

## Canonical filings and source documents — 2026-10-05

The SEC EDGAR submissions adapter and issuer-reference API are implemented with
append-only source-document metadata, compressed raw submissions receipts,
idempotent import, amendment linking and explicit quality checks. Filing content is
not downloaded. The current application database has zero reviewed SEC CIK
mappings and zero source-document rows; no live company coverage is claimed.

| Check                                      | Result                                                                                                                           |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Full `npm run check`                       | Passed: lint, formatting, TypeScript/mypy, Vitest, pytest, contract consistency and production build                             |
| Vitest                                     | 66 passed                                                                                                                        |
| pytest with PostgreSQL integration         | 134 passed, including SEC normalization, idempotent import, amendments, as-of/known-at query behavior and append-only protection |
| Chromium desktop/mobile E2E                | 18 passed; 10 live-database cases skipped because they require a separate imported/demo database                                 |
| PostgreSQL integration suite               | 37 passed on the suite run; the one timed-out legacy import case passed when retried alone                                       |
| Alembic upgrade/downgrade and schema check | Passed; `npm run db:migrate` and `npm run db:check` report no drift                                                              |
| OpenAPI / TypeScript contracts             | Current                                                                                                                          |

The integration subset's first final-schema run hit its 5-second test database
statement timeout during the unrelated bulk legacy price import. Its isolated
retry passed in 61.92 seconds; the source-document migration test passed in the
suite run. The full `npm run check` backend suite also passed all 134 tests.

Coverage is ready for explicitly mapped SEC issuers only. The browser/API surface
shows empty and unmapped states honestly. SEC filing bodies and issuer PDFs remain
on their respective primary sources; see [`source-documents.md`](source-documents.md)
for the source terms, request-rate policy and retention boundary.
