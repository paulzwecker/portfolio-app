# Canonical company operating metrics and guidance

## Purpose

Company-specific operating KPIs such as Uber Gross Bookings and trips, Intuitive
Surgical procedures and installed systems, MSCI ETF-linked AUM and retention, or
Novo Nordisk product/prescription metrics are factual observations, but they are
not financial-statement facts.

They therefore remain separate from:

- `reported_fundamental_observations`, which intentionally stores normalized
  statement facts;
- `consensus_estimate_observations`, which stores provider-specific analyst
  estimates;
- agent-authored `ResearchForecast` rows;
- accepted financial-model assumptions and projections.

This domain gives those company-specific metrics stable semantic identity and
append-only history without teaching the application to parse arbitrary workbook
cells or narrative research notes.

## Metric definitions

`company_metric_definitions` is the semantic dictionary.

Each definition has a stable `metric_key`, optional company scope, display name,
category, value kind, canonical unit/scale, currency policy, aggregation
semantics, default period/basis, allowed scope dimensions and explicit permissions
for actuals, guidance, consensus and model-driver use.

A metric key is an API/data identity, not display copy. Once observations exist,
its meaning cannot be repurposed. If the economics, unit or semantic definition
changes, create a new metric key. Definitions may be deactivated/deprecated
without deleting historical rows.

Common financial-statement metrics should continue to use their existing canonical
domains. A company metric definition is appropriate when the observation would
otherwise be forced into a generic statement field or hidden in prose.

## KPI observations

`company_metric_observations` stores append-only company facts with:

- canonical company and metric-definition identity;
- absolute economic period start/end and optional fiscal labels;
- exact `NUMERIC(38,12)` value;
- explicit qualifier: `EQ`, `APPROX`, `GT`, `GTE`, `LT`, or `LTE`;
- unit, scale and optional currency;
- basis and structured scope JSON;
- company/source publication time when known;
- source type/reference;
- data-quality state and reason;
- optional supersession link for corrections/restatements;
- database recorded time.

A later correction appends a new row and points at the prior observation.
The prior row is never rewritten.

Qualifiers are semantically important. A source statement such as “more than
8 million prescriptions” must remain numeric value `8` with qualifier `GT`;
it must not become an exact eight-million observation.

## Management guidance

`company_guidance_observations` is deliberately separate from actuals and
consensus.

It supports point/range guidance with lower, midpoint and upper values, explicit
basis, target period, scope, issue/source provenance and an append-only
supersession chain. A withdrawal is represented by a new `WITHDRAWN` observation
that supersedes the earlier guidance; the earlier record is retained.

This allows the Company Explorer to compare, without conflation:

1. reported KPI actuals;
2. active management guidance;
3. selected-provider consensus when semantically compatible;
4. research forecasts;
5. accepted model-driver projections.

## Financial-model driver projections

`financial_model_driver_projections` stores accepted company-specific operating
driver paths under an exact `FinancialModelRevision`.

Each row is keyed to:

- model and accepted revision;
- Bear/Base/Bull scenario;
- metric definition;
- forecast year and absolute period;
- exact value/qualifier/unit/scale/currency/basis/scope;
- explicit model rationale.

Driver rows are append-only because changing a driver path requires a new accepted
model revision. They are not reconstructed from revenue, EBIT or valuation outputs.
If a model does not explicitly underwrite a KPI, no driver row should be invented.

The portable Sheets/model contract will add this payload in a later compatible
contract version. Existing accepted model contracts remain valid.

## Read API

The first API slice is read-only:

- `GET /v1/company-metric-definitions`
- `GET /v1/companies/{company_id}/metric-observations`
- `GET /v1/companies/{company_id}/guidance-observations`
- `GET /v1/financial-models/{model_id}/revisions/{revision_id}/driver-projections`

The observation endpoints preserve exact decimal values as strings and expose
source, unit, basis, scope, qualifier and point-in-time fields. `known_at`
continues the repository rule that historical queries cannot see records that the
application had not yet observed/recorded.

## Google Sheets boundary

The canonical Portfolio workbook contains matching authoring/staging surfaces:

- `Metric Registry`
- `KPI Observations`
- `Guidance Observations`
- `Consensus Observations`
- `Model Driver Forecasts`

Those tabs are not PostgreSQL and are not accepted state. They are the structured
workbench side of the hybrid architecture.

A later proposal-adapter slice will validate the explicit Application inbox
contracts and require deterministic preview plus human acceptance before canonical
writes. Until that adapter exists, no ordinary workbook edit is an accepted
application observation.

## Consensus boundary

The existing `consensus_estimate_observations` domain remains canonical for
provider consensus. Today its supported metrics are Revenue and EPS.

The workbook long-form consensus table can stage broader metrics, but unsupported
metrics stay explicitly unavailable for app import until the canonical consensus
metric enum/API is extended. Providers must never be blended to fill gaps.

## Safety and ownership

- PostgreSQL owns accepted history.
- FastAPI owns validation and canonical reads/writes.
- Sheets is a workbench/proposal producer.
- Agents do not receive generic SQL write access.
- Narrative P-/W-* cells, Research Log and Thesis Watch are not machine-parsed
  into observations.
- No paid data source is required by this domain.
- Missing history stays missing; it is never reconstructed from charts or prose.
