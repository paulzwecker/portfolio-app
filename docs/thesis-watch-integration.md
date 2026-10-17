# Thesis Watch integration

## Ownership

The external research agent investigates sources and proposes interpretations. The
application owns canonical accepted research, thesis and model revisions, their
deterministic calculations, and reviewer decisions. A trigger is a research prompt;
it is not an investment conclusion. Nothing in this workflow changes lifecycle,
quality scores, targets, holdings or Execution Pace.

## Trigger-to-review workflow

1. A reviewer or operator manually refreshes source triggers with
   `POST /v1/research-triggers/refresh?lookback_days=30`.
2. The external workflow receives a bounded page from the application-owned
   **Application Thesis Watch Feed** tab. A reviewer publishes at most 50 OPEN
   triggers per action and can advance the offset for additional pages. The
   publisher appends unseen trigger/context fingerprints; exact repeats add no
   rows, and changed accepted context is appended as a new row. Prior rows are
   preserved and verified by fingerprint and read-back. The API alternative is
   `GET /v1/research-triggers?processing_state=OPEN&limit=50&offset=0`; GET does
   not run a scan.
3. Each feed row contains trigger metadata and a compact `context_json` snapshot.
   It returns exact company, security and listing identities; source times and
   captured source details; the current accepted research and thesis revision per
   stream; current model revisions, normalized outputs and their linked evidence;
   and any prior accepted publication linked to the trigger. Full revision
   history remains in Company Explorer and the API. The trigger's original
   effective, observed, recorded and detected times remain separate. Trusted API
   clients can retrieve fresh context from
   `GET /v1/research-triggers/{trigger_id}/context`.
4. The external agent checks primary or otherwise permitted sources, separates
   reported facts from interpretation, and retains the existing event classification:
   `NOISE`, `INCREMENTAL`, or `MAJOR-STRUCTURAL`. This classification is about the
   development under review; it is not a quality score, thesis outcome or action
   instruction.
5. For a meaningful research or thesis update, publish a complete
   `ResearchRevisionContractV1` or `InvestmentThesisContractV1` version `1.1.0` to
   the existing Application Research or Application Thesis Inbox. The contract
   includes `trigger_references`, each with the canonical `trigger_id`,
   classification and classification rationale. It also includes the ordinary
   complete revision snapshot, current `supersedes_revision_id`, source URL,
   observation timestamp and supporting evidence. Trigger-linked submissions need
   at least one source evidence item; thesis submissions need evidence on a claim.
6. The app captures the contract, validates identity, source evidence and trigger
   time, then previews it in `/model-sync`. A named reviewer explicitly accepts or
   rejects it. Accepted trigger links are immutable and visible in Company Explorer.
   An unaccepted proposal appears in Attention Center until it receives a final
   review decision.
7. If accepted evidence justifies a model proposal, the agent uses the existing
   method-specific model contract, references the published thesis revision or
   claim in `supporting_evidence`, and publishes through Application Model Sync
   Inbox. The deterministic engine recalculates it. The reviewer sees the trigger
   classification and source chain beside the output diff and explicitly accepts
   or rejects the model revision.

For `NOISE`, do not create an empty thesis or model revision. A reviewer can record
the classification while completing the Research Trigger task in the Research Queue;
that completion is immutable and closes only that source-derived review condition.
For `INCREMENTAL` or `MAJOR-STRUCTURAL` updates, classification and rationale are
retained with the accepted research/thesis revision that cites the trigger.

## Conflict, replay and retry behavior

The v1.1 contracts remain additive to the existing v1.0.0 contract. Exact replays
are idempotent. Reusing an external revision ID with changed content conflicts.
The trigger must belong to the same company, and the research observation cannot
predate the trigger context supplied by the application. A stale research/thesis
base returns conflict; a stale model base is rejected by the existing Model Sync
preview. Re-read the current context, deliberately rebase, and publish a new
external revision ID. Never edit an already published inbox block.

Google Sheets sync runs and captured candidate contracts remain in review history.
Invalid, conflicting or unavailable runs retain their status and error details.
Corrected payloads are published as a new block and revision ID; a failed attempt
is not treated as accepted. The application never auto-accepts research or model
changes and does not run an agent, call an LLM, or schedule Thesis Watch polling.

## Access boundary

The trigger list and context API operations are read-only. Normal app service
credentials remain behind the existing private local/reverse-proxy boundary. The
manual workbook publisher provides the external agent a bounded handoff without
exposing the local API. It writes only `Application Thesis Watch Feed`, refuses an
unowned or modified tab, and never writes research or model proposals. Sheets remains
the transport; normal application use does not depend on it.

## Role delivery receipts

Milestone 8C adds `ResearchAgentWorkContractV1` and
`ResearchAgentAcknowledgmentContractV1` version `1.0.0`. The feed publisher records a
`GOOGLE_SHEETS` delivery receipt only after its table passes read-back verification.
For a feed row, the receipt identity uses the trigger ID and the unprefixed SHA-256
from `context_fingerprint`. The agent appends its acknowledgment contract to
`Application Agent Work Acknowledgment Inbox`; the operator manually imports it with
`POST /v1/google-sheets-agent-operations/check`. A receipt records delivery and
agent-reported status separately from trigger capture, proposal review, and queue
completion. See [`research-agent-operations.md`](research-agent-operations.md) for
the role APIs, replay behavior and status meanings.
