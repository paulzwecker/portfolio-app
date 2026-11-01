# Recovery C0.1 — Semantic Sheets Reconciliation

> Replace `<PRIVATE_PORTFOLIO_RUN_ID>` from the local private snapshot manifest when
> running the example. Do not commit or publish the actual identifier.

## Decision

**Initial canonical-import source fidelity: NO-GO.** The supplied live comparison completed
its consistency protocol, but `COMPARED` means the comparison ran; it does not mean the
frozen XLSX and live spreadsheet are semantically equivalent. No workbook was edited, no
Neon operation was performed, and no schema was accepted.

This review uses the operator-provided comparison report (report format v2). That report
does not identify its comparator contract version and retained only hashes, not the live
formula text or exact live values. Its cell counts and hashes are useful for triage, but
its original mismatch classes cannot answer formula syntax or numerical-difference
magnitude questions. The new comparator contract is versioned and preserves those exact
details in a private exception ledger for a read-only rerun.

## Sanitized result summary

The comparison covered 7,861 importer-required cells in 2,257 ranges and 38 chunks per
sweep. It made 78 total API requests. Metadata matched the frozen acquisition, both full
live value/formula reads were stable, and no consistency-fence violation was reported.
Google did not provide a revision ID, so the result used the documented metadata plus
two-sweep semantic fence; this is not an atomic Google snapshot token.

The report contains 1,340 mismatch records across 1,340 distinct cells (zero duplicate
observations). These are the classifications in the supplied v2 report; v3 may reclassify
text/number differences while retaining the same source evidence.

| Importer domain                       | Mismatch cells |
| ------------------------------------- | -------------: |
| `identity_lifecycle_and_cached_ranks` |            633 |
| `quality_assessments`                 |            580 |
| `listing_identity_crosswalk`          |            112 |
| `investment_scores`                   |             14 |
| `strategic_targets`                   |              1 |

Of the 1,340 mismatch cells, 1,062 have a source formula and 278 are source literals.
The literal group comprises 276 generic workbook inputs, one legacy listing crosswalk cell
and one workbook score-assessment cell. Formula-bearing status is separate from whether a
cell changes the current importer output.

| Supplied report class       | Count | Affected importer fields                                                            | Assessment                                                                                                                                                                                                                                                                                                                                                    |
| --------------------------- | ----: | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Formula definition mismatch | 1,018 | Legacy row-class/rank outputs and quality/durability scores                         | All 1,018 formula hashes differ. 946 have equal normalized value hashes; 72 differ. Formula text was not retained, so translation, array expansion, locale changes, reference changes and genuine logic changes cannot be distinguished yet. Different formulas are not declared equivalent.                                                                  |
| Other value mismatch        |   214 | 24 company-name cross-checks; 190 score evidence-completeness cells                 | The importer uses the score-sheet name only when the Universe Registry name is blank; all 24 affected rows had a nonblank registry name, so the fallback is not consumed. The 190 evidence cells affect duplicate-source priority by nonempty presence only; source and live cells were both present. Current importer output is unchanged for these records. |
| Value-type mismatch         |    63 | 16 lifecycle buckets; 1 Price Feed listing-identity cell; 46 score provenance cells | These were blank-versus-missing states, not zero-versus-missing. The importer maps blank and missing to `None`, while zero remains a present numeric value. The listing-identity cell is on a Price Feed row excluded by the current auxiliary-listing importer; it is not an initial-import listing blocker.                                                 |
| Stale XLSX cache candidate  |    33 | 21 lifecycle membership weight inputs; 12 scores                                    | Same formula hashes, different cached/live value hashes. This confirms value drift, but not its cause. The formulas were not retained in the report, and indirect dynamic dependencies were not ruled out.                                                                                                                                                    |
| Currency-format mismatch    |    11 | Execution score cells                                                               | Underlying values matched; the discrepancy is number-format metadata. These score fields are not currency quantities.                                                                                                                                                                                                                                         |
| Percent-format mismatch     |     1 | Target source control total                                                         | Underlying normalized Decimal matched. The importer does not scale a value based on display formatting.                                                                                                                                                                                                                                                       |

### Exact importer-field counts

| Target field                                  |                                                                        Count | Source comparison group                                                                 |
| --------------------------------------------- | ---------------------------------------------------------------------------: | --------------------------------------------------------------------------------------- |
| `ListingMapping.row_class`                    |                                                                          111 | Formula definition                                                                      |
| `RankingEntry.legacy_portfolio_position`      |                                                                          177 | Formula definition                                                                      |
| `RankingEntry.legacy_research_position`       |                                                                          200 | Formula definition                                                                      |
| `RankingEntry.legacy_watchlist_position`      |                                                                          219 | Formula definition                                                                      |
| `ScoreAssessment.COMPOUNDER_QUALITY.score`    | 157 formula definitions; 4 stale-cache candidates; 36 formula outputs differ | Scores                                                                                  |
| `ScoreAssessment.DURABILITY_10Y.score`        | 154 formula definitions; 5 stale-cache candidates; 36 formula outputs differ | Scores                                                                                  |
| `legacy_rank_population.current_weight_input` |                                                                           21 | Stale-cache candidates                                                                  |
| `ScoreAssessment.EXECUTION.score`             |                              11 format differences; 2 stale-cache candidates | Score values/format                                                                     |
| `ScoreAssessment.RISK.score`                  |                                 1 format difference; 1 stale-cache candidate | Score values/format                                                                     |
| `ScoreAssessment.evidence_completeness`       |                                                                          190 | Text/number payload; presence-only importer priority                                    |
| `Company.name.cross_check`                    |                                                                           24 | Text/number payload; fallback unused for affected rows                                  |
| `CurrentLifecycle.source_bucket`              |                                                                           16 | Blank/missing representation                                                            |
| `ScoreAssessment.provenance`                  |                                                                           46 | Blank/missing representation                                                            |
| `Listing.exchange_and_ticker`                 |                                                                            1 | Blank/missing representation on a Price Feed row excluded by current auxiliary importer |
| `TargetRevision.source_control_total`         |                                                                            1 | Percent/number formatting                                                               |

### Formula and value breakdown

- Of 1,018 formula-definition differences, all 1,018 source/live formula hashes differ.
- Of those, 946 normalized value hashes match: 422 formula-cache-empty on both sides and
  524 equal populated values.
- The remaining 72 have different populated outputs: 36
  `COMPOUNDER_QUALITY.score` and 36 `DURABILITY_10Y.score`.
- The 33 same-formula/different-output candidates comprise 21
  `legacy_rank_population.current_weight_input` values and 12 score values: 4 compounder,
  5 durability, 2 execution, and 1 risk.
- The original report has no formula text, so the 1,018 formula changes cannot be
  assigned to syntax translation, array expansion, locale conversion, relative/absolute
  reference changes, or economic logic changes. No formula equivalence is inferred from
  matching current results.

## Canonical importer impact

The importer reads workbook cached values, not spreadsheet formula code. Relevant
ownership and transformations are:

- Universe Registry ticker/name/bucket and current/target membership inputs feed company
  identity and explicit lifecycle mapping. A positive current or target weight makes the
  legacy importer classify the company as Portfolio; a stale current-weight cache can
  therefore change lifecycle/membership. The canonical importer does not recompute that
  legacy input from holdings.
- Target Architecture supplies target weights as exact Decimals. Its control total is a
  reconciliation check, not a value to rescale from percent formatting.
- Score G cells and model-tab execution/risk score cells are investment assessments.
  Changed score values are material input differences; they are not safely reconstructed
  from unrelated spreadsheet factors in this importer.
- Score-sheet component cells C:F contribute only a count of nonempty evidence fields to
  duplicate-source priority. Their payload values are not copied into canonical score
  values.
- Market Data `Listings` is the canonical security/listing source. The portfolio
  `Price Feed` is read only for the explicitly supported auxiliary rows; the one reported
  listing-identity type difference is outside that importer selection.
- Holdings and cash cells are parsed as source literals. Missing values remain missing;
  no zero is inferred.
- Legacy rank positions are imported as legacy snapshot inputs, not as a new live ranking
  calculation.

There are **84 known score-value differences** (72 differing formula results plus 12
same-formula cache candidates) and **21 current-weight membership differences**. These
affect canonical source values and/or legacy lifecycle membership and require reconciliation
against the authoritative workbook calculation. The 946 formula-text differences with
equal output remain explicitly unresolved at the formula level. The 214 presence/fallback
and 63 absence-representation differences do not change current importer output under the
existing adapter semantics. The 12 format-only differences do not change stored numeric
values.

## Typed comparison contract implemented

The comparator now reports independent formula, value/type, number-format and importer
impact relations:

- Numeric values are parsed as `Decimal`, never through binary float. Decimal display
  precision and raw input text remain in the private evidence record.
- Currency identifiers are compared as explicit ISO text. A currency number format is
  never treated as a currency conversion or unit declaration.
- Percent values are normalized only when the field contract is percent-valued and the
  source text explicitly carries `%`; number formatting alone never divides or multiplies
  the stored value.
- Dates retain the existing Excel/Google epoch and date-format checks. Invalid date types
  remain invalid.
- Blank and missing can be equivalent only for the current importer's absence semantics.
  Formula-cache-empty and formula errors remain distinct unavailable/error states. Numeric
  zero is never equivalent to absence.
- Formula normalization is limited to trimming whitespace around the formula and one
  optional leading `=`. No formula parser or algebraic rewrite is used. Any other text
  difference remains `TEXT_DIFFERENCE_UNRESOLVED`, even when current output values match.
- Importer-specific equivalence is narrowly documented: score evidence-completeness is
  presence-only; score-sheet company names may be an unused fallback; Price Feed detail
  columns are only consumed for the existing auxiliary-row filter; ordinary blank/missing
  fields both become `None` in the existing adapter.

The supplied v2 report did not retain exact live values or formulas. A machine-readable
v1 private review ledger was created from it with the exact XLSX cached value/type/formula,
live hashes, importer target and an explicit `NOT_RETAINED` marker for live raw evidence.
Comparator contract v3 will write exact source/live values and formulas on the next
authorized read-only run. All raw evidence remains only in the private snapshot store.
Console output and tracked reports remain aggregate-only and contain no cell values,
formulas, file identifiers or private source paths.

## Safe live-value overlay assessment

No overlay is implemented. A future overlay is only supportable if a read-only comparison
produces stable values/formulas across both complete sweeps and stable pre/post metadata,
then stores an immutable overlay manifest bound to the exact XLSX artifact SHA-256,
semantic fingerprint, source identity hash, source-modified time, comparison contract
version and selected cell addresses. Import must verify every binding and refuse the
overlay if any source metadata or artifact hash differs. Only individually reviewed stale
formula-cache cells could be overlaid; the XLSX remains immutable and both cached and live
values/formulas remain auditable. A failed or incomplete fence cannot create an overlay.
This still cannot claim Drive transaction atomicity when Google omits a revision ID.

## GO/NO-GO and next operator action

**NO-GO for initial canonical import.** The 84 score value differences and 21 lifecycle
membership weight differences affect imported canonical inputs. The 1,018 formula text
differences are not yet syntax-classified. Do not replace those inputs with current live
values automatically, infer lifecycle from holdings, or widen the bootstrap to optional
model outputs.

Run the v3 read-only comparator from the authorized Windows PowerShell environment. It
will create a private v3 exception ledger with the raw formula/value evidence needed to
classify the changed formulas and inspect numeric score/weight deltas. If the source
metadata no longer matches the frozen artifact, reacquire a new snapshot and compare that
exact run. Reconcile all changed score and lifecycle values with an investor-authoritative
source before proceeding to another bootstrap preview.

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run source:workbook:compare-values -- '<PRIVATE_PORTFOLIO_RUN_ID>' `
  --store $store `
  --scope canonical-bootstrap `
  --confirm-read-only-live-comparison
```

This command performs only bounded read-only Drive metadata and Sheets API requests. If it
returns `SOURCE_ADVANCED_REACQUIRE_REQUIRED`, use the existing portfolio acquisition command
to freeze the current source, then rerun the comparison with its new run ID. Do not disable
or bypass a restricted proxy.

After rerun, source-fidelity GO requires: stable consistency fence, matching selected
values or a reviewed field-specific importer-equivalence determination, no unexplained
formula-definition changes on relied-upon cells, no formula errors/unavailable required
values, exact identities, and no unreviewed canonical-value differences. Schema acceptance
and production apply remain separate operator approvals.
