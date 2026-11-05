# Minimal Google Sheets Portfolio Bootstrap

## Purpose and scope

This is a bounded vertical slice for the initial canonical portfolio baseline. It
reads the configured native Google portfolio spreadsheet directly through the
existing service-account reader, freezes a content-addressed source snapshot, and
projects only the source fields needed for company identity, held listing identity,
holdings/cash, and strategic targets into the existing canonical import plan.

The path does not use an XLSX export or its formula caches. It does not import
lifecycle, scores, research priority, rankings, model inputs or outputs, market
observations, fundamentals, consensus, theses, or research history. Those domains
remain under their existing workflows.

## Source contracts and ownership

The reader requires these exact tabs and bounded source ranges:

| Sheet                 | Fields consumed                                                                                                                 | Contract use                                                                                                         |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `Universe Registry`   | A ticker, B company name, from row 4                                                                                            | Company identity; row 4 header is checked and data starts at row 5.                                                  |
| `Current Holdings`    | A row kind, B portfolio ticker, D exact source listing, E numeric quantity/balance, G cash currency; L4 portfolio base currency | Stock/ETF holdings and currency-specific cash; row 4 headers are checked.                                            |
| `Target Architecture` | A ticker, D numeric target weight; P3 control total                                                                             | Strategic target values; row 4 headers are checked; zero and blank are distinct.                                     |
| `Price Feed`          | A/B/C/D/H for the explicit supported AUX identity rows                                                                          | Only the existing documented SPYY ETF and TSM ADR mappings are considered. No general ticker inference is performed. |

The Market Data workbook must already have an explicitly approved schema snapshot.
Its `Listings` tab is used as the exact venue, ticker, currency, instrument, and
readiness identity source. Held positions must resolve uniquely to a READY listing
or to one of the supported explicit AUX mappings. A source ticker alone never
selects a listing.

The existing SPYY AUX mapping has one reviewed literal identity: standalone ETF
ISIN `IE00B44Z5B48`, WKN `A1JJTC`, Xetra/Deutsche Börse listing `ETR:SPYY`,
trading currency EUR. The workbook's A-column AUX classification may be a formula
only for that exact identity and an ETF holding; its B/C/D/H identity cells must
remain literal and match the reviewed key, listing and currency. The snapshot's
formula and effective classification remain recorded, and the listing source
reference includes the reviewed identity version. The security has no fabricated
company. The separate USD share-class currency is not substituted for the EUR
listing currency; the canonical security schema does not store ISIN or WKN. Provider
symbols require separate review: the existing Yahoo crosswalk and the issuer's
current Reuters identifier are distinct source claims.
[Deutsche Börse](https://live.deutsche-boerse.com/en/etf/state-street-spdr-msci-all-country-world-ucits-etf-acc)
and [State Street](https://www.ssga.com/at/en_gb/intermediary/etfs/state-street-spdr-msci-all-country-world-ucits-etf-acc-spyy-gy)
provide security and listing evidence. All other derived AUX identity cells and
unreviewed listing variants remain blocked.

The workbook remains authoritative for the values captured by this contract.
Google Sheets API effective values are read directly. Blank, formula-empty,
empty-string, zero, numeric, text, boolean, and error states are preserved
separately. Numeric JSON tokens are decoded as `Decimal` and serialized as exact
decimal strings. Required identity and quantity type checks remain explicit.

## Capture and consistency semantics

The reader uses the existing Google service-account configuration and read-only
Drive and Sheets scopes. Configure `GOOGLE_SHEETS_SPREADSHEET_ID` and
`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE`; if
`GOOGLE_DRIVE_PORTFOLIO_WORKBOOK_FILE_ID` is also set, it must identify the same
spreadsheet. Grant the service account Viewer access only. The reader never writes
to Google Sheets.

Capture verifies Drive identity and metadata and worksheet structure before and
after two complete reads of every contract range. It fails closed on changed
metadata/structure/values, an incomplete API range, duplicate coordinates,
malformed values, or configured row/cell/response limits. Google Sheets does not
provide a transactionally consistent cross-request snapshot: the artifact records
an observed consistent state established by the metadata and two-read fence, not
a guaranteed atomic snapshot.

The reader uses `spreadsheets.get` with declared `ranges` and `includeGridData`,
not `values.batchGet`. GridData response JSON may omit zero-valued `startRow` or
`startColumn` fields and may omit dimension metadata or trailing empty row/cell
entries. The parser treats omitted zero origins as zero, reconstructs blanks only
inside a returned requested-range envelope, and validates metadata arrays if they
are present. A missing requested grid, malformed/partial metadata, malformed cell
data, changing source between sweeps, or a populated record missing a required
field still blocks the import. Capture failures now retain the declared A1 range
and sanitized GridData validation reason in the private run report; the report
does not include workbook values or credentials.

The immutable JSON bundle, manifest, and any later preview report are written to
the existing private SnapshotStore outside the repository and cloud-synced paths.
The raw artifact SHA-256 is the deterministic replay identity; the manifest has
its own integrity digest. Snapshot path, artifact hash, source identity, captured
metadata, structure fingerprint, range contract, and full expected coordinate
coverage are validated again on replay. Never copy snapshots or reports into Git,
CI artifacts, or a public issue.

## Projection and exceptions

The projection reuses `legacy_import.ImportPlan` and its existing canonical import
transaction and receipt behavior. It does not add a second database model or import
implementation. Company names and tickers must be unique and well-typed. Held
listing identities are reconciled against the accepted Market Data snapshot, with
only the explicit supported AUX rules. Holdings and cash use the established
decimal scale and source completeness semantics. A missing quantity is not zero;
when the existing importer permits an explicitly PARTIAL snapshot, that state and
the source warning remain visible in the preview. Target control totals and target
precision are checked by the existing importer; targets are not normalized.

Optional invalid universe rows may be listed as explicit exclusions. Held identity,
target, currency, numeric type, and contract errors are blocking. A positive
`RESERVE` target is not translated into a company allocation; the existing target
contract reports its unsupported semantics. Company identities outside the held and
targeted population that lack a READY Market Data listing are reported separately as
optional listing gaps; their company identities are retained, and no listing is
invented. No lifecycle, score, rank, model, or investment decision is inferred or
written.

The preview report contains source run IDs and hashes, canonical plan counts,
identity reconciliation, warnings/exclusions, target-bound input hash, and a
read-only database diff. Reports are private because source row references and
portfolio composition are sensitive.

## Operator procedure (Windows PowerShell)

Open a protected local PowerShell session with the app's existing environment
configuration loaded. Do not print credentials, service-account content, full
database URLs, or private workbook values. Keep the private store under
`%LOCALAPPDATA%` and verify it is outside the repository and OneDrive.

```powershell
$snapshotStore = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
```

### 1. Capture the authoritative native Sheet

This is a read-only Google API operation that creates a private local snapshot. It
is separate from database preview and does not require or use a database target.

```powershell
npm run db:bootstrap-sheets-minimal -- capture --store $snapshotStore --confirm-read-only-source-capture
```

Record the returned run ID and SHA-256 in the private operator record. Inspect the
private manifest and acquisition diagnostics locally; do not paste portfolio
values or source identifiers into Git or task output. A captured run is
`CAPTURED_REVIEW_REQUIRED`; capture does not approve the source or authorize import.

### 2. Preview the exact frozen source pair

The Market Data source must first have an accepted schema run. Use its accepted run
ID and the exact Sheets capture run/hash from step 1. Configure the existing
database target variables for the exact environment and target. Preview requires
the normal read-only target verifier and the current checkout's Alembic head; it
does not require production-write authorization and executes no PostgreSQL DML,
DDL, sequence changes, receipts, or provider calls.

```powershell
$sheetsRun = '<captured Sheets run id>'
$sheetsSha256 = '<captured Sheets artifact sha256>'
$marketRun = '<accepted Market Data snapshot run id>'

npm run db:bootstrap-sheets-minimal -- preview `
  --store $snapshotStore `
  --sheets-run $sheetsRun `
  --sheets-sha256 $sheetsSha256 `
  --market-run $marketRun `
  --target-environment production
```

Review the private report's identity reconciliation, explicit exclusions, exact
planned record counts, database diff, and target-bound `input_sha256`. Do not
proceed if any blocking issue is present, any held listing is unresolved, the
source has changed, or the target/schema preflight fails.

At implementation handoff, the repository Alembic head is
`c17a0b9d4e62`, while the last reported Neon production head is
`6c2eaf0b8147`. The preview's exact-head verifier will therefore stop if Neon
still has the older head. Do not migrate production as part of this procedure.
Resolve the release/schema mismatch through a separately reviewed migration step
before requesting a production preview. No live Google or Neon request was
performed while implementing this vertical slice.

### 3. Apply boundary (not authorized by this implementation task)

Application is a separate, explicit operator action. It requires the source and
target-bound preview hash to be reviewed, and the exact same source pair and target
to be used. The CLI requires both hash flags to equal the newly recomputed
`input_sha256`, plus an explicit minimal-contract review flag. The normal database
write-target guard remains in force: a production apply additionally requires
temporary `DATABASE_PRODUCTION_WRITES_AUTHORIZED=true`, live Neon identity checks,
database privilege checks, and interactive typing of the exact target phrase
printed by that guard. Do not persist the authorization setting. Never invoke
`apply` or set production authorization without separate approval for the exact
source hashes, preview, target, and recovery point.

The interface, when separately authorized, is:

```powershell
npm run db:bootstrap-sheets-minimal -- apply `
  --store $snapshotStore `
  --sheets-run $sheetsRun `
  --sheets-sha256 $sheetsSha256 `
  --market-run $marketRun `
  --target-environment production `
  --expected-input-sha256 '<reviewed target-bound input sha256>' `
  --approve-input-sha256 '<same reviewed target-bound input sha256>' `
  --confirm-minimal-sheets-contract-reviewed
```

This document and the current task do not authorize that command. The command
rechecks the exact target guard and canonical state inside the transaction, refuses
unrelated non-empty canonical state, and uses the existing append-only bootstrap
receipt plus legacy import transaction. An exact replay returns `ALREADY_APPLIED`
only when the stored projection still matches its receipt; otherwise it stops for
reconciliation. Accepted source changes require a new capture and new preview.

## Verification and present readiness

The implementation has synthetic service-account/API response fixtures and
isolated PostgreSQL tests that create a unique temporary schema in the explicit
`TEST_DATABASE_URL` database ending `_test`. They exercise capture stability,
source mutation/truncation/errors, exact decimal and missing/zero states, market
listing reconciliation, a no-write preview, transaction rollback, apply, and
read-only replay. They do not use production data or call live Google/Neon.

Implementation readiness is not source or production readiness. No live snapshot,
accepted Market Data schema, source row count, held-listing count, production diff,
or production apply is claimed by this implementation. The real capture and
preview must be run and reviewed by the operator. Production apply remains outside
scope and requires its own explicit authorization.
