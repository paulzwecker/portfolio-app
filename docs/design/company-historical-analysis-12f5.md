# Company Historical Analysis UX — Milestone 12F.5

Status: **COMPLETE**

## Purpose

The History view now answers one question: **How have market prices, our expectations and our investment decisions changed over time?** It is a time-aware research workspace rather than a stack of independent market, model, rank and execution panels.

The workspace keeps the application’s existing canonical APIs as the source of truth. It does not recalculate financial values, ranking decisions or portfolio returns in React.

## Information architecture

The view is organised into one shared range context and five progressive sections:

1. **Historical analysis header** — one date-range control (`90 days`, `1 year`, `3 years`, `All available`) and coverage counters.
2. **Market history** — exact-listing split-adjusted price history, selected-listing context, supported regime analytics and an expandable observation table.
3. **Expectations history** — accepted model points grouped by methodology/return basis, fair-value and return series, and source-detail inspection. Fair Value is labelled as a valuation reference rather than a future price forecast.
4. **Forecast vs. outcome, Estimate Momentum and Thesis developments** — point-in-time forecast controls, estimate coverage/freshness and recorded thesis context. Each keeps unavailable and sparse data explicit.
5. **Decision history and Change timeline** — immutable ranking and Execution Pace snapshots followed by a filterable, source-linked event stream. The timeline initially shows the 12 most recent matching events and progressively discloses the remaining history.

The existing company header and tabs remain the navigation frame. A selected model point or timeline event opens the shared `DetailDrawer`, so evidence and timestamps are available without leaving the historical context.

## Canonical data consumed

`CompanyHistoricalAnalysisWorkspace` uses the existing typed `useResearch` contracts:

- `GET /v1/companies/{id}/market-data?history_limit=252` for listing-specific observations and derived market analytics. The view keeps longer range controls explicit when the canonical API has fewer observations.
- `GET /v1/companies/{id}/expected-return-history` for accepted model/output points, methodology, return basis, effective/recorded times and provenance.
- `GET /v1/companies/{id}/temporal-alignment` for point-in-time model/consensus/actual comparisons and subsequent outcomes.
- `GET /v1/companies/{id}/estimate-momentum` for provider continuity, coverage, revision direction and freshness.
- `GET /v1/companies/{id}/thesis` for accepted thesis revisions and research confidence where available.
- `GET /v1/companies/{id}/rankings` and `GET /v1/companies/{id}/execution-pace` for recorded decision snapshots and their original context.

The view also reuses the Phase 11 components `PageSection`, `MetricCard`, `ChartContainer`, `StatusIndicator`, `SourceReference`, `EmptyState`, `PendingOrError` and `DetailDrawer`.

## Temporal and comparability rules

- Market points are keyed to the exact listing and market session date. Listing identity and currency are shown with the chart and are never substituted.
- Market analytics retain their API-provided status and analysis timestamp. The UI does not convert price-only history into dividend-inclusive portfolio performance.
- Model points preserve model effective time, recorded time, model type/version, source kind and return basis. Different methodologies remain separate series; incompatible currencies or listings are excluded from expectation/price comparisons.
- Forecast/actual comparisons are requested with an explicit fiscal year, as-of date and horizon. The temporal-alignment API decides whether a point was knowable at that date; the UI only renders its status and values.
- Estimate, thesis, ranking and Execution Pace entries keep their own effective/event and recorded/run timestamps. The shared timeline aligns events for investigation but does not imply that all streams have the same observation cadence.
- Decision history is labelled **recorded** and uses persisted run context. It is not a hypothetical recomputation from today’s inputs.

The helper `comparableExpectationPoints` only filters on contract-provided listing/currency compatibility and the availability of a contemporaneous canonical quote. An accepted model reference price remains audit context and is never used as a substitute when that quote is missing. The helper does not derive a valuation, return, or forecast.

## Interaction and accessibility conventions

- Range controls use labelled pressed buttons and retain the selected range while navigating the page.
- The market chart exposes point titles and an observation disclosure with source, quality and observation date.
- Model points and timeline rows have explicit `Inspect` actions that open a keyboard-accessible drawer with effective/recorded times, method, status, rationale and source link.
- Forecast controls are labelled fiscal year, forecast date and outcome horizon. Event filtering is labelled by event type.
- Sections stack into one column on small screens; charts use bounded responsive containers and tables are disclosed below the chart rather than forcing the whole page into an unreadable grid.
- Status badges preserve `AVAILABLE`, `STALE`, `PARTIAL`, `DATA_CHECK`, `REVIEW` and `UNAVAILABLE` semantics. Missing values are rendered as unavailable text, never as zero.

## Visual QA

The real local application was inspected with the Alphabet company and its sparse real history at desktop and mobile widths after data loading completed. The screenshots are retained as review artifacts:

- [Desktop history workspace](C:/Users/Paul%20Zwecker/Desktop/Projekte/portfolio-app/docs/design/screenshots/company-history-12f5-desktop.png)
- [Mobile history workspace](C:/Users/Paul%20Zwecker/Desktop/Projekte/portfolio-app/docs/design/screenshots/company-history-12f5-mobile.png)
- [Mobile history workspace, focused section](C:/Users/Paul%20Zwecker/Desktop/Projekte/portfolio-app/docs/design/screenshots/company-history-12f5-mobile-focus.png)

The review confirmed that the price chart and freshness context are visible first, expectations and forecast availability follow, and decision/timeline evidence is progressively disclosed. Mobile layout stacks the market chart, regime card, forecast controls and event rows without requiring a desktop-only table. Sparse consensus and absent thesis history remain visible as explanatory unavailable states.

## Known limitations

- Historical model/estimate/thesis depth is constrained by what is genuinely recorded in PostgreSQL; the UI does not backfill missing history.
- The temporal comparison remains unavailable when fiscal-period, currency or point-in-time evidence is insufficient.
- Portfolio-level historical performance is intentionally not inferred from a company price series or current holdings.
- The legacy standalone history components remain available to other consumers but are no longer rendered by the Company Explorer history route; the new workspace is the single composition for this view.
- This milestone changes presentation and query composition only. It does not alter accepted models, market observations, ranking runs, Execution Pace decisions, holdings, targets or research revisions.
