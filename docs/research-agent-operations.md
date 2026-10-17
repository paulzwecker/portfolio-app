# Research Agent Operations Contract

Version `1.0.0` defines role-specific work delivery and append-only receipts for the three
external research automations. The API schema is the contract authority; its generated form is
`packages/contracts/openapi.json` and the interactive schema is available at `/docs`.

## Role boundaries

| Role                        | Owns                                                                                             | Does not own                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| `DATA_UNIVERSE_STEWARD`     | Provider freshness, identity/mapping issues, factual ingestion status and explicit data blockers | Thesis judgments, model assumptions, lifecycle, holdings or targets       |
| `PORTFOLIO_THESIS_SENTINEL` | New research triggers, evidence review, thesis/research proposals and review completion          | Automatic model acceptance, scores, lifecycle, holdings or targets        |
| `MODEL_ALLOCATION_STEWARD`  | Model integrity/re-underwriting, current portfolio context and reviewed allocation questions     | Automatic assumption acceptance, target changes, holdings or transactions |

## Work retrieval and transport

Call `POST /v1/research-agent-operations/{agent_role}/work` with a
`ResearchAgentWorkRequest` (`as_of`, `limit`, `offset`, and optional `portfolio_id`). The response
is `ResearchAgentWorkContractV1` version `1.0.0`. It contains bounded canonical work payloads,
stable work keys and fingerprints, a delivery ID, and status from the latest receipt. A successful
API response is recorded as delivery. Repeated retrieval of unchanged work reuses its delivery
receipt; completed unchanged work is omitted. Refresh triggers first with
`POST /v1/research-triggers/refresh` when the Sentinel needs newly detected source events.

The direct work, proposal, status and acknowledgment APIs do not currently require user
authentication. They are for the trusted local application boundary only; the development API
binds to loopback and must not be exposed to an external ChatGPT automation. For the three
off-host automations, an operator manually publishes bounded work from `/model-sync` to the fixed
`Application Agent Work Feed` tab. `POST
/v1/google-sheets-agent-operations/{agent_role}/work/publish` accepts only the three role
constants, at most ten items, and no caller-supplied tab or range. It appends a version `1.0.0`
manifest and immutable work rows, then records a `GOOGLE_SHEETS` delivery receipt only after
read-back verification. Exact replays add no rows. This operation is manual and does not create
or change an agent schedule.

Each work row contains a complete `ResearchAgentWorkItemRead` JSON object in `work_item_json`.
Use `payload.work_identity` and `payload.acknowledgment_contract` verbatim when reporting
progress. The feed is append-only and pages are bounded; a later page is requested by the
operator with an offset. `current_status` is the state captured at feed publication time; later
acknowledgments are separate append-only contracts in the acknowledgment inbox. Before repeating
unchanged work, check for a matching receipt by role, work type, key, fingerprint and channel. Skip
`COMPLETED`; if a receipt references a proposal, do not republish the same proposal while it awaits
review. A published feed is a delivery, not proof the automation read or processed it.

Use `GET /v1/research-agent-operations/events` to inspect delivery, failure and receipt history.
The query accepts `agent_role`, `work_key`, and `limit`.
Check a proposal's current review state at
`GET /v1/research-agent-operations/proposals/{proposal_domain}/{candidate_id}` where the domain is
`MODEL`, `RESEARCH`, `THESIS`, or `RISK`. This returns current status, conflict/check reason,
reviewer decision and any accepted revision reference.

## Acknowledgment and completion

Publish a `ResearchAgentAcknowledgmentContractV1` version `1.0.0` to
`POST /v1/research-agent-operations/acknowledgments`, or publish it through the fixed Google
Sheets inbox `Application Agent Work Acknowledgment Inbox` and run
`POST /v1/google-sheets-agent-operations/check`. The Sheet publisher appends the contract in the
same five-column chunked format as the other application inboxes. It never edits older receipts.

Every receipt identifies the role, work type/key/fingerprint, delivery channel, external update
ID, agent run, actor, status and observed time. `BLOCKED`, `SOURCE_UNAVAILABLE`, `STALE_SOURCE`,
and `UNRESOLVED_REVIEW` require a reason. Proposal references may identify a model, research,
thesis or risk candidate. Exact replay of an `external_update_id` is idempotent; reusing it with
changed content conflicts. A receipt based on an older delivery is recorded as `STALE_SOURCE`
when a newer work fingerprint has already been delivered.

Acknowledgment is not Research Queue completion and does not accept a proposal. `COMPLETED` records
that the agent finished its assigned review; an analyst still closes a Research Queue task through
the local `/v1/research-queue/{task_id}/complete` route/UI. Use the existing Google Sheets candidate
preview/accept/reject endpoints for human proposal decisions. Proposal state is returned as context
when an acknowledgment references a known candidate.

Delivery failures are recorded with `POST /v1/research-agent-operations/delivery-failures` and a
unique `attempt_id`; retry success is a separate delivery event. Google Sheets publishers record
success only after write/read-back verification and persist failed publication attempts without
turning those failures into successful delivery receipts.

## Existing source and proposal interfaces

- Trigger list and context: `GET /v1/research-triggers`,
  `GET /v1/research-triggers/{trigger_id}/context`.
- Research queue and history: `GET /v1/research-queue`,
  `GET /v1/research-queue/history`.
- Current portfolio state: `GET /v1/portfolios/{portfolio_id}/overview`.
- Ingestion freshness: included in Data & Universe Steward work items and available in the
  operational ingestion status report.
- Model proposals: `POST /v1/google-sheets-sync/check`, then candidate list, preview and explicit
  accept/reject routes.
- Research/thesis proposals: `POST /v1/google-sheets-research-sync/check`, then candidate list,
  preview and explicit accept/reject routes.
- Risk proposals: `POST /v1/google-sheets-risk-sync/check`, then candidate list, preview and
  explicit accept/reject routes.
- Unified proposal status: `GET /v1/research-agent-operations/proposals/{domain}/{candidate_id}`.
- Existing authoring contracts remain `FinancialModelContractV1` / portable model v2,
  `ResearchRevisionContractV1` 1.0.0 or 1.1.0, `InvestmentThesisContractV1` 1.0.0 or 1.1.0, and
  `RiskAssessmentContractV1` 1.0.0. Their domain validators remain authoritative.

## Cadence and operation

Data checks follow source publication and the documented ingestion cadence; thesis work is
triggered by new material evidence; model and allocation reviews use the existing research queue
and routine review cadence; strategic architecture remains a longer-interval investor review.
The application does not create, edit or activate ChatGPT schedules. In local development, the
recurring operations worker refreshes triggers/queue and publishes bounded role-specific work to
the fixed workbook feed hourly, and polls the explicitly configured proposal/acknowledgment
inboxes at `GOOGLE_SHEETS_POLL_SECONDS` (hourly by default). External ChatGPT runs still follow
their existing schedules. Acceptance and queue completion remain explicit reviewer actions. See
[`recurring-operations.md`](recurring-operations.md) for activation and failure behavior.

Off-host agents use the workbook as transport: read the app-owned work feed and its
`work_item_json.payload.context`; use Application Portfolio State for the separately published
snapshot; publish complete research, thesis, model or risk contracts only through their matching
versioned inbox and bound Apps Script menu; publish acknowledgments through the acknowledgment
inbox. In the currently connected workbook, the separate Thesis Watch Feed tab is not provisioned;
trigger and context are included in Sentinel work items. Keep application credentials outside the
workbook and repository. Data Steward findings can be reported as acknowledgments with source URL
and reason, but canonical factual observations still require a supported provider/import pipeline;
there is no general agent-authored fact inbox. Direct APIs are only an option after a separately
approved authenticated gateway is deployed.
