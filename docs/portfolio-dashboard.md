# Portfolio experience

The Portfolio route answers: **What do I own, what is it worth, and how is the
portfolio positioned?** It composes canonical API results; the browser does not
derive market value, portfolio weights, allocation gaps, Expected IRR, rankings
or Execution Pace.

The page structure and interaction rationale are recorded in
[Milestone 11D — Portfolio Experience](design/portfolio-experience-11d.md).

## Information architecture

1. **Overview** leads with the canonical current portfolio value, position
   count, cash currencies, largest company exposure, valuation cutoff, holdings
   confirmation age, market/FX dates and important valuation or target gaps.
2. **Holdings** presents every accepted snapshot position with exact listing ID,
   ticker, venue, listing currency, quantity, latest price, base-currency market
   value, current weight and company target/gap where the API supplies them. The
   table sorts display rows only. Cash remains shown by original currency.
3. **Allocation and exposure** shows API-provided company, standalone-listing
   and cash weights in one composition view, the largest accepted target gaps,
   and source target revision. Sector, geography and business-model grouping
   remain unavailable until canonical classifications support them.
4. **Performance** explicitly reports unavailable until transaction and
   cash-flow history supports a genuine portfolio return series. Historical
   prices applied to today's holdings would be a hypothetical series, not actual
   portfolio performance.
5. **Decision context** is provided in the dedicated `/decisions` workspace,
   which compares allocation and targets, separates return comparability
   cohorts, explains recorded Execution Pace, and shows API-supplied cash and
   issuer concentration context. Portfolio continues to own holdings
   confirmation and does not duplicate the comparison workspace.
6. **Confirm holdings** starts from the latest complete snapshot and lets the
   investor verify or edit exact listing quantities and cash by currency.
   Explicit confirmation appends a complete snapshot with actor, reason and
   effective time. It does not rewrite the source snapshot or market marks. Zero
   represents an exited listing.

## Source and missing-data behavior

The dashboard consumes `GET /portfolios/{id}/overview`,
`GET /universe/ranking-summary`, `GET /universe/execution-pace-summary`,
`GET /universe/score-summary`, `GET /universe/estimate-momentum-summary`, and
`GET /universe/model-output-summary`. The API supplies portfolio valuation and
allocation values and retains point-in-time rank and Execution Pace inputs.
Current model outputs are shown separately from the historical rank snapshot.
When several model outputs exist, each is disclosed separately; the UI does not
choose or blend one.

Holdings rows start with accepted snapshot positions and join price and
valuation context by exact listing ID. If identity or valuation context is
missing, the recorded quantity/listing remains visible while price, value and
weight stay unavailable. The composition bars display API-provided weights as
received and are not normalized or summed in the browser. Currency exposure is
shown as the original cash balance and its API-provided base-currency mark.

Unavailable values remain text states such as `No run`, `No model`, `Not
assessed`, `No mapping`, `Review`, or `Unavailable`. Risk remains its own score
dimension, where a higher score means more risk. Estimate Momentum availability,
freshness and confidence remain distinct.

The Attention Center is a read-only query across immutable model, estimate,
price, filing, ranking and Execution Pace records. It uses conservative
domain-specific comparisons, preserves source and effective/recorded times, and
does not create a second event store. See [Attention Center](attention-center.md)
for thresholds and coverage limits.

## Current product limits

- Company concentration is shown through current company weights; sector,
  geography, factor and look-through exposure are not calculated because those
  canonical classifications are not complete.
- There is no order-sizing or trade recommendation. Execution Pace is shown with
  current/target context but never changes holdings or strategic targets.
- Current mark-to-market uses the latest accepted holdings quantities with fresh
  exact-listing prices and dated FX at the valuation cutoff. The dashboard shows
  positions-as-of, market-session dates, exact quote/FX timestamps, non-synchronous
  marks and holdings confirmation age separately. A stale holdings snapshot can be marked for context,
  but Portfolio Rank and Execution Pace remain in data-check/review until holdings
  are reconfirmed. Partial valuations keep aggregate totals, weights and gaps null.
- Missing targets for held Portfolio companies are surfaced as investor decisions.
  The dashboard assigns no default weight; the five current gaps are AMD, CELH,
  HIMS, MSCI and NVO. Analytical runs remain append-only and are enabled only
  after the holdings baseline and current valuation pass structural checks.
- Portfolio Rank and Execution Pace run actions are explicitly gated while the
  holdings confirmation is not fresh or the valuation is incomplete. The UI
  explains the blocker; it does not silently create a run or modify holdings,
  target weights, lifecycle or model assumptions.
- Historical portfolio performance remains unavailable until transaction and
  cash-flow history supports a genuine return series. The page does not label a
  historical-price series on today's holdings as realized portfolio return.
- The page shows the latest recorded runs and revisions supplied by the
  canonical domains; it does not infer missing historical state.
