# Portfolio Decision Recovery — 2026-10-16

## Result

The application can mark the latest accepted holdings at current prices, but
the accepted holdings confirmation is 12 days old. The Portfolio page now lets
the investor verify or edit the recorded quantities and cash, then explicitly
append a new complete snapshot. No snapshot, target, ranking run or execution
run was accepted during this milestone.

The current snapshot has 22 security rows and EUR/USD cash. Its current
mark-to-market is EUR 57,825.38722904, with all 22 position rows priced, no
price/FX valuation gaps, the latest held quote session on October 15 and FX data
through October 16. Holdings confirmation freshness is separate from market
freshness.

The accepted target revision remains unchanged. Targets are still missing for
AMD, CELH, HIMS, MSCI and NVO. The Portfolio page surfaces these as investor
decisions and leaves their target weights and allocation gaps null.

## Eligibility evidence

The actual persisted decision runs remain the October 10 records. A rollback-only
database preview recomputed all three layers first against the stale snapshot,
then against an in-transaction simulation that appended the same quantities and
cash with a fresh effective time. The transaction was rolled back and a follow-up
API read confirmed that no canonical state changed. The full counts and run
identities are in
[`portfolio-decision-recovery-2026-10-16.json`](portfolio-decision-recovery-2026-10-16.json).

Before simulated confirmation, Portfolio Rank had 0 ranked, 16 `DATA_CHECK`, 5
`INPUTS_UNAVAILABLE` and 198 `NOT_ELIGIBLE`; the 16 active candidates failed on
the stale holdings confirmation. After the simulated confirmation, it still had
0 ranked, with 13 `DATA_CHECK` and 8 `INPUTS_UNAVAILABLE`. Remaining blockers are
mixed or unresolved return-method cohorts, four legacy returns that did not
retain their exact-listing price basis, one legacy contract outside complete
`PASS`, and eight missing target or Portfolio Score inputs. The five missing
targets remain unavailable; no weight was substituted.

Watchlist Rank is independent of holdings confirmation. It remained at 0 ranked,
59 `DATA_CHECK`, 12 `INPUTS_UNAVAILABLE` and 148 `NOT_ELIGIBLE`. The 59 checks
come from 31 unknown legacy currencies, 23 unclassified legacy methods and five
mixed or incompatible return bases. Twelve Watchlist companies have no numeric
Expected IRR. These are return-source and coverage gaps, not rank-order defects.

Execution Pace moved from 0 available / 21 `REVIEW` before confirmation to 3
available / 18 `REVIEW` in the simulated fresh-snapshot run; 198 other companies
remain `NOT_APPLICABLE`. The three previewed states were `WAIT_LIMIT` for
Intuitive Surgical, Mastercard and Microsoft because each modeled Expected IRR
was below its hurdle. They are decision snapshots, not orders. The remaining
reviews are eight model outputs without effective timestamps, five branches
without usable point-in-time Estimate Momentum history and five missing target
decisions.

## Input and history decisions

The legacy price-regime snapshots were dated October 1 and therefore stale. The
same exact-listing canonical price series had 252-session analytics through
October 14 or 15 for all 22 Portfolio lifecycle listings. Execution Pace now
prefers a fresh, passing mapped legacy regime label; when that label is missing,
stale or unmapped, it may use the existing canonical `trend_state` calculated by
`split-adjusted-price-history-v1`. The run snapshot records the selected source
method and date. The broader, incompletely documented legacy regime is not
recreated, and stale or incomplete analytics still require `REVIEW`.

The holdings form opens with the most recent complete snapshot, preserves exact
listing IDs and currency cash, requires a reason and explicit confirmation, and
uses zero for an exited listing. Editing values resets the confirmation checkbox.
Successful confirmation reloads the canonical overview; the old snapshot remains
in history. Portfolio Rank and Execution Pace actions remain disabled while the
holdings snapshot is stale, incomplete or not fully valued. Watchlist Rank stays
on its existing explicit run action because holdings do not determine its
population.

## Remaining work

An investor must review the 22 quantities and EUR/USD cash before using the new
confirmation action. After that, fresh Portfolio Rank and Execution Pace runs
can be recorded explicitly. To raise their coverage further, resolve return
method/currency/price-basis mapping and missing score inputs, obtain effective
dates for imported model outputs, accumulate legitimate estimate history, and
author or leave the five strategic targets intentionally missing. No target,
model assumption, lifecycle or holding was changed here.
