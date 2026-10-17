# Milestone 11B — Design System & Frontend Architecture

## Purpose and scope

This document turns the approved hierarchy in [Milestone 11A](./product-ux-audit-and-information-architecture-11a.md) into a shared frontend foundation. It covers visual tokens, reusable presentation patterns and incremental migration rules. It does not change financial calculations, API contracts, accepted state or feature methodology, and it does not redesign every route.

The primary visual direction is a restrained, light default with a system-preference dark palette. Dense data uses tabular numerals, compact labels and explicit source/status context. Color supports readable status; text and icons carry the meaning so color is never the sole signal.

## Ownership boundaries

| Location                          | Owns                                                                                                                                                                                                    | Must not own                                                                                           |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `src/components/ui/`              | Small accessible shadcn-style primitives such as Button, Card, Badge and Skeleton.                                                                                                                      | Domain terms, API fetching, financial calculations or investment rules.                                |
| `src/components/app/`             | Application-wide layout and presentation patterns: page header/section, metric grouping, status, freshness, source reference, empty/loading, responsive table, chart framing and focused detail drawer. | Company, portfolio, model or research decisions.                                                       |
| `src/components/features/<area>/` | Components and composition for Portfolio, Decisions, Company, Modeling, Research and Operations. Feature components may call typed data-access code and format API values, but must not recompute them. | A second business-logic layer or shared presentation primitives that belong in `app/`.                 |
| `src/app/`                        | App Router routing, page-level data coordination and composition. Keep new pages thin and preserve current public URLs while migrating.                                                                 | Large financial widgets, duplicate fetch state, or presentation implementations copied between routes. |
| `src/lib/display.ts`              | Shared formatting of financial amounts, percentages, units, dates/times and status labels.                                                                                                              | Rounding values before API/domain calculations or treating missing as zero.                            |

The existing shadcn-compatible Button, Badge and Card are extended in place. No CSS-in-JS, charting, icon or state-management dependency was added. Icons continue to use the installed `lucide-react` dependency.

## Tokens and responsive rules

`src/app/globals.css` is the token source. Tailwind v4 maps the CSS custom properties into utilities. Tokens cover background/foreground, card and popover surfaces, primary/secondary/muted/accent, borders and focus ring, positive/negative/warning/info states, sidebar surfaces, chart palette, radii, content width, sidebar width and responsive page gutters.

Light tokens are the default. A `prefers-color-scheme: dark` override provides a complete dark palette. Both themes retain contrast for text, semantic labels, focus rings and borders. Feature pages should use semantic utilities such as `bg-card`, `text-muted-foreground`, `text-positive`, `text-warning` and `border-border`; avoid hard-coded colors for new work.

The shared application content frame uses `--app-content-width`, `--app-page-gutter` and `--app-page-vertical`. Tables collapse into labeled mobile definition-list cards below the medium breakpoint. Components must use `min-w-0` in grid/flex children where long identifiers or values could otherwise force horizontal overflow.

## Shared patterns

- `PageHeader` provides the consistent title, optional eyebrow, description, context, badge and actions. A route should render one primary page heading.
- `PageSection` gives analysis groups an accessible named section and optional actions.
- `MetricCard` and `MetricGroup` present values supplied by canonical API results; unavailable values remain explicit strings/statuses.
- `StatusIndicator` shows a readable status and icon together. Semantic availability is separate from positive/negative investment performance.
- `DataFreshnessIndicator` includes state, source and an observed timestamp when provided; it never invents an observation time.
- `EmptyState`, `PendingOrError` and `LoadingSkeleton` distinguish no data, loading and recoverable errors.
- `SourceReference` displays an identifier if no canonical URL exists and opens supplied sources in a separate tab safely.
- `ResponsiveDataTable` renders semantic desktop tables and labeled mobile rows instead of forcing page-wide horizontal scrolling.
- `ChartContainer` standardizes chart title, description and source context. Feature code owns the series, domain meaning and accessibility description.
- `DetailDrawer` uses the browser's native dialog semantics, Escape handling and a clear close control for short contextual inspection. Long authoring and review workflows stay on routes.

Use shared components when the same responsibility recurs. Do not wrap every shadcn primitive in an app abstraction without a shared behavior to own.

## Formatting and financial precision

Use the `display.ts` helpers for presentation. The functions format values only; they do not mutate API data or round calculation inputs. Percentage precision is configurable. Currency formatting retains the code when a currency cannot be rendered by `Intl`, and missing inputs use an explicit status string. Date-only market periods are formatted in UTC; timestamps use the viewer timezone and show its abbreviation.

Keep actuals, consensus, agent forecasts and model scenarios distinct in labels and surrounding context. A status such as `UNAVAILABLE`, `NOT_MIGRATED` or `DATA_CHECK` must not be represented as numeric zero or neutral investment judgment.

## Accessibility and interaction

- Keep a visible keyboard focus indicator, skip link, semantic headings, table captions and labeled controls.
- Status uses icon plus text and must meet the text/background contrast of its semantic token in both themes.
- Native dialog interaction supports keyboard dismissal and a visible close action.
- Touch targets should remain comfortably usable; action groups wrap on narrow layouts.
- Preserve URL, filter, company and time context where practical. Do not hide a required action in hover-only UI.

The internal `/design-system` reference uses illustrative content only. It demonstrates status, loading, empty, stale, error, provenance, chart framing, metric and responsive-table patterns without reading portfolio data. The shell exposes its link only in development.

## Incremental migration

1. Keep current routes working while adopting shared tokens and patterns.
2. When next editing a route, replace duplicated page headers, status labels, loading/empty markup and formatting with the shared implementation where semantics match.
3. Move a domain component only after preserving its current source, its imports, route consumers and tests. Put it in the appropriate feature area; do not relocate unrelated modules in bulk.
4. Keep route files as coordinators. Extract data fetching into typed hooks/data-access modules when it has a real consumer or lifecycle boundary.
5. Remove legacy implementations only after all consumers use the replacement and focused browser coverage passes at desktop and mobile widths.
6. Leave backend/domain calculations, revision histories and external contracts untouched during presentation migration.

## Decisions and known migration work

- The implemented shell and current route ownership are recorded in [Milestone 11C — Application Shell & Navigation](./application-shell-and-navigation-11c.md). Its implementation follows the user-directed milestone sequence; the 11A milestone table remains the original proposed ordering.
- Reused the existing Tailwind v4, shadcn-compatible Button/Badge/Card, Radix Slot, and Lucide setup; added only a light Skeleton primitive because the repository did not have one.
- Chose CSS custom properties over another theme framework. Dark mode follows the user's OS preference to keep one coherent default configuration.
- Used a native `<dialog>` for the first detail drawer instead of adding a dialog dependency.
- The 11A information architecture remains a staged plan. Feature routes are not being reorganized wholesale in this milestone.
- Before further route/component relocation, verify the source/target map and preserve any uncommitted files. The current working tree contains outstanding changes outside this design-system scope; migration and full application verification must be completed against a reconciled source tree.

## Verification

Focused display and shared-component tests are in `src/lib/display.test.ts` and `src/components/app/status-indicator.test.tsx`. Browser coverage for the reference page checks keyboard drawer behavior and narrow-screen horizontal overflow in `e2e/design-system.spec.ts`. The full route suite remains required when the existing working-tree component sources are reconciled.
