# Portfolio Research Platform — Application Architecture

**Status:** Target architecture with existing components; verify implementation against repository before execution.  
**Parent:** `docs/architecture/personal-universe.md`  
**Product:** `docs/PRODUCT_VISION.md`  
**Execution:** `ROADMAP.md`

## 1. Architectural decision

Build Portfolio as a **domain-modular application**, hosted in the Personal Universe modular monolith. Keep the existing Next.js app, FastAPI backend, canonical PostgreSQL state and deterministic financial engines. Do not rewrite them merely to align directory names. Move incrementally from Sheets-authoritative legacy workflows to approved, versioned application state. Portfolio stays in `public.*` initially, as permitted by the parent architecture.

### Guiding rules

1. One canonical owner for every fact and decision; make transitions explicit.
2. Financial calculations are deterministic, method-specific, reproducible and backend-owned.
3. Financial sources are evidence, not unqualified application truth.
4. Proposals, derived output, accepted revisions and portfolio actions are different states.
5. Every boundary has identity, version, units, time, provenance, validation and conflict rules.
6. Small end-to-end slices beat universal import/parity machinery.
7. Agents submit evidence and proposed changes; independently authorized reviewers accept changes.
8. Read-only queries and previews are distinct from production writes and schema migrations.

## 2. Logical components

```text
Legacy Google Sheets       Market Data workbook      Yahoo/SEC/other sources
  (model authoring)         (listing/price facts)       (external evidence)
         |                         |                          |
         +-------------------------+--------------------------+
                                   |
                 Bounded source adapters / acquisition
                 exact source identity, effective values,
                 provenance, units, as-of, consistency checks
                                   |
                  Versioned typed packages + raw observations
                     immutable manifest / SHA-256 / schema
                                   |
                      Validation + reconciliation + preview
                        mapping, method, identity, parity,
                         revision ancestry, conflicts
                                   |
                  Explicit acceptance / guarded DB transaction
                                   |
                      PostgreSQL canonical domain state
           Company--Security--Listing / portfolio / models / history
                    / assessments / observations / proposals
                                   |
                       FastAPI domain services and APIs
                       native engines; analytics; ranking
                                   |
                      Authenticated Next.js proxy / UI
        Portfolio / Universe / Company / Model / Research / Admin
                                   ^
                                   |
                    Agent proposal API (inputs + evidence)
                   independent reviewer decision workflow
```

This is a direction diagram, not a claim that every path is already deployed. Read/write controls and domain ownership must be enforced in backend/database code, not merely by the UI.

## 3. Domain boundaries and data ownership

| Domain                    | Canonical responsibility                                                                | Forbidden shortcut                                             |
| ------------------------- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Identity                  | Company, Security, Listing, stable IDs, listing aliases                                 | Treat ticker/provider symbol as company ID                     |
| External facts            | Raw observations, reported fundamentals, estimates, market/FX data, lineage and quality | Blend conflicting providers without precedence/evidence        |
| Financial modeling        | Method-specific inputs, deterministic projections, normalized results, revisions        | Rewrite assumptions from price movement or mix return bases    |
| Investment interpretation | Thesis, independent assessments, durability, quality, execution/risk, rationale         | Conflate model output with lifecycle or approval               |
| Lifecycle and research    | Explicit Portfolio/Watchlist/Candidate/Drop, research prioritization, status            | Infer lifecycle from holdings/rankings                         |
| Portfolio                 | Holdings/cash/account state, strategic targets, allocation, execution                   | Make target weights drift with market prices                   |
| Decision/agent workflow   | Proposed revisions, evidence, reviewer actions, conflicts, immutable receipts           | Agent self-accept or write directly to production tables       |
| Operations                | Acquisition/sync manifests, observability, import preview, provenance and recovery      | Treat a successful API request as a validated financial import |

### Domain flow

`External facts → Model assumptions/projections → Investment interpretation → Portfolio construction → Execution timing`.

Downstream choices must not silently mutate upstream assumptions. Rankings express prioritization, not authorization to buy/sell. Detailed investment and scoring invariants remain in existing domain docs and scoped AGENTS files.

## 4. Canonical identity and currency

- `Company → Security → Listing` is the immutable conceptual boundary; exact security/listing identity is required for holdings and quoted returns.
- Distinguish canonical company key, security ID, listing exchange/ticker, aliases and provider-specific symbols. A provider discrepancy generates a reconciliation issue, not an automatic substitution.
- Distinguish reporting currency, model currency, listing/quote currency, position/portfolio currency and FX observation timestamp. Do not silently infer FX.
- Model bootstrap may establish narrowly scoped identity without fabricating lifecycle, holdings, targets or scores. Legacy identities and existing database UUID contracts require inspection and parity before use.

## 5. Model architecture

### Model protocol

Each supported method has a versioned, discriminated, validated contract with:

- identity: company, security/listing as appropriate, model ID, method, currency, input/output contract version;
- assumptions and units: explicit decimal values, periods and scenarios;
- source: Sheets capture / agent evidence / manually reviewed input, source ID and stable package hash;
- computation: engine version, deterministic projections, method-specific outputs, explicit return basis;
- chronology: source as-of/observed/recorded times and parent/base revision;
- disposition: captured/unaccepted, proposed, validated, conflict, accepted/rejected as applicable;
- accepted revision: append-only evidence, actor and review action.

Existing engines include a 10-year UFCF DCF, owner cash flow and residual income paths. Verify actual availability and behavior. A P-GOOGL Google Sheets capture was live-validated and passed 30 projection + 22 output checks, but its probability inputs differ from an older fixture and it remains an **unaccepted proposed source revision**. UFCF enterprise IRR is not shareholder IRR. Method-specific return metrics must not be displayed or ranked as equivalent without an approved bridge.

### Package boundary and migration strategy

- Prefer **one reviewed worksheet/model at a time** with declared ranges/fields, directly reading Sheets effective values. Do not turn XLSX formula fidelity or full-workbook cell equivalence into a dependency for first value.
- A capture is an immutable, privately stored _observation_, not a transactional Sheets snapshot. Use bounded double reads, metadata checks, exact typed semantics and content-addressed manifests.
- Separate **source-input drift** from **numerical parity** and from **investment acceptance**. Tiny serialization normalization must have a documented, bounded rule and preserve raw inputs.
- For portfolio-wide facts, define distinct typed packages for universe identity, holdings/cash, strategic targets and independent assessments. Never require every research tab for basic bootstrap.
- Adapter → validate → reconcile/diff → approved transaction → readback, with replay/conflict checks. Every imported record retains exact originating package identity.
- Long-term agent producers may use a producer-neutral revision proposal contract; imported Sheets packages and agent-authored packages have different provenance/authority claims.

## 6. Services, APIs and UI

**FastAPI:** canonical validation, native calculation, portfolio analytics, sources/ingestion, model revision and proposal services, ranking, reconciliation and audit. Use typed request/response contracts and explicit permission checks on sensitive actions. Distinct agent and reviewer credentials are required where proposal APIs are activated; never rely on client-side controls alone.

**Next.js:** presentation, user workflows and server-side authenticated API proxy; keep financial calculations on backend. Main experience areas: Overview, Portfolio & Allocation, Universe/Research Queue, Company Explorer, Valuation/Model Workspace, Revision Review, Data Health. Verify existing routes before moving them; preserve deep links and API compatibility.

**UI conventions:** show accepted vs proposed vs stale/unavailable distinctly; signal provenance and method; contextual alerts and next actions; compact evidence-rich data density; usable desktop and mobile. Automated checks plus real browser inspection are required for user-facing milestone acceptance.

## 7. Database, history and operations

- Initially preserve existing Portfolio tables in `public.*`. Use SQLAlchemy/Alembic and one verified migration chain; avoid startup schema creation in production.
- Use relational current-state tables plus only the targeted append-only revisions/snapshots/receipts needed for auditability. Exact base-revision checks protect concurrent edits; idempotency receipts protect replay.
- Guard every production write by verified target identity, source/hash, reviewed diff, recovery point, transaction safety and explicit owner authorization. A role token must not substitute for the approval decision.
- Capture `effective`, `observed`, `recorded` and domain-specific reporting times. Avoid hindsight bias and fabricated market history. Derive analytics from traceable inputs.
- Public APIs and app background refresh need bounded retries, rate/cost controls and observability. Sync jobs should not depend on always-on local development machines.
- Shared Personal Universe deployment creates cross-app release and failure blast radius. Introduce platform packages only from proven reuse, and test unaffected apps when shared code changes.

## 8. Security and trust boundaries

1. Browser requests enter trusted proxy/auth layer; backend independently verifies identity and app permissions.
2. Google/market providers are untrusted inputs; validate schema, units, timestamps and aliases.
3. AI agents are untrusted proposal producers, even if they can execute terminal commands.
4. Distinct read-only, proposal, reviewer, production migration and import privileges; no generic agent DB write rights.
5. Secrets/private financial evidence must stay out of Git, logs and PRs. Check repository visibility/history before pushing.
6. Human approval is mandatory for prod migration/import, model acceptance, authoritative Sheets edits, auth changes, deployment and unattended ingest.

## 9. Migration and implementation phases

1. **Stabilize current repository:** inventory uncommitted model packages, migration heads, API contracts and UI; commit coherent changes; pass integration tests and browser review.
2. **Verify cloud topology and schema:** read-only Neon verification, migration graph and recovery rehearsal without authorization bypass.
3. **First real accepted end-to-end model:** reviewed P-GOOGL package, canonical identity, schema compatibility, scoped preview, separately approved identity/model apply and deployed readback.
4. **Useful portfolio state:** typed, small source contracts for holdings/cash/targets plus company/listing identities; review and sync, not full workbook.
5. **Research-to-decision loop:** work with real assessments, ranks, thesis/history, independent proposals and reviewer UI.
6. **Operational maturity:** security, source freshness, provider quality, failure/recovery UX, cost controls.
7. **Personal Universe extraction:** platform modules/auth/UI/App Hub/app factory only after Portfolio cloud baseline, per parent architecture.

Roadmap sequencing, task IDs and evidence live **only** in `ROADMAP.md`; this document describes architecture, not task progress.

## 10. Architecture decision process

For material change, write short ADR under `docs/architecture/decisions/` with context, alternatives, decision, data ownership impact, compatibility, migrations, verification, risk and reversal. Require owner review for changes to financial semantics, production authority or platform target. Avoid creating placeholder directories or packages before needed.

## 11. Open decisions

Exact identity/auth provider and Vercel–Render trust path; initial portfolio bootstrap source contracts; final domain ownership handoff stages; how legacy enterprise return metrics coexist with canonical shareholder IRR in rankings; price/FX/estimate provider precedence; accepted P-GOOGL drift; feature/release cost targets. Resolve with evidence and reviewed decisions, not agent guesswork.
