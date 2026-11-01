# Recovery B — Source Fidelity and Identity Resolution

> Replace `<PRIVATE_PORTFOLIO_RUN_ID>` from the local private snapshot manifest when
> running the example. Do not commit or publish the actual identifier.

**Assessment: NO-GO for the initial canonical bootstrap.** The change to the read-only
Sheets comparison path is implemented and locally tested, but no live Google comparison
was performed in this runtime. The latest Portfolio snapshot has not been schema-accepted,
and a source-only replay reports 19 blocking source errors.

## Scope and evidence

This review used the latest locally stored Portfolio and Market Data artifacts, verified
each content-addressed artifact against its manifest, and replayed the canonical importer
without connecting to a database. It did not contact Google, change a workbook, accept a
schema, write to Neon, or start ingestion.

The newest local Portfolio artifact is `ACQUIRED_REVIEW_REQUIRED` and unaccepted. It has a
semantic fingerprint version, but its source Drive revision ID is absent. The newest
Market Data artifact has an accepted schema baseline and the same bytes as its acquisition
parent. No newer acquisition is present in the private store. Local artifact integrity does
not establish that either Google source is still current.

The Portfolio snapshot's importer-scoped semantic inventory contains 470 empty formula
caches, zero formula-error cells, and 61 invalid values. Empty caches and invalid values
remain explicit; none are inferred as zero. The previously recorded sample of four cache
mismatches out of seven was not accompanied by a live comparison report. Their causes
remain unclassified. The reported workbook-wide formula errors are outside the currently
verified importer-scoped error count and have not been rechecked live.

## Live comparison implementation

The bounded comparison now supports a native Google spreadsheet with no Drive
`headRevisionId`. It requires exact configured-file identity, native-sheet MIME type, a
present and matching Drive modification time, any captured checksum to match, two stable
reads of importer-allowlisted normalized values and formula definitions, and unchanged
source metadata across the comparison. It records a semantic-consistency protocol and
keeps the source revision match explicitly null when Drive supplies no revision ID. A
source change or an unstable value/formula read fails closed. This is a bounded semantic
fence, not a transactional Google snapshot guarantee.

The comparison remains read-only to Google and writes only a hash-based report in the
private snapshot store. A value mismatch is diagnostic evidence, not permission to choose
the live or XLSX value automatically. Portfolio and Market Data sources retain separate
ownership and acceptance decisions.

## Source-only reconciliation

The frozen pair parses to 219 companies, 100 listing mappings, 22 held positions, 2 cash
rows, 16 target rows, 293 score assessments, and 657 ranking entries (164 ranked entries).
These are source projection counts, not production record counts.

The importer reports 19 blocking errors:

| Issue                       | Count | Effect                                              |
| --------------------------- | ----: | --------------------------------------------------- |
| Incomplete listing fields   |    11 | Exact listing attributes cannot be imported safely. |
| Unresolved listing mapping  |     3 | No authoritative listing mapping is established.    |
| Incomplete lifecycle source |     5 | Lifecycle cannot be imported safely.                |

There are also five unresolved allocation-membership warnings: blank current/target weights
remain missing and are not treated as zero. Duplicate rank positions and invalid rank
values are reported as source gaps by the existing importer policy; they are not promoted
to valid ranked entries.

All 22 held rows map through the current importer. Two held instruments are absent from
the Market Data `Listings` sheet and resolve only through explicit auxiliary `Price Feed`
rows in the Portfolio workbook (one fund and one ADR). This is a documented importer path,
not a guessed substitute, but it remains a cross-workbook exception requiring operator
review before relying on Market Data continuity for those instruments.

The Market Data workbook has 112 listing source rows. Against the older checked-in Yahoo
crosswalk, 18 of 20 ready rows disagree on provider symbol and two exact identities are
absent from the current Market Data listing table. That historical crosswalk is not
authoritative, so this review made no mapping changes and treated these differences as
unresolved provider-identity checks.

The Market Data workbook contains two corporate-action rows; both have valid effective
dates, a source URL, and the workbook's verified flag set. The cited material was not
independently re-fetched or revalidated in this task.

## Decisions

- **Portfolio source fidelity:** NO-GO pending live comparison against the exact current
  source, mismatch classification, and resolution of the importer blockers. No Portfolio
  schema baseline has been accepted.
- **Market Data schema:** its existing schema baseline remains accepted. No new acceptance
  was created. Current-source freshness and provider-symbol exceptions remain unverified.
- **Full source pair/bootstrap:** NO-GO. Acceptance of the Market Data schema does not
  waive the Portfolio fidelity or identity blockers.
- **Production database:** not accessed. No preview or apply was run.

## Operator handoff — independent Windows PowerShell

Run from the Recovery B checkout in the existing local environment with the already
configured read-only service account and permitted network path. Do not disable or bypass
an enforced proxy.

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run source:workbook:compare-values -- '<PRIVATE_PORTFOLIO_RUN_ID>' `
  --store $store `
  --confirm-read-only-live-comparison
```

The command checks source identity and metadata before reading, reads only the importer
allowlist twice, then checks metadata again. It reports counts/classifications and writes
hash-only evidence under the private store's `value-comparisons` directory. If it reports
that the source advanced, acquire a new frozen Portfolio snapshot and compare that new run:

```powershell
npm run source:workbook -- acquire portfolio --store $store `
  --confirm-source-acquisition
# Use the newly emitted run ID in the compare-values command above.
```

Do not accept a schema if there are unexplained importer-value differences or identity
blockers. Reconcile the active listing and lifecycle exceptions against authoritative
company/listing evidence; retain unresolved records as unavailable. For Market Data source
freshness, use a bounded acquisition of the explicitly configured Market Data workbook
only if its live metadata must be refreshed; inspect any resulting schema drift separately.

After these operator checks, rerun source-only reconciliation. Only then prepare a new
read-only database preview. This report does not authorize schema acceptance, a production
preview, a database write, or ingestion.

## Local verification

The new native-Sheets semantic fence, changing values, changing formulas, missing
modification metadata, and source metadata drift have deterministic unit coverage. Focused
checks completed as follows:

- Workbook comparison, semantics, and snapshot-source tests: **52 passed, 1 skipped**.
- Canonical bootstrap non-integration tests: **9 passed**.
- Legacy importer non-integration tests: **2 passed**.
- Ruff check and format check: **passed**; JSON report validation and `git diff --check`:
  **passed**.
- The PostgreSQL-backed legacy importer integration test was attempted against the local
  test database and timed out while waiting for its existing advisory lock, before the
  importer reached its data-write path. No production database was contacted. That
  integration result is **blocked by the local test database state**, not counted as a
  pass; the other two tests in that invocation passed.

Live Google comparison and end-to-end source acceptance remain operator-side steps
because the Codex runtime's configured proxy is unreachable.
