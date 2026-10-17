# Milestone 11H — Operations UX & Frontend Consolidation

## Operations information architecture

`/operations` remains in the shell's separate Operations group so provider and worker diagnostics do not compete with daily investment navigation. It answers whether data movement and agent handoffs are operating, then exposes the recorded details needed to find a blocker.

The page uses this hierarchy:

1. **Glance:** recurring-worker state, canonical market freshness, open proposal count in the returned candidate lists, and recent agent receipt count.
2. **Operations:** worker heartbeat and configuration; market/FX refresh identifiers; recurring-job attempts, success, next attempt, failure and expandable structured result.
3. **Integration review:** Model, Research/Thesis and Risk inbox configuration, latest sync run, candidate states and a direct link to Research review.
4. **Delivery audit:** recent immutable delivery/acknowledgment events with role, work identity, channel, reason and timestamp.
5. **Coverage and blockers:** recurring partial/failure states with a link to Universe for company-level factual coverage.

Status refresh performs only bounded GET requests. It does not launch a job, write to Sheets, accept or reject a proposal, change a model or recompute decisions. Candidate review and its explicit acceptance safeguards remain in `/research?view=reviews`.

## Contracts and boundaries

The page consumes the existing `recurring-operations/status`, three Google Sheets status endpoints, three candidate list endpoints and `research-agent-operations/events?limit=12`. The web proxy allowlists only the event history read route and validates every returned event against the generated OpenAPI contract. Unsupported agent-operation routes remain inaccessible through the proxy.

An integration marked configured means only that configuration and credentials are present. The latest stored synchronization run is displayed separately as the evidence of actual connection behavior. Missing status, candidate or event responses remain unavailable; an empty validated event list is labeled as no receipts, not as no research work. Candidate counts describe records returned by the API, which currently bounds each list at 100. Worker success is not presented as proof that every company is covered.

The backend has no single company-by-domain coverage endpoint. Operations links to Universe and Company Explorer for factual coverage rather than adding duplicate calculations or a new aggregation API in this UX milestone.

## Frontend consolidation audit

- Migrated every consumer away from `components/research-frame.tsx`, a compatibility barrel that only re-exported `useResearch`, `PendingOrError`, `PageHeader` and `DemoNotice`; removed it after confirming no consumers remained.
- Removed `features/portfolio/portfolio-page.tsx` and `portfolio-dashboard.tsx` after confirming they were byte-identical and neither was imported. The active portfolio route remains `portfolio-workspace.tsx`.
- Removed five unreferenced, identical placeholder files under Company/Modeling feature paths that duplicated the same `StatusIndicator` implementation despite having unrelated names. The current shared status component remains the sole owner.
- Centralized Company, Decisions, DCF, Universe and execution-rationale currency/percentage presentation through `lib/display.ts`, preserving their precision and missing-value labels.
- Consolidated Company Explorer's identical 90-session market-data request at the workspace boundary. The identity header and historical Market Facts panel receive the same typed response; switching views no longer fetches that payload a second time.
- Reused the existing status, metric, section, responsive-table, empty-state and shared format components. No new UI dependency or backend/domain behavior was added.
- Kept chart-specific range and period controls separate where they represent different data frequencies and meanings (market-session history versus fiscal-period analysis). A single generic control would obscure those semantics.
- Existing Next/App Router data hooks remain feature-scoped. No duplicate state framework, chart library or API adapter was found or introduced.
- No dependency was added or removed; the current dependency set is used by the active routes and design-system primitives.

## Navigation and journeys

Final navigation remains Overview, Portfolio, Decisions, Universe, Research, selected Company Explorer/Modeling context and a separate Operations group. Candidate, queue and proposal pages remain views in the Research workspace; `/candidates`, `/research-queue`, `/attention` and `/model-sync` preserve the established redirects. See [11C shell and navigation](./application-shell-and-navigation-11c.md) and [11G Research experience](./research-experience-11g.md).

Browser verification covers these six paths in desktop and mobile projects:

- Portfolio overview → holdings confirmation
- Decisions → allocation and opportunity context
- Universe → Company Explorer → thesis/modeling context
- Universe/Candidate Pipeline discovery
- Research queue → proposal review
- Operations → provider/worker diagnostics and company-coverage link

The Operations test also checks mobile viewport overflow, responsive job-table behavior and that “Refresh status” sends no non-GET operation. Existing research tests retain explicit proposal acceptance and stale/conflict safeguards. Keyboard navigation and accessible headings/labels are verified through the existing route-level Playwright assertions and shared-component tests.

## Remaining limitations and acceptance

- Operations is intentionally read-only; manual ingestion, polling, acceptance and recomputation controls remain in their existing purpose-specific workflows.
- It reports the latest stored run, not a complete operational history. Per-integration run-history drill-down is not added here.
- Candidate-list counts are bounded by the existing endpoint limit. A future global coverage report would need a justified API contract, not a frontend rollup over incomplete feeds.
- Operations reads eight lightweight endpoints on entry. It does not poll automatically; the explicit refresh re-reads them. Company market data is fetched once per Company Explorer workspace.
- Automated screen-reader testing is not configured. The verified controls use existing semantic headings, labels, status text, native disclosure elements and responsive table alternatives; a human assistive-technology pass remains useful.
- Existing day-to-day functionality and URLs remain available. No portfolio state, model revisions, data observations or decision history are changed by this UI work.

## Verification results

- Frontend lint and backend Ruff lint passed. TypeScript and Mypy typechecks passed (114 Python source/test files checked).
- Frontend unit/API-contract tests passed: 135 tests across 9 files. OpenAPI and TypeScript contract generation is current.
- Full backend suite passed: 359 tests.
- Production build passed and includes `/operations`, `/portfolio`, `/decisions`, `/universe`, `/research`, `/candidates`, `/research-queue` and compatibility routes.
- Production-browser suite passed: 53 tests across desktop and mobile projects; 11 were intentionally skipped because live API/database checks, demo-seed data, or write-enabled verification require explicit environment flags, plus the mobile-only navigation test is skipped in the desktop project. The six requested user journeys were exercised with deterministic application data.
- `git diff --check` passed. All frontend files and design docs pass Prettier after consolidating formatting in-scope.
- Frontend Prettier and backend Ruff formatting checks passed independently (166 backend files are formatted). The repository-wide `npm run format:check` remains blocked only by four unrelated reconciliation reports under `docs/reconciliation/` (Issuer Identity 10F and Return Comparability 10G JSON/Markdown files). They were left untouched.

No real local investment state was changed during verification. The remaining validation gap is a live assistive-technology review and optional live-database browser run, not a failing mocked desktop/mobile journey.
