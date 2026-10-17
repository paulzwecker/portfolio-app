# Milestone 11C — Application Shell & Navigation

## Purpose

The application shell now follows the investor-oriented 11A information architecture using the shared patterns from 11B. It provides stable wayfinding, a canonical company finder, selected-company context, and route ownership for existing screens. The shell does not change financial calculations, canonical data, or investment decisions.

## Navigation and route map

| User area        | Current destination              | Behavior                                                                                                                                                             |
| ---------------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overview         | `/`                              | Existing overview workspace; title and shell context use “Overview”.                                                                                                 |
| Portfolio        | `/portfolio`                     | Holdings, strategic targets, valuation and current portfolio context.                                                                                                |
| Decisions        | `/decisions`                     | Dedicated workspace for allocation comparison, method-aware Portfolio/Watchlist opportunity context, and recorded Execution Pace.                                    |
| Universe         | `/universe`                      | Company search, lifecycle, canonical score, rank, market and model context.                                                                                          |
| Company Explorer | `/company/[id]`                  | Opened through the global company finder, Universe or existing company links. Existing Company section anchors remain in place.                                      |
| Modeling         | `/company/[id]#canonical-models` | Contextual link for the selected company; uses the existing native model editor and method-specific flows.                                                           |
| Research         | `/attention`                     | Attention Center is the currently supported cross-company research and change-review surface. A separate candidate/research queue page is not exposed by this shell. |
| Operations       | `/operations`                    | Read-only operational summary for recurring jobs, market freshness, Sheets integrations, proposal intake and agent receipts. It does not trigger jobs.               |

`/model-sync` remains a compatibility URL and redirects to `/research?view=reviews`. Existing deep links into Company Explorer sections are unchanged. The development-only `/design-system` reference remains available from the sidebar.

`/research-queue` and `/candidates` preserve compatibility by redirecting into the corresponding Research views. Proposal review is owned by Research; Operations links there but does not duplicate review or acceptance controls.

## Company context and search

The company finder queries the existing typed `universe/market-summary` API with a search term and presents canonical company names alongside exact listing ticker, venue, and currency. It does not search by ticker alone or infer identity. Keyboard users can move through results with the arrow keys, select with Enter, or close with Escape. Short queries do not issue requests; loading, unavailable, and no-match states remain visible.

Selecting a result saves a small recent-company context in browser local storage. Loading a company directly refreshes that context from the Company API response. The shell uses it only for navigation and labels; it is not canonical domain state. Contextual links open Company Explorer, the existing canonical model section, or company source evidence. Clearing browser storage removes this convenience without affecting server state.

On desktop, primary navigation is grouped in a sidebar. On mobile, the same destinations use one expandable menu and the finder remains in the persistent header. Menu selection closes the mobile navigation. Breadcrumbs provide a return to Overview and retain the selected company label where available.

## Operations status

The Operations route reads `recurring-operations/status`, provider-specific Sheets status and candidate collections, and recent `research-agent-operations/events` through the typed API proxy. It presents worker state, heartbeat, market refresh timestamps/run identifiers, recurring job status, workbook credentials/run state, open/conflicting/invalid proposals, and recent agent receipts. Missing timestamps and failed feeds remain explicit. The manual refresh button re-fetches status only; it does not start ingestion, publish to Sheets, accept proposals, or recompute decisions.

## Shared patterns and boundaries

- Reuses `PageHeader`, `StatusIndicator`, `ResponsiveDataTable`, the existing typed `useResearch` data hook, shadcn-compatible controls, and the canonical API proxy.
- Adds `CompanyFinder`, `ContextHeader`, selected-company navigation metadata, and a focused Operations status composition.
- Removes the unused pre-11B root `components/navigation.tsx` and `components/service-status.tsx` after confirming there were no remaining consumers; the shared app-shell versions are the only active implementations.
- `/decisions` is the dedicated read-only investment decision workspace. The Portfolio route retains ownership/holdings confirmation and the former Portfolio Rank deep link remains available.
- Route files remain thin. The Operations component formats status responses only and does not infer job state or perform business calculations.
- No new dependencies or backend changes were introduced.

## Verification and limitations

Playwright coverage checks canonical company search, keyboard result selection, selected-company Modeling navigation, the Decisions route, mobile menu collapse, old operations URL compatibility, and narrow viewport overflow. Existing page and API contracts remain unchanged.

The Company Finder can only show companies returned by the current canonical universe search endpoint. Research Queue, Candidate Pipeline, and model-proposal review are not added as decorative routes. Restoring their original reviewed interfaces remains migration work because their source pages are not present in the current App Router tree.
