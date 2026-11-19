# Company observation proposals v1

The read-only company context supplies agent eyes. This slice provides typed,
review-gated agent hands for **metric definitions**, **KPI actuals**, and **company
management guidance**. There is no new generic workflow engine or data provider.

## Contracts and workflow

`POST /v1/company-observation-proposals` accepts exactly one of:
- `MetricDefinitionBatchV1`
- `KPIObservationBatchV1`
- `GuidanceObservationBatchV1`

All use `contract_version: 1.0.0`, a canonical `company_id`, a stable
`external_batch_id`, a dated authoring timestamp and rationale, and 1–20
strictly typed rows. Extra fields are rejected. Numeric values and scales must
be exact decimal strings, never floating-point inputs. Each observation carries its own HTTPS source. Publication timestamps are
accepted only when known exactly; date-only disclosures remain null rather
than inventing a time. Definition proposals are company-scoped
and deliberately exclude normalized statement facts.

The storage table `company_observation_proposals` is a review inbox. Accepted
KPI and guidance observations remain in their existing append-only canonical
tables; accepted metric definitions retain immutable semantics.

1. Agent submits a batch with `X-Observation-Proposal-Token`. Exact replay of
   producer + external batch ID and content returns `replayed=true`; a different
   payload using the same ID conflicts.
2. Reviewer lists candidates, then requests
   `POST /v1/company-observation-proposals/{id}/preview`.
   Deterministic checks verify metric permissions, company ownership, exact
   unit/scale/currency, fiscal period, external identity and correction lineage.
   Missing/invalid data is never guessed.
3. Reviewer accepts only a `READY` batch using the exact
   `preview_fingerprint` and a decision note. Acceptance rechecks canonical
   dependencies under a company row lock and creates all rows in one transaction.
   Stale previews return `PREVIEW_CHANGED` without writing accepted records.
4. Reviewer may reject with a reason. Final decisions are immutable. Agent can
   inspect its own submission; only reviewers can list, preview, accept, reject.

All source corrections use explicit `supersedes_observation_id` or
`supersedes_guidance_id`, never UPDATE/DELETE. A same-period/scope KPI or
guidance submission without supersession conflicts rather than silently
overwriting a fact. Management guidance can target future periods.

## Access and activation

This is **disabled by default**, including for local development.
`OBSERVATION_PROPOSALS_ENABLED=true` enables the dedicated proposal endpoints;
`OBSERVATION_ACCEPTANCE_ENABLED=true` separately allows canonical acceptance.
Configure distinct long `OBSERVATION_PROPOSAL_AGENT_TOKEN`/`_ID` and
`OBSERVATION_PROPOSAL_REVIEWER_TOKEN`/`_ID` pairs (min. 32-character tokens)
outside Git. Neither credential is a general API token or a model-proposal token.
The proxy middleware only exempts this exact endpoint namespace; dedicated
credentials are required in every environment.

On production targets, mutations also require the existing
`DATABASE_PRODUCTION_WRITES_AUTHORIZED` owner gate. **This PR does not authorize
or activate production writes**, run migrations, schedule sources or accept real
observations. Google Sheets is not parsed by this API; it will become a producer
through a later explicit inbox adapter.

The generated OpenAPI/TS contract is authoritative for payload structures.
