# Controlled workbook import

The application provides a local, repeatable importer for the already implemented
identity, portfolio, score, and ranking domains. It reads the committed workbook
snapshots as migration evidence; it does not connect to Google Sheets or run during
application startup. The importer reads cached OOXML values and never evaluates
spreadsheet formulas.

This importer remains a migration adapter, not an external-provider implementation.
Future provider ingestion uses the raw-record and normalization boundary described
in [external-data architecture](external-data-architecture.md); workbook cell
coordinates will not become canonical domain fields.

## Run it

After configuring local PostgreSQL and applying Alembic migrations:

```sh
npm run db:import-workbook -- --report import-report.json
```

This is a dry run. It writes a JSON report containing the source hashes, mapped
record counts, score/rank coverage, and every unresolved source issue. Review the
report before applying:

```sh
npm run db:import-workbook -- --apply --replace-demo --report import-report.json
```

`--replace-demo` is only for a database containing the explicitly marked fictional
seed. It refuses non-demo portfolios, non-seed authored histories, or prior import
batches. Without `--replace-demo`, the importer requires an empty universe and
portfolio. No existing real data is deleted or reconciled by changing its values.

The workbook pair is identified by SHA-256. Reapplying the same pair is a no-op and
returns the saved import report. A changed workbook pair creates a new import batch;
holdings snapshots, score assessments, lifecycle changes, targets, and rank runs are
compared with current state and appended only under their domain rules. Ranking runs
are always preserved as source observations, never recalculated. Supply
`--observed-at` only when an explicit timezone-aware observation timestamp is known.
Otherwise the importer records its actual run time as the time it observed the file;
it does not claim that time is the workbook's original effective date.

## Source mapping

| Domain                  | Source and treatment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Companies               | `Portfolio_Watchlist.xlsx`, `Universe Registry` ticker/name/research bucket. A blank registry name is filled only by an exact ticker match in another scoped source table and reported as a warning. Company reporting currency is left null.                                                                                                                                                                                                                                                                                                                                                               |
| Securities and listings | `Market Data.xlsx`, `Listings` rows marked `READY`, with exact canonical ticker, `venue:ticker`, exchange, quote currency, and supported instrument basis. Unsupported/incomplete rows are reported and omitted. Current holding SPYY is mapped from its exact `Price Feed` venue/currency identity and represented as a standalone ETF. TSM's local ordinary (`TPE:2330`, TWD) comes from `Listings`; the held ADR (`NYSE:TSM`, USD) is linked to that same company as a separate ADR security using the exact `TSM-ADR` holding/listing key and source underlying relationship. No ADR ratio is inferred. |
| Lifecycle               | Universe Registry explicit Research Bucket plus cached current/target allocation membership, following its documented formula precedence. Positive current/target membership maps to Portfolio and any competing bucket is reported. A blank cached weight is not zero; where it prevents a decision, lifecycle remains unresolved.                                                                                                                                                                                                                                                                         |
| Current holdings        | `Current Holdings` stock and ETF share quantities plus native-currency `Cash Component` rows. The aggregate Cash row is excluded to avoid double counting. Prices, market values, and workbook weight formulas are not imported. The portfolio base currency is read from its explicit summary label. An unresolved held identity makes the snapshot partial; currency values are never converted.                                                                                                                                                                                                          |
| Strategic targets       | Company rows in `Target Architecture`, copied as exact fractional weights including explicit zero. No normalization or lifecycle reconciliation is performed. The combined `RESERVE` row is not a company target; a non-zero reserve blocks target import because the current target model cannot represent its cash/ETF split.                                                                                                                                                                                                                                                                             |
| Canonical scores        | `10Y Durability!G` and `Compounder Quality!G` (0–5); per-company `Execution Score` and `Risk Score` rows (1–5). Rationales and source URLs are retained where present. Blank values do not become score records or zero; coverage is shown as “no assessment in snapshot.” Invalid nonblank score cells become null `INVALID` assessments with a reason. Duplicate summary/detail rows are resolved only where the detailed row has more evidence; conflicts are reported.                                                                                                                                  |
| Ranks                   | Cached Universe Registry Portfolio Rank (L), Watchlist Rank (M), and Research Rank (J) are copied as source observations for their documented populations. Unique positive integer positions are preserved; blanks, malformed values, duplicate positions, and unresolved membership remain explicit unavailable/excluded states. The workbook has 17 shared cached positions across Watchlist/Research entries despite documenting ticker tie-breaks; all affected entries are marked unavailable and no ordinal is reassigned. The application does not recalculate workbook ranks.                       |

These are source-to-domain mappings, not a model of workbook tabs or cell geometry.
See [workbook-map.md](workbook-map.md) for the focused workbook semantics and
[domain-model.md](domain-model.md) for canonical relational ownership.

## Reconciliation and limits

After an applied import, the saved report compares each mapped company, security and
listing identity, resolved lifecycle, current holding snapshot, accepted target,
score observation, and each cached ranking run against the stored relational state.
The report distinguishes a stored-state mismatch from unresolved source rows and
includes both expected/matched counts and source coverage. `MATCHED` means stored
values match the parsed source for the compared domains. `RECONCILED_WITH_SOURCE_GAPS`
means compared values match but some source mappings or inputs remain unresolved.

Current snapshot notes:

- The workbook files do not establish an effective date. Effective time is the
  importer-observed timestamp unless explicitly supplied.
- A model currency column is not assumed to be company reporting currency.
- Unsupported listing rows, blank cached allocations, invalid rank cells, and blank
  scores are not repaired or backfilled by the importer.
- Legacy score migration records current observations only; duplicate rows are not
  fabricated into assessment history.
- Cached rank positions are retained as workbook outputs; their models and source
  inputs remain unmigrated, so numeric rank generation is still disabled. The source
  currently has 17 duplicate rank-position groups plus two malformed rank cells;
  these remain unavailable under the unique-ordinal contract.
- TSM's portfolio holding is specifically the USD NYSE ADR. The TWD TPE ordinary
  listing remains a separate security/listing linked to the same company; holdings
  are never redirected based only on issuer ticker.
- No prices, FX, ADR conversion factors, cost basis, financial assumptions, DCF or
  other valuation output, Expected IRR, or model history is imported.

The main UI reads PostgreSQL. After applying the import, the Portfolio and Universe
views therefore use the imported data instead of the fictional development seed.
The opt-in seed remains for isolated empty development/test databases.

Live browser checks use `E2E_LIVE_API=1` for read-only connectivity and imported-data
flows. The demo-seed UI check requires `E2E_DEMO_SEED=1`, and the test that writes a
fixture company and lifecycle record requires `E2E_ALLOW_WRITES=1`. Point those
seed-dependent or write-enabled checks only at their intended disposable test API;
they are separate from read-only verification of the imported local database.

## Applied snapshot reconciliation (2026-10-04)

The committed pair above was applied with digest
`d0f8137ef9d7441fa78ec1eda4fae5603c255efe651f5f14cbd3042aedb3eac5`. The persisted
state matched every imported record: companies 219/219, securities/listings 90/90,
resolved lifecycle 214/214, holding/cash rows 24/24, company targets 16/16, scores
506/506, and rank-run entries 657/657. The holdings snapshot is `COMPLETE` and the
company target sum is exactly `1.00`. The overall state is
`RECONCILED_WITH_SOURCE_GAPS`, with zero persisted-state mismatches and 48 unresolved
source errors.

The score snapshot contains 213 10Y Durability and 213 Compounder Quality
assessments, each with six companies lacking a source assessment; Execution and Risk
each contain 40 assessments, with 179 companies lacking a source assessment. These
absences are report coverage, not fabricated `MISSING` events. Cached rank counts are
Portfolio 21 ranked / 5 unavailable, Watchlist 57 / 17, and Research 72 / 26; all
other entries are explicitly not eligible. Source issue groups comprise 13 listing
statuses needing mapping, 11 incomplete READY listing rows, five unresolved lifecycle
rows caused by blank allocation caches, two malformed rank cells, and 17 duplicate
rank-position groups. Warnings also record ten exact-name fallbacks, four detailed
score-row choices, three portfolio-membership precedence cases, and the zero
RESERVE row.

The workbook remains the owner of unmigrated listing mappings, original observation
dates it never records, financial-model assumptions and outputs, valuation/Expected
IRR inputs, prices, FX, and calculated ranking methodology. Imported rank values are
the cached source positions only; they do not mean ranking calculations have been
migrated or accepted for parity.

## Separate Milestone 2A price import

`db:import-workbook` remains scoped to companies, listings, lifecycle, holdings,
targets, scores and cached rank observations. It deliberately does not import
prices. Listing-aware historical observations, verified corporate actions and
price-regime snapshots are handled by the separate
[`db:import-market-data`](market-data.md) command. That importer has a separate
content hash, exact venue/ticker/currency/provider-symbol crosswalk, source-quality
report and append-only market batch. It does not evaluate spreadsheet formulas,
connect to Google Sheets or import FX, model assumptions, valuation outputs or
expected returns.
