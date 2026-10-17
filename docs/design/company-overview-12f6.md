# Company Overview & Investment Summary UX — Milestone 12F.6

Status: **COMPLETE**

## Purpose

The Company Overview answers one question: **What matters most about this business right now, and where should I go next?** It is a concise investment-research summary assembled from accepted canonical state. It does not introduce a new analytics engine or reproduce calculations in React.

## Information hierarchy

The page uses the Company Explorer header for identity, exact listing, lifecycle, current quote and quote freshness. The overview then follows the shared three-layer pattern:

1. **Glance** — Investment summary cards show lifecycle, current portfolio position, the method-aware expected return label, decision state and coverage badges. Enterprise-return models are labelled as enterprise IRR; only equity-perspective methods are labelled shareholder IRR.
2. **Analysis** — Investment case, valuation context, independent business assessments and portfolio context are presented as compact cards. Thesis claims, fair values, return basis, scores, target gaps and freshness remain explicit. Fair value is labelled as a valuation reference, not a future price forecast.
3. **Evidence / audit** — Explore-next links lead directly to Financials, Valuation, Thesis, Research and History. Identity, listings, lifecycle history and holding evidence remain available in one disclosure. The compact Attention Center shows the three highest-priority company events and links to their canonical records.

The first screen stays useful for complete, partial, missing-model and conflicted-research states. Empty and stale states explain what is missing and provide the next view to inspect; they are never rendered as zero or a passing conclusion.

## Canonical data consumed

`CompanyOverview` composes existing typed endpoints through `useResearch`:

- `GET /v1/companies/{id}/scores/current` for the four independent score dimensions.
- `GET /v1/companies/{id}/thesis` for the accepted thesis revision, claims, confidence and timestamps.
- `GET /v1/companies/{id}/model-outputs/current` for method-specific scenario values, return basis, normalized outputs and QA state.
- `GET /v1/companies/{id}/rankings` and `GET /v1/companies/{id}/execution-pace` for recorded decision context.
- The existing company detail and market-data requests for portfolio context, exact listings, price freshness and holdings evidence.
- The existing Attention Center feed for material events and data-quality issues.

Model selection is presentation-only: a published complete output is preferred, then another published output, then the first canonical output. No fair value, IRR, rank or allocation value is calculated in the browser. Missing method metadata keeps the return label generic and calls out that the return basis is unavailable.

## Interaction and accessibility

- Shared `PageSection`, `MetricGroup`, `MetricCard`, `StatusIndicator`, `EmptyState`, `Badge`, `Button` and `DetailDrawer` patterns are reused.
- Explore-next cards and contextual links preserve the company ID and selected view, so every detailed workspace is one interaction away.
- The lifecycle editor remains behind the audit disclosure and keeps its existing optimistic-concurrency and reason requirements.
- The compact attention feed is deliberately limited to the three highest-priority recent company items; the full feed remains available through **Open feed**.
- Cards collapse to one column on small screens. The company tab list remains keyboard navigable and scrollable without page-wide horizontal overflow.
- Display percentages use readable two-decimal presentation while API precision is unchanged. Exact source values and timestamps remain available in detailed views.

## Visual QA

The running local application was reviewed with real PostgreSQL-backed data at desktop and mobile widths. The review covered a Portfolio company (Alphabet), a Watchlist company (AAON, Inc.) and a Candidate (Addtech), including complete, partial, missing-listing, missing-model, no-target and no-thesis states.

- [Portfolio desktop overview](C:/Users/Paul%20Zwecker/Desktop/Projekte/portfolio-app/docs/design/screenshots/company-overview-12f6-desktop.png)
- [Portfolio mobile overview](C:/Users/Paul%20Zwecker/Desktop/Projekte/portfolio-app/docs/design/screenshots/company-overview-12f6-mobile.png)
- [Watchlist overview](C:/Users/Paul%20Zwecker/Desktop/Projekte/portfolio-app/docs/design/screenshots/company-overview-12f6-watchlist.png)
- [Candidate overview](C:/Users/Paul%20Zwecker/Desktop/Projekte/portfolio-app/docs/design/screenshots/company-overview-12f6-candidate.png)

The second inspection confirmed the summary is understandable within the initial viewport, return labels respect method metadata, missing states remain prominent, and the mobile stack keeps the next-action links and attention feed usable.

## Known limitations

- Overview completeness is bounded by accepted PostgreSQL state. It does not backfill theses, model inputs, targets, rankings or market facts.
- Sparse or unavailable consensus, filings, model revisions and research evidence remain visible as unavailable; no fallback values are introduced.
- Attention ordering is the existing deterministic feed ordering with a compact top-three presentation. It is not a new recommendation or prioritization engine.
- Detailed scenario editing, evidence drawers and historical comparisons remain in their dedicated Company Explorer views.
- The page does not accept model, thesis or research revisions, confirm holdings, change targets, alter lifecycle or execute trades.
