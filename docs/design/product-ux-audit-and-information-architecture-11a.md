# Milestone 11A — Product UX Audit & Information Architecture

> Implementation note: the shared visual foundation and incremental component ownership rules are documented in [Milestone 11B — Design System & Frontend Architecture](./design-system-and-frontend-architecture-11b.md).

**Status:** Audit and proposal only. No application routes, components, calculations, contracts, or accepted data were changed in this milestone.

## Recommendation

Reorganize around the investor's sequence of work: orient in **Overview**, inspect ownership in **Portfolio**, evaluate alternatives in **Decisions** and **Universe**, then follow a company into **Company Explorer**, **Modeling**, or **Research**. Put provider and synchronization diagnostics in **Operations**. Keep each existing canonical workflow available while its new home is introduced.

Use three consistent levels on the destination pages:

1. **Glance** — what is true now, what changed, and what needs attention.
2. **Analysis** — comparisons, histories, assumptions, and decision context.
3. **Evidence / Audit** — source, effective and recorded times, quality, methodology, revision/run identity, and review trail.

These are information layers, not new domain concepts. They should arrange existing API responses without recreating calculations or hiding unavailable states.

## Audit basis and limits

I inspected the web-specific instructions, all current Next.js primary page routes, shared navigation and page components, and the relevant Company Explorer, Portfolio, ranking, model, Candidate Pipeline, Research Queue, Attention Center, trigger, agent-operation, and recurring-operation documentation.

The local application was **not running** during this audit: the in-app browser had no open tabs and no listener was present on local ports 3000 or 8000. Therefore, this is not represented as a live-database walkthrough. I used the repository's fixture-backed Playwright suite as the browser evidence: **38 desktop/mobile cases passed and 2 were skipped**. Those tests exercise mocked canonical API responses and responsive states; they verify presentation and interaction, not current PostgreSQL coverage. Four live/database-dependent test groups were excluded from that run. No database or portfolio state was changed.

The four named applications are treated as conceptual references for portfolio orientation, compact comparisons, actual-versus-estimate timelines, and allocation visualization. This proposal does not copy their branding or page layouts.

## Current product surface

The current navigation is a fixed sidebar with seven links: Workspace, Portfolio, Attention, Universe, Research Queue, Candidate Pipeline, and Model Sync. On small screens it changes into a two-column link grid. The routes already contain substantial, tested domain UX; the problem is primarily where the work is grouped and how much context each screen has to carry.

| Current route / surface              | Current visible responsibilities                                                                                                                                                                                                                                                                                             | Proposed home                                                                                                                                                                                                                                                                                    |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/` — Workspace                      | Welcome copy, empty Overview card, links to Portfolio and Universe, API/database service status.                                                                                                                                                                                                                             | **Overview**: a live operating brief with canonical portfolio posture, material changes, decision state, and blockers. Keep service health in a compact status affordance and Operations.                                                                                                        |
| `/portfolio`                         | Current mark-to-market value and dates, holdings freshness, target architecture, largest exposure, gaps, cash and FX, standalone securities, holdings confirmation, Portfolio Rank, Watchlist opportunities, Attention Center, data-quality checks, accepted risk assessments, and explicit rank/Execution Pace run actions. | **Portfolio** for positions and target architecture. Move cross-company decision ordering to **Decisions**; show only concise change and data-risk summaries on Overview. Keep holdings confirmation explicit and history-preserving.                                                            |
| `/universe`                          | Company search; lifecycle, score, ranking, price, model, Estimate Momentum, and Execution Pace filters; sorting; company identity/listing and investment context in the company list.                                                                                                                                        | **Universe**: discovery and comparison table with a small default column set, optional columns, and a company detail drawer/route. Preserve all filters and explicit missing states.                                                                                                             |
| `/company/[id]` — Company Explorer   | Identity/listings and lifecycle header; 20 in-page anchors spanning context, attention, scores, market, fundamentals, sources, consensus, research, thesis, risks, momentum, forecast/outcome, model methods and outputs, histories, ranks, and Execution Pace.                                                              | **Company Explorer** as the entity-centered destination. Group existing sections into Glance, Analysis, and Evidence / Audit; replace the long anchor inventory with a smaller section navigation and contextual sub-tabs. Preserve deep links to every retained section.                        |
| `/attention`                         | Full source-linked material-change feed and filters.                                                                                                                                                                                                                                                                         | **Overview → Change feed** as a prominent summary plus a full feed view under Overview. Link a feed item to its canonical source and distinguish it from review tasks in Research.                                                                                                               |
| `/candidates`                        | Candidate search/status/stage filters, ranked Candidate queue, selected-company gate workflow, evidence and research recommendation history.                                                                                                                                                                                 | **Research → Candidate Pipeline**. Keep the gate sequence and explicit recommendation separate from lifecycle promotion.                                                                                                                                                                         |
| `/research-queue`                    | Thesis Watch handoff, lifecycle/search/completion filters, derived research needs, trigger scan/publication, task completion and immutable completion history.                                                                                                                                                               | **Research → Review Queue**. Keep current tasks and completed history distinct; connect each trigger to the related Company Explorer evidence.                                                                                                                                                   |
| `/model-sync`                        | Recurring operations status, model proposal discovery/preview/accept/reject/history, portfolio-state publication, research/thesis and risk proposal sync, agent work-feed publication, and synchronization run history.                                                                                                      | Split into **Modeling → External revision review** for model contracts; **Research → Agent submissions** for research/thesis/risk; **Operations → Integrations and jobs** for portfolio-state publishing, provider/workbook status, polling, errors, and run receipts. No capability is removed. |
| Company-embedded model panels        | UFCF, owner-cash-flow, and residual-income viewing/editing, deterministic preview, output and revision inspection, migration/parity status, and imported output history.                                                                                                                                                     | **Modeling** for the full authoring workspace, with Company Explorer as the entry point and the model editor available in company context. Keep method-specific inputs and outputs separate.                                                                                                     |
| Shared shell and reusable components | `Navigation`, `PageTitle`, `ServiceStatus`, badges/cards, `AttentionCenter`, `HoldingsConfirmation`, `RiskAssessments`, `RecurringOperationsStatus`, and domain panels.                                                                                                                                                      | Shared navigation, page header, status, filters, responsive table/card, provenance, and review patterns described below. Keep domain-owned calculations and validation in the API.                                                                                                               |

## Component inventory and placement

| Component group                  | Current examples                                                                                                                                                           | Destination / role                                                                                                                                                                                                          |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Global shell                     | `Navigation`, root sidebar/header, skip link, `PageTitle`, `ServiceStatus`                                                                                                 | Shared shell. Navigation exposes the eight investor destinations; the header provides global company search, active portfolio/workspace context, and a compact system-status affordance. Keep keyboard skip/focus behavior. |
| Portfolio posture and allocation | `MetricCard`, `GapRow`, `OpportunityRow`, `WatchlistOpportunityRow`, `DataQualityCard`, `ExecutionSummaryCard`                                                             | Portfolio owns valuation, holdings, target, gaps, and exposure. Decisions owns rank and pace comparison. Overview gets compact, linked summaries only.                                                                      |
| Confirmation and risk            | `HoldingsConfirmation`, `RiskAssessments`                                                                                                                                  | Holdings confirmation in Portfolio; qualitative portfolio/company risk in Portfolio or Company Explorer with exact baseline and stale-state labels. Risk findings remain separate from numeric Risk scores.                 |
| Universe and rank context        | Universe filters/list rows and Company Explorer `RankingPanel`                                                                                                             | Universe is for company discovery; Decisions compares rank types; Company Explorer shows the selected company’s recorded position, run and input context. Do not blend Portfolio, Watchlist, or Research Rank.              |
| Company context                  | Identity/listings, lifecycle, targets/holdings, independent scores, market facts, reported fundamentals, consensus, filings, thesis and evidence, risk, research forecasts | Company Explorer. Keep identity, source and effective/recorded dates visible; use progressive disclosure for long history.                                                                                                  |
| Market and return analysis       | Price/regime chart, Estimate Momentum, temporal alignment, forecast accuracy, expected-return history/attribution, scenario/decision evaluation                            | Company Explorer Analysis; Portfolio Analysis for portfolio-level aggregates only where canonical histories support them. Retain exact listing, currency, method, period, and knowledge-time context.                       |
| Model authoring and interchange  | Canonical DCF/archetype editors, migration status, imported outputs, Sheets model review                                                                                   | Modeling. Distinguish accepted native revisions from imported output snapshots and pending external proposals. Keep preview → compare → explicit acceptance.                                                                |
| Research workflow                | Candidate Pipeline, Research Queue, thesis, sources, agent research/risk submissions, triggers and handoffs                                                                | Research. Queue items are work needs; Attention items are source changes. Link them instead of duplicating them.                                                                                                            |
| Operations and integration       | `RecurringOperationsStatus`, ingestion freshness, Google Sheets status/runs, publication receipts, partial failures                                                        | Operations. Show concise coverage and job state first; expose provider/run diagnostics on demand. Keep important operational data risks linked from Overview and affected companies.                                        |

## Proposed navigation

Use the following primary information architecture. The first four destinations support frequent portfolio review; the remaining sections open focused workflows.

1. **Overview** — portfolio brief, material change feed, important blockers.
2. **Portfolio** — current holdings, latest known positions, mark-to-market value, targets, weights, gaps, cash, confirmation.
3. **Decisions** — Portfolio Rank, Watchlist Rank, Research Rank, Execution Pace, historical runs, and eligibility / excluded reasons. These remain distinct views and definitions.
4. **Universe** — search, filter, and compare tracked companies across lifecycle states.
5. **Company Explorer** — global company finder plus selected-company destination. The persistent search/quick switch opens the canonical company route; every table and alert links here.
6. **Modeling** — native models and methodology-specific editors, revisions and diffs, imported-output distinction, external Sheets proposal review.
7. **Research** — Candidate Pipeline, cross-lifecycle Review Queue, thesis/evidence, agent forecasts and submissions, risk proposals, trigger handoffs.
8. **Operations** — factual-data coverage, ingestion freshness and runs, provider diagnostics, Google Sheets connection/publication, recurring jobs and errors.

On desktop, use a compact primary sidebar with clear group boundaries and a persistent Company Finder. On mobile, use a single accessible menu/sheet with the same destinations and an always-available company-search affordance; do not squeeze eight labels into a two-column nav. The active company, portfolio, and relevant “as of” context should remain apparent after navigation.

## Primary investor journeys

1. **Understand current portfolio state:** Overview → Portfolio glance → inspect positions, valuation cutoff, confirmation age, targets and largest gaps → open missing quote/FX or target detail if needed. Current mark-to-market is not historical performance.
2. **Investigate a company:** Company Finder or Universe row → Company Explorer Glance → review listing/lifecycle/holding/target and quality/risk context → open Analysis or Evidence for a specific question.
3. **Compare opportunities:** Universe → set lifecycle and availability filters → choose comparable model/return basis and period where available → compare canonical API results → open a company for detail. Incompatible returns stay separate or unavailable.
4. **Evaluate model assumptions:** Company Explorer or Modeling → select model and accepted revision → inspect method-specific assumptions/scenarios → recalculate preview → compare assumptions, projections and outputs → enter rationale/source → explicitly append a revision. Sheets proposals use the same preview and acceptance path.
5. **Decide strategic allocation:** Portfolio → target and current allocation context → Decisions for rank and pace evidence → investor reviews strategic target independently. Execution Pace is timing context and never edits targets or holdings.
6. **Review agent research:** Research Review Queue → open trigger and exact source context → inspect thesis/research proposal and its base → preview → accept/reject explicitly → record completion separately. A delivered agent work item is not an accepted conclusion.
7. **Confirm holdings:** Portfolio → compare the exact latest snapshot, listings, quantities and cash → reconfirm unchanged or edit → provide actor/reason/effective time → append a new snapshot. Prior snapshots remain available.
8. **Diagnose missing data:** Overview/company status link → Operations coverage for provider/run-level cause → affected company’s Evidence / Audit for exact listing, observation, source and timestamps → retry only through the existing bounded ingestion flow.

## Shared three-layer page specification

| Destination      | Glance                                                                                                                         | Analysis                                                                                                                               | Evidence / Audit                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Overview         | Current value only when complete, latest holdings date, material changes, top actionable review needs, major data/model risks. | Brief links into portfolio and decision comparisons; no decorative or unsupported performance chart.                                   | Feed source/time on expansion; last successful ingestion and outstanding data-quality links.                                   |
| Portfolio        | Total and valuation status, positions-as-of, mark date, freshness, current weights, target gaps and cash currencies.           | Holdings/targets view, concentration context, allocation gap ordering, and time selection only for supported as-of valuation.          | Holdings confirmation history, price/FX observation identity, target revision and valuation completeness reasons.              |
| Decisions        | Latest preview/run and ranked/eligible counts separately by decision type.                                                     | Type-specific candidate list, supporting context and explicit exclusions. Execution Pace remains downstream and separate.              | Immutable run definition/version, as-of input snapshot, methodology, source records and missing-data reasons.                  |
| Universe         | Search result count and key identity/lifecycle/availability signals.                                                           | Compare companies with selectable supported fields and exact context; filters start compact and advanced filters progressively expand. | Row-level source/freshness and reason details, with a direct Company Explorer link.                                            |
| Company Explorer | Identity/listings, lifecycle, current portfolio/target context, independent score/rank/model/market availability.              | Business facts, consensus and agent forecast timelines, method-specific models and return comparisons.                                 | Filings and source links, accepted thesis/research/model revisions, exact dates, provenance, run IDs and supersession history. |
| Modeling         | Company/method, accepted revision, currency, freshness/parity state, and pending proposal count.                               | Method-specific assumptions, scenario inputs, deterministic projection/output preview, revision comparison.                            | Rationale/source, input basis, revision and contract identity, parity result, external publication and review history.         |
| Research         | Work by lifecycle and priority, open blockers, new evidence awaiting review.                                                   | Candidate gates, thesis claims, source comparison and proposal review.                                                                 | Evidence relations, source publication/observation/recording times, acknowledgments and immutable completion/review history.   |
| Operations       | Job health, source coverage/freshness and the few failures that require action.                                                | Provider, mapping, ingestion, workbook sync and recurring job diagnostics.                                                             | Attempt/run history, raw/provider source identity where available, retry reason and synchronization receipts.                  |

## Shared interaction conventions

- **Page headers:** one clear task-oriented title, scope/context (portfolio, lifecycle, listing, or selected “as of”), short description, and one primary action. Put optional actions in a secondary menu. Avoid repeating the same lifecycle/freshness explanation in every card.
- **Section navigation:** use a small number of accessible tabs or section links. Retain deep links and browser history for Company Explorer sections. Do not render 20 equal-weight anchors in the first viewport.
- **Comparison controls:** expose metric, fiscal period/horizon, source, methodology/return basis, listing/currency, and forecast/knowledge cutoff only when relevant. Keep effective/publication time distinct from observed/recorded time. Never imply unlike methods are directly comparable.
- **Detail drawers:** use a right-side drawer on wide screens and a full-height sheet/page on narrow screens. Include a heading, close button, Escape behavior, focus trap/restore, and deep-linkable company/source identity. Use the drawer for row context, not for a long authoring workflow.
- **Freshness:** show a readable state and relevant date/source (for example Fresh, Stale, Partial, Data check, Unavailable). Do not rely on color alone. “Stale but usable for context” must remain different from “eligible for current decision.”
- **Missing values:** retain explicit labels and reasons. Never format null as 0, neutral, rank 0, or a passing state. Keep the empty-state scope precise: no observation, no mapping, not migrated, insufficient history, or incompatible basis.
- **Provenance:** each material figure or assessment should expose its source/provider and effective/period date; recorded/observed time and revision/run identity belong in the detail surface. Historical views preserve “known then” versus “reported later.”
- **Responsive tables:** desktop gets sortable, labeled columns with a pinned identity column only where useful. Narrow layouts show a concise company card with the most decision-relevant fields and expandable detail; do not require page-wide horizontal scrolling to find identity or status. Preserve filter and sort controls in a compact filter sheet.
- **Review actions:** proposals and snapshot confirmations show preview/diff and source context before an explicit action. Confirmation/acceptance never happens on row selection or because a feed item was delivered.
- **Accessibility:** semantic landmarks and heading order, visible focus, keyboard-operable menus/filters/drawers, labeled inputs, announced loading/success/error states, and non-color status cues are acceptance requirements for each refactor slice.

## Low-fidelity destination specifications

### Overview

```text
Overview   [Portfolio selector] [As-of context when supported]
[Portfolio value/status] [Largest exposure] [Target gap] [Freshness]
[Material changes / review now]          [Decision snapshot: ranks + pace]
[Coverage/model risks]                   [Continue research / confirm holdings]
```

Lead with current canonical state and explain completeness. Use the Attention Center as a concise “changed” section; show research tasks separately. Do not show historical portfolio performance until transaction/holdings history supports an honest return series.

### Portfolio

```text
Portfolio  [valuation cutoff] [Confirm holdings]
[Value] [Positions as of] [Market/FX through] [Holdings age]
[Positions / cash / standalone listings]  [Current vs strategic target]
[Largest gaps]                            [Exposure and valuation-quality details]
```

Keep current mark-to-market, historical as-of reconstruction, holdings confirmation age, and quote/FX freshness independently labeled. Target edits remain an explicit investor-authored operation; no rank or pace action writes a target.

### Decisions

```text
Decisions  [as-of] [Preview / record run]
[Portfolio Rank] [Watchlist Rank] [Research Rank] [Execution Pace]
[Eligible / unavailable / data-check, per selected decision]
[Company] [Position/status] [Main supporting context] [Explicit reason]
[Run history and method details]
```

Each decision type has its own definition and status vocabulary. A cross-type switch is not a composite score. Preview and persistence are visibly separate operations.

### Universe

```text
Universe  [Search company, ticker, listing] [Lifecycle] [Availability]
[Filters: Scores] [Model/return basis] [Market] [Decision type] [More]
[Company/listing] [Lifecycle] [Quality] [Model/return] [Rank/status]
```

Default to useful discovery columns. Advanced filters (provider, history depth, data quality) open progressively. On mobile, a company card carries identity, lifecycle, one selected comparison context, and explicit missing state; detail opens Company Explorer.

### Company Explorer

```text
Company + lifecycle  [listing selector with venue/currency] [freshness]
[Glance] [Analysis] [Evidence / Audit]
Glance: thesis summary · score/risk · model/return basis · holding/target · latest change
Analysis: financial facts · consensus/agent forecasts/actuals · market · model scenarios
Evidence: source docs · assessments · model/research/thesis revisions · run history
```

Company-level section selection remains available through sub-tabs or a section index. Keep the current distinct objects and methodology behavior, but give each section a direct URL and a compact summary state.

### Modeling

```text
Modeling [Company] [Method] [Accepted revision] [Pending external proposal]
[Assumptions] [Scenarios] [Projections] [Valuation/outputs] [History]
[Edit inputs + rationale/source] → [Deterministic preview] → [Diff] → [Append revision]
```

Do not create a generic model grid. Preserve separate model families, imported-output-only coverage and parity limitations. Existing Company Explorer authoring remains a supported entry point.

### Research

```text
Research [Portfolio] [Watchlist] [Candidate] [Open/complete]
[Work queue: why now, company, source, next action]
[Candidate gates] [Thesis & evidence] [Agent submissions / review]
[History and acknowledgment distinct from acceptance]
```

Use lifecycle priority and existing Research Rank only as documented. Do not imply queue completion changes lifecycle, model or allocation state.

### Operations

```text
Operations [overall status] [last successful update]
[Domain coverage & freshness] [Jobs due/failed/partial] [Workbook connection]
[Provider / mapping / attempt detail] [Retry through existing bounded operation]
```

Prioritize actionable configuration and failures. Raw/provider details and long run lists are behind a selected domain or job, not in the daily portfolio glance.

## Design risks and trade-offs

- **Breadth versus discoverability:** today’s Company Explorer exposes 20 anchors because it owns many canonical domains. Grouping improves orientation, but every item still needs a direct, bookmarkable path and an explicit missing state.
- **Concise glance versus investment context:** compact cards can hide return methodology, listing basis, stale data, or missing inputs. Summaries must retain a visible status and a one-step path to source detail.
- **Decision unification versus semantic separation:** one Decisions destination improves access but can imply that ranks, strategic target, and Execution Pace are interchangeable. Keep distinct tabs, labels, run histories, and API-sourced explanations.
- **Portfolio performance:** date controls resemble consumer portfolio apps, but the system must not invent performance without valid transaction/holdings history. Initially limit time selection to supported as-of valuation and canonical historical facts.
- **Attention versus work queue:** Attention is a feed of source changes; the Research Queue is review work with completion state. Link matching items and avoid copying all feed items into tasks.
- **Operations visibility:** moving diagnostics away from primary navigation reduces daily clutter but can hide operational risks. Overview must surface material stale/missing conditions and link to the exact Operations diagnostic.
- **Table density:** Universe and Portfolio need different defaults. Preserve comparison efficiency on desktop and readable identity/status on mobile; avoid shrinking all columns into unreadable cards.
- **Scope and regression:** the current screens contain broad, tested functionality. Introduce new homes before retiring old entry points; do not combine this IA work with investment-rule or API changes.
- **External integrations:** Google Sheets is transport/authoring support, not a second canonical store. Keep source revision, base revision and acceptance status visible in the new Modeling/Research homes.

## Migration sequence and acceptance criteria

| Slice                                   | Scope                                                                                                              | Acceptance criteria                                                                                                                                                                                                                   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **11B — Navigation shell and Overview** | New information architecture shell, global Company Finder, Overview from existing canonical results.               | All current routes remain reachable; Overview distinguishes current valuation from performance; key missing/stale states link to source pages; desktop/mobile and keyboard tests pass; no backend calculation or state mutation.      |
| **11C — Portfolio and Decisions**       | Separate holdings/targets workflow from rank/run exploration; add type-specific Decision views using existing API. | Current and strategic weights/gaps remain API-sourced; each rank and Execution Pace stays distinct; preview versus record is explicit; confirmation remains append-only; all existing decision cases remain available and responsive. |
| **11D — Universe and Company Explorer** | Simplify Universe defaults and group Company Explorer into Glance/Analysis/Evidence.                               | All current Company sections have a mapped, deep-linkable destination; no method/history/identity content is lost; exact listing/currency and provenance remain visible; mobile does not require page-wide horizontal scroll.         |
| **11E — Research workspace**            | Candidate Pipeline, Research Queue, thesis/evidence and proposal review under one Research destination.            | Trigger, queue, candidate, proposal and acceptance statuses remain distinct; evidence/source is reachable in one step; completion/acceptance stays explicit and historical.                                                           |
| **11F — Modeling workspace**            | Dedicated model list/editor/revision review, with Sheets and imported-output distinction.                          | All supported methods retain method-specific inputs and deterministic preview; imported outputs remain read-only; conflict and base-revision behavior unchanged; explicit acceptance required.                                        |
| **11G — Operations workspace**          | Coverage, ingestion jobs, Sheets sync, publication and failure history.                                            | Existing bounded jobs, manual actions, statuses and receipts remain available; operational failures are surfaced from Overview without duplicating domain state.                                                                      |
| **11H — Entry-point cleanup**           | Remove redundant links only after new locations are established.                                                   | Route inventory is fully mapped; deep links redirect or remain valid; no feature is removed without a tested replacement; route and accessibility checks pass.                                                                        |

For each slice, capture before/after desktop and mobile browser states using fixture data, test empty/loading/error/partial states, test keyboard navigation, and verify that only intended frontend composition changes. Any need for new domain state, a new calculation, or altered investment behavior is out of scope and requires a separate milestone.

## Proposed next step and trade-off

Start 11B with the navigation shell, Company Finder, and Overview because it establishes the shared wayfinding and daily entry point before moving existing features. The main trade-off is that an Overview may initially have many explicit “unavailable” cards; prefer a small honest brief with links over filling space with unsupported performance or derived metrics. The full live-database review should happen when the local app and API are available; this audit’s browser evidence is fixture-backed.
