# Milestone 12F.1 — Company Financials UX Redesign

## Purpose and review notes

The Financials view answers **how has this company's financial performance
developed, and what do available forecasts imply?** The implementation keeps
FastAPI as the owner of period selection, fact precedence, fiscal labels,
point-in-time cutoffs and data quality. React only arranges the canonical
response and provides presentation controls.

The mandatory inspection found that the previous 12B workspace already had the
right table → chart and source-drawer foundation. Its main usability gaps were
that statement sections and estimates shared one crowded control row, mixed
units were only separated implicitly, coverage was hard to assess before reading
the table, and the unavailable Growth & Ratios area was not an actionable view.
The real local database was inspected through Adyen (portfolio, EUR listing,
fresh quote). Its canonical reported-fundamental response currently has no
eligible facts, so the page correctly renders an explicit empty/coverage state.
Fixture-backed browser tests provide the complete populated, partial and source
drawer states.

## Information architecture

| Layer            | Experience                                                                                                                                                                                                                                                           |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Glance           | Coverage cards for timeline columns, reported rows, forward rows and flagged cells; annual/quarterly and history controls; the latest observation timestamp.                                                                                                         |
| Analysis         | One chart above one compact statement table. The table is the selection surface: checking a row immediately adds it to the chart. Statement tabs separate Income Statement, Balance Sheet, Cash Flow Statement and Estimates.                                        |
| Evidence / audit | A cell opens the contextual source drawer with the selected observation, alternate sources, publication/observed/recorded times, correction lineage and quality reason. The Sources & alignment action opens the complete limitation, provider and research archive. |

Growth & Ratios is an explicit view that explains why it is unavailable. The
page does not derive ratios, EPS, EBITDA, free cash flow or growth in the
browser. Accepted model projections are explicitly kept in Valuation until an
accepted revision carries a verified fiscal-period anchor.

Actuals, analyst consensus and agent forecasts remain visibly distinct through
row labels, chart line styles and the source visibility toggles. Consensus is
never blended across providers. Missing, stale, conflicting and unknown-basis
cells remain in the table/drawer and do not become chart points.

## Interaction decisions

- **Period:** Annual or Quarterly controls reset the default history window to
  10 years or 16 quarters. The range selector and app-knowledge cutoff remain
  addressable controls; the cutoff is sent to both `as_of` and `known_at`.
- **Metric selection:** Each row has an accessible checkbox. Six rows may be
  selected at once. Selected chips above the chart can remove a series without
  losing the table position.
- **Chart comparison:** Separate scales is the honest default. Indexed
  comparison is enabled when selected rows have different currency/unit bases;
  it normalizes each plotted series to 100 at its first available observation
  for visual trend comparison only. Raw values remain in table cells, tooltips
  and the source drawer. A zero baseline cannot be indexed and remains
  available in separate-scale mode.
- **Periods:** Fiscal labels are emitted by the API only when contemporaneous
  filing evidence supports them. Ambiguous periods continue to show their date
  rather than an inferred fiscal year. Repeated comparative facts are selected
  by the canonical backend period semantics, not by the order returned to React.
- **Sources:** Every available value is a button that opens evidence. Source
  status and reason are present in the row even when the value is unavailable.

## Components changed and boundaries

- `FinancialStatementsWorkspace` now composes coverage cards, category-aware
  row filtering, explicit unavailable states and comparison mode state.
- `FinancialMetricSelector` owns the compact category/source toolbar and the
  separate-scale/indexed comparison choice.
- `FinancialSeriesChart` owns only SVG presentation geometry. Indexed values are
  temporary chart coordinates; canonical source values are untouched.
- `financial-series.ts` owns deterministic presentation helpers for series
  gaps and indexed chart geometry; it does not calculate financial metrics.
- `FinancialStatementsTable`, `FinancialSourceDrawer`, `FinancialPeriodControls`
  and shared `MetricCard`, `MetricGroup`, `ChartContainer`, `DetailDrawer` and
  status components are reused.

No API schema, financial calculation, accepted model, holding, target,
consensus observation or reported fact was changed.

## Verification and visual review

- Frontend typecheck and lint passed.
- Financial-series unit tests pass, including missing/checked gaps, zero and
  negative source values, indexed comparison, and zero-baseline refusal.
- Existing Company Explorer browser coverage passed at desktop and mobile
  widths with the populated fixture, including row selection, quarterly/annual
  switching, source drawer, no page-wide overflow and missing-source states.
- The live local application was started with the canonical API and inspected at
  desktop and mobile-sized browser views. Adyen's empty reported-fundamental
  state was verified as explicit rather than rendered as zero. Full populated
  visual coverage is represented by the fixture-backed browser run because the
  current local Adyen record has no eligible canonical statement observations.
- A final live pass after the chart rendering guard verified populated Alphabet
  data, the evidence drawer, the quarterly controls and the narrow mobile table
  without browser console errors.

## Known limitations

- Growth & Ratios, derived FCF, EBITDA and EPS remain unavailable until their
  canonical contracts are populated; no frontend fallback is appropriate.
- Native model projections still require explicit fiscal anchors before they can
  join this timeline.
- The compact table intentionally uses a local horizontal scroll region on
  narrow screens; the surrounding page does not overflow horizontally. A
  future small-screen card/period switch can be added if period breadth makes
  the table too dense in real populated datasets.
