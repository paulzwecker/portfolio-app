# Return Comparability & Decision Eligibility Recovery — 2026-10-16

## Result

The live canonical database supports current, exact-listing recalculation for all 14 active native models: 9 Portfolio and 5 Watchlist. Current rank previews remain at zero ranked entries. No accepted model, holdings, target, lifecycle, ranking, or execution history was changed. The full 92-company active-universe company-by-company audit is in the companion JSON report.

## Current eligibility

| Layer          |                  Current read-only preview | Main blocker                                                                                                                                                         |
| -------------- | -----------------------------------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Portfolio Rank |    0 ranked; 16 data checks; 5 unavailable | 16 targeted positions use a holdings confirmation 12 days old; 5 held Portfolio companies have no authored target.                                                   |
| Watchlist Rank |   0 ranked; 59 data checks; 12 unavailable | 66 output-only contracts have no classified return method; 43 have unknown currency; all output-only contracts lack historical share-price basis and effective date. |
| Execution Pace | 0 available; 21 review; 198 not applicable | 16 portfolio decisions fail on stale holdings confirmation; 5 fail on missing explicit target.                                                                       |

Counts match the latest persisted rank and execution runs (Portfolio Rank 16 data checks / 5 unavailable; Watchlist Rank 59 data checks / 12 unavailable; Execution Pace 21 review / 0 available). The fresh read-only preview was not persisted. Exact run IDs, as-of cutoffs, all company blockers, and a count-before/count-after persistence check are in JSON.

Before/after eligibility is unchanged: Portfolio Rank stayed at 0 ranked / 16
`DATA_CHECK` / 5 `INPUTS_UNAVAILABLE`; Watchlist Rank stayed at 0 / 59 / 12;
Execution Pace stayed at 0 available / 21 `REVIEW`. The persisted latest runs
precede the preview by minutes. This audit added no decision runs or entries.

For Portfolio, 16 companies with targets are currently gated by the 12-day-old
holdings confirmation. The other five still need investor-authored target
decisions: AMD, Celsius Holdings, Hims & Hers, MSCI Inc., and Novo Nordisk.
Three additional Portfolio Score gaps remain behind the holdings gate: dLocal,
Reddit, and Taiwan Semiconductor Manufacturing each lack the Execution and Risk
assessments. All other Portfolio Score dimensions are present.

For Watchlist, the per-company primary blockers are grouped as follows: 31
companies have unknown legacy model currency; 23 have an unclassified method; 12
have no numeric Expected IRR; and the five native owner-cash-flow models (Axon,
Comfort Systems USA, Rubrik, Toast, and Veeva) are withheld because this run
cannot choose a partial cohort around the unresolved legacy population. The
field-level gaps overlap: all 66 output-only contracts lack an effective date,
classified return method, linked valuation listing, and retained historical
quote basis; 43 also lack documented currency and 14 are not complete `PASS`
outputs. Three unique current listing candidates have model-currency conflicts
(Accelleron: USD vs CHF; Rheinmetall: SEK vs EUR; Spotify: EUR vs USD). Those
are unresolved model/listing basis checks, not permission to substitute or
convert.

## Comparability findings

The native Portfolio cohort comprises 7 `UFCF_ENTERPRISE_IRR@1` models and 2 `UFCF_ENTERPRISE_HMODEL_IRR@1` models. They cannot be combined into one Portfolio Rank. The standard enterprise cohort also spans USD and EUR; ranking rules preserve local currency and exclude FX return.

The native Watchlist cohort comprises 5 current `OWNER_CASH_FLOW_EQUITY_IRR@1` models. These all recalculate at current exact-listing prices. Their owner-available cash flow is an equity return convention, but not necessarily a forecast of cash distributions. They are blocked from ranking as a partial subset while the remaining Watchlist population contains unclassified/incomplete incompatible bases.

All 9 native Portfolio models and all 5 native Watchlist models recalculate at
fresh current exact-listing quotes. The Portfolio methods are 7 enterprise UFCF
v1 and 2 enterprise UFCF H-model v1. The Watchlist methods are 5 owner
cash-flow equity IRR v1. Residual-income is supported by the application, but
there is no active Portfolio or Watchlist native model in that family.

UFCF DCF v1/H-model v1 results are enterprise returns; the current model does not retain financing, future debt/cash, or payout schedules needed for an enterprise-to-shareholder bridge. Owner cash flow and residual income use equity perspectives with distinct cash-flow definitions and remain separately labeled. Native model and output revisions retain their original prices and effective dates; current calculations use newer exact-listing market prices without creating revisions.

Output-only legacy contracts cannot be safely upgraded with inferred method, effective date, or historical quote basis. Even where the company has a unique canonical listing, the imported row does not prove that the legacy model used that listing and currency. When multiple listings exist, such as TSM local ordinary versus US ADR, ambiguity is explicit. No FX/share-ratio bridge or historical date was fabricated.

## Execution Pace trend

The existing fallback is working: for native models with a unique exact valuation listing, a fresh passing mapped legacy regime remains preferred; when stale/unmapped, the calculation records the canonical `split-adjusted-price-history-v1` trend state and its date. The current preview records canonical-trend references for native holdings whose legacy regime snapshot is stale. No fallback is applied where the model/listing link is missing; those cases remain review states. The 10G preview helper is now read-only and shares the exact builder with persisted runs.

The canonical trend fallback was recorded for the 9 native Portfolio listings
with exact model/listing links. Twelve output-only Portfolio points did not have
a source-linked valuation listing; no company-level ticker guess was attached
to their model return to manufacture price-regime context.

## Migration candidates

No active output-only model is immediately importable solely from current comparison metadata. Prior migration evidence indicates the next safe investigation cohort remains the supported UFCF DCF tabs `P-AMD`, `P-ADYEN`, `P-BKNG`, `P-CELH`, `P-MELI`, `P-MSCI`, and `P-NVO`; these still require source mapping/parity, AMD share-basis reconciliation, MSCI input validation, or exact DKK/Copenhagen price-basis proof. `P-SPGI` remains unsupported SOTP. `P-MORN`, `W-DLO`, `W-RDDT`, and `W-TSM` are owner-cash style candidates requiring tab-specific methodology/parity; the Toast method is not generalized to them. TSM specifically must keep its TWD local ordinary and held USD ADR distinct. No model was migrated in this milestone.

## Tests and persistence

Backend return-semantics, portfolio-rank, watchlist-rank, and Execution Pace tests passed (45 tests). The Execution Pace preview/persist equivalence and no-insert behavior are covered by the database integration test. Ranking/execution run and entry counts before and after preview are recorded in JSON; previews do not mutate accepted history.

## Company-by-company audit

The JSON report lists every active Portfolio and Watchlist company with current rank state/reason, exact canonical listing candidates, model source/method/currency/date/price-basis state, current native recalculation (where applicable), score completeness, target/weight/holdings freshness, and Execution Pace inputs/trend provenance.
