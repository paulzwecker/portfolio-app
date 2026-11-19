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
  Actuals must be exact EQ and VERIFIED/RESTATED. Unknown or qualified
  comparisons are withheld rather than guessed. The comparison uses exact
  fixed-decimal arithmetic, not rounded JavaScript Numbers. A model driver or
  guidance observation accepted **after the actual became known** is displayed
  but does not receive a predictive performance verdict. Withdrawn guidance
  is not benchmarked.
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
