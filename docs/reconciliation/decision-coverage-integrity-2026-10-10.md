# Decision Coverage & Integrity — 2026-10-10

This reconciliation uses the local canonical PostgreSQL database at the current
cutoff. It records new immutable ranking and Execution Pace snapshots without
changing holdings, target allocations, lifecycle, assessments, model assumptions,
accepted model revisions or historical source facts. Machine-readable counts and
run identities are in [the JSON report](decision-coverage-integrity-2026-10-10.json).

## Decision-layer coverage

| Layer                       | Before this reconciliation                                                                     | Latest canonical state                                                                                                                                                                                                        |
| --------------------------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Portfolio Rank              | Run `ecce3252-df8f-4da2-a411-d5c331878dca`: 0 ranked, 16 `DATA_CHECK`, 5 `INPUTS_UNAVAILABLE`  | Run `52ffc6ae-2825-4cad-9f3e-a35e93bf0d80`: unchanged; all 16 current-weight checks remain blocked and five companies still lack authored targets                                                                             |
| Watchlist Rank              | Run `dfc9b27f-33d7-4f22-b477-50e49e008227`: 0 ranked, 59 `DATA_CHECK`, 12 `INPUTS_UNAVAILABLE` | Run `5b719264-e005-47e6-b1a7-b9330be4b411`: 0 ranked, 55 `DATA_CHECK`, 16 `INPUTS_UNAVAILABLE`. Four newly accepted native models replace prior unknown-method/currency checks with explicit stale-reference-price states     |
| Research Rank               | Run `367b6e87-6a4a-4baa-a920-6e2c5f888896`: 96 ranked, 5 unavailable, 118 not eligible         | Run `f88fa8cb-aeeb-4143-b446-e61863d01b55`: same coverage; 96 ranked, 5 unavailable, 118 not eligible                                                                                                                         |
| Estimate Momentum           | No available signal: Portfolio 0/21, Watchlist 0/71                                            | Unchanged. Portfolio has 17 `INSUFFICIENT_HISTORY` and 4 `NO_MAPPING`; Watchlist has 1 and 70 respectively. All 92 are `NO_DATA` for freshness                                                                                |
| Execution Pace              | No recorded run                                                                                | Run `085e9098-b526-4827-8a40-c9b39215b2ba`: 0 available, 21 `REVIEW`, 198 `NOT_APPLICABLE`                                                                                                                                    |
| Expected Return History     | All 92 Portfolio/Watchlist companies had partial history                                       | Still partial for all 92, with 273 points: 167 imported legacy revisions, 92 imported current contracts and 14 native revisions. 51 points have a classified method; only the 14 native points retain their exact quote basis |
| Expected Return Attribution | No complete, comparable historical change series                                               | Still unavailable for these 92 companies: 91 first/last comparisons are undated and one Watchlist company has no pair. Each of the 14 native models has only one accepted native revision                                     |

The Watchlist Rank state transition for Axon Enterprise, Comfort Systems USA,
Rubrik and Veeva Systems is deliberate: the new run now selects their accepted
native owner-cash-flow models, but those models have stale reference prices. The
old run's unknown imported method/currency state was not a useful current eligibility
answer. Their transitions are visible as four source-linked Rank Change items in
the Attention Center; no ordinal rank was fabricated.

Research Rank continues to use its existing candidate-only lifecycle and seed
semantics. Its five unavailable entries lack point-in-time lifecycle. No investment
ranking semantics or return-comparability rules changed in this reconciliation.

## Current input coverage and blockers

The portfolio has 21 held listings and exact current observations for all 21, but
only five quotes are fresh: ADYEN, ASML and NOVO-B have October 5 closes; CPRT and
UBER have October 9 closes. The other 16 held listings have October 2 closes, now
outside the five-day window. Portfolio valuation therefore remains
`INCOMPLETE_PRICE_COVERAGE`: 5/21 positions valued, 16 price gaps, 16/21 target
entries, and no current weights. FX is not the present blocker: the required
USD/EUR and DKK/EUR observations are already current through October 9, and no FX
pair was unmapped in the attempted provider preview.

A Yahoo preview targeted 19 exact Portfolio listing identities, including the 16
stale held listings. The local connection refused all 19 requests (`NETWORK_ERROR`,
Windows error 10061); FX refresh was not due. The preview applied no records, and
the prior observations remain canonical. The complete request report is
[decision-coverage-market-refresh-portfolio-dry-run-2026-10-10.json](decision-coverage-market-refresh-portfolio-dry-run-2026-10-10.json).

There are 9 native Portfolio models (all have numeric Expected IRR; six current
model-price references are fresh and three stale) and 5 native Watchlist models.
Only Toast currently has a complete Watchlist output, numeric return and fresh
reference price. Axon, Comfort Systems, Rubrik and Veeva have partial outputs and
stale model-price references. Current native return methods remain in three
distinct cohorts: seven standard enterprise UFCF, two enterprise H-model UFCF and
five owner-cash-flow equity models. No cross-method cohort was combined.

For Watchlist Rank, the latest run records 23 unclassified legacy methods, 31
unknown legacy currencies, one stale native reference price, 12 missing numeric
legacy returns, and four stale native listing observations. The 23/31/1 states
are `DATA_CHECK`; the 12/4 states are `INPUTS_UNAVAILABLE`. In Portfolio, the 16
`DATA_CHECK` states come from incomplete current market weights, and five missing
targets remain unavailable. No target was inferred from holdings or a prior rank.

Estimate Momentum has no current primary-provider continuity. The local database
has 67 imported legacy estimate observations, all marked `DATA_CHECK`, with the
latest snapshot dated September 12. There is no configured FMP API key and no
usable primary-provider mapping. The signal remains unavailable rather than
reusing stale or invalid observations. The five-year return-history issue also
remains: imported model outputs commonly lack source effective dates, and legacy
snapshots do not retain the quote used at calculation time.

Reported fundamentals are also absent from canonical state for this active
population: zero observations across 21 Portfolio and 71 Watchlist companies.
They therefore cannot refresh native assumptions or support forecast-versus-actual
comparisons. The current ranking and Execution Pace implementations do not consume
reported fundamentals directly, so no derived financial fact was substituted.

Score coverage remains 21/21 Portfolio and 71/71 Watchlist for Durability and
Compounder Quality. Execution and Risk assessments exist for 18/21 Portfolio
companies and 9/71 Watchlist companies. Those missing assessments were not
fabricated; they are not substitutes for the immediate quote, target and model
blockers above.

Ten Watchlist companies still have no exact canonical listing mapping, and among
the 61 with listings, 48 latest market observations are stale. The unresolved
companies are Accelleron Industries, BONESUPPORT, Exosens, Fabrinet, INVISIO,
Medistim, Meta Platforms, Nova, Rheinmetall and VINCORION. No ticker or ADR
substitute was introduced.

## Attention Center and dashboard

The portfolio dashboard remains explicit: five positions valued, sixteen price
gaps, sixteen authored targets and zero calculable current portfolio weights. No
strategic allocation change was made.

The 30-day Attention Center now returns 155 items after a temporal-integrity fix.
Previously, 92 undated bulk-import snapshots appeared recent only because their
database receipt fell inside the lookback window. Imported output events now
require a source effective date inside the window; the snapshots remain available
in Company history. The feed still shows 42 source-dated model-output imports,
14 native model revisions, 88 current data-quality states, 7 material price moves
and 4 Watchlist Rank state changes. The extra rank items explain the four native
model eligibility transitions above.

## Highest-impact remaining blockers

1. Restore outbound provider connectivity, then rerun the exact-listing market
   refresh and re-record decision snapshots. This can address 16 Portfolio quote
   gaps and stale Watchlist listings without changing listing identity.
2. Obtain explicit target evidence for the five untargeted Portfolio companies.
3. Resolve Watchlist identity mappings from authoritative issuer/exchange evidence;
   do not guess an ADR or ticker.
4. Complete the four partial Watchlist model outputs and refresh their model
   reference prices through an accepted revision/recalculation workflow.
5. Establish a valid, continuous primary consensus stream and mappings before
   enabling Estimate Momentum; do not rehabilitate the 67 `DATA_CHECK` rows as
   usable history without source reconciliation.
6. Preserve historical return gaps: source dates and exact legacy calculation
   quotes are absent for many imported outputs, so they cannot support point-in-time
   attribution.

## Verification records

The Portfolio, Watchlist and Research runs were created through the existing
`create_ranking_run` domain workflow. Execution Pace was recorded through
`create_execution_pace_run`. All four runs are immutable and tagged with source
`decision-coverage-integrity-2026-10-10`; the detailed post-run counts and dry-run
provider errors are in the linked JSON reports.

Verification passed: `npm run check` (lint, formatting, web/API typechecks, 87 web
tests, 224 API tests, contract check and production build), `npm run
test:integration` (43 database-backed tests), and `npm run db:check` (no schema
drift). The representative legacy ranking and signal parity tests in
`test_portfolio_rank.py`, `test_watchlist_rank.py`, `test_research_rank.py`,
`test_execution_pace.py` and `test_estimate_momentum.py` passed. The dashboard and
Attention Center Playwright flows passed on desktop and mobile (4 runs).
