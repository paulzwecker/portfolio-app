# Recovery C0 — Scalable Sheets Value Validation

> Replace `<PRIVATE_PORTFOLIO_RUN_ID>` from the local private snapshot manifest when
> running the example. Do not commit or publish the actual identifier.

> **Current source-fidelity status:** this implementation note predates the successful live
> comparison and its semantic review. See
> [Recovery C0.1](recovery-c0.1-semantic-sheets-reconciliation-2026-10-31.md); completion
> of the comparison did not establish source equivalence.

## Result

**Implementation complete; live source-value validation still requires the authorized
Windows PowerShell run.** The Codex runtime's configured proxy is unreachable, so this work
made no Google API requests. No workbook, database, schema baseline, or recurring operation
was changed.

## Root cause and measured plan

The previous comparator allowed at most 1,000 compact ranges and 60,000 requested cells.
The frozen portfolio source required 3,641 exact, sparse ranges across all importer domains.
Its requested range area was 20,431 cells, so the range-count ceiling was the blocker; the
cell-area ceiling was not exceeded. Ranges were not inflated by filling gaps with broad
rectangles.

The local planner reread the frozen artifact, verified its raw SHA-256 and semantic
fingerprint, then produced these sanitized counts:

| Scope                           | Selected cells | Exact ranges | Chunks per sweep | Estimated requests including two metadata reads | Budget |
| ------------------------------- | -------------: | -----------: | ---------------: | ----------------------------------------------: | ------ |
| Initial canonical bootstrap     |          7,861 |        2,257 |               38 |                                              78 | Fits   |
| Optional model/research imports |         12,570 |        1,036 |               18 |                                              38 | Fits   |
| All importer domains            |         20,431 |        3,641 |               61 |                                             124 | Fits   |

The initial-import scope includes identity/lifecycle and cached ranks, holdings and cash,
targets, quality assessments, listing crosswalk, research-priority inputs, and investment
scores. Published model outputs/currency/history and legacy estimate history are explicitly
separate because they are consumed by the model/analytics bootstrap, not the initial
canonical portfolio import.

## Implementation

- Importer cells are grouped by row in one pass. This also removes the prior repeated
  full-sheet scan behavior when building value definitions.
- Selected cells become deterministic compact A1 ranges. Duplicate ranges are deduplicated,
  conflicting dimensions fail closed, and ranges are split into requests bounded by 60
  ranges and 8,000 requested cells.
- The complete plan is checked before any live request. Per-run limits are 30,000 selected
  cells, 60,000 requested cells per sweep, 4,000 ranges, and 70 chunks per sweep. There is
  no sampling or automatic limit increase. An exceeded plan records counts and limits and
  returns `BLOCKED_VALIDATION_BUDGET_EXCEEDED` without making a Google API request.
- The initial metadata check, both complete value/formula sweeps, and final metadata check
  form one consistency fence. Each request and retry uses the same 1.05-second request
  pacer. Stable Drive metadata and equal full-sweep value and formula fingerprints are
  required; native Sheets without Drive revision IDs use the documented semantic fence.
- Progress includes selected cells, ranges, chunks, requests/attempts, completed cells,
  compared cells, mismatch classes, and consistency outcome. API failures and final
  metadata failures preserve completed progress. CLI output and tracked reports contain no
  cell values or file identifiers. Comparison contract v3 stores exact mismatch evidence
  only in the protected private snapshot store; see Recovery C0.1 and the source-acquisition
  runbook.
- Decimal text, blank versus zero, formula errors, dates, currency identifiers, and number
  formats use the existing semantic normalization. No live result is substituted into the
  frozen workbook.

The theoretical maximum is 426 HTTP attempts including retries (70 chunks per sweep plus
two metadata requests, each with up to three attempts). Actual successful requests are
expected to be 124 for the all-importer scope or 78 for the initial bootstrap scope using
the current source population.

## Verification

Verification: 76 tests passed, 1 skipped, and 7 integration-marked tests were excluded
because this task does not require a database. Ruff check/format and targeted mypy passed.
Tests cover large sparse workbooks, range/cell chunk boundaries, duplicate range removal,
scope separation, explicit budget blocking before requests, source changes between reads,
value/formula changes between sweeps, zero-mismatch completion, API failures, request
pacing, and retention of progress on failure. Snapshot-local planning confirmed raw and
semantic integrity and the counts above. No live Google comparison was performed due to
the restricted proxy; fixtures do not establish live source fidelity.

## Operator command

Run from the repository in the authorized Windows PowerShell environment, using the latest
frozen snapshot in the private store:

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run source:workbook:compare-values -- '<PRIVATE_PORTFOLIO_RUN_ID>' `
  --store $store `
  --scope canonical-bootstrap `
  --confirm-read-only-live-comparison
```

This performs read-only Drive metadata and Sheets value/formula requests. It does not edit
the workbook, connect to Neon, import data, or accept a schema. The service account must
have Viewer access and `spreadsheets.readonly` authorization. Do not bypass network policy
if the configured proxy is unavailable.

## Source-fidelity decision at C0 completion

At the time this implementation milestone completed, the comparator was ready to run, but
source fidelity was **not yet GO**. The later operator-provided live comparison and its
reconciliation are recorded in Recovery C0.1. GO for a domain
requires exit code 0, status `COMPARED`, zero mismatch classes, stable source metadata, both
complete sweeps with matching values and formulas, exact snapshot integrity, and acceptable
states for every relied-upon field. Any mismatch, formula error, missing required sheet,
source change, incomplete request, or budget block remains NO-GO for the affected scope.
After any source advance, acquire and validate a new frozen snapshot; do not accept or import
from an older run by default.
