# Milestone 11F — Company Explorer & Financial Modeling UX

Milestone 12B extends the Financials view described here with the
`FinancialStatementsWorkspace`: a selectable metric table, multi-series chart and
source/alignment drawer. The older card-oriented component names below describe the
pre-12B migration and are retained only as historical architecture context.

## Product structure

The Company Explorer is organized around the investor's company-review question:
what is known about the business, what is expected, and what is it worth? A stable
identity header is followed by six focused views: Overview, Financials, Valuation,
Investment Thesis, Research & Evidence, and Historical Analysis. This follows the
11A Glance / Analysis / Evidence hierarchy while keeping the user's current company
context visible.

The route at `apps/web/src/app/company/[id]/page.tsx` only resolves the route parameter
and renders the workspace. `CompanyExplorerWorkspace` chooses the tab and mounts the
relevant domain panels. Existing section hashes map into the new view so deep links
from the app shell continue to work. Tab state is addressable by `?view=` and supports
arrow, Home and End keyboard navigation.

## Domain ownership and component map

| User task                                      | Components                                                                                                    | Canonical reads                                                        |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Identify the issuer and exact quote basis      | `CompanyIdentityHeader`, `CompanyOverview`                                                                    | Company detail and listing-specific market data                        |
| Read financial history                         | `FinancialStatementsWorkspace`, `FinancialSeriesChart`, `FinancialStatementsTable`, `FinancialSourceDrawer`   | Reported fundamentals and definitions                                  |
| Compare outside expectations                   | `FinancialMetricSelector`, `FinancialSourceDrawer`                                                            | Provider-continuous consensus and accepted agent research revisions    |
| Review or edit valuation                       | `CanonicalDcfExplorer`, `CanonicalArchetypeExplorer`, `ModelMigrationStatus`, `ModelOutputs`                  | Native model revisions/calculation preview and imported output history |
| Review thesis and evidence                     | `CompanyInvestmentThesis`, score editor/history                                                               | Accepted thesis revisions, linked evidence and score assessments       |
| Inspect primary documents and qualitative risk | `SourceDocuments`, `CompanyRiskAssessments`                                                                   | Filing metadata and accepted risk-assessment history                   |
| Examine changes over time                      | `MarketFacts`, `EstimateMomentum`, `TemporalAlignment`, `ExpectedReturnHistory`, ranking and execution panels | Time-stamped canonical observations and immutable decision snapshots   |

Generic display behavior lives in shared components under `components/app` and
`components/features/modeling`. Domain components remain under the Company or
Modeling feature boundary. The shared financial output comparison handles only
presentation of normalized values and before/after differences; it does not
recalculate or compare the underlying methods.

## Financial exploration rules

Reported statements are selected by metric and annual or quarterly period. Available
canonical statement facts are displayed with economic period, source filing context,
provider, filing date, correction history, units, currency and quality state. A
compact multi-series chart connects resolved observations only when their units and
currencies match and breaks at missing or checked windows. When selected rows have
different bases, the Financials view offers an explicit indexed comparison (100 at
each series' first available observation); raw values remain in the table and drawer.
It does not calculate ratios, growth, free cash flow, EBITDA or EPS. Conflicting
observations, unknown currency and missing periods remain explicit in the table;
incomparable series are not silently placed on one raw-value scale.

Consensus, agent research, reported actuals and accepted model projections are
separate streams. The Agent Research panel preserves author, source, fiscal period,
scenario, rationale, uncertainty and revision history. Method projections remain in
Valuation because ordinal projection years cannot be treated as fiscal years without
an explicit mapping in the accepted model state.

## Valuation and model editing

The existing canonical editors remain the source of model authoring:

- UFCF DCF keeps enterprise cash-flow assumptions, scenarios, deterministic API
  previews, projection review and revision conflicts.
- Owner Cash Flow keeps per-share owner-cash-flow methodology and its own projections.
- Residual Income keeps book value, ROE and residual-income methodology.

The view makes model identity, listing/currency basis, accepted revision, rationale,
sources, projections, normalized outputs and revision history visible in one place.
The deterministic engines and return semantics remain in FastAPI. Preview is not
acceptance; explicit acceptance appends against the displayed base revision. Imported
legacy output snapshots stay read-only and visually distinct from native editable
models. The shared output grid aligns labels and precision; it does not make methods
economically interchangeable.

## Accessibility and responsive behavior

The tablist has a single selected tab stop, labeled tabs and one associated panel.
Arrow keys move selection; Home and End move to the first and last view. The identity
selector is labeled and uses exact listing IDs. The actuals chart has an accessible
summary, and the reported-value table remains the detailed alternative. Shared tables,
cards and editors use narrow-screen layouts; the tab rail may scroll horizontally,
while the page itself does not require a wide desktop viewport.

## Verification

The Company Explorer tests cover legacy-anchor mapping, tab semantics, missing versus
zero values, fiscal-period labels, chart provenance and exact-listing context. Browser
coverage uses the existing company fixtures to exercise factual history, consensus,
agent forecasts, thesis evidence, filing history, return history and the model editor
at desktop and mobile widths. UFCF DCF, owner-cash-flow and residual-income views all
use the shared normalized-output presentation while keeping method-specific inputs
and projections.

## Limitations

- Reported EBITDA, EPS and free cash flow are not synthesized when those facts are not
  present in the canonical reported-fundamentals contract.
- Native model projections still lack a fiscal-year anchor in accepted revisions, so
  they remain in Valuation instead of appearing as apparently aligned statement
  forecasts.
- Historical model projections without an explicit fiscal mapping cannot be placed
  on the reported/consensus fiscal timeline.
- Native model editors retain their existing method-specific forms; a unified
  cross-method scenario probability visualization has not been added.
- Sensitivity controls remain limited to the assumptions and previews implemented by
  each supported model family. No frontend valuation or sensitivity formula was
  introduced in this milestone.
