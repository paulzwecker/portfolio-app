# Workbook agent instructions: research and thesis publication

Keep research work and publication separate. A draft that has not passed your
research review must not be published. When ready, publish a complete version
`1.1.0` `ResearchRevisionContractV1` in `Research Revision Contract!A1`, or a
complete `InvestmentThesisContractV1` in `Investment Thesis Contract!A1`. Version
`1.0.0` remains valid for proposals with no trigger link. Use
the canonical company UUID (and security UUID only when security-scoped), the
current accepted revision ID as `supersedes_revision_id`, a new unique
`external_revision_id`, author/source identity, rationale, and the true
observation timestamp. The application contract is the schema authority; do not
rename fields or infer missing history.

Before publication, include source evidence in the contract: at least one
`evidence` item for research, and evidence on at least one thesis claim. Keep
agent forecasts separate from third-party consensus and from accepted model
assumptions. Thesis claims are opinions supported or contradicted by their
linked evidence, not reported facts.

Use **Portfolio model → Publish research forecast to application inbox** or
**Publish investment thesis to application inbox**. These actions append to the
separate `Application Research Inbox` or `Application Thesis Inbox`; they do not
replace earlier publications. An exact replay is ignored. A changed payload
must use a new external revision ID. Then wait for an application reviewer to
check, preview, and explicitly accept or reject the proposal. Do not treat an
inbox publication as accepted research. If the application reports a stale base,
re-export/re-read the current canonical revision and deliberately rebase your
proposal before publishing a new external revision.

The application does not infer research from arbitrary workbook edits and does
not automatically publish or accept proposals.

## Delivery acknowledgment

The external operating contract is `ResearchAgentWorkContractV1` and
`ResearchAgentAcknowledgmentContractV1`, both version `1.0.0`; canonical field
definitions are in `docs/research-agent-operations.md` and the exported OpenAPI
contract. For work received through `Application Agent Work Feed`, copy the complete
`payload.work_identity` exactly. For a Sentinel trigger, inspect `payload.trigger`
and `payload.context` in that same work item; the connected workbook currently has
no separate `Application Thesis Watch Feed` tab. Do not replace the work key or
fingerprint with a trigger ID or context fingerprint.

Use **Portfolio model → Publish agent work acknowledgment to application inbox**
to append the complete acknowledgment to `Application Agent Work Acknowledgment
Inbox`. Use a new unique `external_update_id` for a changed status; exact replays
remain idempotent. An acknowledgment records receipt or completion only. It does
not accept a research, thesis, risk or model candidate and does not complete a
Research Queue task; those remain separate reviewer actions.

Before processing a feed row again, check the acknowledgment inbox for a receipt
with the same role, work type, work key, fingerprint and channel. Skip matching
`COMPLETED` work. If a receipt references an existing proposal, do not republish
the same content while it awaits review; use a new update ID only when the work
status or evidence has materially changed.

Role-specific instructions are in `DataUniverseStewardInstructions.md`,
`PortfolioThesisSentinelInstructions.md`, and
`ModelAllocationStewardInstructions.md`.

For the three existing off-host automations, use **Application Agent Work Feed** for bounded
role-specific assignments. The local application operator manually selects the role and publishes
up to ten items from `/model-sync`; the feed is append-only, includes an explicit version and
content fingerprint, and records delivery only after read-back. Read each row's `work_item_json`
and copy `payload.work_identity` exactly into an acknowledgment. Feed delivery does not prove the
agent read or completed the work. No automation should call the local API: current API operations
do not require user authentication and the development service listens on loopback. Use the
existing workbook inboxes and menu actions for off-host proposals and receipts.

## Sentinel trigger context

The operator publishes bounded role work to `Application Agent Work Feed`. For
Sentinel trigger rows, `work_item_json.payload.trigger` carries trigger identity
and source times, while `work_item_json.payload.context` carries exact company,
security and listing identities, current accepted research/thesis revisions,
model revisions and outputs, linked evidence, and prior accepted publications.
Use the work item's `payload.work_identity` for acknowledgment. Do not require or
read a separate Thesis Watch tab unless it has been deliberately provisioned.

Classify each investigated development using only `NOISE`, `INCREMENTAL`, or
`MAJOR-STRUCTURAL`, with a short rationale. For a meaningful research or thesis
proposal, include the trigger in `trigger_references` in the complete version
`1.1.0` contract, with its classification and rationale. Cite independent source
evidence as usual; a trigger is a prompt, not evidence that the development is
true. A `NOISE` item should not create an empty thesis/model revision; leave it for
the application reviewer to close as noise. If evidence justifies model changes,
reference the accepted research or thesis revision in the model contract's
supporting evidence. Do not modify holdings, targets, lifecycle, scores, or accepted
model state. Publication only creates a candidate. A human reviewer decides
whether to accept or reject it.
