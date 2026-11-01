# Native Google Sheets canonical source-value bundle

> Replace `<PRIVATE_PORTFOLIO_RUN_ID>` from the local private snapshot manifest when
> running the example. Do not commit or publish the actual identifier.

## Purpose

For an explicitly configured native Google spreadsheet, the initial Portfolio bootstrap
uses the Google Sheets API `effectiveValue` for each declared importer field. The frozen
XLSX remains the immutable source artifact for worksheet structure, headers, formula text,
cached values, number formats, date system and parser compatibility. It is not a fallback
for absent live values.

The current contract versions are:

- `native-google-sheets-source-values-v2`
- `portfolio-import-source-authority-v2`
- `native-google-sheets-source-approval-v2`

The source bundle is private and content-addressed under the acquisition store's
`source-value-bundles/<acquisition-run-id>/<sha256>.json` directory. Its SHA-256 binds
the frozen artifact, workbook identity digest, source revision/modified-time/checksum,
schema fingerprint, importer semantic fingerprint, field mapping and captured live cell
evidence. The bundle stores exact decimal text, source types, explicit blank/zero states,
XLSX original/cached values and formulas, live entered formulas and effective values, and
effective format metadata. It also preserves whether a coordinate was represented by
CellData, an explicit empty CellData object, metadata-only CellData, or an omitted CellData
inside a confirmed range. It contains no credential or raw Google file ID.

## Consistency semantics

Acquisition occurs only after the read-only comparator has checked the configured file
identity and source metadata, read the complete selected importer ranges twice, confirmed
that normalized values, formula definitions, exact entered/effective cell evidence, number
formats and cell-presence states agree between reads, and rechecked Drive metadata. Any API
failure, missing requested range, uncovered importer coordinate, changed value/formula/cell
presence, or metadata mismatch prevents bundle creation. Omitted CellData positions are
reconstructed as blanks only if the requested GridData range is present and its complete
row and column metadata dimensions match the requested bounds. Required-nonempty values are
validated separately from transport coverage. The bundle is an **observed consistent source state**;
Google Sheets does not provide a transaction token for this multi-request capture, so it is
not represented as a guaranteed atomic snapshot.

Only `canonical-bootstrap` fields are captured. Optional model/research outputs remain a
separate import scope. The importer applies the exact approved bundle in memory before
building the import plan. Both preview and apply require the same acquisition run, bundle
SHA-256 and separate source-value approval SHA-256; the bundle hash participates in the
import fingerprint and provenance. The importer verifies the exact field/cell set,
transformations, authority policy, source identity, artifact/schema/semantic hashes and
source metadata again. An altered, incomplete, stale or unsupported bundle fails closed.

## Formula and field policy

XLSX formula text and cache, Google Sheets entered formula and effective value, and their
typed representations are retained as distinct evidence. The application imports the live
effective value for the field named in the importer contract; it makes no claim that Excel
and Google Sheets formulas are equivalent. A formula-definition difference remains a
review signal even when current values match.

`Price Feed` has a field-specific source policy: the exact auxiliary-row class/key,
canonical ticker, venue-and-ticker listing identity, company name and quote currency are
mapped to their named importer fields. The live effective value drives the importer field;
both formula definitions remain evidence. No Excel formula semantics are inferred. If a
consumed `Price Feed` formula definition differs, approval additionally requires the
explicit `--confirm-price-feed-formula-policy` flag. The resulting canonical preview still
has to pass exact held security/listing identity and reconciliation checks.

Type errors, formula errors, non-finite numerics and invalid/missing live formula results
are blocking. Omitted-in-range blanks, returned empty cells, literal empty strings and
formula results of empty strings remain distinct in bundle evidence. A blank remains blank;
an explicit zero remains zero. Required-nonempty importer fields that are blank or empty
block source-value approval; other empty values remain explicit and are handled by the
existing canonical importer validation. Context-dependent policies use captured Sheets
peer-cell values rather than XLSX caches. Numeric API values are
decoded as `Decimal` and serialized to exact decimal strings; binary floats are rejected.
Date serials retain their source number-format and workbook date-system evidence. Currency
codes are preserved as identities and are not converted by this contract.

## Separate review gates

Three decisions remain separate:

1. **Schema baseline acceptance** accepts a structural workbook contract only.
2. **Source-value approval** explicitly accepts one reviewed, content-addressed observed
   Sheets value bundle for canonical import. It does not accept schema changes, resolve
   listing mappings, assign lifecycle, or approve investment decisions.
3. **Canonical bootstrap preview/apply** validates the exact source pair and database
   target; production apply still requires its independent authorization and recovery
   procedure.

For a new native Sheets import the earlier review-gated XLSX-cache overlay is not combined
with the bundle and is rejected by the bootstrap. Existing overlay candidates and receipts
remain immutable evidence; they cannot be converted into source-bundle approvals. Acquire
and compare the selected frozen snapshot again, then review and approve the resulting
bundle. There is no automatic migration of prior overlay approvals.

## Read-only operator procedure

Run this in the authorized Windows PowerShell environment with the configured service
account and private snapshot store. The comparison makes read-only Google API requests. It
does not edit Sheets or contact Neon. Do not route around a restricted proxy. For the
currently selected frozen portfolio snapshot, use its exact acquisition ID:

```powershell
$snapshotStore = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
$portfolioRun = '<PRIVATE_PORTFOLIO_RUN_ID>'

npm run source:workbook:compare-values -- $portfolioRun `
  --store $snapshotStore `
  --scope canonical-bootstrap `
  --confirm-read-only-live-comparison
```

Proceed only if comparison status is `COMPARED` and
`canonical_source_bundle.status` is `CAPTURED_REVIEW_REQUIRED`. Record the emitted bundle
hash from the local command output; do not place the private bundle or report in Git. Inspect
the sanitized summary, including cell-presence and empty-state counts by sheet, importer
field, semantic type and empty-value policy. A `CAPTURED_BLOCKED` bundle or any uncovered
coordinates/required-nonempty issues is a NO-GO; do not approve it. If source metadata no
longer matches the frozen acquisition, acquire and review a new snapshot before repeating
the command.

```powershell
$bundleSha256 = '<exact-source-value-bundle-sha256>'
npm run source:workbook:source-bundle -- inspect `
  --store $snapshotStore `
  --portfolio-run $portfolioRun `
  --bundle-sha256 $bundleSha256
```

Only after reviewing the private bundle and its field-level differences, create a separate
immutable source-value approval. The following example requires review acknowledgments for
live Sheets authority and XLSX value/formula differences. Include
`--confirm-price-feed-formula-policy` when the inspected bundle reports any consumed
Price Feed formula-definition difference. These flags record a human decision; they do not
assert formula equivalence.

```powershell
npm run source:workbook:source-bundle -- approve `
  --store $snapshotStore `
  --portfolio-run $portfolioRun `
  --bundle-sha256 $bundleSha256 `
  --reviewed-by '<reviewer>' `
  --review-note '<summary of reviewed fields, differences, and remaining exceptions>' `
  --confirm-sheets-values-authoritative `
  --confirm-xlsx-value-differences `
  --confirm-formula-definition-differences `
  --confirm-price-feed-formula-policy
```

Omit a difference acknowledgment only when the corresponding inspected count is zero. The
approval command does not approve a schema or authorize database writes. It returns the
immutable approval receipt hash. Preserve it with the private source records.

For a read-only bootstrap preview, pass the exact same source bundle and receipt hashes to
the existing command (along with the separately reviewed Market Data acquisition):

```powershell
npm run db:bootstrap-canonical -- preview `
  --store $snapshotStore `
  --portfolio-run $portfolioRun `
  --market-run '<exact-approved-market-data-run-id>' `
  --portfolio-source-value-bundle-sha256 $bundleSha256 `
  --portfolio-source-value-approval-sha256 '<exact-approval-receipt-sha256>' `
  --target-environment production
```

The preview remains subject to independent target verification and read-only database
guards. It must still report unresolved held listing identities, lifecycle classifications,
targets and other source exceptions explicitly. No source-value bundle automatically
resolves those issues.
