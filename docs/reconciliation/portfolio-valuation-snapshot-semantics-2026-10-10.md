# Portfolio Valuation & Snapshot Semantics

**Milestone:** 6.10b  
**Database:** local PostgreSQL  
**Valuation checked:** 2026-10-10 21:33 UTC

## Result

The current portfolio value is now available at **€58,453.85** from all 22 accepted security positions, EUR and USD cash, exact-listing prices, and dated FX. The prior complete holdings snapshot remains dated 2026-10-04 and is **6 days old**. The dashboard labels it stale but does not discard valid current market observations or imply that current prices refreshed holdings quantities.

Before the change, all 22 held listings had fresh prices, but none could be applied to the October 4 holdings snapshot under the current-valuation query. The query incorrectly tied the freshness of price/FX observations to the holdings effective date and separately rejected the six-day-old snapshot. USD cash consequently lacked FX, and total value, weights, and target gaps were unavailable.

## Valuation semantics

The ordinary overview request is a current mark-to-market. It selects the latest accepted holdings and target snapshots known at the valuation cutoff, then independently selects each exact listing’s eligible fresh price and each needed dated FX observation. Quote and FX effective timestamps are returned separately. Nineteen cross-currency security marks are explicitly `NON_SYNCHRONOUS`; their price and FX timestamps differ. Three EUR positions require no FX. No held positions have unknown quote times in the current data.

An explicit `as_of` request remains a historical reconstruction: holdings effective/recorded times, price market/observed/recorded times, and FX effective/observed/recorded times are all bounded by that cutoff. Regression tests confirm newer quotes and FX do not leak into an earlier valuation. Calculations are read-only and repeatable; this milestone did not write new holdings, targets, model revisions, rank runs, or Execution Pace runs.

## Current portfolio coverage

- Security positions valued: **22/22**; company weights: **21/21**. Company, standalone-security, and cash weights sum to **100%** at stored precision.
- EUR cash: €1,301.68. USD cash: $3,433.45, converted at USD/EUR 0.8924 effective 2026-10-09 21:29 UTC, for €3,064.01.
- Sixteen companies have target gaps. Targets remain absent for **AMD, CELH, HIMS, MSCI, and NVO**; no values were inferred.
- Largest current company exposures are Alphabet (8.59%), ASML Holding (8.22%), Amazon (8.01%), MercadoLibre (7.52%), and AMD (7.43%). AMD has no accepted target.
- Full values, dates, weights, timing states, and reconciliation counts are in [the machine-readable report](portfolio-valuation-snapshot-semantics-2026-10-10.json).

Portfolio Rank remains at 0 ranked: 16 entries are `DATA_CHECK` because the holdings confirmation is stale, and five are `INPUTS_UNAVAILABLE` because the targets are missing. Execution Pace remains unavailable for all 21: 16 require review for stale holdings and five lack target rows. This preserves the documented requirement for fresh position confirmation and explicit strategic targets even though the factual current mark is available.

## Presentation and verification

The Portfolio page distinguishes current mark-to-market from historical as-of, shows valuation/market/FX cutoffs, holdings confirmation age, per-position quote and FX timing, currency-specific cash balances and weights, and explicit non-synchronous timing. Market-session dates are displayed as dates; exact current-quote and FX timestamps remain separate. Percentages, including Expected IRR, hurdle, upside, and weights, are displayed to one decimal place without changing API or calculation precision.

Deterministic API tests cover later prices/FX against an older holdings snapshot, historical no-look-ahead behavior, EUR/USD cash, exact listing and FX requirements, stale holdings versus stale quotes, missing inputs, timing states, and read-only repeatability across holdings, prices, FX, targets, models, rankings, and execution history. Frontend contract tests cover explicit unavailable/timing states. The responsive Portfolio dashboard test checks that quote observation times appear alongside stale-holdings disclosure.

Verification passed: `npm run check` (lint, formatting, frontend typecheck, API mypy, 89 frontend tests, 236 backend tests, contract check, production build); `npm run test:integration` (46 PostgreSQL integration tests); and `npm run test:e2e` (24 passed across desktop/mobile, 10 live-only tests skipped under the default configuration). After the final UI wording and history-count assertions, frontend lint/typecheck/tests/contracts, the browser suite, and the targeted PostgreSQL regression passed again. `git diff --check` is clean.
