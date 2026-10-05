# Portfolio Research Platform

A web-based public-equity research, financial-modeling and portfolio-management platform for a concentrated long-term investment process.

The application succeeds the legacy Google Sheets Portfolio/Watchlist system.

Its purpose is to combine:

- portfolio management
- company research
- external market/fundamental data
- financial modeling
- historical analysis
- model revision tracking
- ranking and decision support

in one canonical, auditable application.

---

# Product direction

The application should make it easy to:

- understand the current portfolio
- compare current vs strategic target allocation
- manage Portfolio, Watchlist and Candidate companies
- compare opportunities across the universe
- inspect and edit financial models
- analyze Bear/Base/Bull scenarios
- track Expected IRR and valuation changes
- inspect reported fundamentals, consensus estimates, filings and source documents
- understand what changed and why
- compare historical forecasts with later actual outcomes
- manage research, thesis and supporting evidence

The product should feel like investment-research software rather than a spreadsheet in a browser.

---

# Architecture

```text
External data / filings
          ↓
Canonical factual data
          ↓
Financial models
          ↓
Investment interpretation
          ↓
Portfolio / execution
          ↓
Web application
```

Technology:

### Frontend

- Next.js
- TypeScript
- shadcn/ui
- Tailwind CSS
- TanStack Table
- Recharts

### Backend

- FastAPI
- Python
- Pydantic
- SQLAlchemy
- Alembic

### Data

- PostgreSQL

PostgreSQL is canonical for migrated application domains.

---

# Financial modeling

The application supports first-class financial-model authoring.

Accepted financial-model state is revisioned and auditable.

Models may use different methodologies.

The application standardizes common interfaces without forcing every company into a universal valuation engine.

Current native methodology families include:

- UFCF DCF
- owner-cash-flow
- residual income

Additional methodologies are added only after their economic behavior and parity are understood.

---

## Model outputs

Production models expose normalized decision-useful outputs where applicable:

- Bear/Base/Bull Fair Value
- scenario probabilities
- Weighted Fair Value
- Weighted Upside
- Expected Cash-Flow IRR
- Hurdle
- Expected Excess
- Forward Fundamental CAGR

Legacy model methods may retain method-specific return definitions until explicitly migrated to canonical semantics.

---

# Google Sheets interoperability

Google Sheets remains a supported external financial-model editor.

```text
Web App
   ↕
Canonical Model Contract
   ↕
Google Sheets
```

The application remains canonical for accepted model state and revision history.

Sheets-originated and web-originated edits use the same revision model.

Stale external edits must not overwrite newer application revisions.

AI reasoning may happen externally in Sheets or other agent workflows.

Normal application use and deterministic financial calculations do not require LLM inference.

---

# External data platform

The application uses provider-independent pipelines for:

- market prices
- FX
- corporate actions
- reported fundamentals
- consensus estimates
- company/reference data
- filings and source documents

The general flow is:

```text
Provider
   ↓
Raw observation
   ↓
Normalization
   ↓
Canonical observation
   ↓
Derived analytics
```

Multiple providers may complement one another.

Provider provenance is preserved.

Conflicting observations are not silently merged.

Historical data is modeled point-in-time so the platform can distinguish what was known at a historical date from information reported later.

This enables future analyses such as:

```text
Our forecast
vs
Consensus
vs
Actual result
vs
Subsequent market return
```

---

# Core investment concepts

## Identity

```text
Company → Security → Listing
```

Tickers belong to listings.

This supports:

- multiple share classes
- ADRs
- multiple exchanges
- currency-aware market data

## Lifecycle

Companies have explicit lifecycle state:

- Portfolio
- Watchlist
- Candidate
- Drop

## Portfolio

Keep separate:

- current holdings
- strategic target allocation
- execution timing

## Quality and risk

The investment process tracks independent dimensions including:

- 10Y Durability
- Compounder Quality
- Execution
- Risk
- valuation

These are not collapsed into a single opaque score.

---

# Main application areas

## Portfolio

Current holdings, market values, strategic targets and allocation gaps.

## Universe

Cross-company comparison of Portfolio and Watchlist companies.

## Company Explorer

Deep company view combining:

- identity/listings
- lifecycle
- portfolio context
- scores
- rankings
- market data
- filing and issuer source documents
- financial history
- model outputs
- model revisions
- estimates
- research/source context

## Model Editor

Direct editing and revisioning of supported financial-model methodologies.

## Research Pipeline

Candidate research workflow and eventual thesis/evidence management.

---

# Current project state

The application already includes:

- Company → Security → Listing identity
- lifecycle history
- holdings and cash
- strategic target revisions
- canonical scores
- ranking infrastructure
- controlled legacy workbook import
- historical market-data ingestion
- corporate-action support
- canonical SEC filing and issuer source-document catalog
- normalized model-output ingestion
- Company Explorer
- native financial-model revisions
- web-based model editing
- Google Sheets model-contract round trips
- migration/parity tooling

Native financial-model coverage is being expanded gradually from verified reference models.

The external-data platform is being expanded toward complete:

- market/FX coverage
- fundamentals
- historical estimates
- filings
- forecast-vs-actual analysis

Detailed implementation status belongs in `docs/verification.md` and the relevant domain documents rather than this README.

---

# Repository structure

```text
.
├── apps/
│   ├── api/
│   │   └── AGENTS.md
│   └── web/
│       └── AGENTS.md
├── packages/
│   └── contracts/
├── docs/
├── infra/
├── scripts/
├── tools/
├── AGENTS.md
└── README.md
```

Important documentation includes:

- `docs/domain-model.md`
- `docs/architecture.md`
- `docs/external-data-architecture.md`
- `docs/source-documents.md`
- `docs/financial-models.md`
- `docs/workbook-map.md`
- `docs/migration.md`
- `docs/verification.md`

Read domain-specific documentation only when relevant to the task.

---

# Development

## Requirements

- Node.js 24 LTS
- Python 3.12
- PostgreSQL
- npm

Docker is not required.

---

## Install

From the repository root:

```sh
npm ci
npm run setup
```

Configure the root `.env` with at least:

```text
DATABASE_URL=...
```

Optionally configure:

```text
TEST_DATABASE_URL=...
```

Use application database credentials, not PostgreSQL administrator credentials.

---

## Create local database

For the standard local setup:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -X -h 127.0.0.1 -U postgres -d postgres -f infra/create-local-db.sql
```

or, when `psql` is on PATH:

```sh
psql -X -h 127.0.0.1 -U postgres -d postgres -f infra/create-local-db.sql
```

---

## Start

```sh
npm run db:migrate
npm run dev
```

Default endpoints:

- Web: `http://127.0.0.1:3000`
- API docs: `http://127.0.0.1:8000/docs`
- API liveness: `http://127.0.0.1:8000/health/live`
- API readiness: `http://127.0.0.1:8000/health/ready`

---

# Development data

Optional fictional development seed:

```sh
npm run db:seed
```

Do not use fictional seed data in a database intended for real workbook migration.

Legacy workbook and market-data migration use dedicated import workflows documented in:

- `docs/workbook-import.md`
- `docs/market-data.md`
- `docs/model-output-ingestion.md`
- `docs/native-model-input-migration.md`

Use dry-run/reconciliation workflows before applying real imports.

---

# Verification

Run the standard repository checks:

```sh
npm run check
```

Additional checks may include:

```sh
npm run test:integration
npm run db:check
npm run test:e2e
```

The project expects:

- lint and formatting checks
- TypeScript checks
- Python typing
- frontend tests
- backend tests
- API contract checks
- migration validation
- production build
- financial parity tests where applicable

Do not mutate the real application database from automated tests.

---

# API contracts

Pydantic schemas own backend API contracts.

Regenerate committed client contracts with:

```sh
npm run contracts:generate
```

Check for drift with:

```sh
npm run contracts:check
```

Frontend code should consume generated contracts rather than independently redefining backend response types.

---

# Database migrations

When changing persistence models:

```sh
node scripts/uv.mjs run --locked --project apps/api alembic -c apps/api/alembic.ini revision --autogenerate -m "describe the change"

npm run db:migrate
npm run db:check
```

Review generated migrations before applying them.

Do not create schema automatically at application startup.

---

# Guiding principles

Correctness and traceability matter more than minimizing code volume.

Do not:

- change financial meaning for implementation convenience
- fabricate missing history
- hide missing data as zero
- silently reconcile conflicting external observations
- bypass revision/provenance rules
- turn Google Sheets into a second canonical datastore

The long-term objective is a canonical, interconnected investment platform in which:

- humans can work directly in the web application
- agents can research and update models externally
- Google Sheets remains a supported modeling environment
- external data is clean, historical and traceable
- all accepted state converges into one auditable system
