# Company Explorer

`/company/[id]` is the company research cockpit. The route stays thin; the workspace
loads a focused view and composes the existing feature components. Canonical API
responses own all portfolio and financial calculations.

## Company workspace

The stable header shows canonical company identity, lifecycle, reporting currency,
the exact selected listing, its quote currency and its listing-specific freshness.
Selecting another listing changes only the quote context. It does not substitute a
security or change the model's valuation listing.

The workspace uses six keyboard-accessible tabs and preserves legacy section links:

| View                | Main purpose and contents                                                                                                                                                               |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overview            | Company context, lifecycle, holdings/target context and the company Attention Center.                                                                                                   |
| Financials          | Selectable reported annual/quarterly statement rows with a multi-series chart and source drawer; third-party consensus; agent-authored forecasts. Each source stays separately labeled. |
| Valuation           | Method-specific native editors for UFCF DCF, owner cash flow and residual income; projections, revisions, imported output snapshots and model migration status.                         |
| Investment Thesis   | Independent score assessments and their history alongside accepted, versioned thesis claims and evidence.                                                                               |
| Research & Evidence | Filing/source documents and accepted qualitative risk assessments with their portfolio baseline.                                                                                        |
| Historical Analysis | Listing-specific market history, Estimate Momentum, point-in-time forecast-versus-outcome alignment, expected-return history, rankings and Execution Pace.                              |

Reported metric exploration supports only canonical facts returned by the reported
fundamentals API (including revenue, operating income/EBIT, cash-flow, balance-sheet
and shares facts). The selectable chart is presentation-only, supports multiple rows,
and groups each currency/unit basis into its own facet. Missing, conflicting and
quality-checked periods break a line; mixed bases remain in the table and are not
plotted together. The interface does not synthesize EBITDA, EPS, free cash flow,
ratios or growth from other facts. Missing, conflicting and not-imported values keep
their explicit status.

Consensus estimates, agent research forecasts, reported actuals and accepted model
projections use separate sections and labels. A model projection is not mapped to a
fiscal year unless its accepted revision provides that mapping. Valuation retains the
distinct economic methodology of each supported model family; normalized output
formatting is shared, while deterministic recalculation remains in the API. Edits use
the existing preview, explicit acceptance, stale-base conflict and append-only
revision workflow. Imported workbook output snapshots remain read-only.

Tabs use the shared responsive layout and preserve URL view state. Long evidence and
revision histories use disclosure controls. On narrow screens the tab list scrolls
without page-wide horizontal overflow, tables use the shared responsive table, and
model editors keep their existing responsive forms and method-specific projections.
See [company-explorer-11f.md](design/company-explorer-and-modeling-11f.md) for the
implementation map, shared financial components, verification and limitations.

## Canonical reads

The page uses the existing FastAPI read operations through the same-origin research
proxy:

- `GET /v1/companies/{company_id}` for identity, securities/listings, lifecycle
  history, latest holding context, target allocation, and API-computed company
  allocation context (current value, weight and target gap when coverage permits).
- `GET /v1/companies/{company_id}/scores/current` and
  `GET /v1/companies/{company_id}/scores/history` for versioned assessments.
- `GET /v1/companies/{company_id}/rankings` for the current stored runs and
  immutable company history.
- `GET /v1/companies/{company_id}/market-data?history_limit=252` for each supported
  listing’s quote, price observations, freshness and price-regime facts.
- `GET /v1/companies/{company_id}/reported-fundamentals` for canonical statement
  periods, coverage, source alternatives, filing provenance and conflicts; optional
  `period_type`, `as_of` and `known_at` filters preserve period and point-in-time
  semantics. `GET /v1/reported-fundamental-definitions` describes observed metrics
  and marks free cash flow as derived.
- `GET /v1/companies/{company_id}/financial-statements` for the Financials workspace:
  unique economic-period columns, reported/consensus/agent rows, source IDs,
  explicit availability states, alignment limitations and nested source history.
  `period_type`, `period_limit`, `as_of` and `known_at` preserve the same
  point-in-time rules; fiscal labels are emitted only when contemporaneous filing
  evidence supports them.
- `GET /v1/companies/{company_id}/consensus-estimates` for separately retained
  provider streams, their continuity selection, current forward periods and captured
  history; optional `as_of` and timezone-aware `known_at` preserve point-in-time
  semantics.
- `GET /v1/companies/{company_id}/estimate-momentum` for the deterministic partial
  legacy signal and its per-period revisions, with optional `as_of` and timezone-aware
  `known_at`. It reports revision direction, confidence, data quality and freshness
  separately. See [estimate-momentum.md](estimate-momentum.md).
- `GET /v1/universe/estimate-momentum-summary` for the compact company-wide read, with
  lifecycle/search filters and the same time cutoffs.
- `GET /v1/companies/{company_id}/temporal-alignment` for the point-in-time annual
  Revenue comparison. `fiscal_year` and `as_of` are required; timezone-aware
  `known_at` and `outcome_known_at` separate forecast knowledge from later outcome
  knowledge, and `horizon_days` selects a subsequent total-return period. Native
  model FY alignment remains unavailable until a revision has an explicit fiscal-year
  anchor. See
  [temporal-alignment.md](temporal-alignment.md) for the exact cutoff and coverage
  rules.
- `GET /v1/companies/{company_id}/forecast-accuracy` for historical agent,
  accepted-model and selected-consensus forecasts compared with later reported
  facts. Source, metric, fiscal period and outcome-known cutoff filters are
  supported. See [forecast-accuracy.md](forecast-accuracy.md) for timestamp,
  fiscal-period, exact-metric and aggregation rules.
- `GET /v1/companies/{company_id}/source-documents` for filing/source metadata,
  SEC identity status and source history; optional `document_type`, `as_of` and
  timezone-aware `known_at` filters preserve type and point-in-time semantics.
- `GET /v1/companies/{company_id}/research` for the separate agent-authored
  forecast and assessment streams, with optional `as_of` and timezone-aware
  `known_at` cutoffs. See [research-forecasts.md](research-forecasts.md).
- `GET /v1/companies/{company_id}/thesis` for point-in-time thesis streams,
  keyed claims, current/prior revisions, support/contradicting/context evidence,
  and linked filing/reported-fact provenance. A Sheets research agent can publish a
  complete `InvestmentThesisContractV1` snapshot through
  `POST /v1/investment-thesis-revisions`; see
  [investment-thesis.md](investment-thesis.md).
- `GET /v1/companies/{company_id}/risk-assessments` for current company-linked
  findings and accepted history. `GET /v1/portfolios/{portfolio_id}/risk-assessments`
  shows portfolio-level accepted assessments. Inbox review is performed in the
  separate Sheets risk-assessment workflow; no assessment changes portfolio or
  model state. See [risk-assessments.md](risk-assessments.md).
- `POST /v1/companies/{company_id}/source-documents` to append an HTTPS issuer
  annual-report or earnings-release reference. SEC filing metadata enters through
  the reviewed CIK ingestion command.
- `GET /v1/companies/{company_id}/model-outputs/current` and
  `GET /v1/companies/{company_id}/model-outputs/history` for imported normalized
  model-output snapshots and recorded history;
- `GET /v1/companies/{company_id}/expected-return-history` for a read-only,
  point-in-time composition of imported outputs, native revision outputs, exact
  listing prices, and the selected point-in-time estimate context. Optional
  `as_of` and timezone-aware `known_at` cutoffs are supported. Imported snapshots
  remain distinct from native revisions, undated imports remain visible but are
  not charted, and no historical record is recalculated or overwritten. See
  [expected-return-history.md](expected-return-history.md) for the source and
  cutoff rules.
- `GET /v1/companies/{company_id}/expected-return-attribution` compares two IDs
  from the expected-return history. Native same-method revisions are recalculated
  across symmetric price, probability, required-return and other-model-input
  counterfactuals. Legacy outputs, missing values, and method changes remain
  explicitly output-only or residual. See
  [expected-return-attribution.md](expected-return-attribution.md).
- `GET /v1/companies/{company_id}/financial-models` and
  `POST /v1/companies/{company_id}/financial-models` to list or create accepted
  UFCF DCF models;
- `GET /v1/financial-models/{model_id}`, `GET /v1/financial-models/{model_id}/revisions`,
  `GET /v1/financial-models/{model_id}/revisions/{revision_id}` and
  `POST /v1/financial-models/{model_id}/revisions` to inspect current state/history
  and append a recalculated revision.
- `GET /v1/companies/{company_id}/canonical-financial-models` and method-specific
  `POST` operations for owner-cash-flow/residual-income initial creation and preview;
- `GET /v1/canonical-financial-models/{model_id}`, historical revision reads and
  method-specific preview/append endpoints for native edits;
- `/v1/canonical-financial-models/{model_id}/contract` export, preview and import
  operations for portable v2 external edits.

The frontend formats and arranges these responses. It does not derive ranks, scores,
Expected IRR, fair values, FX, portfolio weights or lifecycle decisions. The
canonical-model form sends explicit inputs; the API validates, recalculates and
accepts the new immutable revision.

## Availability and ownership

An absent position is distinguished from an incomplete holding snapshot. An absent
target is shown as no authored target. Missing scores and model fields remain
unavailable/not supplied, never zero. Market facts are identified by listing and
retain stale, quality-check, unknown-currency and missing-history states. Portfolio
company market value, current weight and target gap come from the backend company
allocation context and appear only when its dated price/FX coverage permits.
currency values depend on the backend’s dated-price/FX completeness rules. Unknown
model currency is not inferred from the listing or reporting currency. Model
`effective_at` stays unknown when the source did not record one; `recorded_at` remains
visible.

The rank panel displays current immutable rank positions, as-of run state and
explicit unavailable/data-check statuses. Watchlist Rank includes its snapshotted
Expected IRR source and separate durability, quality, and forward-compounding
context. Historical entries are read as recorded and never recalculated from current
inputs. Portfolio and Research positions remain imported source snapshots.
The score panel keeps Risk’s higher-is-greater-risk direction separate from the
higher-is-better dimensions. Model output snapshots do not own scores, lifecycle,
holdings, targets, market facts or ranking state.

The Explorer now contains a read/review surface for first-class thesis and evidence
history; direct web editing of thesis revisions is not included in this slice.
Consensus coverage remains partial until primary provider mappings and prospective
snapshots are configured. Unsupported model types are shown as not natively editable
rather than filled with workbook-derived placeholders.

The Scenario Calibration & Decision Evaluation panel exposes numeric Bear/Base/Bull
projection groups, eligible proper scores, valuation-only scenario snapshots, and
subsequent outcomes for immutable Portfolio Rank, Watchlist Rank and Execution Pace
snapshots. It excludes Research Rank from return evaluation and displays insufficient
samples and missing source/period states explicitly. See
[decision-evaluation.md](decision-evaluation.md) for calculation and comparability
rules.

## Boundary before broader model support

Imported workbook-output snapshots remain distinct from native model state. The
three supported methods store accepted, recalculable revisions. Further methods
need methodology-specific input/projection structures and reference fixtures before
they can author accepted revisions:

- model identity/type, currency and forecast horizon;
- revisioned assumptions and model-specific drivers;
- Bear/Base/Bull scenarios, probabilities and methodology-appropriate projections;
- deterministic calculation ownership and normalized output generation;
- provenance, effective/recorded times, rationale and immutable model revision history;
- representative source-model fixtures and calculation reconciliation before any
  model architecture is declared migrated.

SOTP, additional financial-sector variants and other bespoke models remain outside
the native editor until separately reconciled. The editor does not turn imported
normalized output snapshots into editable model assumptions. Score assessment and
lifecycle controls remain their own domain operations.
