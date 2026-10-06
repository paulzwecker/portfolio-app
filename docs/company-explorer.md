# Company Explorer

`/company/[id]` is the company-level research surface. It composes persisted domain
views and exposes method-specific authoring workflows for three supported canonical
model methodologies; all model calculation remains in the API.

## Information structure

The Explorer is arranged for a top-down company review:

1. **Identity header** — company name, lifecycle, reporting currency, and all known
   listing symbols with their venue and listing currency. Listing identity remains
   distinct from company identity.
2. **Company context** — securities and listings, explicit lifecycle with a folded
   transition form and decision history, plus current holding-snapshot completeness,
   observed positions and accepted strategic target. Portfolio-currency position
   values and their price/FX availability are shown as returned by the API.
3. **Quality and risk** — the independent 10Y Durability, Compounder Quality,
   Execution and Risk assessments with their definition scale/direction, rationale,
   effective date, status and per-dimension history. New assessments remain an
   explicit user action that appends history.
4. **Market facts** — a listing-specific latest split-adjusted close, source date,
   provider, quality and freshness. Price history charts and regime measures are
   available within a per-listing disclosure.
5. **Reported fundamentals** — annual, quarterly and instant revenue, income,
   balance-sheet, cash-flow and diluted-share facts, with source/currency/period
   provenance, filing history, conflicts, quality and explicit not-imported states.
   The Explorer does not calculate FCF, ratios or growth from these observations.
6. **Consensus estimates** — provider-specific forward annual/quarterly revenue and
   EPS, exact fiscal period where available, mean/range, analyst count, currency,
   snapshot freshness, data-quality reason and expandable revision history. Provider
   continuity is visible; fallback series remain separate and never fill a primary
   provider gap. Consensus is not a native model assumption.
7. **Estimate Momentum** - a separate API-calculated direction and confidence-adjusted
   score from point-in-time annual Revenue/EPS revisions. The Explorer shows the 12M,
   6M and 3M comparison values and dates, per-period analyst coverage, separate history coverage/confidence, selected provider, freshness
   and quality state. Missing history is unavailable, not neutral. Persistence and
   analyst up/down breadth remain uncalculated because their inputs cannot be safely
   derived from the captured consensus domain.
8. **Filings and source documents** ? SEC filings and issuer source links by type,
   filing/publication date, reporting period, accession/reference, amendment link,
   retrieval/recorded time and data-quality state. Unmapped SEC identity and empty
   history remain explicit. The view links to primary sources without downloaded
   filing text or AI-generated summaries.
9. **Canonical models** — UFCF DCF, owner-cash-flow and residual-income assumptions,
   scenarios, method-derived projections, normalized outputs, availability and
   immutable revision history. Each method has a corresponding form and calculation
   preview. Imported workbook output snapshots remain separate and read-only.
10. **Imported valuation outputs** — current normalized Bear/Base/Bull outputs,
    probabilities, Weighted Fair Value/Upside, Expected Cash-Flow IRR, Hurdle,
    Expected Excess, Forward Fundamental CAGR, model currency/status, quality,
    provenance and recorded/effective times. Historical snapshots are expandable.
11. **Ranking context** — Portfolio, Watchlist and Research state remain separate.
    Stored rank positions are shown only where recorded; unavailable, excluded,
    partial and not-migrated states remain explicit. Each type retains its run history.

A compact in-page navigation links to these sections. The layout folds longer
histories and price details behind native disclosure controls, while keeping current
company and investment context visible. Cards collapse into a single-column flow on
small screens; tables and fixed-width spreadsheet layouts are not used on this page.

The **Forecast vs. outcome** section follows consensus estimates. It displays the
selected native model revision, selected consensus period and later reported Revenue
for the chosen fiscal year where each source can be aligned. Current model projections
have ordinal years but no fiscal-year anchor, so their requested-FY value remains
explicitly unavailable instead of using revision time as a proxy. Its controls select
fiscal year, forecast cutoff and market return horizon. The display retains revision
provenance, both temporal cutoffs, exact-listing baseline price, total-return outcome
and explicit coverage states; it does not produce a forecast-quality score.

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
- `GET /v1/companies/{company_id}/market-data?history_limit=90` for each supported
  listing’s quote, price observations, freshness and price-regime facts.
- `GET /v1/companies/{company_id}/reported-fundamentals` for canonical statement
  periods, coverage, source alternatives, filing provenance and conflicts; optional
  `period_type`, `as_of` and `known_at` filters preserve period and point-in-time
  semantics. `GET /v1/reported-fundamental-definitions` describes observed metrics
  and marks free cash flow as derived.
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
- `GET /v1/companies/{company_id}/source-documents` for filing/source metadata,
  SEC identity status and source history; optional `document_type`, `as_of` and
  timezone-aware `known_at` filters preserve type and point-in-time semantics.
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

The Explorer does not currently contain first-class thesis, evidence or additional
financial-model input domains. Consensus coverage remains partial until primary
provider mappings and prospective snapshots are configured. Unsupported model types are
shown as not natively editable rather than filled with workbook-derived placeholders.

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
