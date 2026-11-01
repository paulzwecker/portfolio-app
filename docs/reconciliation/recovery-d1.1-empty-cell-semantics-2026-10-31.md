# Recovery D1.1 — Empty-cell semantics

> Replace `<PRIVATE_PORTFOLIO_RUN_ID>` from the local private snapshot manifest when
> running the example. Do not commit or publish the actual identifier.

## Finding on the prior comparison

The saved comparison for the selected frozen Portfolio workbook reported 7,861 required
importer coordinates, 7,474 returned `CellData` objects, and 358 coordinates treated as
missing. The old reader indexed returned `CellData` objects but did not retain an explicit
per-requested-range coverage map. It therefore conflated an absent `CellData` entry with an
uncovered coordinate.

The saved report confirms that all requested chunks completed, the two value/formula sweeps
were stable, and source metadata matched. It does **not** retain the per-range `GridData`
envelopes, dimension metadata, or an absent-coordinate ledger. Consequently, the exact 358
cannot now be assigned to sheets, importer fields, semantic types, or valid blank versus
incomplete response. The aggregate counts also do not reconcile to a one-to-one cell count:
the 7,474 number counts returned `CellData` objects, while 358 counts expected importer
coordinates. The difference must not be explained by assumption.

The best-supported root-cause classification is therefore: **the old completeness check
could produce false missing-cell reports for sparse Sheets responses; the historical evidence
cannot prove that all 358 were valid blanks**. A new live comparison is required to classify
the exact fields using the current contract. The previous 358 are not waived.

## Corrected contract

The v2 reader requests row and column metadata for each bounded range and requires one
matching `GridData` range envelope per request. It maps each response from its explicit
zero-based `startRow` and `startColumn`, verifies the requested dimensions, and fails closed
on absent/duplicate/unexpected ranges, truncated metadata, malformed rows, or oversized
cell arrays. Only omitted `CellData` positions inside a confirmed range with complete
requested dimension metadata are reconstructed as blank coordinates. This follows the
Sheets API's representation of requested ranges and row/column metadata ([GridData
reference](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets)).

The source bundle now distinguishes:

- Omitted `CellData` inside a confirmed requested range (`BLANK` plus an omitted-data state).
- An explicitly returned empty `CellData` object or metadata-only cell.
- A literal empty string.
- A formula whose effective value is an empty string.
- A formula with no effective result, which remains an error.
- An uncovered coordinate or missing range, which blocks capture.
- Numeric zero, retained as the exact value `0`.

The canonical importer field policy is stored for each source cell. Required nonempty
identities, row kinds, base currency, source control totals, held quantities/cash balances,
identified target values, and selected exact-listing mapping fields make the bundle
`CAPTURED_BLOCKED` when empty. Other empty values remain explicit for the existing importer
to validate; unknown mapped fields default to `CANONICAL_IMPORTER_VALIDATES`, not optional.
No blank is converted to zero or filled from an XLSX formula cache.

Both complete reads are fenced over normalized semantics, formula definitions, exact entered
and effective values, number formats, and cell-presence states, plus the existing before/after
source metadata checks. Preview and apply continue to replay the same immutable bundle and
approval identities. Equal reads describe an observed consistent state, not a transactional
Google Sheets snapshot.

The bundle/approval/authority contract versions are now `native-google-sheets-source-values-v2`,
`native-google-sheets-source-approval-v2`, and `portfolio-import-source-authority-v2`.
The prior XLSX-cache overlay remains separate, immutable evidence and is not approved or
applied by this change.

## Operator recapture

Run only in the separately authorized Windows PowerShell environment with the configured
read-only service account and private snapshot store. The Codex runtime did not make a live
request because its configured proxy is restricted. This command does not contact Neon or
edit the Google workbook:

```powershell
$snapshotStore = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
$portfolioRun = '<PRIVATE_PORTFOLIO_RUN_ID>'

npm run source:workbook:compare-values -- $portfolioRun `
  --store $snapshotStore `
  --scope canonical-bootstrap `
  --confirm-read-only-live-comparison
```

The comparison output should contain sanitized counts by sheet, target field, semantic type,
empty-value policy, and cell-presence/empty state. Proceed to human review only if status is
`COMPARED`, the bundle is `CAPTURED_REVIEW_REQUIRED`, and no required-nonempty or coverage
issues remain. `CAPTURED_BLOCKED`, a missing range/coordinate, unstable blank state, source
metadata mismatch, or incomplete response is NO-GO. If the frozen snapshot metadata no longer
matches the source, acquire a new snapshot and review it before comparison.

No schema acceptance, source-value approval, bootstrap preview/apply, Neon write, or recurring
operation is authorized by this recovery task.
