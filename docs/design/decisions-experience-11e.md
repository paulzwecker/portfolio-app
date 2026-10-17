# Milestone 11E — Decisions & Capital Allocation

## Primary question

The Decisions workspace answers: **What should I investigate or consider
changing, and why?** It presents canonical decision context without creating
new investment rules, inferred targets, suggested trades, or persisted runs.

## Page hierarchy

- **Baseline:** current mark-to-market status, holdings freshness, and accepted
  target revision. These establish the timestamp and quality context for the
  decision views.
- **Allocation:** current company weights beside accepted strategic targets,
  using the portfolio API's weights and gap values. A held company with a 0%
  target remains visibly held; a target-only company is distinct from a held
  position; a missing target remains `No target`. Partial/unconfirmed holdings
  and stale snapshots are disclosed. The section also shows the largest
  API-reported issuer weight, cash balances/base-currency marks by currency,
  and standalone security exposure. These are funding and concentration
  context only; the page does not calculate look-through exposure or recommend
  reallocating cash.
- **Opportunity:** Portfolio Rank and Watchlist Rank are shown in separate
  tables. Rank-time Expected IRR, hurdle, Expected Excess, Fair Value, method,
  quality inputs, price basis and run date remain traceable. Rows are grouped
  only by the canonical return-comparability cohort in their ranking snapshot.
  Rows without a cohort are isolated under “No comparable return cohort.”
  Current allocation context is explicitly labeled separately from rank-time
  inputs.
- **Execution Pace:** the latest recorded status, pace when available, reason,
  as-of time and input notes. `REVIEW`, `UNAVAILABLE` and no-run states remain
  distinct. The interface explains that timing guidance is not an order, trade
  size, or target change.
- **Decision detail drawer:** selecting a company opens its current/target
  context, rank eligibility reason, quality scores and rationale, return
  methodology and limitations, execution input snapshot, and published model
  output provenance. Links open Company Explorer and Modeling in context.
- **Audit:** holdings snapshot, target revision, valuation basis and market/FX
  timestamps remain available below the decision views.

## Data and financial integrity

The page reads the existing `/portfolios/{id}/overview`,
`/universe/ranking-summary`, `/universe/execution-pace-summary`,
`/universe/model-output-summary`, `/universe/score-summary`, and
`/return-methodologies` APIs. It displays canonical percentages and money values
and uses the portfolio API's allocation gap. The browser does not recalculate
weights, returns, ranks, scores, target gaps, or execution signals.

Opportunity figures are explicitly marked as rank-snapshot values. Current
allocation weights are displayed separately. Method comparability comes from
the persisted ranking snapshot's cohort; no cohort means no direct comparison.
The methodology policy disclosure provides the canonical cross-method rules
and rationale without inferring a bridge from model names.

The route is read-only. It does not confirm holdings, write a strategic target,
accept a model revision, or create rank/Execution Pace runs. Historical rank and
execution records remain immutable.

## Shared patterns and responsive behavior

The workspace reuses `PageHeader`, `PageSection`, `MetricGroup`, `MetricCard`,
`DataFreshnessIndicator`, `StatusIndicator`, `ResponsiveDataTable`, `DetailDrawer`,
`SourceReference`, and the existing `ExecutionPaceCompact` evidence view.
`components/features/decisions/` owns allocation, return-comparison, execution
rationale, detail drawer, and typed view composition.

Allocation uses aligned bars on the same 0–100% display scale. At mobile widths,
the shared responsive table becomes definition-list cards. Opportunity cohort
tables retain their cohort labels and search filter; execution cards wrap
without requiring a page-wide horizontal scroll. Detail uses the accessible
native dialog drawer with an explicit close control and escape handling.

## Verification and limitations

Fixture browser tests cover a held zero-target position, a target-only row, a
missing target, stale holdings, a missing Expected IRR, separate UFCF and owner
cash return cohorts, and an Execution Pace `REVIEW` state. The tests verify
mobile rendering and that viewing decisions sends no write request.

The workspace can only show decision history and inputs returned by canonical
summaries. It does not synthesize a ranking if no run exists, compare
unclassified methods, make an investment decision, infer an order, or replace
missing model/target/quality data. Detailed holdings confirmation and analytical
run recording remain in their existing investor-controlled workflows.
