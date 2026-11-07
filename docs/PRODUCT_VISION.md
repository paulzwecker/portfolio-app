# Personal Universe product vision

Owner-confirmed direction, updated 2026-11-07. This document owns product outcomes.
[ROADMAP.md](../ROADMAP.md) owns capability status, priority and the execution cursor.
The [platform architecture](architecture/personal-universe.md) and
[Portfolio architecture](architecture/portfolio-application.md) own technical boundaries.
Detailed financial and source contracts retain authority over their domains.

## Destination

Personal Universe is a private, extensible personal app store. One authenticated
App Hub lets the owner discover and launch their reviewed applications, with
consistent navigation, design, settings, security and operational visibility.
Adding a useful app should primarily require its domain behavior and workflows.
Proven identity, UI, API, database, testing and release conventions should be reusable.

Prefer one Next.js application on Vercel, one FastAPI service on Render and one
Neon PostgreSQL database. Apps remain bounded modules with explicit ownership and
versioned contracts. Sharing infrastructure never grants cross-app table access.
Separate a workload when measured security, reliability, performance or total-cost
needs justify it. Preserve Portfolio's existing URLs and `public.*` ownership
through incremental migration.

The app store is a private catalog of reviewed modules. Public distribution,
billing, arbitrary runtime code installation and enterprise multi-tenancy are
outside the initial product scope.

## Portfolio first

Portfolio Research is the flagship application and first proof of the platform.
It should become a dependable daily research and investment workspace before major
platform extraction, a generator or a second app absorbs development effort.
Security, useful shared primitives and operating safeguards can improve earlier
when they solve a demonstrated Portfolio need.

Portfolio serves the existing concentrated, durable, high-quality, long-duration
compounding strategy. Approved investment rules remain in the
[domain contract](domain-model.md) and [financial models](financial-models.md).

A useful Portfolio release lets the investor complete these jobs with real,
reconciled information in the hosted application.

| Investor job          | Required outcome                                                                                                                                                     |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Understand ownership  | Exact holdings and currency-specific cash, EUR valuation, current weights, strategic target gaps, concentration and visible freshness/coverage                       |
| Understand a business | Financial statements and fundamentals, original filings, consensus where permitted, thesis claims, evidence, risks, unresolved questions and independent assessments |
| Challenge valuation   | Method-specific assumptions, scenarios, per-share fair values, appropriate expected returns, sensitivities, evidence and revision comparisons                        |
| Prioritize action     | Explainable Universe/research comparisons, valid ranking cohorts, allocation context, Execution Pace rationale and actionable in-app alerts                          |
| Learn from history    | Genuine prices, estimate/model/thesis revisions and recorded decisions with their original dates, inputs and methodology                                             |
| Operate safely        | Observable manual refresh, reproducible source transfers, clear blockers, explicit review, recovery and bounded cloud operation without a workstation                |

## Complete data foundation

Reliable pipelines must cover current and historical stock prices, dated FX,
splits/dividends and other supported corporate actions, financial statements,
reported fundamentals, filings, third-party consensus and agent-maintained models.
Each pipeline needs exact identity, units, currencies, fiscal/session dates,
source rights, provenance, raw observation retention, idempotent refresh,
reconciliation, freshness and failure visibility.

Prioritize held listings and active Watchlist businesses, then expand the research
universe. Define and review coverage by issuer, instrument, metric and period.
SEC coverage alone cannot establish international coverage. An installed consensus
adapter cannot establish provider access or data-use rights. Surface unsupported
coverage explicitly and retain it as a gap until the agreed scope is met.

Sector, geography and business-model exposure require canonical classifications.
Transaction/cash-flow history must support genuine portfolio performance and
benchmarking. Current-holdings hypothetical price history has a separate meaning.

## Hybrid agent and model lifecycle

Finance agents continue research and model authoring in Google Sheets for cost
efficiency. They explicitly publish complete, versioned method contracts. The
application captures immutable publications, validates identity, evidence, units,
revision ancestry and native calculation, then presents a reviewable proposal.
PostgreSQL owns accepted canonical revisions and audit history.

Every company may have multiple independent valuation methodologies. Each model
owns its assumptions, source evidence, scenarios, calculation outputs and revision
history. The current identity is company, exact listing and model type. Company
valuation synthesis or choosing a decision model requires an explicit versioned,
economically justified contract and owner approval.

Calculation parity, source freshness and investment validity are separate review
questions. A publication or successful calculation never accepts changed assumptions.
Routine automatic promotion requires an approved policy and separate activation.
Future in-app agents can produce the same typed contracts and use restricted
proposal APIs. Research execution stays outside the application until a concrete
benefit justifies moving it.

## Financial and decision integrity

- Preserve Company → Security → Listing, reporting/model/quote/portfolio currencies,
  share bases, fiscal periods and effective/observed/recorded dates.
- Preserve the chain from facts through models, investment interpretation,
  portfolio construction and execution. Targets express strategic intent.
  Execution states carry rationale and require investor action.
- Keep 10Y Durability and Compounder Quality (0–5), Execution (1–5) and Risk
  (1–5, higher is riskier) independent. Lifecycle is explicitly `PORTFOLIO`,
  `WATCHLIST`, `CANDIDATE` or `DROP`. Scores need supporting evidence and approved definitions.
- Keep reported actuals, external consensus, agent forecasts and accepted model
  projections distinct. Missing values remain unavailable.
- Expected shareholder cash-flow IRR uses its reviewed probability-weighted cash
  flows. Legacy enterprise UFCF returns retain their distinct economics. The
  investor hurdle differs from WACC. Fair Value is a valuation reference.
- Preserve immutable accepted history, contradictions, conflict detection and
  source ownership. Later-known facts cannot populate an earlier decision state.
- Keep private evidence outside public Git. Guard production writes, migrations,
  deployments, source edits, acceptance and recurring activation separately.

## Delivery order and success gates

1. Complete useful Portfolio workflows on the agreed real-data scope. The hosted
   app must support daily ownership, business investigation, valuation and decision
   review with explicit exceptions. A minimal identity import is one foundation.
2. Mature operations alongside that work. Require effective authentication,
   reviewer authority, current recovery protection, bounded jobs, monitoring and
   controlled releases before broader or unattended operation.
3. Extract proven shared foundations incrementally, introduce a private App Hub
   and enforce module/API/schema ownership while preserving Portfolio workflows.
4. Prove reuse with one genuinely useful second app on the shared stack. Its
   authenticated end-to-end workflow and cross-app regressions validate the module
   conventions. Introduce a generator only where repeatable structure is proven.

Acceptance uses unit, integration, contract, authorization and responsive browser
evidence, followed by reconciled live readback for operational claims. The roadmap
separates implementation, local verification, live-source validation, production
preview and operational verification. Gated tasks stay visible while independent
ready work progresses. Coverage targets, source licensing, new financial policy
and investment acceptance remain explicit owner decisions.
