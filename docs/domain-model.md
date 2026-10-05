# Domain model

Status: Milestones 1A-1C, controlled legacy-record import, listing-specific market
facts, normalized output ingestion, the Company Explorer, three representative
canonical financial-model methodologies, provider-neutral external-data
contracts, Yahoo market-data ingestion, SEC reported fundamentals, and canonical
consensus-estimate snapshots are implemented. Cached source ranks remain distinct from rank calculations. Native model-input coverage across
the tracked workbook population remains very low; see the source-grounded
[model migration inventory](model-migration-inventory.md).

## Milestone 1A implementation decisions (recorded before implementation)

- Implement Company, Security and Listing with UUID primary keys. Securities carry
  their share class/instrument type and an optional same-company underlying security
  reference for ADR identity. Listing tickers are unique within a venue. FX requires
  dated observations and remains separate from ADR/share conversion ratios.
- Lifecycle events own history. A separate `company_lifecycle_current` table points
  to the authoritative event for each company; it does not add lifecycle to Company.
  Explicit transitions lock the company, check the expected prior event, append a
  sequential event and update the pointer in the same transaction. Milestone 1A
  rejects backdated/future-effective transitions rather than inventing replay rules.
- Retain `portfolios` while the application exposes one logical portfolio. Current
  holdings are the latest observed snapshot by effective time, not the last import.
  Complete, partial and unavailable snapshots remain distinguishable. Holdings
  reference the actual listing; separate `holding_cash_positions` retain native
  currency balances. Short positions and brokerage accounts are out of scope.
- Quantities/balances use `NUMERIC(28,10)`; company target weights use
  `NUMERIC(18,12)`. Decimal fractions cross the API as strings. Unknown quantity or
  cash balance stays null in partial snapshots; observed zero stays zero.
- Target revisions are explicitly created as drafts and accepted through a domain
  operation. Acceptance locks the portfolio/revision and checks each fractional
  weight in [0,1] and the invested total ≤ 1. Residual is strategic cash. Accepted
  revisions cannot be edited; missing rows remain distinct from authored zero.
- Domain services and ORM guards protect append-only snapshots/events and accepted
  targets. Restrictive database foreign keys protect historical identity references.
  No generic event-sourcing framework or business-rule triggers are introduced.
- Audit actors are explicit `LOCAL_USER`, `SYSTEM`, or `IMPORT` values with reason,
  source and timezone-aware effective/recorded timestamps. Authentication is deferred.
- Current market weights and allocation gaps require fresh listing-aware prices and
  dated FX for every holding and cash balance. Missing coverage leaves aggregate
  values null with an explicit explanation. Target weights remain independent.
- Development seed data is fictional and clearly marked demonstration data. It is
  opt-in, idempotent, and refuses to populate a nonempty real-data universe.
- Scores are four independent, versioned dimensions. Their assessments are
  append-only; corrections point to the superseded assessment. Missing values are
  null with an explicit assessment status.
- Ranking definitions, runs, and per-company entries preserve separate Portfolio,
  Watchlist, and Research concepts. Cached legacy rank positions are imported as
  source observations, while the application still emits no calculated ranks until
  their inputs and methodology are migrated.
- One standalone ETF security may have no company reference, with an exact listing
  identity. Other standalone instrument classes and instrument-level target design
  remain deferred.

Milestone 0 established infrastructure; Milestone 1 migrated core investment state.

Implemented tables are `companies`, `securities`, `listings`, `lifecycle_events`,
`company_lifecycle_current`, `portfolios`, `holding_snapshots`, `holding_positions`,
`holding_cash_positions`, `target_allocation_revisions`, `target_allocations`,
`score_definitions`, `score_assessments`, `ranking_definitions`, `ranking_runs`,
`ranking_entries`, `legacy_import_batches`, `market_data_batches`,
`price_observations`, `corporate_actions`, `price_regime_snapshots`, and
`fx_observations` (22 domain tables total). Revisions `a57efdd8015f`,
`4cef0ea57fba`, `f93584e17442`, `ac6e0a489b51`, `45571a6d359b`,
`a5bfc471caef`, and `01773da3b70f` follow baseline `0001`.

## Milestone 2A implementation

Market history is keyed by `listing_id`, not ticker. Price observations preserve
provider/adjusted values, currency, provider symbol, adjustment basis, source
quality, recorded time, import batch and source locator. Workbook snapshots are
immutable receipts; later provider snapshots append rows. Corporate actions are
listing-specific metadata and do not cause a second price adjustment.
`PriceRegimeSnapshot` stores rolling metrics, computed trend/correction states,
the source regime label, quality and methodology reference. The broad regime
label is retained as an observed legacy value because its full rule is not
documented. Missing history remains null.

The workbook importer remains a migration adapter. Provider adapters use the
provider-neutral raw-record and normalizer contracts in
[`external-data-architecture.md`](external-data-architecture.md); Yahoo Finance is
the first live development adapter, with exact reviewed listing/currency-pair
crosswalks and compressed source payloads. Canonical price, FX and corporate-action
observations remain domain-owned. Query selection prefers quality first and then
the reviewed Yahoo source tier; alternate source observations are retained, not
merged or overwritten.

Position values use fresh split-adjusted closes in listing currency. Portfolio
base values require explicit fresh, dated direct or inverse FX observations. The
active provider crosswalk now includes the held TSM ADR and SPYY ETF as their exact
listings, and provides USD/EUR and DKK/EUR observations. The currently imported
portfolio snapshot has complete fresh price/FX coverage; the ten active Watchlist
companies without safe canonical listing mappings remain explicit gaps. Market
facts do not change lifecycle, targets, scores, rank history, model assumptions or
execution. See [market-data.md](market-data.md).

## Reported fundamentals

`CompanyProviderIdentifier` stores an operator-verified SEC CIK mapping and evidence.
`ReportedFundamentalBatch` records immutable, repeatable ingestion receipts, while
`ReportedFundamentalObservation` stores provider-neutral annual, quarterly and
instant facts with filing, fiscal-period, source, currency/unit, quality and
supersession context. Raw SEC payloads use the shared external raw-payload store.
Standard us-gaap and ifrs-full concepts are mapped through an explicit allowlist;
provider tags remain provenance. SEC has the current preferred source tier, and
future normalized-provider observations remain separate and conflict-visible.

Missing metrics stay `NOT_IMPORTED`; potential changed comparative filings are
appended as `POTENTIAL_RESTATEMENT` with `DATA_CHECK`. `known_at` queries limit facts
to what the application had observed and recorded by that time. Free cash flow is
declared as a derived analytic but is not computed here; total debt, growth and
ratios are also outside the reported-fact layer. No real SEC crosswalk or statement
fact is loaded yet; see [reported-fundamentals.md](reported-fundamentals.md) for
coverage and the mapping/import workflow.

## Consensus estimates

`ConsensusEstimateProviderMapping` records evidence-backed provider-symbol and
optional listing/currency identity with role, priority, effective time and recorded
time. `ConsensusEstimateBatch` preserves provider or legacy import receipts and
reconciliation. `ConsensusEstimateObservation` stores immutable, provider-specific
annual/quarterly Revenue and EPS forecasts with exact Decimal mean/range, analyst
count, period end, snapshot/observed/recorded times, currency/unit, source, quality
and correction linkage. Raw external responses use the shared payload store.

Consensus source continuity selects one primary series; gaps are not filled from a
fallback. Without a primary, one uniquely highest-priority fallback may be selected.
Tied fallbacks are ambiguous. Provider values never blend, and consensus never
mutates native model assumptions. The migrated legacy baseline lacks vendor,
currency and absolute fiscal dates, so it remains visible as `DATA_CHECK`. See
[`consensus-estimates.md`](consensus-estimates.md) for exact source limits, coverage
and the FMP mapping/sync workflow.

## Filings and source documents

`SourceDocumentBatch` records immutable provider ingestion receipts and points to
retained raw submissions metadata. `SourceDocument` is the canonical filing/source
catalog: company and optional security identity, provider/jurisdiction, external
identifier, canonical type/form, reporting period, source dates, canonical URL,
retrieved/recorded times, quality and amendment/supersession links. SEC EDGAR
submissions normalize reviewed CIKs into supported 10-K, 10-Q, 8-K, 20-F and 6-K
records. Issuer annual reports and earnings releases can be represented as HTTPS
references. Filing bodies and issuer documents are not copied into this catalog.

Document rows and ingestion batches are append-only. A changed SEC response for an
existing accession is reported as a conflict rather than overwriting the captured
metadata. Amendments link to a captured matching original when possible; missing
dates and unresolved amendment links remain `DATA_CHECK`. Source dates and
application knowledge times are distinct for point-in-time reads. The implementation,
operator workflow and retention limits are documented in
[`source-documents.md`](source-documents.md).

## Milestone 2C Company Explorer

The Company route is a read-oriented research surface over existing canonical
domains. It brings company/security/listing identity, explicit lifecycle, the latest
observed holding and accepted target, independent score dimensions, stored ranking
run state, listing-aware prices, normalized model-output snapshots and available
history, consensus estimates and filing/source-document metadata into one navigable
view. It adds no financial or ranking calculation and does not treat presentation
state as a new domain owner.

The page presents identity, lifecycle and portfolio context first; then quality and
risk; factual market observations and freshness; normalized valuation/return
outputs; and ranking context. Long lifecycle, score, rank, model and price-regime
history uses user-opened disclosures. The API remains responsible for values such
as native/base market value and their completeness state. Listing, reporting, model
and portfolio currencies remain separate, and unknown or stale values stay explicit.

The Company Explorer does not expose editable model assumptions. The imported model
contract is output-only; native model editing requires the later revisioned model
input domain, calculation ownership and workbook parity work described by Milestone
3A. See [company-explorer.md](company-explorer.md) for the page inventory and
availability boundary.

The application supports independently authored state, imported records, and
fictional demonstration records. Import provenance and limitations are described in
[workbook-import.md](workbook-import.md). The REST operation inventory is in
[architecture.md](architecture.md); verification evidence is in
[verification.md](verification.md).

The model in this document is intentionally evolutionary. It defines domain ownership and semantic boundaries first; tables should be implemented only when required by the current vertical slice.

---

## 1. Authority and ownership

Explicit user instructions, `AGENTS.md`, `README.md`, and the documentation in this directory govern architecture and domain ownership.

The legacy Google Sheets workbooks are migration references and temporary reference implementations for deliberately selected calculations and outputs. Their physical sheet layout is not the database schema.

The required dependency direction is:

```text
Market facts
    ↓
Estimates and company facts
    ↓
Financial models
    ↓
Investment interpretation
    ↓
Portfolio construction
    ↓
Execution timing
```

A downstream layer must never silently rewrite an upstream assumption.

Examples:

- market price may change valuation context
- price momentum may change Execution Pace
- price momentum must not change long-term DCF assumptions
- model output must not change lifecycle
- holdings must not automatically create strategic target weights
- target weights must not change because market prices move

---

## 2. Application ownership boundaries

### Next.js

Next.js owns:

- presentation
- navigation
- interaction
- filtering
- sorting
- user-facing editing flows
- visualization
- responsive UI
- client-side interaction state

The frontend must not become an independent financial-calculation engine.

Investment logic must not be duplicated inside React components.

---

### FastAPI

FastAPI owns:

- domain validation
- domain operations
- financial calculations
- portfolio analytics
- scoring/ranking algorithms
- model engines
- ingestion workflows
- snapshot creation
- data-quality rules
- future agent/research workflows

---

### PostgreSQL

PostgreSQL owns canonical persisted state and auditable history after the relevant domain has completed migration.

Persisted history must preserve what was known or explicitly authored at the time.

Do not rewrite historical observations to match current state.

---

## 3. Identity model

The application distinguishes three levels of investment identity:

```text
Company
   ↓
Security
   ↓
Listing
```

These concepts must not be collapsed.

---

### 3.1 Company

A `Company` represents the stable business / issuer identity.

Examples:

- Alphabet Inc.
- ASML Holding N.V.
- dLocal Limited

A company may have multiple securities.

Company identity should contain relatively timeless issuer-level attributes.

Typical fields may include:

- id
- legal / canonical name
- display name
- reporting currency
- country / jurisdiction where applicable
- created timestamp
- archived/inactive metadata where necessary

A ticker is never a company identifier.

Lifecycle is not an immutable company attribute and should not be stored as an ordinary field on the core company record.

Unknown reporting currency remains null.

---

### 3.2 Security

A `Security` represents an economic instrument or share class associated with a company.

Examples:

- Alphabet Class A common equity
- Alphabet Class C common equity
- an ordinary share
- an ADR / depositary receipt
- a preferred share

A company may have multiple securities.

Typical fields may include:

- id
- company_id
- security type
- share class
- canonical security name
- underlying security relationship where applicable
- active/inactive status
- metadata required for economic identity

The security layer exists because:

- one company may have multiple share classes
- one economic security may appear through multiple listings
- ADRs and ordinary shares must not be conflated
- ticker changes must not change the security's economic identity

---

### 3.3 Listing

A `Listing` represents a venue-specific tradable quotation of a security.

Typical fields include:

- id
- security_id
- exchange / venue
- ticker
- listing currency
- instrument/listing type
- active-from timestamp/date
- inactive-from timestamp/date where applicable

Listing identity is scoped by venue.

Ticker alone is not globally unique.

Listing currency is distinct from:

- company reporting currency
- model currency
- portfolio currency

Historical listings referenced by observations or transactions must not be hard-deleted.

---

## 4. Listing conversion and ADR governance

Changes in ADR/share conversion must be historically auditable.

Use an effective-dated revision model such as:

`listing_conversion_revisions`

A revision may contain:

- listing_id
- underlying_security_id or underlying_listing_id where appropriate
- effective_from
- effective_to where needed
- conversion ratio
- source
- recorded_at

Define the conversion ratio explicitly.

Preferred semantic:

> underlying ordinary shares represented by one listed receipt

Known conversion ratios must be positive.

Unknown conversion ratios remain null.

Never silently assume a ratio of 1.

Changes append a new revision rather than rewriting historical assumptions.

FX conversion and ADR/share conversion are separate operations:

- share ratio converts units
- FX rate converts currencies

---

## 5. Investment lifecycle

Canonical lifecycle states are:

- `PORTFOLIO`
- `WATCHLIST`
- `CANDIDATE`
- `DROP`

Lifecycle belongs to the investment-universe domain.

It must not be inferred from:

- holdings
- target allocations
- financial models
- scores
- ranking results
- price movements

Lifecycle changes only through an explicit domain operation.

---

### 5.1 Lifecycle history

Use append-only lifecycle events.

Proposed entity:

`lifecycle_events`

Typical fields:

- id
- company_id
- previous_state nullable
- new_state
- effective_at
- recorded_at
- actor
- reason
- source / provenance where applicable

Initial assignment may have no previous state.

A lifecycle transition must:

1. validate the transition
2. append the event
3. update any materialized current-state projection
4. commit atomically

---

### 5.2 Current lifecycle

Lifecycle history is authoritative.

For query convenience, the application may maintain a current-state projection.

Possible approaches:

- derive current state from the latest lifecycle event
- maintain a dedicated `company_lifecycle_current` projection updated transactionally

Do not store lifecycle as an ordinary mutable field on `companies`.

If a projection exists, it is current-state infrastructure rather than historical authority.

---

## 6. Portfolio domain

The initial application supports one logical investment portfolio.

A `portfolios` table should nevertheless exist so later multi-portfolio support does not require redesign.

Brokerage-account modeling is out of scope for Milestone 1.

Short positions are out of scope for Milestone 1.

Cash is in scope architecturally.

---

### 6.1 Portfolio

Proposed entity:

`portfolios`

Typical fields:

- id
- name
- reporting/base currency
- created_at
- optional status

Portfolio currency does not replace:

- company reporting currency
- security/listing currency
- financial-model currency

---

## 7. Holdings

Holdings represent observed portfolio state.

They do not represent strategic target allocation.

They do not automatically determine lifecycle.

---

### 7.1 Holding snapshots

Proposed entity:

`holding_snapshots`

A snapshot represents observed portfolio holdings at an effective point in time.

Typical fields:

- id
- portfolio_id
- effective_at
- recorded_at
- source
- actor/import identity
- completeness state
- notes where needed

Accepted historical snapshots are append-only.

A completeness state must distinguish:

- complete observed snapshot
- partial snapshot
- unavailable/missing holdings data

A complete empty portfolio is different from missing data.

---

### 7.2 Security positions

Proposed entity:

`holding_positions`

A security position belongs to one holding snapshot and references a security or listing according to the selected implementation.

For the initial application, positions should normally reference the actual held listing when known, because price and currency depend on listing identity.

Typical fields:

- id
- holding_snapshot_id
- listing_id
- quantity
- optional cost_basis
- optional cost_basis_currency
- source metadata where required

Constraints:

- one aggregated position per listing per snapshot
- quantity uses exact decimal storage
- missing quantity is not zero
- stored zero means an explicitly observed zero where such storage is required

Historical positions must not be overwritten.

---

### 7.3 Cash positions

Cash must not be modeled as a fake company or fake security.

The holdings model should support native-currency cash.

A suitable implementation may use either:

```text
holding_security_positions
holding_cash_positions
```

or a unified position model with a structural constraint that exactly one asset type is populated.

The exact implementation may be chosen during the holdings vertical slice.

Required semantics:

- cash has a currency
- cash has a quantity/balance
- native EUR and USD cash remain distinguishable
- cash can participate in portfolio value later once FX support exists

Milestone 1 does not need advanced cash analytics.

---

## 8. Strategic target architecture

Current holdings and strategic target architecture are separate concepts.

Target architecture represents the long-term desired portfolio configuration if valuation and thesis remain acceptable.

Target changes require explicit authorship.

Price changes must never create target revisions.

---

### 8.1 Target allocation revisions

Proposed entity:

`target_allocation_revisions`

Typical fields:

- id
- portfolio_id
- status
- effective_at
- created_at / recorded_at
- actor
- reason
- notes

Suggested statuses:

- `DRAFT`
- `ACCEPTED`

Accepted revisions are immutable.

Corrections or strategic changes create a new revision.

---

### 8.2 Target allocations

Proposed entity:

`target_allocations`

For Milestone 1, target weights are company-level.

Typical fields:

- id
- target_allocation_revision_id
- company_id
- target_weight

Constraints:

- unique company per revision
- use exact decimal storage
- weight unit is fractional:
  - `0` = 0%
  - `0.05` = 5%
  - `1` = 100%
- each target weight must satisfy:

```text
0 <= target_weight <= 1
```

The sum of invested company target weights may be:

```text
<= 1
```

Residual allocation represents strategic cash.

Do not require invested company weights to sum exactly to 100%.

Missing target and explicit zero target are different states.

A missing allocation row means no target has been authored for that company in the revision.

An explicit zero means the company was deliberately assigned a zero target where that distinction is required.

---

### 8.3 Future target granularity

Company-level targets are the deliberate Milestone 1 scope.

This must not be interpreted as a permanent rule that all future allocations must be company-level.

Future requirements may include:

- specific share classes
- ETFs
- other securities
- explicit cash targets
- instrument-level strategies

Do not build those abstractions before they are required.

---

## 9. Current vs target reconciliation

Current holdings and target allocation are independent observations.

The application should make disagreement visible.

Examples:

- owned company with target weight 0
- positive target but no current position
- current holding not currently classified as `PORTFOLIO`
- target company whose lifecycle has not yet been reconciled

The system must not silently fix these inconsistencies.

A user/domain operation may explicitly reconcile them.

---

## 10. Versioned score assessments (Milestone 1B)

Scores remain independent dimensions.

Known current dimensions:

### 10Y Durability

Scale:

```text
0–5
```

Higher is better.

Purpose:

Assess whether competitive advantage / relevance is likely to persist for 10+ years.

---

### Compounder Quality

Scale:

```text
0–5
```

Higher is better.

Purpose:

Assess how effectively the business can convert growth and reinvestment into long-term shareholder value.

---

### Execution

Scale:

```text
1–5
```

Higher is better.

Interpretation:

- 5 = repeated strong delivery against operating KPIs/guidance, improving economics and capital discipline
- 1 = persistent execution failure

---

### Risk

Scale:

```text
1–5
```

Higher means greater structural/business/financial/regulatory/geopolitical risk.

Important:

```text
1 = relatively low risk
5 = relatively high risk
```

Risk excludes valuation.

---

### 10.1 Score definitions and assessments

`score_definitions` versions each explicit dimension and records:

- dimension
- scale
- methodology
- units
- directionality
- units
- methodology and source reference
- effective date and active/retired status

and:

`score_assessments` references a company and one definition version and records an
exact decimal value to four fractional places when assessed, explicit status/reason when it is not, effective
and recorded timestamps, rationale, actor, source, and optional supersession link.

Accepted score assessments should be append-only.

Corrections should create a new assessment referencing the superseded observation.

Missing/invalid scores remain null with a quality/status reason.

An absent score never passes a gate.

Definitions and assessments are immutable after creation. A correction is a new
assessment that references the prior one. Null/unavailable/invalid scores never
become zero, neutral, or passing. This is a domain-specific model, not a generic
no-code scoring framework.

The application may understand the known investment dimensions explicitly while preserving versioned methodology.

---

## 11. Ranking definitions and immutable runs (Milestone 1C)

Rankings are distinct from scores.

Future ranking categories include:

- Portfolio Rank
- Watchlist Rank
- Research Rank

The three ranking types remain separate: `PORTFOLIO`, `WATCHLIST`, and `RESEARCH`.
Each has a versioned `ranking_definitions` row containing its documented ordering,
population, required inputs, workbook/source reference, effective date, and
implementation status (`NOT_MIGRATED`, `PARTIAL`, or `READY`). Definitions are
immutable; changing a rule requires a new version.

The relational implementation uses:

- `ranking_definitions`
- `ranking_runs`
- `ranking_entries`

A `ranking_runs` row records one definition version, as-of and recorded timestamps,
run status, actor, reason, and source. Its `ranking_entries` snapshot one state for
each company present in the universe at that run. Company creation, source-recorded,
accepted, and effective timestamps are checked against the run's `as_of` boundary;
a later-recorded or not-yet-effective observation cannot leak into an earlier run.
A numeric position is a positive
integer only for `RANKED`; all other statuses require a null position. Per-run
company identity and ordinal positions are constrained against duplicates.

Entry statuses include `RANKED`, `INPUTS_UNAVAILABLE`, `NOT_ELIGIBLE`, `EXCLUDED`,
and `NOT_MIGRATED`. Runs and entries are append-only. Company views select the latest
run for each active definition and expose prior per-company entries as history;
universe changes or lifecycle changes never rewrite earlier snapshots.

### 11.1 Workbook-supported semantics and current availability

Focused inspection of `Portfolio_Watchlist.xlsx` records these separate rules in
`docs/workbook-map.md`:

- **Portfolio Rank** orders non-empty Portfolio Score descending, then ticker
  ascending for ties. Its active decision population is companies with a positive
  observed current weight or target weight. Cached unique positions are imported;
  Portfolio Score remains unmigrated.
- **Watchlist Rank** orders Expected IRR descending, then ticker ascending, for
  explicit `WATCHLIST` lifecycle members. Cached unique positions are imported;
  Expected IRR and valuation remain unmigrated.
- **Research Rank** orders Research Sort Key descending, then ticker ascending.
  Cached unique positions are imported; the sort key and upstream inputs are not
  migrated.
- The Watchlist view's separate Candidate Rank starts with Fit Tier and then uses
  Expected IRR. It is not the canonical IRR-first Watchlist Rank and is not
  implemented here.

Milestone 1C stores auditable source positions and explicit availability snapshots,
not calculated ranks. Cached positions are preserved only where they fit the
unique-ordinal contract; duplicate or malformed cells and unresolved population
inputs remain `INPUTS_UNAVAILABLE`. Missing values are never replaced with rank zero
or an invented ordinal result. Rankings do not change lifecycle, holdings, target
weights, model assumptions, or execution behavior.

Historical ranking runs preserve:

- ranking-definition/version
- company universe and per-company state at the run
- output position or explicit missing/exclusion status and reason
- as-of and recorded timestamps, actor, reason, and source

Historical rankings are read from stored runs and are never recomputed using today's
lifecycle membership or inputs. Future numeric rank generation must wait for the
documented upstream values and a scoped parity migration. No generic rules engine is
used.

---

## 12. Provenance and auditability

Material changes should preserve enough provenance to explain:

- what changed
- when it was economically effective
- when the system observed/recorded it
- who or what created the change
- why it changed
- which evidence supported it

Possible provenance fields include:

- source URL
- source identifier
- observation timestamp
- effective date/time
- recorded timestamp
- actor/calculation identifier
- reason
- superseded record reference

Source records may be shared when several observations originate from the same import/source.

Credentials and secrets are never provenance fields.

---

### 12.1 Effective time vs recorded time

These are distinct facts.

Example:

```text
Company result effective: 2026-09-30
System records result:    2026-10-02 08:15
```

Both may matter.

Do not collapse them into one timestamp where domain meaning requires both.

---

### 12.2 No fabricated history

An imported workbook snapshot is evidence only for values actually observed or documented at that point.

Do not create historical rows merely because current values are known.

Do not reconstruct fictional historical estimates, scores, fair values or portfolio states.

---

### 12.3 Corrections

Accepted historical observations are not overwritten.

Corrections append a new record and identify the prior record they supersede where applicable.

---

### 12.4 No generic event-sourcing system

The application does not require general-purpose event sourcing.

Use:

- conventional relational state tables
- append-only snapshots
- revision tables
- event tables where the domain specifically requires them

Avoid introducing an event-sourcing framework merely for architectural purity.

### 12.5 Controlled workbook import receipts

`legacy_import_batches` stores an immutable receipt for each applied pair of scoped
workbooks. It retains both source SHA-256 hashes, the combined deterministic digest,
the time the import observed the files, and a JSON reconciliation report. The unique
digest makes an identical rerun idempotent. The report records unresolved mappings
without converting them to domain values; the batch is a migration receipt, not a
general event log or a runtime connection to Google Sheets. See
[workbook-import.md](workbook-import.md).

---

## 13. Missing data

Null is semantically different from zero.

Null may mean:

- unknown
- missing
- unavailable
- invalid
- not yet researched
- not applicable

A separate status/data-quality field should clarify the meaning where necessary.

Zero represents a real observed or explicitly authored value.

Never:

- treat missing price as zero
- treat missing assessment as neutral
- treat missing assessment as passing a gate
- treat missing target as zero target
- treat absent expected return as zero expected return
- invent default FX/ADR values to complete a calculation

Missing information should remain visibly incomplete.

---

## 14. Currency and economic comparability

The following currencies are distinct concepts:

- company reporting currency
- security/listing currency
- portfolio currency
- model currency
- cost-basis currency

Do not implicitly treat them as interchangeable.

Future valuation comparisons must preserve the exact:

- model currency
- listing price currency
- FX observation
- ADR/share conversion

used in the calculation.

Receipt ratio conversion changes security units.

FX conversion changes currency units.

These must remain separate operations.

Milestone 1 does not need to implement FX histories or valuation conversion.

---

## 15. Normalized model outputs and the model-authoring boundary

The normalized model-output contract exposes a common interface independent of
underlying valuation methodology. Milestone 2B persists workbook-published values
as exact-decimal `model_output_snapshots`, with separate immutable import receipts.
Current contract snapshots and recorded legacy revisions share the normalized
fields but retain their distinct snapshot kind and source identity.

Canonical fields include:

- Bear FV
- Base FV
- Bull FV
- Bear Probability
- Base Probability
- Bull Probability
- Weighted Fair Value
- Weighted Upside
- Expected Cash-Flow IRR
- Hurdle
- Expected Excess
- Forward Fundamental CAGR
- Research/model status
- Contract/model availability status

Company identity is the relational company reference and the legacy model key is
retained for source traceability. Model currency is imported only when its label
and currency code are explicit in the model sheet. A current-contract import time
is the recorded time only: because the contract has no effective timestamp,
`effective_at` remains null. Legacy history uses only its recorded As-of Timestamp.

Missing values stay null and output-quality status distinguishes partial, bad,
unavailable, and complete snapshots. An invalid nonblank cell is retained in the
field-issue provenance and its numeric value remains null. Unknown currency is not
inferred from a quote, listing or company reporting currency. Historical rows are
append-only; a correction under an existing legacy revision ID is rejected rather
than rewriting the accepted record.

The model-output interface does not own 10Y Durability, Compounder Quality,
lifecycle, holdings, targets or rankings. These are read from their canonical
domains when needed and are not copied into output history.

This is output ingestion, not full model authoring for every legacy model. Three
representative methods now have methodology-specific canonical authoring domains:
UFCF DCF, owner cash flow and residual income. Assumptions, projections and formulas
for other model types remain in the legacy modeling environment until separately
migrated and reconciled. The per-tab population and migration blockers are recorded
in the [model migration inventory](model-migration-inventory.md).

### Canonical financial-model state (Milestones 3A–3D)

`financial_models` stores model identity/type, company and valuation-listing
references, model currency and the current-revision pointer. Each accepted
`financial_model_revisions` row is immutable and records effective/recorded time,
actor, source, source revision identity, rationale and its base revision. The
normalized output row is shared; assumption and projection schemas remain
methodology-specific. Supported native methods are `UFCF_DCF_10Y_FADE`,
`OWNER_CASH_FLOW_10Y` and `RESIDUAL_INCOME_10Y_FADE`. They use dedicated DCF,
owner-cash-flow and residual-income relational tables rather than a generic
expression engine. Exact decimal values use PostgreSQL `NUMERIC`; each accepted
revision is recalculated and persisted transactionally.

Revision creation checks the current base revision under a row lock. A stale edit
returns a conflict rather than replacing a newer accepted state. The model pointer
is a current-state projection only: all prior revisions and their assumptions,
scenario drivers, projections and outputs remain readable. Workbook parity is
currently represented by P-GOOGL, W-TOST and W-HDFC fixtures; this is not a batch
migration of real model assumptions. See [financial-models.md](financial-models.md)
for methodology formulas, portable contract versions, APIs and limits.

A financial model does not own lifecycle.

---

### 15.1 Weighted Fair Value

Weighted Fair Value is:

```text
SUMPRODUCT(
    scenario fair values,
    scenario probabilities
)
```

It is a valuation reference.

It is not a fixed-horizon price prediction.

---

### 15.2 Expected Cash-Flow IRR

Expected Cash-Flow IRR is calculated once from probability-weighted expected shareholder cash flows.

Do not average Bear/Base/Bull IRRs.

For dividend-paying companies:

- modeled dividends are explicit shareholder cash flows
- terminal proceeds are separate
- dividends must not be double counted in terminal value

---

### 15.3 Hurdle

Hurdle represents investor required return / risk adequacy.

It is not automatically equivalent to WACC.

---

### 15.4 Expected Excess

```text
Expected Excess
=
Expected Cash-Flow IRR
-
Hurdle
```

Expected IRR is the primary opportunity-return measure after quality/durability gates.

Expected Excess is secondary context.

---

## 16. Investment decision hierarchy

The intended decision sequence is:

```text
1. 10Y Durability
2. Compounder Quality
3. Forward Fundamental Compounding
4. Valuation / Expected IRR
5. Portfolio Fit
6. Execution Timing
```

Do not collapse these dimensions into a single opaque score.

Execution timing must never alter:

- valuation assumptions
- target architecture
- lifecycle
- durability
- quality
- long-term thesis

---

## 17. Actor identity

Authentication is out of scope for Milestone 1.

Audit records may use explicit system identities such as:

- `LOCAL_USER`
- `SYSTEM`
- `IMPORT`

These represent activity provenance, not an authentication system.

The schema should remain easy to migrate to real users/actors later.

Do not introduce authentication solely for audit fields.

---

## 18. Structural implementation rules

Use foreign keys and database constraints for structural invariants.

Prefer:

- surrogate primary keys
- UUIDs unless a compelling reason exists otherwise
- exact decimal types for financial quantities
- timezone-aware timestamps
- explicit uniqueness constraints
- non-destructive history
- null-safe semantics

Avoid:

- ticker primary keys
- floating-point storage for allocation weights
- hidden business rules in database triggers where normal service logic is clearer
- premature generic abstraction
- hard deletion of historically referenced identities

API/domain-service validation and database structural constraints should complement each other.

---

## 19. Milestone 1A implementation scope (completed)

Implement only the first verified vertical slice.

Required domain entities:

```text
companies
securities
listings

lifecycle_events
optional current-lifecycle projection

portfolios

holding_snapshots
holding positions
cash-position support or a clean extension point

target_allocation_revisions
target_allocations
```

Milestones 1B and 1C add only the distinct score assessments and ranking snapshot
infrastructure described in sections 10 and 11. Do not yet implement:

- market-price ingestion
- FX
- financial models
- DCF calculations
- scenario engines
- Expected IRR
- numerical Portfolio, Watchlist, or Research rank calculations
- estimate momentum
- execution signals
- Thesis Watch automation

---

## 20. Milestone 1A user-facing flows

The first implemented schema must support useful application flows.

### Portfolio

Show:

- current positions
- strategic target weights
- target gaps where meaningful without invented prices
- cash where supported
- explicit data completeness/freshness

Do not invent market values before price data exists.

---

### Universe

Show:

- companies
- lifecycle
- useful filtering
- security/listing identity where relevant

Canonical lifecycle must be explicit.

---

### Company

Show:

- company identity
- securities
- listings
- lifecycle history
- current holding context
- current target context

The page should establish the future Company Explorer structure without implementing valuation yet.

---

## 21. Seed data

Development seed data may be used to demonstrate flows.

Seed data must be clearly marked as non-production/demo data.

The seed should include:

- several companies
- representative lifecycle states
- one company with multiple securities/listings where useful
- one portfolio
- current holdings
- native-currency cash if implemented
- one accepted target-allocation revision

Do not confuse seed data with migration of the real workbook.

---

## 22. Migration strategy

The legacy workbook remains the reference implementation during migration.

Do not rewrite all functionality at once.

For each migrated domain:

1. identify authoritative workbook ownership
2. document semantic behavior
3. implement the smallest coherent replacement
4. compare new state/outputs with the workbook
5. add automated regression tests where appropriate
6. migrate downstream consumers only after verification
7. retire workbook ownership only when the new implementation is trusted

The web application's database gradually becomes the canonical source of truth domain by domain.

---

## 23. Current Milestone decisions

The following decisions are considered resolved for Milestone 1A:

### Identity

```text
Company → Security → Listing
```

### Lifecycle

Explicit append-only transitions.

Current lifecycle is derived/projected from lifecycle history.

### Portfolio

One logical portfolio initially.

Multi-portfolio schema supported.

Broker accounts out of scope.

### Holdings

Long positions and cash are in scope.

Short positions are out of scope.

### Targets

Company-level strategic targets.

Fractional weights.

```text
0 <= weight <= 1
sum(company targets) <= 1
```

Residual represents strategic cash.

### Scores

Milestone 1B definitions and append-only assessments are implemented for the four
canonical dimensions. Missing values remain explicit nulls with statuses.

### Ranking

Milestone 1C provides three separate, versioned definitions and immutable run
snapshots. Supported cached workbook positions are imported as source observations
without recalculation. Rankings do not own lifecycle or portfolio/model state, and
numeric ranking generation remains unavailable until its source inputs are migrated.

### Authentication

Out of scope.

Use local/system/import actor identities.

### Provenance

Domain-specific append-only audit structures.

No generic event-sourcing framework.

---

## 24. Remaining future decisions

The following decisions should be deferred until their corresponding domain is implemented:

- broader standalone fund and ETF modeling beyond the imported SPYY security
- security-level versus company-level models in unusual multi-class situations
- exact cash-target representation if strategic cash needs explicit target rows
- transaction-ledger support
- brokerage/account hierarchy
- FX provider mappings, precedence and history coverage
- provider-specific crosswalk, precedence and retention decisions under the
  [external-data architecture](external-data-architecture.md)
- honest known-at query APIs for each canonical data domain
- research-source relational model
- native model-authoring and assumption-versioning strategy
- assumption-versioning strategy
- estimate-history schema
- numeric ranking inputs and parity implementation details
- execution-signal persistence
- multi-user authentication/authorization

Do not pre-solve these by building abstractions before requirements exist.

---

## 25. Guiding principle

Implement the smallest verified domain slice that preserves the investment system's semantics.

Prefer explicit, understandable domain models over clever generic frameworks.

Correctness, auditability, and economic meaning take priority over minimizing table count or code volume.
