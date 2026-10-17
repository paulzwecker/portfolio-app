# Milestone 12B — Interactive Company Financial Statements

## Product surface

Company Explorer → Financials is now a statement workspace rather than a stack of
separate metric cards. It answers: **which reported or forecast series changed, over
which periods, and what source supports each value?**

The workspace has three layers:

1. A compact chart above the table shows the selected metric rows. Reported actuals
   are solid, analyst consensus is dashed and agent forecasts are dotted. Rows are
   grouped into separate currency/unit facets; a line is broken at missing,
   quality-checked or implausibly long reporting gaps.
2. The selectable table keeps metric labels and the period header sticky while its
   own container scrolls horizontally and vertically. A checked row is charted. A
   value cell is an accessible button that opens the source drawer.
3. The source drawer provides filing, correction, consensus and research revision
   history, or a consolidated alignment view for unavailable coverage and model
   fiscal-anchor limitations.

Annual and quarterly controls are independent of the source streams. The app
knowledge cutoff is sent as both the publication (`as_of`) and application knowledge
(`known_at`) cutoff, so later observations cannot appear in an earlier view. Legacy
hashes `#reported-fundamentals`, `#consensus-estimates` and `#research-forecasts`
continue to select the Financials view.

## Canonical data contract

`GET /v1/companies/{company_id}/financial-statements` returns:

- `periods`: unique economic period columns with a fiscal label only when the source
  filing evidence supports it;
- `rows`: canonical reported metrics plus separately identified consensus and agent
  forecast rows, each retaining currency, unit, scenario and availability reason;
- `cells`: exact numeric values or null with `AVAILABLE`, `CONFLICT`, `DATA_CHECK` or
  `UNAVAILABLE` status and source observation IDs;
- `reported_periods`, `consensus`, `research`: the nested source records used by the
  drawer and revision archive; and
- `limitations`: explicit alignment failures, unsupported metrics and model mapping
  notes.

The backend groups reported facts by metric, statement, period type, duration/instant,
period bounds, currency and unit. SEC `fy`/`fp` values remain filing context. They do
not create a second economic period when a later filing repeats an earlier comparative
fact. A direct contemporaneous annual/quarterly filing label is used for the column;
ambiguous labels remain an explicit date-only column. Instant balance-sheet facts are
included only when their period end matches an eligible duration period (and the
annual year-end anchors Q4 in the quarterly view).

The canonical reported layer currently supports Revenue, Gross Profit, Operating
Income, Net Income, Cash and Equivalents, Current Debt, Non-current Debt, Operating
Cash Flow, Capital Expenditures and Diluted Weighted-average Shares. EPS, EBITDA,
Free Cash Flow, growth and ratios remain visible as unavailable rows or limitations;
the frontend does not synthesize them. Unknown currency/unit, stale consensus and
conflicting facts stay out of chart geometry while remaining inspectable in the table
and drawer. Zero is a valid observation and remains distinct from a missing value.

Consensus is provider-continuous: only the selected provider can form an aligned row;
alternate providers remain in the archive. A forecast requires an explicit period end,
known currency and supported unit. Agent forecasts retain scenario and revision
identity. Native model projections remain in Valuation because current accepted model
revisions do not carry an explicit fiscal-year anchor; ordinal model years are not
silently placed on this fiscal statement timeline.

## Shared components

The implementation is contained under
`apps/web/src/components/features/company/financial-statements/`:

- `FinancialStatementsWorkspace` owns view state and data loading;
- `FinancialSeriesChart` renders presentation-only geometry and exact point tooltips;
- `FinancialStatementsTable` provides sticky labels, local scroll and cell controls;
- `FinancialPeriodControls` manages annual/quarterly/range/cutoff context;
- `FinancialMetricSelector` switches statement categories and source visibility; and
- `FinancialSourceDrawer` reuses `DetailDrawer`, `SourceReference` and
  `StatusIndicator` for evidence and history.

Formatting remains centralized in `lib/display.ts`; domain selection and fiscal-period
resolution remain in FastAPI. No chart dependency or client-side financial calculation
was added.

## Verification and visual QA

The existing Company Explorer browser test now exercises actual rows, multiple chart
series, missing balance-sheet coverage, annual/quarterly controls, source alignment,
source evidence and desktop/mobile no-overflow behavior. Pure frontend tests cover
zero/negative values, missing and checked cells, long quarterly gaps and compact
financial formatting. Backend tests cover repeated SEC comparative filings, fiscal
label ambiguity, annual/quarterly composition, consensus period/currency/unit/time
metadata, stale state and route validation.

The live Microsoft view was captured before and after against the local PostgreSQL
database:

| View    | Before                                               | After                                              |
| ------- | ---------------------------------------------------- | -------------------------------------------------- |
| Desktop | [before desktop](screenshots/12b/before-desktop.png) | [after desktop](screenshots/12b/after-desktop.png) |
| Mobile  | [before mobile](screenshots/12b/before-mobile.png)   | [after mobile](screenshots/12b/after-mobile.png)   |

The before view showed a long vertical actuals chart and repeated cards for consensus
and agent research. The after view presents two selected actual series above one
scrollable statement table; the mobile capture exercises quarterly periods and the
balance-sheet category. The table remains the source of record when a chart cannot be
drawn.

## Known limits

- Current model projections have no accepted fiscal-period anchor and therefore remain
  a Valuation concern until that metadata is authored.
- Reported/consensus/agent observations are not FX-converted or merged across units.
- Derived ratios, growth, EPS, EBITDA and FCF are intentionally not introduced here.
- Historical SEC `fy`/`fp` context can be ambiguous when the original contemporaneous
  filing was not captured; the API keeps a date-only label instead of inferring a
  calendar fiscal year.
