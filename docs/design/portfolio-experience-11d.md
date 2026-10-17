# Milestone 11D — Portfolio Experience

## Primary question

The Portfolio page answers: **What do I own, what is it worth, and how is the
portfolio positioned?** The page prioritizes canonical ownership and valuation
before decision signals. It does not change financial calculations, holdings,
accepted targets, model revisions, rankings or Execution Pace definitions.

## Page hierarchy

- **Overview:** current portfolio value only when the API reports a complete
  valuation; accepted position count; cash balances by original currency;
  largest company exposure; valuation status/cutoff; holdings confirmation
  age; market and FX dates; missing targets and valuation gaps.
- **Holdings:** sortable, responsive listing table. Snapshot rows are joined to
  valuation context by exact listing ID. It displays company identity and
  Company Explorer link when mapped, security/listing identity, venue, currency,
  quantity, latest quote and its date/observed time, base-currency value, weight,
  and target/gap when the API supplies a company context. An unmatched row keeps
  the accepted listing ID and quantity but has explicit unavailable market
  fields.
- **Allocation and exposure:** one company/standalone listing/cash composition
  view displays API-supplied weights without browser-side normalization. The
  adjacent view presents target gaps and cash in original and portfolio base
  currencies. Sector, geography and business-model selectors remain visibly
  unavailable because canonical classifications are incomplete.
- **Performance:** states that historical portfolio performance is unavailable
  until transaction and cash-flow history can support it. It does not show
  current holdings replayed against past prices as realized performance.
- **Decision and research context:** the Portfolio page retains relevant data
  quality context and holdings workflows. Cross-company rank and execution
  comparisons live in the dedicated `/decisions` workspace; links to the
  original Portfolio Rank deep link remain compatible.

## Interactions and integrity

Section links retain direct hash navigation. The prior `/decisions` redirect is
replaced by the dedicated decision workspace. Existing `/portfolio#portfolio-rank-heading`
links still open the retained Portfolio decision context. The global “Confirm
holdings” action opens the existing holdings confirmation disclosure. The confirmation flow remains
investor-controlled: it pre-fills the latest complete snapshot, requires an
explicit review checkbox and reason, and appends a new snapshot only after the
user submits. After acceptance, the page reloads the canonical overview.

Rank and Execution Pace recording are disabled while holdings freshness is not
`FRESH` or the current portfolio valuation is incomplete. The blocking reason
is shown beside each disabled action. This frontend guard follows the portfolio
operating contract; domain validation remains on the API.

The UI uses `PortfolioOverview` and existing decision summary endpoints. It
does not sum cash currencies, reconstruct portfolio weights, invent missing
classifications, infer targets, calculate returns, or make an allocation/trade
recommendation. It consumes the API's valuation mode, as-of dates, price/FX
freshness, current weights, gaps and quality states.

## Shared component use

The page reuses the shared `PageHeader`, `PageSection`, `MetricCard`,
`DataFreshnessIndicator`, `StatusIndicator`, `ResponsiveDataTable`,
`ChartContainer`, `EmptyState`, and shadcn-compatible `Card`, `Badge` and
`Button`. Domain composition is under `components/features/portfolio/`; rank,
opportunity, quality and review presentations were moved there from the former
root `components/portfolio-dashboard.tsx` module.

## Verification

Fixture-backed browser coverage checks 22 listing positions, the standalone
SPYY listing, EUR and USD cash, exact listing identifiers, stale holdings,
unwritten targets, unavailable classification groupings, performance empty
state, sorting, and narrow-screen rendering without page-wide horizontal
overflow. Tests assert that merely opening the page and confirmation form sends
no write request. A separate existing workflow test covers explicit holdings
confirmation and its appended snapshot request.
