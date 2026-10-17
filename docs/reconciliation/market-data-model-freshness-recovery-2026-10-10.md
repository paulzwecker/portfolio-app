# Market Data & Model Freshness Recovery — 2026-10-10

## Result

Yahoo Finance ingestion is operational from this machine when its two chart hosts bypass the inherited dead local proxy. The bounded refresh restored fresh prices for all 21 Portfolio company listings and the held SPYY listing, plus five exact Watchlist listings. Native current Expected IRR now recalculates from the latest eligible listing quote without changing accepted revisions.

The portfolio is still not usable for current weights or allocation decisions. Its latest holdings snapshot is the imported October 4 snapshot; it is six days old at this review cutoff and is not changed here. The only valuation gap is its USD cash: the snapshot is too old for the freshness policy, and the newer October 9 FX observations cannot be applied to an October 4 point-in-time balance. No look-ahead rate or fabricated balance was used. All 21 held company positions and the separate SPYY position have individually valued exact-listing prices, while portfolio total and current weights remain explicitly unavailable.

The original Phase 6 readiness issue is therefore partly resolved: quote coverage is restored, but portfolio-weight, rank and Execution Pace availability remain blocked by dated portfolio state and incomplete targets. This review did not record new ranking or Execution Pace runs.

## Dependency and price-basis findings

The application’s provider path is `YahooFinanceProvider` → exact venue/ticker/currency crosswalk and Yahoo response validation → append-only canonical price/FX observations → point-in-time query selectors → portfolio, model and decision consumers. The complete trace, including before/after semantics, is in [market-price-dependency-analysis-2026-10-10.md](market-price-dependency-analysis-2026-10-10.md).

The 16 stale Portfolio quotes came from missing/stale canonical observations. Legacy workbook prices were not selected as current market quotes. Imported `ModelOutputSnapshot` values remain historical evidence and are explicitly `NOT_RETAINED` when no exact historical share-price basis was migrated. Native accepted revision outputs retain their original quote observation and calculation; that accepted reference price is not overwritten when the market moves.

Current native calculations now load the effective accepted assumptions, request the exact model valuation listing’s quote under `as_of` and `known_at`, enforce quote freshness and currency equality, and call that model family’s deterministic engine. The result is a read-only query calculation. Portfolio Rank, Watchlist Rank and native-model Execution Pace snapshots use that current result when they are recomputed. No quote move creates a model revision. Imported legacy outputs cannot be re-priced without accepted inputs and remain historical.

The regression example is Alphabet: its accepted revision retains the original $338.24 reference price and accepted output, while its current query calculation uses the fresh $351.66 GOOGL observation. The API exposes both price bases and the derived outputs separately.

## Provider diagnosis and refresh

The Python HTTP transport honored process proxy variables pointing to `http://127.0.0.1:9` for `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY`. The proxy refused the connection with Windows error 10061. Requests through a proxy-disabled opener to both `query1.finance.yahoo.com` and `query2.finance.yahoo.com` returned HTTP 200. This was local proxy configuration, not a Yahoo endpoint, provider restriction, symbol mapping, transport-library or normalization failure. No alternate provider adapter was needed. The existing provider remains provider-independent at the domain boundary and retains Yahoo source identity.

The process-scoped `NO_PROXY` override for those two Yahoo hosts is documented in [external-data-operations.md](../external-data-operations.md). It preserves unrelated proxy settings. The applied refresh used exact checked-in mappings and returned no mapping or fetch failures:

| Scope                             |                                                             Before |                                                           After |                                                           Applied facts |
| --------------------------------- | -----------------------------------------------------------------: | --------------------------------------------------------------: | ----------------------------------------------------------------------: |
| Portfolio company listings        |                                            5/21 fresh; 16/21 stale |                                                     21/21 fresh |                                    195 daily prices; 1 corporate action |
| All held listings, including SPYY |                                            6/22 fresh; 16/22 stale |                                                     22/22 fresh |         Included the 21 Portfolio company listings and SPYY · ETR · EUR |
| Watchlist listings                | 13/61 mapped listings fresh; 48/61 stale; 10/71 companies unmapped |      18/61 mapped listings fresh; 43/61 stale; same 10 unmapped |                      31 daily prices for AXON, FIX, RBRK, TOST and VEEV |
| FX                                |           Exact current quote coverage incomplete for this refresh | Four dated rows added: USD/EUR and DKK/EUR, effective October 9 | These observations do not revalue the older October 4 holdings snapshot |

All refresh reports show `APPLIED`, exact mappings, no fetch failures and no unresolved listings. Yahoo chart responses also contained one corporate action, retained with the existing unverified status. A repeat import of exact `NASDAQ:GOOGL` over the same 90-day overlap inserted zero prices, zero FX rows and zero actions; it retained three new raw response payloads for audit. Canonical observation ingestion is idempotent while raw transport evidence remains append-only.

## Portfolio valuation and decision preview

The live portfolio API reports all 21 company positions and the standalone SPYY position as individually `VALUED` from fresh exact-listing prices. The aggregate remains `INCOMPLETE_HOLDINGS`, with a single `cash:USD / FX_UNAVAILABLE` gap. The imported holding snapshot is effective `2026-10-04T20:53:02Z`; as of October 10 it exceeds the five-day holding freshness window. Since balances and holdings were expressly out of scope for mutation, this review leaves them untouched. The accepted target revision is also unchanged; it has no authored target for AMD, Celsius Holdings, Hims & Hers, MSCI Inc. or Novo Nordisk.

Fresh quote-derived current returns are now available for all accepted native models with resolvable inputs: 9/9 Portfolio models and 5/5 Watchlist models. Phase 6’s prior report showed six Portfolio native model outputs with fresh reference-price status and three stale, and four Watchlist native models with stale listing quotes. Those old output snapshots remain preserved; the new availability comes from separate recalculation at current quotes.

The ranking and Execution Pace results below are read-only previews at `2026-10-10T18:19:29Z`. The Execution Pace service was invoked inside a PostgreSQL transaction and rolled back; no new runs were retained.

| Decision layer | Before refresh                                                                   | After refresh preview                          | Remaining blocker                                                                                                                                                                                      |
| -------------- | -------------------------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Portfolio Rank | 0/21 ranked; 16 `DATA_CHECK`, 5 `INPUTS_UNAVAILABLE`                             | 0/21; same status counts                       | Sixteen current weights unavailable because the imported snapshot is stale and USD cash cannot be valued at that snapshot’s cutoff; five targets are unauthored                                        |
| Watchlist Rank | 0/71 ranked; latest persisted state had 55 `DATA_CHECK`, 16 `INPUTS_UNAVAILABLE` | 0/71; 59 `DATA_CHECK`, 12 `INPUTS_UNAVAILABLE` | 23 unclassified legacy return methods, 31 unknown legacy currencies, 12 missing numeric legacy Expected IRRs, plus an incompatible/incomplete return cohort; ten companies lack exact listing mappings |
| Execution Pace | 0/21 available; 21 `REVIEW`                                                      | 0/21 available; 21 `REVIEW`                    | Sixteen require complete current holding weights; five have no accepted explicit target                                                                                                                |

The Watchlist status shift reflects native models becoming current-quote calculable; the eligible return population still cannot be ordered as one comparable cohort. No missing score, target, return, FX rate or company mapping was filled with a fallback.

## Integrity and verification

The Portfolio holdings snapshot and accepted target revision remain at their imported IDs and dates. Accepted model revision IDs, assumptions and frozen outputs remain unchanged. Previous ranking and Execution Pace runs are immutable and were not rewritten. The repeat-import report confirms zero duplicate canonical observations.

The current model calculation tests verify that a quote change changes derived outputs without changing accepted revision state; stale quotes and listing/currency mismatches leave returns unavailable; and prior quote/output history remains reproducible. Full `npm run check` passed: lint, formatting, frontend typecheck, API mypy, 88 frontend tests, 229 backend tests, generated-contract check and production build. `npm run db:check` found no new schema migrations. Browser verification passed 24 tests with 10 database/API-dependent tests skipped by the browser suite configuration; separate live API and PostgreSQL queries exercised current price, model-return and rolled-back decision-preview flows.

## Remaining blockers and next operating actions

1. Reconcile and import a current, source-supported Portfolio holdings/cash snapshot through the existing holdings workflow. Then obtain the exact dated FX rates needed for that snapshot’s effective time and verify aggregate valuation/weights. This requires authoritative current holdings evidence; this review deliberately did not make it up or alter the imported snapshot.
2. Obtain explicit target evidence for AMD, Celsius Holdings, Hims & Hers, MSCI Inc. and Novo Nordisk. Do not infer zero targets.
3. Resolve the ten unmapped Watchlist listings only from issuer/exchange evidence. Do not use economically different securities as substitutes.
4. Continue to preserve Watchlist exclusions until legacy method/currency classification and missing numeric outputs are resolved. Fresh quotes alone do not make those returns comparable.
5. Configure this machine’s proxy bypass for the two Yahoo chart hosts (or repair the loopback proxy) for future provider runs. No daily ingestion schedule was established by this milestone.

SEC/FMP credentials and their associated fundamentals, filing and consensus pipelines remain separate operational gaps; they were not prerequisites for this bounded market-price recovery.
