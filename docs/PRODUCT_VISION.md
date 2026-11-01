# Portfolio Research Platform — Product Vision

**Status:** Working product charter; confirm inferred priorities before changing strategic direction.  
**Parent architecture:** `docs/architecture/personal-universe.md`  
**Application architecture:** `docs/architecture/portfolio-application.md`  
**Execution:** `ROADMAP.md`

## North star

A private, professional-grade investment research cockpit where one investor can understand every business, challenge the investment thesis, evaluate model-driven expected returns, allocate capital deliberately, and trace **why and when** decisions changed. Day-to-day use should be possible in the deployed app without relying on a local development machine. AI agents accelerate research and propose revisions; deterministic calculation, provenance, permissions and approval remain in the application.

**The app is not an Excel clone**, autonomous trading bot, unattended investment decision maker or generalized enterprise portfolio management SaaS.

## Users and core jobs

**Primary user:** portfolio owner/researcher; one-user-first access model. **Secondary actor:** restricted research agent proposing changes. **Reviewer:** separately authorized human role (may be the owner, not the proposing agent).

1. **Portfolio pulse:** See current holdings, cash, total value, portfolio weights, target gaps, concentrations, attribution, exposure, fresh/stale coverage and operational alerts; know what needs attention next.
2. **Company investigation:** Open one canonical company, recognize exact securities/listings, browse thesis, scores, business quality, risks, financial trends, market facts, corporate actions, source provenance and historical research.
3. **Valuation:** Inspect method-specific models with explicit inputs, scenarios, fair values, return bases, sensitivities and native calculations. Compare current accepted version with proposals and prior revisions. Avoid confusing enterprise UFCF IRR with shareholder IRR.
4. **Prioritization:** Rank Portfolio, Watchlist and Research separately, reflecting approved durability/quality/valuation/risk rules, with explainable scores and meaningful missing-data statuses.
5. **Capital allocation:** Compare strategic target weights against actual holdings and execution opportunities, without letting price movements silently change long-term conviction or target architecture.
6. **Research loop:** Agent collects evidence, proposes structured assumption/score/thesis changes with rationale and base-revision linkage; reviewer validates, accepts or rejects; accepted changes persist as auditable revisions.
7. **History:** Reconstruct what was known at a date, which model version and market observations supported a decision, and how rankings, valuations, scores and allocations evolved.
8. **Operations:** Inspect source freshness, import/sync failures, provider coverage, scheduled-job health and changes requiring approval; recover safely from failure.

## Domain principles / investment contract

- Optimize for a concentrated portfolio of durable, high-quality, long-duration compounders, consistent with the existing approved investment framework; **do not invent new buy/sell policy in code**.
- Preserve the decision chain: reported facts/estimates → financial models → investment interpretation → portfolio construction → execution timing.
- Independent metrics include 10Y Durability (0–5), Compounder Quality (0–5), Execution (1–5), Risk (1–5, higher is riskier); do not collapse into an unapproved opaque score.
- Explicit lifecycle: `PORTFOLIO`, `WATCHLIST`, `CANDIDATE`, `DROP`; never inferred from holdings or rankings.
- Canonical `Company → Security → Listing`; currencies and return methodologies are distinct. Expected Excess = Expected IRR − investor hurdle; hurdle is distinct from WACC. Weighted Fair Value is a valuation reference, not a fixed-horizon price forecast. For details, existing approved domain documentation prevails.
- Data gaps must remain visible. Missing is never zero; an unapproved proposal is never displayed as accepted valuation.

## Product experience

- **Home / Overview:** actionable scorecard of portfolio, target gaps, new information and research queue; not a wall of repeated KPIs.
- **Portfolio:** holdings, cash, allocation/targets, exposures, concentration, performance and reconciliation/freshness flags.
- **Universe & Research Queue:** powerful search, lifecycle and ranking filters, explicit confidence/coverage and clear next research actions.
- **Company Explorer:** coherent tabs/sections for Overview, Business & Thesis, Fundamentals, Market, Valuation, Assessments, Portfolio context and Change History. Labels/routes are proposals, not assumed current implementation.
- **Model workspace:** method-appropriate Bear/Base/Bull analyses, scenario probabilities, WFV, appropriately labeled IRR/excess, historical revision comparisons and agent proposal review.
- **Admin / Data Health:** source status, schema/contracts, synchronization/import previews, approvals, audit and recovery diagnostics.
- **Agent workflows:** structured, typed, authenticated proposal APIs; no free-form SQL or direct production mutation.

Interaction standards: action-first layouts, responsive desktop/mobile, accessible keyboard interactions, progressive disclosure, compact analytic density, interpretable charts, and meaningful loading/empty/error/stale states. Calculations reside server-side and are not duplicated in React.

## Data lifecycle and source-of-truth transition

Initially Google Sheets remains authoritative for the legacy portfolio research/workbook workflow; Market Data workbook/providers contribute source observations. A **small, versioned, source-authenticated package per domain or financial model** crosses into canonical application contracts. Native engines validate and compute; accept/reject workflow controls canonical revision state. PostgreSQL becomes authoritative for **explicitly migrated and accepted** app domains, not retroactively for every workbook field. Each transfer has a named owner, identity, timestamp, hash, preview/reconciliation and conflict policy. No wholesale workbook fidelity requirement or silent bidirectional writes.

A working real P-GOOGL package has been captured and numerically checked, **but its source-input drift is a proposed revision, not accepted production state**. Other model archetype adapters and proposal review are implemented locally but not thereby production-active. Verify current repository state before relying on any report.

## Platform fit

Portfolio is the first app within the Personal Universe modular monolith: one Next.js deployable, one FastAPI deployable and initially one Neon PostgreSQL database; private App Hub and common auth/design/API/DB conventions develop incrementally **after Portfolio is useful and stable in the cloud**. Preserve legacy Portfolio `public.*` tables initially. Avoid premature platform extraction and mass rename.

## Outcomes / acceptance signals

- **Useful cloud baseline:** actual verified company/listing/holdings/cash/targets information appears in the hosted app with freshness, identity and error states; normal usage needs no local laptop.
- **Trustworthy model flow:** at least one reviewed real-source financial model is accepted via scoped, audited transaction and visible with native calculation parity and revision history.
- **Safe agent loop:** an agent can submit a structured evidence-backed proposal, cannot self-approve, and a reviewer can accept/reject safely with correct conflict behavior.
- **Daily decisions:** user can quickly identify priority research, portfolio gaps and changes that matter, with traceable calculation inputs.
- **Reliability:** production target verification, tested migrations/recovery, role separation, CI/E2E and no silent data corruption.
- **Reusable foundation:** second personal app can reuse platform services without a second default Neon/Render/Vercel stack, once Portfolio reaches a stable v1.

## Explicitly deferred / non-goals

Autonomous trading, unattended model acceptance, full replication of spreadsheet UI and formula caching, arbitrary agent database access, importing every historical research artifact before basic utility, enterprise IAM, microservices, generic workflow engines, speculative model methodologies, and moving Portfolio tables to `portfolio.*` as a launch prerequisite.

## Decisions to confirm through roadmap gates

Exact production identity/session provider; detailed exposure/performance data sources; which workbook domains transition first; acceptance process for proposed source revisions; production release approvals; whether and when the app becomes primary model-authoring UI; realistic cost/latency budgets. Record decisions, owners and ADR links in `ROADMAP.md`; never silently guess.
