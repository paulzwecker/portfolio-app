# Portfolio dashboard

The Portfolio route is the read-first view of canonical holdings, strategic
targets and current analytical/decision context. It composes existing API
results; the browser does not derive market value, weights, allocation gaps,
Expected IRR, rankings or Execution Pace.

## Information architecture

1. **Portfolio posture** shows the API-valued portfolio total, accepted invested
   and strategic-cash targets, the largest currently valued company exposure,
   and the latest immutable Execution Pace run.
2. **Allocation review** highlights the largest API-provided target gaps and
   keeps cash, FX and price-coverage gaps visible. A positive target-minus-current
   gap means a company is below its accepted target. The display does not make
   an allocation recommendation.
3. **Capital review** shows current holdings and target companies with current
   portfolio weight/value, strategic target, latest Portfolio Rank, current
   normalized model output, Estimate Momentum and Execution Pace. Scores,
   model source details and pace input snapshots are progressively disclosed.
4. **Watchlist opportunities** uses Watchlist Rank independently from Portfolio
   Rank and exposes model, score, estimate and source context without adding a
   Watchlist company to holdings or targets.
5. **Attention Center** shows material source-linked changes and current review
   states, with company, event, lifecycle, severity and status filters. It uses
   the dedicated canonical feed rather than treating every recent record as an
   alert.
6. **Data and model checks** calls out explicit missing, stale, partial,
   unranked and review states returned by canonical domains.
7. **Record a new analytical review** is collapsed by default. It appends a
   Portfolio Rank or Execution Pace run and never edits upstream portfolio or
   model state.

## Source and missing-data behavior

The dashboard consumes `GET /portfolios/{id}/overview`,
`GET /universe/ranking-summary`, `GET /universe/execution-pace-summary`,
`GET /universe/score-summary`, `GET /universe/estimate-momentum-summary`, and
`GET /universe/model-output-summary`. The API supplies portfolio valuation and
allocation values and retains point-in-time rank and Execution Pace inputs.
Current model outputs are shown separately from the historical rank snapshot.
When several model outputs exist, each is disclosed separately; the UI does not
choose or blend one.

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
- Holdings can be fully valued only with complete, fresh listing prices and
  dated FX. The API keeps portfolio weights and gaps unavailable when those
  inputs are not comparable.
- The page shows the latest recorded runs and revisions supplied by the
  canonical domains; it does not infer missing historical state.
