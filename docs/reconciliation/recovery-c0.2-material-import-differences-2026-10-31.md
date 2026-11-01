# Recovery C0.2 — Material Import Differences

> Replace `<PRIVATE_PORTFOLIO_RUN_ID>` from the local private snapshot manifest when
> running the example. Do not commit or publish the actual identifier.

## Decision

**Portfolio value fidelity: NO-GO. Canonical bootstrap preview: NO-GO.** No
schema was accepted, no Google workbook was edited, and no Neon connection or write
occurred.

The structural workbook contract remains suitable for a separate structural review. That
does not approve the values used by the canonical importer. The supplied live comparison
was stable but predates a recorded comparison-time field; a new bounded read-only comparison
is required before a value overlay can be reviewed. The remaining listing, lifecycle and
supported Price Feed formula exceptions also prevent an import-ready source determination.

## Root cause of the 105 material differences

All **105** changed canonical importer values are numeric cached-formula outputs in the
frozen XLSX that differ from stable effective values read from the same formulas in Google
Sheets. After expanding shared formulas, all 105 source formulas exactly match the live
formula text; none contains a function currently classified as volatile by the comparator.
This rules out a parser mapping, formula-translation, numeric, date or currency conversion
defect. It verifies a cache/live calculation disagreement, but the available evidence cannot
prove whether the XLSX cache was stale at export or a referenced workbook input changed
after export. They therefore remain stale-cache _candidates_, not accepted values.

| Importer target                               | Changed cells | Effect                                                     |
| --------------------------------------------- | ------------: | ---------------------------------------------------------- |
| `ScoreAssessment.COMPOUNDER_QUALITY.score`    |            40 | Score value differs                                        |
| `ScoreAssessment.DURABILITY_10Y.score`        |            41 | Score value differs                                        |
| `ScoreAssessment.EXECUTION.score`             |             2 | Score value differs                                        |
| `ScoreAssessment.RISK.score`                  |             1 | Score value differs                                        |
| `legacy_rank_population.current_weight_input` |            21 | Legacy lifecycle membership input differs                  |
| **Total**                                     |       **105** | **84 scores and 21 membership inputs; 105 distinct cells** |

Of the 105, 72 were initially grouped as formula-definition mismatches and 33 as stale-cache
candidates. Shared-formula expansion against OOXML anchors proves all 72 translated shared
followers match live formula text. The other 33 comprise 5 shared-formula anchors and 28
direct formulas that already had exact text. Thus there is no importer mapping, numeric,
currency, or formula-text discrepancy in these 105 cells.

The v3 comparison recorded no timestamp for the comparison window. Its stable two-sweep
result remains valid evidence for diagnosis, but it is insufficient for an immutable overlay
that must carry the live observation window. Comparator v5 records UTC comparison start and
completion timestamps and a durable attempt ID. The v3 evidence is deliberately not
accepted by the overlay command.

## Formula-text review

The earlier v3 report contained 1,018 formula-text differences:

- **907 shared-formula cells** are now expanded relative to their OOXML shared-formula
  anchors. All 907 expanded formulas match the live formula text exactly. This resolves the
  representation difference without algebraic or locale-based formula rewriting.
- **111 direct formulas** remain textually unresolved. Their source/live function signatures
  differ while their cell-reference sets match, so the available evidence does not establish
  an XLSX syntax translation or equivalent calculation. All 111 are in the `Price Feed`
  row-class field. Of these, 104 had matching current values and 7 had no usable effective
  value on unsupported row keys. The current importer consumes exactly one of the 104
  matching-value rows; the other 110 rows are outside its supported mapping. The consumed
  row remains a blocker because current-value equality does not prove formula equivalence.
- The earlier count of 524 cells with matching values and unresolved formula text predates
  shared-formula expansion. Those observations are not all residual blockers: the 907
  proven shared-formula expansions are now classified separately.

Formula comparison continues to normalize only whitespace and an optional leading `=`.
No formula is declared equivalent solely because its current output matches.

## The 441 unavailable/error states

| Importer target/state           |   Count | Import effect                                                                                    |
| ------------------------------- | ------: | ------------------------------------------------------------------------------------------------ |
| Cached legacy ranking positions |     429 | Imported as explicit unavailable/not-eligible states; no rank is fabricated                      |
| Company name                    |       3 | Two rows have the existing exact-ticker name fallback; one row has no ticker and is not imported |
| `Price Feed` row-class formula  |       7 | Unsupported auxiliary keys; not consumed by the current importer                                 |
| Current/target membership input |       2 | Consumed by lifecycle mapping and remain unavailable                                             |
| **Total**                       | **441** | **Only the two membership inputs affect current lifecycle resolution**                           |

The two unavailable membership inputs are among five companies whose current and target
weights are incomplete. The other blank inputs are equivalent blank/missing source states,
not comparison differences. The importer does not infer lifecycle from a research bucket
when either membership weight is missing. All five remain unresolved; none is a held
company.

The comparison ledger contains **3,043 observations covering 3,043 distinct cells**. Its
1,070 source-fidelity review observations cover 1,070 distinct cells: 105 changed values,
441 unavailable/error states and 524 equal-current-value/formula-text observations from the
v3 report. The 524 are included in the formula review above, not additional changed values.

## Source-only canonical reconciliation

This is a deterministic parser reconciliation of the two frozen XLSX artifacts only. It is
not the canonical-bootstrap preview and did not connect to a database. Counts below are the
cached-XLSX projection before any new comparison or reviewed overlay:

| Domain                                              |                                                                                                          Source-only count |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------: |
| Companies                                           |                                                                                                                        219 |
| Securities                                          |                                                                                                                        100 |
| Listing records                                     |                                                                                                                        100 |
| Held positions                                      |                                                                                                                         22 |
| Cash rows                                           |                                                                                                                          2 |
| Target allocations                                  |                                                                                                                         16 |
| Score assessments                                   |                                                                                                                        506 |
| Portfolio / Watchlist / Research rank rows          |                                                                                                                   219 each |
| Lifecycle: Portfolio / Watchlist / Candidate / Drop |                                                                                                          21 / 71 / 96 / 26 |
| Lifecycle unresolved                                |                                                                                                                          5 |
| Additional source-only warnings                     | 10 name fallbacks; 3 Portfolio-membership overrides; 4 duplicate score rows resolved by detail; 1 unmodeled reserve target |

All 22 held positions have resolved exact listing identities and quantities in the
source-only plan. None of the 11 incomplete listing records or 3 unresolved listing
mappings belongs to a held position. The incomplete listing records comprise 10 Watchlist
and 1 Drop row; the 3 unresolved listing mappings comprise 1 Watchlist and 2 rows whose
lifecycle is unresolved. They require exact source evidence or explicit deferral; no venue,
currency, security, or listing identity has been inferred.

Other source-only exceptions are 11 duplicate cached rank positions and 2 invalid rank
values. They remain explicit ranking data-quality states and must not be renumbered or
silently normalized. The source-only parser does not change workbook content or any
canonical database record.

The complete source-only issue-code counts are in the machine-readable report. The 5
`ALLOCATION_MEMBERSHIP_UNRESOLVED` and 5 `LIFECYCLE_SOURCE_INCOMPLETE` entries refer to the
same five unresolved lifecycle rows, not ten separate companies. The parser also records 10
company-name fallbacks, 3 Portfolio-membership overrides of a research bucket, 4 duplicate
score rows resolved by the documented detail priority, and one reserve target not modeled.
These warnings are disclosed; none represents an inferred source correction.

## Overlay and remaining resolution

An immutable overlay implementation is available for a future v5 comparison. It is narrowly
limited to the five fields above and is tied to the acquisition run, artifact and semantic
hashes, source identity hash, Drive metadata, comparison report hash/time window, exact
source cells, original and live decimal text, and formula identities. It remains
`REVIEW_REQUIRED` until a human explicitly creates a separate local approval receipt. The
canonical importer and preview use the same approved values; the original XLSX is never
modified. Overlay identity contributes to import idempotency and provenance. Candidate
generation also blocks if any formula-text difference remains on a currently consumed field,
including the single supported `Price Feed` row. Thus a fresh v5 read alone may not make an
overlay available; the formula issue must first be resolved with exact source evidence.

No candidate was generated from the v3 report because it lacks a recorded comparison time;
the unresolved consumed `Price Feed` formula is an independent blocker. No Google Sheet
correction or importer mapping change has been verified or applied.
The current runtime cannot make the authorized Google API request through its restricted
proxy. In the authorized Windows PowerShell environment, run the exact bounded comparison
first and inspect its private evidence. The candidate command is conditional: it must remain
blocked while the supported `Price Feed` formula difference remains unresolved. Do not
approve an overlay merely because the compared output values match.

```powershell
$snapshotStore = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run source:workbook:compare-values -- '<PRIVATE_PORTFOLIO_RUN_ID>' `
  --store $snapshotStore `
  --scope canonical-bootstrap `
  --confirm-read-only-live-comparison

# Run only after reviewing the v5 private report and confirming no consumed formula blocker remains.
npm run source:workbook:value-overlay -- candidate `
  --store $snapshotStore `
  --portfolio-run '<PRIVATE_PORTFOLIO_RUN_ID>'
```

If source metadata advanced, reacquire the workbook and use that new frozen run throughout.
If the supported formula difference remains, stop and obtain authoritative source evidence
or a separately reviewed contract correction; do not create an approval receipt. If a
candidate is generated, review it locally. Only after that review, use its exact printed
hash in the separate `approve` command documented in
[workbook-source-acquisition.md](../workbook-source-acquisition.md). Candidate generation
and approval do not accept either workbook schema or write to Neon.

## Readiness matrix

| Gate                              | Result             | Reason                                                                                                                            |
| --------------------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| Portfolio schema acceptance       | **NO-GO for now**  | Structural checks passed, but importer-value fidelity and one consumed formula remain unresolved; do not baseline yet             |
| Portfolio importer-value fidelity | **NO-GO**          | The 105 values need a fresh timestamped comparison and explicit overlay review; one consumed row-class formula remains unresolved |
| Lifecycle completeness            | **NO-GO**          | Five companies have incomplete membership inputs; do not infer zero weights or lifecycle                                          |
| Listing completeness              | **NO-GO**          | Eleven records have incomplete fields and three mappings remain unresolved                                                        |
| Canonical bootstrap preview       | **NO-GO**          | Both source schema acceptance and importer blockers remain outstanding                                                            |
| Production import                 | **NOT AUTHORIZED** | No approval or production write was requested or performed                                                                        |

## Verification

- Frozen portfolio and Market Data artifact hashes verified locally before parsing.
- Source-only parser result: 219 companies, 100 securities, 100 listing rows, 22 positions, 2 cash rows,
  16 targets, 506 scores, and 219 rows in each of three legacy ranking projections.
- Formula-expansion review: 907/907 shared formulas exactly match the recorded live formula;
  111 non-shared `Price Feed` formula definitions remain unresolved.
- Overlay focused tests: exact-decimal preservation, explicit zero, unresolved formula,
  wrong type/target, duplicate cells, approval/hash binding, stale source-cell rejection,
  and unapproved overlay rejection.
- No Google API request, workbook edit, schema acceptance, Neon connection, database write,
  provider ingestion, or recurring-operation change occurred.
