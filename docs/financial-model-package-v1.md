# Financial Model Package v1 — P-GOOGL Proof of Concept

## Purpose and scope

`financial-model-package-v1` is a strict, replayable transport contract for one
existing Google Sheets model: P-GOOGL, Alphabet common stock on NASDAQ, listed
and modeled in USD. It is deliberately not a universal workbook parser. The
captured values come directly from Google Sheets `effectiveValue` and
`userEnteredValue`; XLSX formula caches are not read by this exporter.

PostgreSQL remains canonical for accepted model revisions. A captured package
is an unaccepted proposal. Capture, inspect, validate and preview do not accept
a model. Acceptance is a separate explicitly confirmed operation behind the
existing database write-target guard.

## Contract contents

The package has five independently typed parts:

- `identity`: source model key; company, exact security/listing, currency,
  methodology/version, economic cash-flow basis, enterprise perspective and
  return comparability.
- `inputs`: the existing `DcfCalculationInput` contract, including base
  assumptions, Bear/Base/Bull scenario probabilities and annual assumptions.
- `published_outputs`: source-published scenario fair values, weighted value
  and upside, legacy return stream, hurdle/excess, and 30 projection values.
- `revision`: base canonical revision, content-derived external revision ID,
  normalized input digest and explicit unaccepted state. The source effective
  date, author and authored time remain unknown unless a later contract can
  prove them.
- `source` and `source_cells`: Google Drive metadata, hashed spreadsheet
  identity, exact declared ranges, typed source values, original formulas,
  effective values, number formats and explicit blank/error/zero states.
- `probability_normalization`: absent when the exact source probability sum is
  one; otherwise records the bounded Base-residual normalization and both raw
  and canonical triples.

Unknown fields, methods, identities, range sets, missing cells, malformed
numbers and unsupported value types fail schema validation. Number values are
stored as decimal strings in canonical JSON. Blank, empty text, formula-empty,
zero and error are distinct.

## Declared source scope

Only these 17 P-GOOGL ranges are captured:

| Range                                 | Use                                                   |
| ------------------------------------- | ----------------------------------------------------- |
| `B4`                                  | Original legacy reference price, parity evidence only |
| `B12`                                 | Source reference                                      |
| `B15`                                 | Model currency declaration                            |
| `B17:B24`                             | Base DCF assumptions                                  |
| `E16:S22`                             | Bear/Base/Bull years 1–5 assumptions                  |
| `E24:S24`                             | Scenario year-10 UFCF growth assumptions              |
| `B205:D205`                           | Bear/Base/Bull terminal growth assumptions            |
| `AO4:AO8`                             | Scenario probabilities and published weighted outputs |
| `L202:N202`                           | Published Bear/Base/Bull per-share fair values        |
| `C40:G40`, `C60:G60`, `C80:G80`       | Published years 1–5 projections by scenario           |
| `G202:G206`, `H202:H206`, `I202:I206` | Published years 6–10 UFCF by scenario                 |
| `P212:Z212`                           | Published legacy enterprise-return cash-flow stream   |
| `AA212:AC212`                         | Published legacy Expected IRR, hurdle and excess      |

The B4 quote has no trustworthy effective timestamp and is never imported as
market data. This model's legacy return is `UFCF_ENTERPRISE_IRR` against
implied enterprise cost. It remains explicitly enterprise-based and is not
represented as canonical shareholder cash-flow IRR or as directly comparable
to shareholder-return methods.

## Source consistency and immutable storage

The exporter confirms exact native-spreadsheet identity, reads the P-GOOGL tab
structure, reads the declared ranges twice, then rechecks tab structure and
Drive metadata. Metadata, structure, formulas and typed values must match
across the full window. Responses and requests are bounded by the existing
read-only Sheets reader plus a fixed package range/cell/request budget. Any
failed range, incomplete grid, changed metadata, changed formula/value or
invalid source identity stops capture.

Google Sheets does not provide a transactionally consistent multi-range
snapshot. A successful package therefore means an **observed consistent state
across two reads**, not a transactional snapshot. The package blob is
content-addressed by SHA-256; capture manifests are append-only and record
source metadata, capture time and the payload hash. Repeated captures with
identical package contents have identical payload hashes. Private blobs and
reports are stored by default under the operator's local
`%LOCALAPPDATA%\PortfolioResearch\workbook-snapshots` directory and must not
be copied to Git, CI or cloud-synced directories.

Preview and any later acceptance load the same immutable package blob and
require its hash. The native mapper validates source-cell-to-input
reconstruction, input digest, exact company/listing identity and the existing
methodology. It recalculates with the existing deterministic DCF engine and
compares all 30 projections and 22 normalized output/return checks against the
approved P-GOOGL parity fixture. A mismatch remains a blocking exception.

## Read-only operator workflow (Windows PowerShell)

The strict schema can be emitted without contacting Google or a database:

```powershell
npm run db:financial-model-package -- schema
```

If capture reports that Bear, Base and Bull probabilities do not sum exactly
to one, first run the bounded read-only diagnostic below from the independent
Windows environment configured for Google access. It reads only `AO4:AO6`,
checks Drive metadata and tab structure before and after, and performs two
complete value/formula reads. Exact values, formulas, format metadata, the
Decimal sum and its delta from one are written only to the private
`financial-model-packages-v1/reports/probability-diagnostic-*.json` directory.
The command prints only a sanitized status summary. It does not capture a model
package, connect to PostgreSQL, or normalize probabilities.

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run db:financial-model-package -- diagnose-probabilities --store $store --confirm-read-only-source-diagnostic
```

The mapper is explicitly Bear=`AO4`, Base=`AO5`, Bull=`AO6`. Google Sheets
`effectiveValue.numberValue` is the underlying number, including for cells
formatted as percentages; number formatting is presentation metadata and is
not divided by 100. The adapter requires all three cells to retain the
declared `PERCENT` format and underlying values in the 0-to-1 fraction range.

For a nonzero sum residual no larger than `1e-15`, the adapter closes the
probability simplex deterministically by setting Base to `1 - Bear - Bull`.
This is a decimal-serialization boundary correction, not a redistribution of
the Bear and Bull assumptions. It preserves the original typed values and
formulas in `source_cells`, and records original/normalized triples, residual,
adjusted scenario, rule version and exact adjustment in
`probability_normalization`. Missing, nonnumeric, negative, above-one,
unexpectedly formatted or materially non-unit triples fail closed. The native
`FinancialModelRevisionCreate` validator remains unchanged and still receives
an exact Decimal sum of one.

Parity validation separately compares the unmodified source probabilities
with the approved fixture. A difference larger than the same serialization
bound is reported as `PROPOSED_SOURCE_REVISION`, even if native projection and
published-output parity passes within its approved numeric tolerances. The
adapter does not replace source probabilities with fixture values. Any such
package remains an unaccepted proposal and requires the established review.

Run from the repository root in the independent Windows environment configured
for Google access. The application service account needs Viewer access to the
configured spreadsheet. This command performs only bounded Google reads and
writes the captured package to the private local store:

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run db:financial-model-package -- capture --store $store --confirm-read-only-source-capture
```

Record the returned `run_id` and `payload_sha256` locally. The package contains
private model assumptions and outputs; do not paste its JSON into GitHub, CI,
issues or task messages. Inspect and validate it offline:

```powershell
$runId = '<captured-run-id>'
$packageHash = '<captured-payload-sha256>'
npm run db:financial-model-package -- inspect --store $store --run-id $runId --payload-sha256 $packageHash
npm run db:financial-model-package -- validate --store $store --run-id $runId --payload-sha256 $packageHash
```

Validation reports the parity-check counts and writes detailed reconciliation
only to the private store. For canonical identity and stale-base preview, use
the existing verified, read-only database target. This task does not run that
preview or connect to Neon:

```powershell
npm run db:financial-model-package -- preview --store $store --run-id $runId --payload-sha256 $packageHash --target-environment production
```

The `accept` command is provided for a later separately authorized review only.
It requires two identical explicit package-hash approvals, a separate
confirmation switch, and the normal guarded production write configuration.
Do not run it as part of capture or preview. It creates a native revision only
if exact canonical identity, parity and current base-revision checks pass. An
existing model without a supplied base revision blocks rather than being
overwritten.

## Future non-Sheets producers

V1 is intentionally Google-Sheets-specific at the source-evidence boundary:
its cell map denotes actual P-GOOGL coordinates. A direct research-agent
producer must not fill those coordinates with invented spreadsheet evidence
or claim Google source metadata. A later contract version can keep the same
identity / inputs / published-outputs / revision / provenance envelope while
replacing the `source` and `source_cells` representation with a versioned
producer-neutral evidence block. That block should carry the author identity,
authored and observed times when known, source references, exact-listing
identity, base canonical revision and the same decimal/state semantics. Its
deterministic outputs must still be produced or verified by the backend model
engine. The agent needs no PostgreSQL access; its package would enter the same
validated preview and explicit acceptance path. V1 does not pretend that this
future adapter already exists.
