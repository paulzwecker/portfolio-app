# Agent Model Revision Proposals v1

## Purpose

`FinancialModelRevisionProposalV1` is the application API contract for external
agents that propose changes to an already accepted canonical model. It is a
producer-neutral JSON envelope with a strict method discriminator. Agent
payloads contain inputs only; the API recalculates outputs with the existing
native UFCF DCF, owner-cash-flow, or residual-income engine. The API does not
create models or assign identities.

Google Sheets packages and agent proposals remain distinct producer paths.
Existing Sheets inbox imports are not reclassified as agent proposals. The
accepted model revision remains canonical, immutable state; the proposal row is
an auditable review candidate.

## Version and identity contract

- `contract_type`: `FinancialModelRevisionProposalV1`
- `contract_version`: `1.0.0`
- `model_id`, `company_id`, and `valuation_listing_id`: existing canonical UUIDs
- `base_revision_id` and `base_revision_number`: exact accepted revision the
  agent read
- `model_currency` and `methodology_version`: must match the canonical model
- `external_revision_id`: stable producer revision identity, unique per model
  and configured producer
- `authored_at` and `effective_at`: timezone-aware, not in the future
- `source_reference`: HTTPS source URL
- `rationale`: required explanation
- `supporting_evidence`: at least one unique canonical research or thesis
  evidence reference; the API resolves and verifies company/security scope
- `method`: exactly one method discriminator and its native typed inputs

Supported method discriminators and input types:

| `method.methodology`       | `method.inputs`                |
| -------------------------- | ------------------------------ |
| `UFCF_DCF_10Y_FADE`        | Existing `DcfCalculationInput` |
| `OWNER_CASH_FLOW_10Y`      | Existing `OwnerCashFlowInput`  |
| `RESIDUAL_INCOME_10Y_FADE` | Existing `ResidualIncomeInput` |

Decimal inputs must use decimal strings. Existing native schemas enforce
scenario completeness, Bear/Base/Bull identities, exact probability totals,
units/ranges, and method-specific assumptions. Unknown fields—including
agent-supplied outputs, author IDs, reviewer IDs, or approval flags—are rejected.
The producer and author identities are taken from server configuration, never
from the submitted JSON.

The actual JSON Schema is published by FastAPI OpenAPI at `/openapi.json` under
`FinancialModelRevisionProposalV1`; this document intentionally does not copy
the full native financial input schemas.

## Authentication

Set the following API environment variables outside Git:

- `MODEL_PROPOSAL_AGENT_TOKEN` and `MODEL_PROPOSAL_AGENT_ID`
- `MODEL_PROPOSAL_REVIEWER_TOKEN` and `MODEL_PROPOSAL_REVIEWER_ID`

Each token must contain at least 32 characters. Tokens and identities must be
distinct. The variables are paired; a partial pair prevents settings from
loading. Missing proposal-role configuration fails closed with HTTP 503. A bad
role token returns HTTP 401. The role token is sent as
`X-Model-Proposal-Token` and is checked in every environment. The proposal API
namespace uses these dedicated role tokens and does not require sending the
broader `API_ACCESS_TOKEN`; all other remote API routes remain behind that
separate application/proxy credential. Deployments still require
`API_ACCESS_TOKEN` as a server configuration setting. The proposal token grants
no access to other API routes or privileges beyond its configured role. Local
development remains a trusted boundary for the rest of the API, as before.

Agents can submit proposals and inspect their own status. Reviewers can list,
inspect, preview, accept, or reject proposals. The configured agent and reviewer
identities cannot be equal. No endpoint gives agents database access.

## API workflow

1. The agent obtains the current model identity, accepted revision ID/number,
   currency, method version, and canonical evidence IDs from read APIs.
2. It submits a complete `FinancialModelRevisionProposalV1` to
   `POST /v1/model-revision-proposals` with the agent token.
3. Exact replay of the same producer revision and body returns the existing
   proposal with `replayed: true`. Reusing the external revision ID with
   changed content returns HTTP 409.
4. A stale base is retained with status `CONFLICT`. Concurrent proposals from
   the same base are surfaced by their proposal IDs; only one can ultimately
   be accepted because acceptance locks and rechecks the canonical model.
5. A reviewer lists and inspects candidates, then calls
   `POST /v1/model-revision-proposals/{id}/preview`. The response includes
   assumption and output differences, current and proposed outputs, and the
   server-generated `preview_fingerprint`.
6. To accept, the reviewer explicitly posts that fingerprint and a decision
   note to `POST /v1/model-revision-proposals/{id}/accept`. The service
   recalculates while holding the model lock. If quote-derived or calculated
   outputs differ from the reviewed preview, it returns `PREVIEW_CHANGED` and
   requires another preview and decision. Successful acceptance appends an
   immutable revision and persists linked evidence in the same transaction.
7. To reject, the reviewer posts a required decision note to
   `POST /v1/model-revision-proposals/{id}/reject`. Rejection is final.
8. Either role may read an individual proposal status, but an agent can only
   read proposals created by its configured identity. Proposal listing is
   reviewer-only.

Proposal statuses are `PENDING`, `READY`, `CONFLICT`, `INVALID`, `ACCEPTED`,
and `REJECTED`. Final decisions cannot be changed. An accepted canonical model
revision stores the proposal author, authored timestamp, HTTPS source reference,
rationale, external evidence links, producer source label, and a unique internal
source-revision identity. Reviewer identity, decision note, accepted revision
link, and review time remain on the retained proposal row.

## Migration from a Google Sheets research agent

An existing agent can move to this API without changing Sheets or the native
model engines. It should read the accepted canonical base and evidence IDs from
the app, map its method-specific input fields to the corresponding native input
schema, assign a stable external revision ID, and submit the JSON proposal.
The workbook may remain a research workspace, but publication to this API is a
separate explicit action. Do not place API tokens in a workbook or expose the
application database URL to the agent. Do not automate reviewer actions.

## Operational boundary

The migration `9f2a6d4c81b7` adds only the proposal inbox table and indexes.
Local schema integration tests use the repository's isolated
`TEST_DATABASE_URL` schema fixture. This feature has not been activated on
Neon, deployed, or authorized for unattended review. Environments whose schema
has not applied this migration fail closed through the existing database/API
readiness behavior.
