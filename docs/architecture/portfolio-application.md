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

### Transaction-ledger transition

C2.3 now has a [candidate settled-ledger preview](../portfolio-ledger.md) that
reconciles explicit opening accounts to the current observed snapshot and projects
supported activity through a read-only API. Ending-statement/account comparisons
and the Portfolio private-file review UI are locally verified. Immutable candidate
packets and explicit accept/reject/correction receipts are locally verified through
the private API and browser. Saving and decisions require explicit human actions
and server authorization. Dated whole-portfolio publication and ownership guards
are locally verified through the API, with canonical Portfolio source/readback.
A separate hash-bound owner command promotes the accepted candidate to an immutable
snapshot and lineage receipt. Same-cutoff replacement stays blocked by snapshot
uniqueness. Full workbook apply becomes an ownership conflict after transfer.
The browser publication review is locally verified with explicit source-bound
confirmation and read-only recovery of ambiguous responses. Real account/source
review and production ownership activation remain gated. V2 packets additionally
support evidenced dividend receipts, explicit withholding/fees and standalone tax
debits, plus matched same-currency cash and same-listing security transfers with
two account source records, through the same reviewed lifecycle, locally verified
in isolated schemas
and responsive browser tests. Quote currency and observed settlement currency stay
independent. Security-transfer acquisition basis and gains remain explicitly
unavailable pending reviewed lot accounting. No dividend entitlement, conversion
or reinvestment is inferred.
The steps below describe the complete transition; remaining accounting coverage
is planned.

C2 adds transaction-based accounting to the existing snapshot portfolio. This is
a planned domain extension, with status and acceptance in `ROADMAP.md`. Reuse
SQLAlchemy/Alembic, exact decimal types, canonical identity, import previews,
receipts, domain transactions, guards and shared UI. A portfolio ledger is an
explicit accounting domain, not a generic event-sourcing platform.

1. **Retain the observation anchor.** Preserve the verified snapshot, native-currency
   cash, effective/recorded dates, import receipt and accepted target revision.
   Pin their IDs/hashes in a private cutover preview. Quantities do not establish
   acquisition dates, costs, brokers or historical capital contributions.
2. **Stage an evidenced opening state.** Choose an explicit cutover date. Record
   opening security/cash balances with provenance, distinct from buys/deposits.
   Broker/account allocation needs statement evidence or an explicitly reviewed
   unallocated opening classification. Preserve unknown acquisition lots/costs.
   Require exact listing quantities and per-currency cash to reconcile to the
   anchor before owner-approved cutover, with zero unexplained differences.
3. **Add genuine activity.** Typed records cover buy/sell, dividend/withholding,
   fees/taxes, deposit/withdrawal, cash/security transfer, FX and reviewed corporate
   actions. Preserve trade, settlement, effective and recorded times, original
   currencies, source row, account and linked security/listing. Paired transfer/FX
   legs reconcile across accounts. Unsupported instruments and incomplete records
   enter explicit review instead of being discarded or coerced to zero.
   Executed FX rates, gross/net amounts and charges are transaction evidence;
   dated valuation FX is a separate input. Current spot rates cannot fill missing
   historical transaction currencies or acquisition costs.
4. **Reconcile before changing the current read model.** Run candidate ledger
   projections alongside observed snapshots. Compare quantities, currency cash,
   account totals and source coverage. Owner approval selects the dated canonical
   source and a versioned projection; new dated snapshots retain ledger lineage
   and the existing investor-confirmation rules. Keep the original accepted
   snapshots and receipts available for comparison and recovery.
5. **Review source ownership explicitly.** After a reviewed ledger cutover, Sheets
   holdings/cash become reconciliation evidence for the covered scope. A later
   workbook sync must not overwrite ledger-derived state. Until that ownership
   transfer is implemented and authorized, use the existing workbook contract.
   Strategic targets, lifecycle and models keep their separate review paths.
6. **Backfill only evidenced history.** Later broker imports must reproduce the
   cutover balances before expanding historical coverage. A versioned reconstruction
   selects one opening boundary per covered scope, avoiding double-counting opening
   balances plus earlier trades. Missing history stays explicit. Position-history
   conflicts block promotion rather than being patched with invented transactions.

Broker parsers should onboard one reviewed format at a time through the existing
staging/review pattern. Pin raw-file hash, parser/contract version and stable source
record identity. Re-import is idempotent, changed or overlapping rows produce
conflicts, and acceptance is atomic. Accepted corrections link reversals or
superseding records with source/rationale. Preserve original accepted history.
Broker records may contain private account identifiers and belong outside Git.

Public corporate-action observations and actual account activity have different
authority. A provider dividend is not evidence that an account received cash or
paid withholding. A split must not adjust an already-adjusted broker position
twice. Reconcile broker events with verified action evidence and declared price
adjustment semantics before deriving quantities, income or performance.

### Accounting and performance boundaries (planned)

- **Positions and gains.** Derive holdings and native-currency cash from accepted
  opening balances/activity. Track lots and carried acquisition evidence through
  transfers. Version the cost-allocation, fee/tax, FX and rounding policy before
  calculating realized/unrealized gains. Unknown cost blocks the affected gains,
  independently of whether market value is available. Portfolio accounting policy
  and jurisdiction-specific tax reporting require distinct reviewed contracts.
- **Scope and flows.** Declare account versus consolidated portfolio boundary.
  Transfers inside the consolidated portfolio are internal; transfers crossing
  its boundary are external flows, including securities at evidenced valuations.
  Retained dividends are portfolio income/cash, with separately recorded expenses
  and withholding. A subsequent withdrawal is a separate external flow. Avoid
  double-counting dividends, transfers or fees through adjusted prices and ledger
  events. Report gross/net fee/tax treatment explicitly.
- **TWR.** Link subperiod returns around external flows using evidenced valuations
  and an explicit same-day timing convention. If only daily observations support
  an approximation, declare that methodology and coverage. Missing flow-boundary
  valuations or invalid denominators must produce an unavailable/qualified result.
  The methodological reference is the [GIPS calculation handbook](https://www.gipsstandards.org/standards/gips-standards-for-firms/gips-standards-handbook-for-firms/).
- **XIRR.** Use dated investor-perspective external flows plus the ending portfolio
  value with a declared 365-day convention. Since-cutover analysis uses opening
  market value as an analytical boundary, separately labeled from actual deposits
  in the ledger. Preserve exact flow/FX evidence and handle no-root, ambiguous-root,
  sign/date and incomplete-coverage cases explicitly. The numerical reference is
  [Microsoft XIRR](https://support.microsoft.com/en-us/excel/functions/xirr-function?nochrome=true).
- **Coverage and history.** Separate since-cutover from since-inception performance.
  An unknown historical cost does not alone prevent since-cutover TWR/XIRR when
  valuations and actual intervening flows are complete. Full since-inception claims
  require genuine history. Benchmarks need matching periods, currency and return
  basis. Version inputs, calculation and corrected historical reports. Model
  expected cash-flow IRR and enterprise UFCF IRR retain their financial-model meaning.

Owner decisions needed for implementation are the evidenced cutover/account scope,
lot-allocation policy, fee/tax/FX and same-day timing conventions, supported first
broker format and history coverage. Local synthetic development may proceed while
those gates remain open. Production schema, ownership transfer, imports and any
restatement require their established separate approvals.

## 4. Canonical identity and currency

- `Company → Security → Listing` is the immutable conceptual boundary; exact security/listing identity is required for holdings and quoted returns.
- Distinguish canonical company key, security ID, listing exchange/ticker, aliases and provider-specific symbols. A provider discrepancy generates a reconciliation issue, not an automatic substitution.
- Distinguish reporting currency, model currency, listing/quote currency, position/portfolio currency and FX observation timestamp. Do not silently infer FX.
- Model bootstrap may establish narrowly scoped identity without fabricating lifecycle, holdings, targets or scores. Legacy identities and existing database UUID contracts require inspection and parity before use.

## 5. Model architecture

### Model identity and company scope

Each company may own several independent valuation methods. Canonical identity is
company, exact listing and model type, with a revision pointer/history per model.
Publication revision labels are resolved within that model. Valuation UI selection
carries the exact model ID through summary, history and editor. Company synthesis
and decision-model selection require an explicit versioned economic contract and
owner approval. See [decision 002](decisions/002-independent-company-models.md).

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

### Published-model boundary

Google Sheets is the current agent modeling workspace. Agents explicitly publish completed, versioned contracts. The application discovers publications through the existing bounded inbox adapter, validates native calculations and records review candidates before acceptance. Canonical contracts and engines remain independent of Sheets coordinates. A future producer can deliver the same publication as JSON. The publication protocol and implementation boundaries are specified in [model-publications.md](../model-publications.md).

Routine policy-controlled promotion is a future authority transition requiring separate owner approval and activation. Existing reviewed acceptance remains the operational rule.

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

## 9. Delivery boundaries

[ROADMAP.md](../../ROADMAP.md) owns capability status, dependencies and execution.
The [product vision](../PRODUCT_VISION.md) defines a useful Portfolio release.
The minimal canonical portfolio restoration is recorded in the
[production baseline](../production-canonical-baseline.md). Broader model, market,
research and decision coverage requires its own reconciled operational evidence.

Complete source-backed investor workflows before major platform extraction.
Security, recovery, bounded refresh and proven reusable components develop alongside
those workflows. Native provider deployments and separate migration/data approvals
follow the [deployment runbook](../deployment-and-migrations.md). Keep production
activation separate from implementation and local tests.

## 10. Architecture decision process

For material change, write short ADR under `docs/architecture/decisions/` with context, alternatives, decision, data ownership impact, compatibility, migrations, verification, risk and reversal. Require owner review for changes to financial semantics, production authority or platform target. Avoid creating placeholder directories or packages before needed.

## 11. Open decisions

Outstanding decisions include dated P-GOOGL assumptions and first-model acceptance,
permitted consensus/international sources, classification and transaction-history
coverage, model selection/synthesis for decisions, source-ownership transitions,
hosted reviewer identity, reliable cloud job operation and resource budgets.

Current code uses a production web Basic Auth gate, a trusted server-to-server API
token and dedicated model proposal roles. Shared personal OIDC/session and app-scoped
permissions are platform targets. Hosted role configuration still needs operational
verification. These are distinct from the already recorded authenticated M1 readback.
Resolve each change through evidence and its review/authorization boundary.
