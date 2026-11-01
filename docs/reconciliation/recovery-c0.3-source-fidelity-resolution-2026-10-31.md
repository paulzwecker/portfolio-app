# Recovery C0.3 — Source-Fidelity Resolution

## Decision

**NO-GO for Portfolio schema acceptance and canonical bootstrap preview.** The exact
source values are available for operator review in a private local decision package, but
they have not been approved. One importer-consumed formula definition remains unresolved,
105 formula-derived values remain pending individual review, and five keyed companies still
have unresolved lifecycle inputs. No schema acceptance, workbook edit, Neon connection,
database mutation, or overlay approval occurred.

## Comparison evidence

The v5 comparison completed a stable two-read comparison of 7,861 canonical-bootstrap
cells. Source metadata matched the frozen acquisition; values and formula definitions were
stable across both reads. A Drive revision identifier was unavailable. The completed report
omitted its `scope` field. C0.3 verifies scope from the matching durable start record for the
same run, comparison contract, attempt and timestamp; it does not infer scope from a sample
or merely from matching output values. New completed reports now persist `scope`. The report
recorded 108 source-fidelity observations, which C0.3 reclassified against the actual
importer row-selection behavior:

| Finding                                         |   Count | C0.3 treatment                                                 |
| ----------------------------------------------- | ------: | -------------------------------------------------------------- |
| Changed importer values                         |     105 | Pending operator review; live values are proposals only        |
| Consumed formula-definition difference          |       1 | Remains unresolved and blocks overlay candidate generation     |
| Empty formula caches on an unkeyed registry row |       2 | Not consumed by the importer; excluded from lifecycle blockers |
| **Importer-relevant review items**              | **106** | **All unresolved**                                             |

The two empty formula caches are on a registry row without a canonical company key. The
canonical importer skips that row. They do not belong to, or explain, the five unresolved
lifecycle records. The comparison consumer gate now follows this row-selection rule.

The acquisition manifest's semantic fingerprint covers the full imported workbook domain,
while the comparison fingerprint is scoped to canonical-bootstrap fields. Those hashes are
not interchangeable. Candidate validation now recomputes the canonical-bootstrap fingerprint
from the exact frozen XLSX and compares it with the scoped comparison fingerprint; raw artifact
hash and fingerprint-version checks remain in place.

## The 105 changed values

All 105 are formula-derived numeric score or legacy membership inputs. Their expanded
source formula text matches the corresponding live formula text, and the v5 live values were
stable across two reads. The discrepancies remain `STALE_XLSX_CACHE_CANDIDATE` findings:
without a Drive revision identifier or other authoritative calculation record, the evidence
cannot distinguish an XLSX cache that was stale at export from a recalculation after export.
The stable values do not authorize replacement.

Formula-resolution evidence for these 105 cells comprises 72 shared-formula translations, 5
shared-formula anchors and 28 direct formulas. All 105 expanded definitions match their
live formula text exactly; no algebraic equivalence or value-based formula normalization was
applied.

| Importer target                        |   Count |
| -------------------------------------- | ------: |
| 10Y Durability score                   |      41 |
| Compounder Quality score               |      40 |
| Execution score                        |       2 |
| Risk score                             |       1 |
| Legacy current-weight membership input |      21 |
| **Total**                              | **105** |

The private package presents both exact values and the original formula evidence for each
entry. No live value has been accepted, and no absent value has been converted to zero.

## Consumed formula difference

One `Price Feed` auxiliary row-class formula is consumed as a gate by the importer when it
decides whether to emit a supported auxiliary listing record. It has no direct persisted
row-class destination. The frozen XLSX expression contains an export-only unsupported-function
placeholder absent from the live formula; the cell-reference sets and current output match.
This is consistent with a possible XLSX formula-serialization translation, but the available
evidence does not prove equivalent function semantics. It remains a blocker.

Resolve it with authoritative workbook-owner/source-contract evidence, a corrected source
and a new frozen acquisition, or a separately reviewed narrow importer-contract change with
regression tests. Do not suppress the formula difference based on current output equality.

## Lifecycle and source-only reconciliation

Five keyed companies remain lifecycle-unresolved because the source does not provide a
complete, decisive combination of membership weights and explicit research bucket. The two
unkeyed empty formula caches described above are unrelated. The private package has a
pending decision record for each unresolved company; no lifecycle was inferred.

Frozen-workbook parser counts (not a database preview): 219 companies, 100 securities, 100
listing records, 22 held positions, 2 cash rows, 16 targets, 506 score assessments and 657
cached ranking entries. All 22 held positions resolve to exact listing identities in this
source-only projection. Other parser errors remain: 11 incomplete listing records, 3
unresolved listing mappings, 11 duplicate cached rank positions and 2 invalid cached rank
values. These are still importer blockers or explicit data-quality exceptions. The five
unresolved lifecycle rows are not included in any inferred lifecycle count.

## Overlay status

The existing review-gated overlay workflow was exercised against the v5 evidence. It
correctly refused to generate a candidate because the consumed formula difference remains
unresolved. The private validation ran directly against the frozen snapshot and did not write
a candidate file. **No overlay candidate exists; its SHA-256 is null.** The 105 value proposals
cannot enter the importer until the formula blocker is resolved and a candidate passes the
existing validation contract. The two unkeyed formula-cache observations do not justify an
overlay.

## Operator action

Review the private decision package under the user-scoped temporary review directory
`PortfolioResearchC03Review`. It contains company identities, exact source coordinates,
original XLSX and live values/formulas, the five lifecycle records and pending decision
fields. Do not copy it to Git or a shared report.

For each of the 105 changed values, record an explicit decision and evidence. Resolve the
one formula discrepancy using one of the evidence-backed paths above. Review all five
lifecycle records individually; supply authoritative membership evidence or preserve their
unresolved state. Only then rerun the overlay candidate command. Any later overlay approval
requires reviewing the exact generated candidate and its hash using the existing explicit
`source:workbook:value-overlay approve` workflow. Schema acceptance and production import
remain separate later approvals.

The current source is **NO-GO**. Remaining listing and cached-ranking errors also prevent
the canonical import from being considered ready.

## Verification

- Workbook value-comparison and overlay tests plus offline canonical-bootstrap tests: 89
  passed after final scoped-fingerprint changes; 6 integration/source-data tests were
  deselected from this unit/offline run.
- Isolated local PostgreSQL canonical-bootstrap resume/idempotency and read-only-preview
  tests: 2 passed on the verified local `portfolio_app_test` target; per-test schemas were
  used and dropped.
- Ruff checks for changed source/tests: passed.
- Mypy for the two changed source modules: passed.
- No Google API request, workbook edit, schema acceptance, Neon connection, production write,
  or production migration occurred.
