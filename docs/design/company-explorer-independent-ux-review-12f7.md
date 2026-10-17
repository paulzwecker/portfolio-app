# Company Explorer — Independent UX Review & Refinement (12F.7)

Status: **COMPLETE**

## Scope and review method

This review treats Company Explorer as one investor workflow. I inspected the
running PostgreSQL-backed application before changing code at desktop width and
at a narrow mobile width, then exercised the six views for Alphabet (Portfolio),
Axon Enterprise (Watchlist, owner-cash-flow model), AAON (incomplete Watchlist)
and Addtech (Candidate with missing listing/model state).

The review covered:

- Overview and company identity/listing context
- Financials table → chart selection, annual/quarterly controls and source access
- Valuation summary, scenario selection, model-family selection and draft entry
- Investment Thesis missing state, quality assessments and research-next queue
- Research & Evidence activity, filings, source links and review queue
- Historical Analysis price, expectations, estimates, decisions and event timeline

No accepted model, thesis, holding, target, score, ranking or research record was
changed during inspection.

## Initial independent assessment

The overall structure is coherent and the six views share a recognizable header,
tab rail, exact-listing context and explicit missing states. Financials and
Research & Evidence are especially usable for sparse real data: they explain
what is unavailable and retain source actions. Valuation correctly separates
enterprise UFCF from owner-cash-flow equity IRR at the summary level.

The main risks were semantic rather than cosmetic. Historical Analysis used a
shareholder-return label for an enterprise UFCF series, the DCF editor called an
old model calculation price a “Current quote” while the shared header showed a
newer canonical quote, and a settled no-model response could remain presented as
“Loading.” These findings could mislead an investor even though the underlying
calculations were unchanged.

## Findings register (before refinement)

| ID   | Page / component                                           | Investor task affected                                        | Evidence                                                                                                                                                                       | Severity  | Root cause                                                                                  | Proposed improvement                                                                                                                                                                          | Scope                                          |
| ---- | ---------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| F-01 | Historical Analysis / `CompanyHistoricalAnalysisWorkspace` | Understand the economic meaning of historical expected return | Alphabet showed “Expected shareholder return” while the adjacent methodology and API value were “Probability-weighted enterprise UFCF IRR.”                                    | **Major** | Static equity label in a method-aware history surface.                                      | Derive the label from canonical return perspective: shareholder for EQUITY, enterprise for ENTERPRISE, generic when unclassified. Apply the same label to timeline cards and event summaries. | Systemic within historical return presentation |
| F-02 | Valuation / `CanonicalDcfExplorer`                         | Compare the accepted valuation with today’s market price      | The header showed fresh GOOGL $340.59 (16 Oct), while the expanded DCF editor showed “Current quote” $351.66 dated 9 Oct and marked stale.                                     | **Major** | A revision/output price basis is labelled as a live quote.                                  | Rename the editor field to “Price basis at calculation” and explain that the header is the current canonical quote; preserve the stored date/status.                                          | Local semantic presentation                    |
| F-03 | Overview / `CompanyOverview`                               | Diagnose missing model coverage                               | Addtech’s settled `NO_MODEL` response still showed “Loading accepted model output…” in the valuation card.                                                                     | **Major** | The view distinguishes request error from data response but not an explicit empty response. | Render “No accepted model output” when the canonical response is present without a selected model. Keep loading only while the request is unresolved.                                         | Shared missing-state pattern                   |
| F-04 | Historical Analysis                                        | Read return and market context quickly                        | Historical cards and timeline values exposed long decimal strings such as `12.7970006925%` and `22.6324376098%`.                                                               | Minor     | History reused high-precision display formatting intended for exact audit values.           | Use readable two-decimal display in summaries; retain exact values in source/detail interactions.                                                                                             | Local readability                              |
| F-05 | All views                                                  | Keep orientation while moving between workflows               | The identity header and tab rail are consistent. The generic company subtitle is repeated across all views, but it does not block navigation and the active tab remains clear. | Polish    | Shared header copy is intentionally broad.                                                  | Keep for this bounded milestone; consider view-specific supporting copy only if it can be sourced without duplicating page explanations.                                                      | Shared, deferred                               |

Before screenshots and prior visual evidence are retained in the earlier
milestone artifacts:

- [12F.5 history desktop](screenshots/company-history-12f5-desktop.png)
- [12F.6 overview desktop](screenshots/company-overview-12f6-desktop.png)
- [12F.6 overview mobile](screenshots/company-overview-12f6-mobile.png)

## Planned bounded refinement

1. Make historical return labels perspective-aware without changing API data.
2. Clarify the DCF editor’s stored price basis without replacing it with a new
   quote or calculation.
3. Make settled no-model states explicit on Overview.
4. Reduce historical summary precision while preserving exact source values.
5. Add focused tests for return-label semantics and explicit no-model states.

The rest of the review remains presentation-only. No new financial calculations,
methodologies, data contracts or investment rules are planned.

## Refinements implemented

The bounded fixes were completed without changing backend contracts, canonical
state or financial calculations:

- `CompanyHistoricalAnalysisWorkspace` now derives Expected Return labels from
  the canonical return perspective. Enterprise UFCF history is presented as
  “Expected enterprise return”; shareholder methods retain “Expected
  shareholder return”; unclassified methods use “Expected return”. The label is
  consistent in the summary, timeline and model-event cards.
- Historical summary, chart-tooltip and decision-context percentages now use a
  readable two-decimal presentation. Exact values remain in the underlying
  API/source detail rather than being rounded in canonical data.
- `CanonicalDcfExplorer` now calls the stored revision value “Price basis at
  calculation” and labels its status “Price basis”. The editor explains that
  the shared company header is the current canonical quote, while the displayed
  value is the immutable price captured for that model output.
- `CompanyOverview` now distinguishes a settled `NO_MODEL` response from a
  request that is still loading. Candidate and incomplete Watchlist states
  show “No accepted model output” with a direct Valuation path instead of a
  persistent loading message.
- Focused regression coverage was added for return-perspective labels and the
  explicit no-model state. Existing Company Explorer components and shared
  design-system primitives were reused.

## Investor workflows exercised

| Workflow                  | Live evidence and result                                                                                                                                                                                                                            |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A — Portfolio overview    | Alphabet overview showed exact GOOGL listing, fresh quote, Portfolio lifecycle, target/current context, scores and explicit missing thesis state.                                                                                                   |
| B — Financial statements  | Alphabet Financials supported annual/quarterly controls, selectable metric rows, compatible charting and source inspection; unavailable EPS/EBITDA/cash-flow/consensus remained explicit.                                                           |
| C — Valuation/modeling    | Alphabet enterprise UFCF and Axon owner-cash-flow views preserved method-specific return semantics, scenario selection and revision/editor entry. The DCF editor now clearly distinguishes its stale historical price basis from the current quote. |
| D — Thesis/research       | Alphabet’s missing thesis, quality dimensions, filings, source links and open research queue were inspectable; no empty state was presented as a conclusion.                                                                                        |
| E — Historical analysis   | Alphabet history exposed price, expectations, decisions and timeline context with enterprise-return labels, readable precision and explicit unavailable/no-look-ahead states.                                                                       |
| F — Incomplete coverage   | AAON showed unavailable method/return context without fabrication; Addtech showed no listing/model state and now renders an explicit no-model valuation card.                                                                                       |
| G — Responsive navigation | Desktop and narrow mobile views retained the shared identity header, exact-listing context, selected tab, meaningful loading/empty states and reachable next views.                                                                                 |

## Before/after visual evidence

The existing 12F.5/12F.6 artifacts remain the baseline. New captures were made
after the refinements against the running PostgreSQL-backed application:

- [History desktop after](screenshots/company-explorer-12f7-history-after-desktop.png)
- [History mobile after](screenshots/company-explorer-12f7-history-after-mobile.png)
- [Candidate overview desktop after](screenshots/company-explorer-12f7-candidate-after-desktop.png)
- [Candidate overview mobile after](screenshots/company-explorer-12f7-candidate-after-mobile.png)
- [Valuation/editor desktop after](screenshots/company-explorer-12f7-valuation-after-desktop.png)

The history capture shows “Expected enterprise return” and rounded summary/event
values. The valuation capture shows the fresh current quote in the company
header alongside the separately labelled stale “Price basis at calculation”.
The Candidate capture shows “No accepted model output” for a settled `NO_MODEL`
response. Mobile inspection confirmed the identity/header and tab rail remain
usable at 390px; the full historical analysis remains vertically progressive
rather than presenting a clipped desktop table.

## Final scorecard

Scores use a five-point scale (5 = excellent). The minimum completion threshold
for this audit is 4, with no unresolved Critical or Major usability defect.

| Area                           | Score | Evidence                                                                                                                                        |
| ------------------------------ | ----: | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Information hierarchy          |     4 | Glance/analysis/evidence layers are consistent across all six views.                                                                            |
| Navigation and discoverability |     4 | Shared company header, exact-listing context, tabs and contextual next links were exercised.                                                    |
| Financial readability          |     4 | Method-aware return labels, compact precision and explicit units/statuses are visible.                                                          |
| Modeling workflow usability    |     4 | Scenario controls, accepted/draft boundary, editor entry and revision evidence are clear.                                                       |
| Research/evidence usability    |     4 | Filings, source links, queue items and missing thesis states are grouped by purpose.                                                            |
| Interaction consistency        |     4 | Shared tabs, cards, status indicators, drawers and explicit missing states are reused.                                                          |
| Desktop usability              |     4 | Desktop screenshots and live workflows show readable density and clear primary actions.                                                         |
| Mobile usability               |     4 | 390px live inspection and after screenshot retain context, controls and progressive disclosure.                                                 |
| Accessibility                  |     4 | Live accessibility trees exposed named tabs, controls, headings, listings, statuses and source actions; no browser warnings/errors were logged. |
| Frontend architecture/reuse    |     4 | Changes are limited to presentation adapters and existing shared primitives; no duplicate calculation or API layer was added.                   |

## Verification

- Live desktop and mobile inspection completed for all six Company Explorer
  views, plus Axon, AAON and Addtech representative states.
- Browser diagnostics for the final live pass reported no console warnings or
  errors.
- `npm run test --workspace @portfolio/web` passed (163 tests).
- Focused Company Explorer tests passed (2 files, 7 tests), including the new
  return-label and no-model regressions.
- `npm run typecheck --workspace @portfolio/web` passed.
- `npm run lint --workspace @portfolio/web` passed.
- `npm run build --workspace @portfolio/web` passed.
- Prettier checks passed for the changed source, test and review-document files.
- Focused Company Explorer browser coverage passed (4/4 desktop/mobile cases).

No backend, database, API, accepted model, thesis, holding, target, ranking or
execution record was changed by this milestone.

## Remaining limitations

Real development data is intentionally sparse: some companies have no accepted
thesis, consensus history, exact listing or comparable model. Those states
remain visible and are not scored as product defects. The DCF editor continues
to show the historical price basis captured with its accepted output while the
header shows the current quote; the new wording makes that distinction explicit.
The shared company subtitle remains intentionally generic, and could receive
view-specific supporting copy in a future information-architecture pass if a
canonical source can provide it without duplication.

## Upstream suggestions

- Universe and Portfolio links should preserve the selected company and target
  view when opening Company Explorer.
- Comparative tables should carry method-aware return labels and exact-listing
  context in their compact cells, using the same missing/stale status language.
- Any future visual work should continue to consume canonical summaries and
  source timestamps rather than adding frontend calculations.

This milestone is complete. The next milestone was not started.
