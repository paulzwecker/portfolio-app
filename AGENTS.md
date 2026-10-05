# AGENTS.md

## Mission

Build and maintain a web-based public-equity research, financial-modeling and portfolio-management platform.

The application succeeds the legacy Google Sheets Portfolio/Watchlist system while preserving its economic meaning, auditability and investment discipline.

The goal is not to reproduce spreadsheets in a browser.

The goal is a canonical, traceable investment platform with strong modeling, data and research workflows.

---

## Instruction hierarchy

Follow, in order:

1. explicit user instructions
2. this file
3. relevant scoped `AGENTS.md`
4. relevant domain documentation in `docs/`
5. legacy workbook behavior where deliberately used as migration evidence

Do not mechanically read every document for every task.

Read the documentation relevant to the area being changed.

When financial behavior is ambiguous, preserve known behavior and document the uncertainty rather than inventing investment policy.

---

# Architecture

## Frontend

Next.js owns presentation and interaction.

Do not duplicate canonical financial, ranking, scoring, portfolio or reconciliation logic in React.

See `apps/web/AGENTS.md`.

## Backend

FastAPI owns:

- domain validation
- deterministic financial calculations
- portfolio analytics
- external-data normalization
- model/revision operations
- rankings/signals
- ingestion and synchronization

See `apps/api/AGENTS.md`.

## Database

PostgreSQL is canonical for migrated application state and history.

Use relational current state plus targeted revision, event and snapshot tables.

Do not introduce generic event sourcing without a demonstrated need.

---

# Core domain boundaries

Preserve this direction:

```text
External facts
    ↓
Estimates / reported fundamentals
    ↓
Financial models
    ↓
Investment interpretation
    ↓
Portfolio construction
    ↓
Execution timing
```

Downstream domains must not silently rewrite upstream assumptions.

Examples:

- price momentum may affect execution timing
- price movement must not change model assumptions
- target weights do not automatically change when prices change
- model outputs do not determine lifecycle
- rankings do not change holdings or targets by themselves

---

# Identity

Use:

```text
Company → Security → Listing
```

A ticker is a listing attribute, not a company identifier.

Keep reporting currency, model currency, listing currency and portfolio currency distinct.

Never substitute one listing for another merely because market data is easier to obtain.

Detailed identity semantics belong in `docs/domain-model.md`.

---

# Investment semantics

The system supports concentrated, long-duration ownership of exceptional businesses.

Decision hierarchy:

1. 10Y Durability
2. Compounder Quality
3. Forward fundamental compounding
4. Valuation / Expected IRR
5. Portfolio fit
6. Execution timing

Expected Cash-Flow IRR is the primary modeled opportunity-return measure after quality and durability gates.

Investor hurdle is a required-return/risk-adequacy measure and is not WACC.

Expected Excess is:

```text
Expected IRR - Hurdle
```

Weighted Fair Value is a valuation reference, not a fixed-horizon stock-price forecast.

---

# Scores

Keep independent:

- 10Y Durability: 0–5, higher better
- Compounder Quality: 0–5, higher better
- Execution: 1–5, higher better
- Risk: 1–5, higher means more risk

Do not collapse these into an opaque composite unless approved domain logic explicitly requires it.

---

# Lifecycle and portfolio

Lifecycle is explicit:

- `PORTFOLIO`
- `WATCHLIST`
- `CANDIDATE`
- `DROP`

Do not infer lifecycle from holdings, models, rankings, scores or prices.

Keep separate:

- current holdings
- strategic target architecture
- execution timing

Execution Pace must not rewrite long-term target weights or underwriting assumptions.

---

# Financial models

The application is canonical for accepted model state and revision history.

Google Sheets remains a supported external model-authoring environment.

```text
Web App
   ↕
Canonical Model Contract
   ↕
Google Sheets
```

Both web and Sheets edits must enter the same revision system.

Never silently overwrite a newer model revision.

Separate:

- editable assumptions
- deterministic projections
- normalized outputs

Different businesses may use different valuation methodologies.

Standardize interfaces, not financial methodology.

Normal application use should not require LLM inference.

External agents may perform reasoning and propose model updates, but deterministic calculations and accepted revision history remain auditable application state.

See `docs/financial-models.md`.

---

# Model-output semantics

Production models expose a normalized interface where applicable:

- Bear/Base/Bull FV
- scenario probabilities
- Weighted Fair Value
- Weighted Upside
- Expected Cash-Flow IRR
- Hurdle
- Expected Excess
- Forward Fundamental CAGR
- model currency/status

Bear/Base/Bull are explicit economic scenarios.

Do not average scenario IRRs.

Canonical Expected Cash-Flow IRR uses probability-weighted expected shareholder cash flows.

Where migrated legacy models use a different return definition, preserve that methodology and label it explicitly rather than silently redefining it.

---

# External data

Build one clean canonical dataset from complementary sources.

Use:

```text
provider
  ↓
raw observation
  ↓
normalization
  ↓
canonical observation
  ↓
derived analytics
```

Provider schemas must not become domain schemas.

Preserve source provenance and point-in-time semantics.

Prefer primary sources for reported facts where practical.

Use complementary providers for coverage and fallback.

Do not silently blend conflicting observations.

Source precedence is domain-specific.

For consensus estimates, preserve provider continuity rather than synthesizing estimates across vendors.

See `docs/external-data-architecture.md` and `apps/api/AGENTS.md`.

---

# Time, history and missing data

Missing is not zero.

Use explicit null and quality/status states.

Never fabricate historical data.

Historical observations and accepted revisions must not be rewritten to match current state.

Where relevant distinguish:

- reporting/economic period
- effective/publication time
- observed/retrieved time
- recorded time

Historical analysis must avoid look-ahead bias.

Material changes should retain appropriate provenance.

---

# Migration

Migrate domain by domain.

For each migrated domain or financial calculation:

1. identify authoritative legacy/source semantics
2. implement the smallest coherent replacement
3. reconcile against representative source data
4. add deterministic tests
5. migrate downstream dependencies only after verification

A visually correct UI is not proof of migration correctness.

Prioritize active Portfolio and Watchlist usefulness over abstract architectural completeness.

Do not add methodologies or infrastructure merely to increase coverage counts.

---

# UI direction

The product should feel like professional investment research software, not a spreadsheet rendered in a browser.

Prefer:

- strong information hierarchy
- compact layouts
- progressive disclosure
- traceable changes
- historical context
- responsive design
- explicit freshness/data-quality states

Avoid:

- giant forms
- duplicated metrics
- unnecessary spreadsheet-like grids
- decorative charts with no analytical value

See `apps/web/AGENTS.md`.

---

# Engineering

Prefer:

- explicit code
- strong typing
- small domain modules
- deterministic functions
- financial regression tests
- ordinary relational designs
- reuse before abstraction

Avoid:

- speculative rules engines
- generic workflow systems
- generic event sourcing
- infrastructure without a demonstrated requirement

Do not weaken financial or data-integrity semantics to simplify implementation.

---

# Agent behavior

For each task:

1. inspect the current implementation
2. read only relevant documentation
3. preserve domain ownership
4. make the smallest coherent change
5. run relevant checks
6. verify affected user flows
7. update documentation only when domain/architecture meaning changes

Prefer solving the requested problem over expanding scope.

---

# Definition of done

A change is complete when appropriate to its scope:

- implementation works
- relevant tests/typechecks pass
- migrations/contracts are valid where affected
- missing/error states remain explicit
- financial parity is checked where required
- historical/provenance behavior remains correct
- relevant UI works on desktop and mobile
- documentation reflects material semantic changes

Correctness, economic meaning and traceability take priority over minimizing code volume.