# Workbook Bootstrap Readiness Ledger

> Historical evidence for the recorded milestone/date. Current production scope is in [production-canonical-baseline.md](production-canonical-baseline.md), and current execution is in [ROADMAP.md](../ROADMAP.md). Retain the safety and provenance details for the workflows they describe.

This document records the sanitized integration status for Recovery Tasks R1 and
R2. It contains no workbook values, private source identifiers, acquisition
manifests, or content hashes.

## Integrated implementation

R1's importer-scoped source-fidelity implementation is present in commit
`4931b18` and is included in the R3 baseline. It adds a versioned semantic
fingerprint for importer-owned portfolio fields, preserves raw artifact hashing,
and represents blank, zero, invalid, formula-cache-empty, and formula-error
states separately. Numeric values are normalized with `Decimal`; source type and
formula presence are included in the semantic projection. A read-only live Sheets
comparison is available for bounded, allowlisted ranges and fails closed when
source revision or repeated effective values are unstable.

R2 made no repository or database changes. Its local, read-only review found the
Market Data workbook structurally suitable for an explicit schema-baseline
decision: all five required tabs and mapped headers are present, the frozen
artifact hash and schema fingerprint verify, and the required tabs contain no
formulas or formula errors. The parser ignores hidden cache and unrelated tabs.
This structural result is independent of the Portfolio workbook's formula-value
fidelity review.

## Dependency ledger

| Gate                       | What the R1/R2 result establishes                                                                                                                                  | Still required                                                                                                                                                                                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Portfolio source fidelity  | The semantic fingerprint and bounded comparison implementation are present and testable. Missing, zero, invalid, cached-formula, and error states remain distinct. | Reacquire a current frozen Portfolio snapshot, run the read-only live comparison in the authorized Windows environment, and classify the previously reported importer-relevant mismatches. The historical snapshot predates semantic fingerprint v2.                                 |
| Market Data schema         | The reviewed frozen snapshot has the expected structure and passes the local hash, fingerprint, header, type, and required-tab checks.                             | An operator must explicitly accept the schema baseline for the reviewed snapshot. A source revision ID was unavailable; the acquisition has a modification timestamp, but current Drive state was not rechecked during R2.                                                           |
| Market Data rows           | The source values can be parsed exactly and reconciled against the importer rules without changing identity or currency semantics.                                 | Resolve or explicitly exclude the active unsupported/unmapped listing cohort; review provider-symbol disagreements and the numeric regime identity; account for held listings not represented in the Market Data Listings tab; review source-asserted corporate-action verification. |
| Combined canonical preview | The read-only preview implementation and its target safeguards are present.                                                                                        | Use current, reviewed snapshots for both workbooks; complete source-value and row-mapping reviews; accept each applicable schema explicitly; then run the preview against an independently verified target. No import is implied by a passing preview.                               |
| Production bootstrap       | No production write or authorization was performed.                                                                                                                | Separate explicit production authorization and the guarded interactive target confirmation remain mandatory after preview review.                                                                                                                                                    |

## Sanitized R2 observations

- The workbook has 112 listing rows: 109 marked READY and 3 marked NEEDS MAPPING.
- The source universe has 219 distinct company identities. Of 92 active Portfolio
  and Watchlist identities, 81 have importer-ready Market Data mappings; 11 do
  not. These are row-level identity/method support issues, not structural schema
  failures.
- All 22 held instruments resolve across the two source workbooks. Twenty are
  present in the Market Data Listings tab; two rely on explicit Portfolio
  workbook mappings and therefore need separate Market Data coverage before
  this workbook alone can supply them.
- Daily Prices has 75,112 rows, with 75,101 eligible under current importer
  rules. No duplicate listing/session keys, nonpositive closes, negative volume,
  or listing/price-currency mismatches were found. The remaining exclusions,
  unavailable quality values, and date gaps remain explicit; they are not
  converted to observations or inferred from calendar assumptions.
- Daily market dates are stored as date-only sessions. Some source date cells
  include a time component; the importer intentionally discards that component
  and does not claim an intraday observation time.
- Price Regime has 92 rows. Comparable derived numeric metrics and trend states
  reconciled within the existing tolerance; insufficient-history values and
  data-check rows remain unavailable or flagged.
- The checked-in Yahoo crosswalk is advisory for this review. Provider-symbol
  differences require explicit reconciliation before provider ingestion; they
  do not justify substituting a listing or rewriting the workbook mapping.
- The exact private acquisition snapshots remain outside the repository and are
  byte-different from the older tracked reference workbook artifacts. No private
  snapshot, manifest, report, or hash is included in this baseline.

## Verification

- Focused source-acquisition, source-fidelity, importer, market-data, model-output,
  and database-guard unit tests: **115 passed, 1 skipped** (6 integration tests
  deselected by the unit-test filter).
- Full API integration selection: **113 passed, 4 skipped**. Two role-privilege
  tests require `CREATEROLE`; two PostgreSQL migration tests require PostgreSQL 18
  client tools or the configured tools container. They now skip with explicit
  prerequisite messages instead of failing setup.
- Repository contract check, repository source-data policy, Ruff checks and format
  checks passed.

## Operational safety

At integration time, effective settings report production writes disabled,
cloud ingestion disabled, recurring operations disabled, Google Sheets polling
at zero, and FMP consensus ingestion disabled. R1/R2 did not connect to Neon, edit
Google Sheets, ingest provider data, accept a schema, or enable a worker. The
separate uncommitted workbook-sync work was preserved outside this baseline.

The R2 structural GO is not an import-data GO. The unresolved R1 Portfolio
formula comparison and the R2 listing/source exceptions remain explicit blockers
for the combined canonical bootstrap preview.
