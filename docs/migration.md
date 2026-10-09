# Migration strategy

## Current scope

Milestone 0 establishes the application shell, API/database connectivity, environment configuration, schema migration mechanism, contracts, and development checks. Milestone 1A adds identity, explicit lifecycle history, observed holdings/cash, and accepted targets. Milestone 1B adds the four versioned score dimensions and append-only assessments. Milestone 1C adds separate versioned Portfolio, Watchlist, and Research ranking definitions plus immutable runs. All three ranks now calculate their distinct documented rules from canonical point-in-time inputs; cached workbook rank cells remain migration evidence only and are not current calculation inputs.

`npm run db:seed` is an opt-in fictional development demonstration. Its marked
records are not migration fixtures or accepted real investment state. The seed
refuses an existing real-data universe. The repeatable, dry-run-first import and
reconciliation workflow is documented in [workbook-import.md](workbook-import.md).
Import batches retain source hashes and reports. The importer refuses to mix
fictional seed state with imported state unless the caller explicitly replaces a
seed-only database after authored-history checks pass.

The initial development database is a locally installed PostgreSQL instance. Connection details come from environment configuration. SQLAlchemy and Alembic use the same database setting, so a later container-hosted PostgreSQL service can be selected without changing application or domain code. See the repository [README](../README.md) for installation and startup commands.

## Sources and authority

Explicit user instructions, `AGENTS.md`, `README.md`, and `docs/` define intended rules and ownership. Legacy workbook artifacts are migration evidence. Use selected authoritative workbook calculations as references during their migration; do not elevate every historical sheet or formula into architectural authority.

Maintain the source inventory in [workbook-map.md](workbook-map.md). When a workbook behavior conflicts with an explicit rule or has unclear semantics, record the exact discrepancy, preserve verified behavior where possible, and resolve the affected definition before cutting over dependent functionality. Do not silently choose a simpler calculation or manufacture missing inputs.

## Acceptance sequence for each financial or analytical module

1. Identify the scoped module, its authoritative outputs, upstream inputs, owners, units, currencies, source/version, and observation time. Record any ambiguous formula behavior.
2. Capture representative fixtures from that reference version. Include ordinary and edge cases, missing/invalid values, alternate listings and currency conversions where applicable. Capture only observations that actually exist.
3. Implement deterministic backend calculations with documented formulas and explicit data-quality states. Expose a stable Pydantic contract; keep React limited to presentation and interaction.
4. Compare outputs to the captured reference inputs/outputs. Record tolerances explicitly by field; tolerances must reflect precision/rounding and must not conceal semantic discrepancies.
5. Add regression tests that demonstrate reconciliation and ownership boundaries. Test null handling, scenario cash-flow treatment, and other relevant invariants. Resolve material mismatches before acceptance.
6. Accept the module and then migrate downstream consumers. Record the acceptance evidence and make PostgreSQL canonical for that migrated domain. A polished UI or healthy database connection does not establish financial parity.

For data-only domains, verify identity, lifecycle ownership, completeness, units, provenance, and representative imported records before cutover. A successful import count alone does not establish semantic correctness.

## Vertical delivery order

Start with universe identity and explicit lifecycle, then current holdings and strategic targets as separate slices. Add the Company Explorer and normalized model outputs before migrating individual financial engines. Estimates, market history, research workflows, and automation follow deliberately.

The [domain model](domain-model.md) distinguishes implemented Milestone 1 tables
from future design. Later sections are not a schema to create wholesale. Ranking
definitions capture the focused workbook semantics in [workbook-map.md](workbook-map.md),
but actual rank calculation requires migration of its upstream inputs and parity
evidence. Defer unrelated dependencies and product domains until their scoped slice.

## Ranking migration boundary

The workbook evidence defines three independent sorts: Portfolio Score
descending for the active positive current/target portfolio population; Expected IRR
descending for explicit WATCHLIST members; and Research Sort Key descending for the
Research Universe. Each has ticker-ascending tie order and leaves a blank key
unranked. Watchlist Candidate Rank, which orders Fit Tier before Expected IRR, is a
separate concept and must not replace canonical Watchlist Rank.

Milestone 1C persists the definitions, cached source observations, and explicit
per-company states. Watchlist Rank sorts comparable Expected IRR inputs, keeping
native shareholder-cash-flow and legacy normalized return semantics in separate
cohorts. Portfolio Rank implements the workbook's IRR-first Portfolio Score and
also keeps those return semantics separate. Research Rank implements the Candidate
High/Low tier and persistent-seed Research Sort Key, including its explicit blank
seed fallback. Each run retains exact inputs, source references, status and output;
later state cannot regenerate old results. Missing inputs, stale/mismatched prices,
unknown currency, ambiguous identity, and unsupported cohorts remain explicit.
Rankings do not own or mutate lifecycle, portfolio targets/holdings, model
assumptions, or execution.

Canonical score assessments and cached rank observations are imported by the
controlled workflow in [workbook-import.md](workbook-import.md). Their source
coverage and record-level provenance are retained. This data-only cutover does not
claim parity for financial models or computed ranking methods. Blank score coverage
remains an explicit report gap, and source dates unavailable in the workbook remain
unknown rather than reconstructed.

## Data changes and schema changes

Alembic owns schema evolution. Do not call SQLAlchemy `create_all()` on application startup or depend on a developer's pre-existing tables. Each schema change has a reviewed migration and is checked against a disposable PostgreSQL database before use with real application data.

Workbook imports and analytical backfills are separate, explicit workflows, not hidden server-startup behavior. The scoped importer is repeatable by workbook-pair hash, records an import batch and reconciliation results, and applies domain-specific duplicate/history rules. It uses the actual import observation time only when the source does not document a date; that timestamp is not represented as the original economic effective date.

Historical analytical records are append-only after acceptance. Corrections create attributable new records that reference the corrected observation. Today's prices, model assumptions, lifecycle, and target weights cannot be used to rewrite historical results. Mutable current-state projections must retain the historical decisions or observations from which they were derived.

Downgrades may destroy data once later schema migrations add domain tables. Review the particular migration and use a backup or disposable database as appropriate; an Alembic downgrade is not a general data-recovery strategy. Milestone 0's baseline contains no domain data to roll back.

## Completion evidence

Record tested code/version, fixture identity, accepted tolerances, reconciliation
outcome, regression checks, unresolved limitations, and canonical ownership for each
migrated module. The data import reconciles supported records against the parsed
source snapshot; it does not establish calculation parity for Portfolio Rank,
Research Rank or any financial model. Watchlist Rank parity is limited to the
representative workbook cases documented in [watchlist-rank.md](watchlist-rank.md).
A cutover is complete only when consumers use the accepted owner and no longer
depend on Sheets as the application database for that domain.

## Milestone 2A: canonical market facts

The `Market Data.xlsx` import is separate from `db:import-workbook`. It resolves exact
venue/ticker/currency listing identities, validates provider symbols and reports
non-ready, unsupported or conflicting rows without guessing. The command is
idempotent by workbook content hash and stores immutable price observations, source
batch metadata, corporate actions and dated regime snapshots. A numeric or trend /
correction reconciliation mismatch prevents apply. Detailed source metrics,
provider coverage and remaining gaps are in [market-data.md](market-data.md) and the
machine-readable report linked there.

This importer is a migration adapter, not a live feed. Runtime provider interfaces,
raw-payload retention and multi-source selection follow the
[external-data architecture](external-data-architecture.md).

Market data is factual state. It cannot write lifecycle, targets, scores, ranking
runs, model assumptions or execution. Dated FX observations are the only currency
conversion input. Without complete fresh price/FX coverage, current portfolio base
value, weights and allocation gaps remain null. Portfolio target architecture stays
separate from current market weights.

## Milestone 2B: canonical model-output snapshots

The explicit `db:import-model-outputs` workflow imports only cached, published
outputs from the versioned Model Output Contract and mapped output cells from the
legacy revision ledger. It stores exact-decimal, immutable snapshots with model
status, explicit model currency where documented, workbook/cell provenance, and
recorded/effective time kept separate. It does not evaluate formulas or import
assumptions. Lifecycle, scores, targets, prices and other domain-owned values are
excluded.

The importer validates the contract labels and performs nine exact cached-value
comparisons against representative native model cells before allowing an apply.
It then checks persisted normalized values. Unresolved identities, undocumented
currencies, malformed cells and unavailable model contracts remain explicit in
the batch report. Importing normalized results is not acceptance of model formula
parity; the financial-model authoring environment remains the workbook until a
later migration completes representative calculation reconciliation. See
[model-output-ingestion.md](model-output-ingestion.md).

## Native model-input population assessment

The read-only inventory of all 116 `P-` / `W-` model tabs is in
[model-migration-inventory.md](model-migration-inventory.md), with its generated
machine-readable artifact at
[`reconciliation/model-migration-inventory-2026-10-05.json`](reconciliation/model-migration-inventory-2026-10-05.json).
It separates normalized-output publication from tab-level native assumption
mapping, records lifecycle, identity and currency evidence, and proposes small
Portfolio-first batches. The inventory command does not write model state or
evaluate financial formulas. The first import accepted parity-proven `P-GOOGL` and
`W-TOST` inputs; the next reviewed Portfolio DCF sub-batch accepted `P-ASML`,
`P-ISRG` and `P-MA` as canonical revisions. See the
[native model-input import runbook and reconciliation](native-model-input-migration.md).
Future batches still require a tab-specific input/output fixture,
listing/currency validation, immutable revision provenance, and an explicit
decision on legacy versus canonical shareholder-cash-flow IRR semantics.

## Milestones 6.1–6.3: operational coverage, ingestion and native-model evidence

The receipt-based operational audit is in
[`operational-coverage-audit.md`](operational-coverage-audit.md), with its
company-level matrix at
[`reconciliation/operational-coverage-matrix-2026-10-06.json`](reconciliation/operational-coverage-matrix-2026-10-06.json).
Recurring provider ingestion uses the existing adapters and canonical observation
tables; operational run/attempt status is added by Alembic revision
`6e6c2d4e8a19`, chained after `main`'s `8f96876cc9e9` execution-pace migration.
See
[`external-data-operations.md`](external-data-operations.md) for the daily
schedule, provider limits, freshness rules, replay and command interface.

The latest native-model parity receipt is
[`reconciliation/native-model-input-import-2026-10-06.json`](reconciliation/native-model-input-import-2026-10-06.json).
It is explicitly parity-only (`canonical_application_state: NOT_QUERIED`); it does
not replace the earlier applied migration receipts or establish current database
state. See the [model migration reconciliation](native-model-input-migration.md).
