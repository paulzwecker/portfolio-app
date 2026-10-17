# Expected-return semantics and comparability

Expected IRR is a method-specific output, not a universal label for one economic
claim. The normalized output field is retained for compatibility, while every
classified output points to an immutable, versioned return-method definition.
Definitions and the current pairwise method policy are available at
`GET /v1/return-methodologies`.

## Supported definitions

| Code                            | Perspective and cash-flow basis                                                                                        | Entry / price basis                                                                                            | Comparison policy                                                                                                     |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `UFCF_ENTERPRISE_IRR` v1        | Enterprise: probability-weighted unlevered FCF plus source terminal enterprise value, including its 2.5 growth premium | Exact valuation-listing price × diluted shares, less opening net cash/debt; exact split-adjusted listing quote | Direct only against the same versioned method. It is not an equity shareholder return.                                |
| `UFCF_ENTERPRISE_HMODEL_IRR` v1 | Enterprise: probability-weighted UFCF plus Year 10 UFCF and a Gordon terminal without the extra 2.5 growth premium     | Exact valuation-listing price × diluted shares, less opening net cash/debt; exact split-adjusted listing quote | Direct only against the same versioned method; not comparable to `UFCF_ENTERPRISE_IRR`.                               |
| `OWNER_CASH_FLOW_EQUITY_IRR` v1 | Equity: probability-weighted owner cash flow per diluted share, terminal owner cash flow and terminal net cash/share   | Exact valuation-listing share price; exact split-adjusted listing quote                                        | Same method is direct. Cross-comparison with residual income is conditional because the cash-flow conventions differ. |
| `RESIDUAL_INCOME_EQUITY_IRR` v1 | Equity: probability-weighted explicit dividends and terminal book value plus residual income per share                 | Exact valuation-listing share price; exact split-adjusted listing quote                                        | Same method is direct. Cross-comparison with owner cash flow is conditional because the cash-flow conventions differ. |

“Owner cash flow” is an owner-available cash-flow convention, not necessarily a
cash distribution or dividend. Residual-income cash flows explicitly include
dividends and terminal book/economic value. Enterprise UFCF is before financing
and shareholder distribution. The current DCF model does not retain a future
debt/cash, interest, debt-service, financing, or payout schedule. No deterministic
enterprise-to-equity bridge is therefore supported, and no bridge is applied.

## Comparability matrix

| Left / right                                                 | Classification                                                   | Rule                                                                                                                                  |
| ------------------------------------------------------------ | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| UFCF enterprise v1 / UFCF enterprise v1                      | Direct, same currency; direct with FX excluded across currencies | Same claimholder perspective and versioned cash-flow method. A currency difference is not converted into a forecast FX return.        |
| UFCF enterprise v1 / UFCF enterprise H-model v1              | Not comparable                                                   | Both are enterprise UFCF returns, but their Year 10 terminal cash-flow definitions differ.                                            |
| UFCF enterprise H-model v1 / UFCF enterprise H-model v1      | Direct, same currency; direct with FX excluded across currencies | Same versioned Gordon-terminal return method.                                                                                         |
| Owner cash-flow equity v1 / owner cash-flow equity v1        | Direct, same currency; direct with FX excluded across currencies | Same versioned cash-flow method.                                                                                                      |
| Residual-income equity v1 / residual-income equity v1        | Direct, same currency; direct with FX excluded across currencies | Same versioned cash-flow method.                                                                                                      |
| Owner cash-flow equity v1 / residual-income equity v1        | Conditional equity comparison                                    | Both are equity-perspective rates, but their shareholder cash-flow and terminal-value conventions differ. Keep method labels visible. |
| UFCF enterprise / either equity method                       | Not comparable                                                   | Different claimholder and cash-flow perspectives; no supported bridge.                                                                |
| Any unclassified, unknown-version or unknown-currency result | Unavailable or data check                                        | Do not infer a method, currency conversion, or neutral value.                                                                         |

The API matrix describes methodology pairs. Company-level comparisons also
require a documented currency and the exact listing/price basis. Rates remain in
model-local currency. Cross-currency results are labeled FX-excluded; the
application has no modeled currency return that would support converting one
company's IRR into another currency's return.

Ranking preserves same-method cross-currency rates as local-currency rates and
labels FX as excluded; it does not claim a base-currency portfolio return. A user
who needs base-currency opportunity comparisons still needs supported currency
return assumptions.

## Historical classification and provenance

Native output rows reference the methodology version used by their accepted
revision. New method versions are new rows; prior revisions and output rows keep
their original identity. Imported legacy output snapshots keep their original
number and are classified only for exact model keys with migration/parity evidence:
`P-GOOGL`, `P-ASML`, `P-ISRG`, `P-MA`, `P-CPRT`, `P-UBER`, and `P-MSFT` as
UFCF enterprise; `P-AMZN` and `P-HIMS` as UFCF enterprise H-model;
`W-TOST` as owner cash flow; and `W-HDFC` as residual income. Other workbook keys
remain `UNCLASSIFIED` even if a tab title looks familiar.

Legacy snapshots do not retain the exact quote observation used in their
calculation. Their method may be classified while their historical share-price
basis remains `NOT_RETAINED`. Current/native revisions retain exact listing, quote
observation, effective time and currency evidence where available. A method label
does not repair missing historical inputs or establish full workbook parity.

Expected-return history shows the method, perspective, currency and retained
price-basis state at each point. Attribution requires matching classified method
and version and the same currency; a method/currency transition is not bridged.
Estimate observations remain context unless a supported model explicitly consumes
them.

## Ranking behavior

Watchlist Rank first requires one comparable perspective cohort. UFCF enterprise
cannot be ordered with equity returns. Owner cash-flow and residual-income returns
may share the equity cohort, but the UI must preserve their conditional method
difference. If the eligible population contains both enterprise and equity
methods, no partial cohort is selected: entries receive `DATA_CHECK` because the
single run cannot choose which Watchlist population to order.

Portfolio Rank uses the documented Expected IRR and Expected Excess components.
Because each method's hurdle has a different economic basis, one run requires one
exact return-method code/version cohort; mixed methods receive `DATA_CHECK`.
Research Rank is unaffected. Ranking runs remain immutable, and ranks do not
change targets, holdings, lifecycle, assumptions, or Execution Pace.

## Return-semantics milestone baseline (2026-10-09)

The local PostgreSQL reconciliation is captured in
[`reconciliation/return-semantics-2026-10-09.json`](reconciliation/return-semantics-2026-10-09.json).
Seven active native models are classified: six Portfolio UFCF DCFs and one
Watchlist owner-cash-flow model. The six Portfolio companies—Alphabet, ASML
Holding, Copart, Intuitive Surgical, Mastercard and Uber Technologies—now form a
same-method UFCF v1 comparison cohort. ASML remains denominated in EUR while the
other five are USD; the rates retain their model currency and no FX return is
added. These names are method-comparable, but that does not imply complete current
Portfolio Rank eligibility.

The imported output history has method classifications for 22 legacy UFCF
snapshots, two legacy owner-cash-flow snapshots and one legacy residual-income
snapshot. The matching source tabs are six, one and one companies respectively.
Two additional current-contract snapshots are classified (Toast owner cash flow
and HDFC residual income). All other imported snapshots remain unclassified.
Classified legacy snapshots still lack their exact historical quote basis, so
they support method labeling rather than fully reconstructed historical return
comparisons or attribution.

The active return-basis-aware Watchlist Rank v5 run has 0 ranked, 59
`DATA_CHECK`, 12 `INPUTS_UNAVAILABLE` and 148 `NOT_ELIGIBLE` entries. The checks
are 23 unclassified legacy methods, 35 unknown legacy currencies and one stale
native Toast reference quote. Its run ID is `dfc9b27f-33d7-4f22-b477-50e49e008227`.
The prior v4 run and the earlier v3 run with 14 positions remain immutable history;
their ranks are not carried into v5. Portfolio Rank v4 has 0 ranked, 16
`DATA_CHECK`, 5 unavailable and 198 not-eligible entries. Its 16 data checks are
blocked by incomplete current market-weight coverage; the five missing targets
stay unavailable. Its run ID is `ecce3252-df8f-4da2-a411-d5c331878dca`. The
earlier v3 and v2 runs remain preserved. The stricter captured-price requirement
does not further reduce this Portfolio run because incomplete current market
weights already block all 16 candidates before return-cohort selection. Neither
current run establishes a cross-method score or rank.

## Portfolio native-model coverage batch (2026-10-09)

The next controlled batch accepted Amazon, Hims & Hers, and Microsoft as native
Portfolio DCF models. The application-state receipt and idempotent replay are at
[the batch-3 apply report](reconciliation/portfolio-native-model-coverage-batch-3-apply-2026-10-09.json)
and
[the batch-3 replay report](reconciliation/portfolio-native-model-coverage-batch-3-replay-2026-10-09.json).
All three preserved the explicit Year 6–10 source growth paths and passed 30/30
projection and 22/22 normalized-output/return-stream comparisons.

Amazon and Hims use UFCF_ENTERPRISE_HMODEL_IRR v1. Their Expected IRR stream
ends with Year 10 UFCF plus a Gordon terminal value without the separate 2.5
terminal-growth premium used in their Fair Value formulas. Microsoft retains
UFCF_ENTERPRISE_IRR v1 because its return terminal includes that premium.
Explicit tail assumptions alone do not select a return method. All three remain
enterprise returns, not shareholder-distribution IRRs.

The database now has native models for 9 of 21 Portfolio companies (42.9%), up
from 6 of 21, plus 1 of 71 Watchlist companies. Seven Portfolio models use
UFCF_ENTERPRISE_IRR v1; Amazon and Hims form a separate H-model cohort. Rates
across these different terminal bases are not combined.

A read-only Portfolio Rank preview still has zero ranked entries: 16 candidates
remain DATA_CHECK from incomplete current market weights and five have no
authored target. The three new models did not clear those blockers. No new
ranking run was recorded. No Execution Pace run exists; a read-only preview
returns REVIEW for all three new models because Amazon and Microsoft lack
complete current holding weights, Hims has no target, and all three exact-listing
quotes were stale on 2026-10-09. Their deterministic model calculations are
complete, but the stale quotes are not actionable current valuation inputs.

## Out of scope

There is no universal return conversion, FX-return forecast, inflation
normalization, market-risk adjustment, or return bridge between enterprise and
equity perspectives. Historical legacy return values are not recalculated or
renamed. Any future bridge requires a supported financing/distribution model,
source methodology evidence, representative parity tests, and a new explicit
versioned definition.
