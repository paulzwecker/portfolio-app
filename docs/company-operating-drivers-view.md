# Company Explorer — operating KPIs and drivers

The **Operating KPIs** tab at `/company/{id}?view=operating` composes the
accepted `CompanyAgentContextV1` response into a working evidence review:

- Stable company-specific operating metric definitions, accepted current
  actuals, issuer management guidance and revision-bound Bear/Base/Bull model
  driver projections. Their provenance and accounting/economic periods remain
  distinct and visibly labeled.
- Economic-period grouping, with metric selection. No interpolation, scaling,
  inferred forecasts or blended provider values.
- "Above/within/below" guidance and "above/on/below" model-driver badges only
  when exact metric, fiscal period, scope, unit, scale and currency align.
  Actuals must be exact EQ and VERIFIED/RESTATED; there must be exactly one
  comparable current actual. Equivalent scope dimensions match regardless of
  JSON key order. Ambiguous actuals are displayed without a verdict.
  The comparison uses exact fixed-decimal arithmetic, not rounded JavaScript
  Numbers. Actual issuer publication time (`reported_at`) must be known.
  Model drivers must have been accepted strictly before publication; management
  guidance must have been both issued (when known) **and accepted** strictly
  before publication. Same-time/post-result expectations are displayed without
  predictive verdicts. Withdrawn guidance is not benchmarked.
- A compact "Prior BASE assumptions to review" panel highlights comparable
  differences between a published actual and an accepted pre-result BASE driver.
  It shows the exact actual, prior assumption, model revision and primary-source
  link, with a control to filter the detailed metric. There is no materiality
  threshold, investment execution advice or automatic revaluation. Unknown
  timestamps, duplicate comparable actuals and ON-target results create no
  review prompt.
- Provider consensus revenue/EPS is shown separately; it is **not** treated as
  company-specific operating guidance or model drivers.
- Partial history, unsupported coverage and missing definitions are explicit.
  No data is not zero, and a missing row is not evidence that the issuer did
  not publish it.

This is a **read-only** client; proposal acceptance and canonical imports
remain server-side human-reviewed workflows. It uses the existing authenticated
company context API and React components, not a second source of truth.
Accepted model driver rows appear here once explicitly published with an
accepted model revision (see the model publication contract).

Isolated UI tests check metric grouping, exact comparability, status handling
and source attribution. The tab has not been deployed or supplied live data
from a production environment as part of PR #42.
