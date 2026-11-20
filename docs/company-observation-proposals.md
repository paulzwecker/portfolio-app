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
   Missing/invalid data is never guessed. SEC-hosted sources or items marked
   `SEC_10Q` also require a unique operator-reviewed company SEC CIK mapping
   matching the source URL. Missing, ambiguous and mismatched crosswalks
   produce an `INVALID` preview, and the mapping identity participates in
   the fingerprint rechecked at acceptance. A direct API proposal cannot
   bypass this guard by avoiding the steward CLI.
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

## Google Sheets is another producer, not another acceptance system

The manual, default-off `POST /v1/google-sheets-observation-sync/check` route
reads **only** the named `Application Observation Inbox` tab using the existing
read-only Sheets API client. It accepts the same three strict JSON batch types
as the direct API endpoint and calls the **same** `submit()` service,
idempotency fingerprint and canonical candidate table.

No separate Sheets-specific canonical acceptance mechanism or shadow model is
created. The reviewer always uses the existing
`/v1/company-observation-proposals/{id}/preview|accept|reject` endpoints, and
only a reviewer role can accept. This bridge never edits workbook cells,
previews, accepts or rejects proposals. No automatic schedule is enabled.

See [Sheets observation inbox](google-sheets-observation-inbox.md) for the
five-column chunk format, activation prerequisites and response semantics.

Metric-definition proposal batches may explicitly set
`model_driver_allowed: true` when a company-specific metric is intended for
accepted financial-model operating paths. It defaults to `false`. This
permission is still subject to independent human proposal preview/acceptance;
it is not inferred from an existing KPI or activated by importing an agent
forecast. Provider consensus remains independently disabled.

## Company Explorer reviewer workflow

The Operating KPIs tab provides a human review panel for the same canonical
observation proposal table used by API agents and the Sheets inbox. The
server-only Next.js API proxy forwards reviewer requests with
`OBSERVATION_PROPOSAL_REVIEWER_TOKEN`, never exposing the token to the browser.
Only exact `GET /company-observation-proposals` and reviewer
`POST /{id}/preview|accept|reject` paths are allowlisted. Browser submission
using the reviewer role is intentionally **not** supported.

The reviewer sees proposal source and metrics, runs a deterministic preview,
provides a decision note and confirms accept/reject with a second button press.
The app updates its accepted operating KPIs only after the API reports actual
acceptance. The API still requires `OBSERVATION_ACCEPTANCE_ENABLED` for canonical
changes and owner-approved production write authorization.

When reviewer credentials or the feature are disabled, the review queue is
unavailable rather than silently granting broader API access. No credentials
are stored in public Git or sent to browser code. This feature introduces no
new review role, database state or scheduling.
