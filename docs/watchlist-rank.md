# Canonical Watchlist Rank

Watchlist Rank v3 is the first calculated member of the existing ranking run
infrastructure. It applies the documented `Universe Registry!M4:P` rule to
companies whose lifecycle is explicitly `WATCHLIST` as of the run:

1. Expected IRR descending.
2. Canonical listing ticker ascending for equal values.

This is an ordinal sort, not a composite score. A missing Expected IRR is
`INPUTS_UNAVAILABLE`; no zero or neutral value is substituted. A positive position
is assigned only to a supported input. Other lifecycle states are `NOT_ELIGIBLE`.
Runs and per-company entries are immutable and include the input/source snapshot used
to explain the result.

## Input policy

Native model revisions expose shareholder-cash-flow Expected IRR. Imported normalized
legacy outputs preserve the legacy Expected IRR field. Those semantics are not
assumed to be comparable. When at least one eligible native return is available, a
run ranks the native cohort and marks legacy-only candidates `DATA_CHECK`. When no
native return is available, a run may rank current legacy contract outputs that have
PASS contract validation, complete or partial output quality, documented currency,
no field-level IRR issue, and an unambiguous listing ticker. The entry snapshot keeps
the source record, model/revision identity where available, effective and recorded
times, return semantic, currency, listing, native reference-price evidence,
migration status and surrounding model outputs.

Native returns require one unambiguous accepted native model series, a non-null
Expected IRR, matching documented model/output currency, and a fresh exact-listing
reference price no more than five calendar days old. A later exact-listing price
known at the run time makes the model output a `DATA_CHECK`; the run never silently
uses a stale valuation. Multiple effective model series, unknown listing identity,
duplicate canonical ticker tie keys, unknown legacy currency, and imported
IRR-field issues also remain `DATA_CHECK`.

10Y Durability, Compounder Quality, Forward Fundamental CAGR, Fair Value, Hurdle and
Expected Excess are retained as separate context and are displayed in Company and
Universe. The rules do not document numeric quality/durability thresholds or a
portfolio-fit adjustment for this rank. The system therefore does not infer a
pass/fail quality gate, combine the dimensions, or adjust positions. The active
Watchlist list is the formula population; score absence remains explicitly visible
in context. This preserves the hierarchy without inventing a gate rule. The legacy
Watchlist **Portfolio Candidate Rank** remains a separate Fit-Tier-first concept.

Creating a run is a manual, auditable action from Universe with actor, reason and
source. It does not alter lifecycle, model inputs, targets or holdings. New source
records and later lifecycle changes cannot regenerate previous runs.

## Workbook comparison

The reference is `Portfolio_Watchlist.xlsx`, SHA-256
`27F1889A7185E8759486409490DB4D52C694F0084D0A914B234A1E251AB78CE9`. The sorted
application formula reproduces nine representative leading cached examples exactly:
ATAT, RELY, NU, MNDY, GRAB, TOST, APP, KVYO and MEDI. A source scan found 74 explicit
Watchlist rows (71 cached positive ranks and three blank ranks); 73 Expected IRR
cells parsed numerically and one was text (`-6%`). For the rest of the cache, the
documented formula disagrees with 62 positions, and six cached rank positions are
duplicated. This is not full-universe workbook parity: the old cache may be stale or
may reflect other undocumented state. We preserve the source cache as imported
history and do not reverse-engineer or overwrite it. The structured evidence is in
[`reconciliation/watchlist-rank-legacy-2026-10-05.json`](reconciliation/watchlist-rank-legacy-2026-10-05.json).

## Current development run (2026-10-05)

Definition v3 recorded run `64ddcdf9-d5be-46b2-be47-c7c6dcf6b4b4` over the 219-company
universe, including 71 explicit Watchlist members. Fourteen members received ranks,
45 are `DATA_CHECK`, and 12 are `INPUTS_UNAVAILABLE`; the remaining 148 are outside
the Watchlist population. All 14 positions use the legacy normalized-output cohort.
The source workbook has 74 explicit Watchlist rows, so its historical membership
does not exactly match the application's 71 canonical members; the run follows
current application lifecycle state and does not alter membership to force parity.
No valid native return was available for comparison: the sole native Watchlist model
(Toast) is blocked because an exact-listing price observation postdates its accepted
output reference price. Among the 45 data checks, 35 have unknown model currency, nine
have ambiguous or missing listing mappings, and one is the stale native reference
price. All 12 unavailable entries lack numeric Expected IRR. These are source/data
coverage states, not failures of the ordinal sort. The run record and counts are
captured in the reconciliation JSON above. The latest run snapshots inputs and
source context for ranked and `DATA_CHECK` entries, so eligibility failures can be
reviewed against the exact observations available at run time.

## Current limitations

- A single ordinal run cannot compare legacy normalized Expected IRR with native
  shareholder-cash-flow IRR until an accepted equivalence/reconciliation rule exists.
- The current native-first cohort policy can make coverage sparse while older
  normalized outputs remain `DATA_CHECK`.
- Numeric durability/quality gate thresholds are unresolved. No gate result is
  emitted by the rank.
- Portfolio Rank is now active with the documented Portfolio Score; current input
  coverage and semantics are in [portfolio-rank.md](portfolio-rank.md).
- Research Rank is now active from imported Candidate High/Low tier and deep-dive
  seed; source parity and unavailable lifecycle cases are in
  [research-rank.md](research-rank.md).
- Candidate Rank has not been migrated.
- Legacy Expected IRR values with unknown effective dates can be used only in a
  run recorded after their source record was imported; the snapshot labels effective
  time `UNKNOWN` rather than backdating it.

The next ranking work should first reconcile native and legacy Expected IRR
semantics on overlapping companies. It should not add a composite rank or enable
Candidate Rank as a substitute.
