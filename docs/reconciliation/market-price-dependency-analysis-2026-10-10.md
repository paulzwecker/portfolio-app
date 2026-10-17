# Market-price dependency analysis — 2026-10-10

The dependency trace below was recorded before the Milestone 6.9 behavior change;
the post-change rules follow it.

| Consumer                          | Current price basis                                                                                                                                                                                                                                                    | Historical/source price behavior                                                                                                                                                                              | Freshness behavior                                                                                                                                                                    |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Provider → canonical observations | `YahooFinanceProvider` resolves only an exact listing crosswalk (venue, ticker, currency, security type). `YahooChartNormalizer` checks returned symbol, exchange, currency and instrument type. Provider payloads and normalized observations retain source identity. | Replays append/deduplicate canonical observations; changed facts are corrections, not in-place overwrites.                                                                                                    | The adapter itself does not decide current-vs-stale; `listing_market_data` does.                                                                                                      |
| Current quote selection           | `domain.queries.listing_market_data` selects the latest effective market date, then quality tier, provider tier, current-quote kind and recorded time. `as_of` and `known_at` constrain both effective and knowledge time.                                             | Historical price queries use the same exact listing and point-in-time cutoffs.                                                                                                                                | Only PASS/PASS_VERIFIED_FALLBACK with a positive split-adjusted close can be fresh; age over five calendar days is STALE.                                                             |
| Portfolio valuation/weights       | `domain.queries.overview` uses the exact holding listing’s canonical selected quote, requires it within five days of the holdings date, and requires dated, eligible FX for non-base currencies.                                                                       | No model reference price or workbook price is used for holding value.                                                                                                                                         | A missing/stale/quality-checked price, old holdings-date match, or missing FX leaves the aggregate/weights null and identifies the gap.                                               |
| Native model calculation          | `domain.services._latest_model_market_price` selects canonical quote for `FinancialModel.valuation_listing_id`. DCF, owner-cash-flow and residual-income engines require a fresh quote in the model currency for price-sensitive outputs.                              | On acceptance, the immutable revision output stores `current_price`, `price_observation_id`, effective date and quality. These values are the revision’s original calculation basis, not mutable assumptions. | New edits/recalculations use the latest eligible canonical quote; quote changes alone do not create model revisions.                                                                  |
| Current Native Expected IRR       | Portfolio Rank and Watchlist Rank read the accepted `FinancialModelOutput`. They currently return DATA_CHECK when a later exact-listing quote exists than that output’s accepted reference quote; they do not recalculate the return from accepted assumptions.        | The accepted output and linked quote remain a valid historical revision snapshot.                                                                                                                             | A new fresh quote does not currently restore rank eligibility until the output is recalculated through a new accepted revision, even though quote changes are not assumption changes. |
| Imported legacy model outputs     | Imported `ModelOutputSnapshot` rows retain legacy outputs/provenance but have `share_price_basis_status=NOT_RETAINED` in expected-return history. Rank validation requires an explicit exact-listing, method, currency and retained price basis.                       | Cached workbook reference/output values remain historical migration evidence; they are not canonical current quotes.                                                                                          | These snapshots cannot silently stand in for a current canonical observation and remain unavailable/data-check where basis is absent.                                                 |
| Execution Pace                    | Its input builder joins the model point to market data for the model’s exact valuation listing. Weighted upside is derived from the point’s scenario-weighted Fair Value and the selected current quote.                                                               | Expected IRR in the input is still from the immutable model output/history point and its retained reference quote.                                                                                            | Pace requires a fresh exact-listing quote and a current-compatible model-price status; an older model basis is REVIEW.                                                                |
| Dashboard and Company/Universe UI | Frontend renders Portfolio, Market, Model, Rank and Execution API responses; it does not independently select prices or calculate returns.                                                                                                                             | Revision and expected-return history show the accepted/imported historical values and their source price context.                                                                                             | UI missing/stale states reflect API status.                                                                                                                                           |

## Provider failure diagnosis

The active Python transport uses `urllib.request.urlopen`, which honors standard proxy environment variables. In the local process, `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY` all resolve to the non-listening `http://127.0.0.1:9`; `NO_PROXY` does not include Yahoo. Requests through the configured proxy reproduce `WinError 10061` for both Yahoo chart hosts. The same exact HTTPS chart requests succeed with a proxy-disabled opener (HTTP 200). This identifies the refusal as the inherited local proxy route, not a Yahoo symbol, endpoint, response, or normalizer defect. A bounded Yahoo-domain `NO_PROXY` override is safe to test for the requested refresh; general proxy behavior should remain intact.

## Before-change conclusion

Current Portfolio price/weight gaps come from absent or stale canonical price observations, not from imported sheet prices being selected as live quotes. Separately, frozen native revision outputs correctly preserve their historical calculation basis, but current ranking and Execution Pace need a deterministic query-time recalculation from the same accepted methodology inputs and a fresh exact-listing quote. Such a derived current calculation must remain separate from the immutable revision output and must not author a new revision.

## After-change behavior

The shared read-only calculator now loads the effective accepted inputs for a
native model revision, selects the exact valuation listing's observation with
both cutoffs, enforces quote freshness and model-currency equality, and calls
that model family's deterministic engine. The current result is separate from
`FinancialModelOutput`; the original accepted quote, output, assumptions and
history remain unchanged. A stale or currency-incompatible quote produces null
Expected IRR and Expected Excess while retaining model Fair Values and an explicit
price status.

Portfolio Rank and Watchlist Rank use the current native calculation and record
its normalized output, current quote observation, and the accepted source price
in each new immutable run. Execution Pace selects the same current calculation
for native revisions; its snapshot separately retains the accepted reference
price and the latest portfolio quote. Historical ranking/execution runs and
historical expected-return points are not rewritten. Imported workbook output
snapshots still cannot be recalculated without accepted inputs and never use
cached workbook prices as current quotes.

## Live reconciliation after refresh

The local refresh restored fresh prices on all 21 exact held company listings
and the separately held SPYY listing. Company positions were individually
valued from their exact fresh listing prices. Aggregate portfolio valuation
and current weights remained unavailable because the unchanged holdings snapshot
is effective 2026-10-04 and is six days old at the review cutoff; its USD cash
cannot be converted using FX observations first effective on 2026-10-09 without
look-ahead. The live overview reports one gap, `cash:USD / FX_UNAVAILABLE`, and
`INCOMPLETE_HOLDINGS`.

Fresh-price query calculations are available for all nine accepted native
Portfolio models and all five accepted native Watchlist models. Ranking and pace
previews were run without retaining a new snapshot. Portfolio Rank remains
blocked by the stale aggregate weights for 16 companies and missing authored
targets for five. Watchlist Rank remains blocked by method/currency/data-quality
gaps. Execution Pace remains `REVIEW` for all 21 Portfolio companies: 16 require
complete weights and five lack explicit targets. The machine-readable counts
and ingestion replay evidence are in
`market-data-model-freshness-recovery-2026-10-10.json`.
