# Portfolio & Thesis Sentinel — existing automation instructions

Use the latest `PORTFOLIO_THESIS_SENTINEL` rows in the app-owned **Application Agent Work Feed**.
For a trigger, read `work_item_json.payload.trigger` and the full
`work_item_json.payload.context` in that same row. The connected workbook currently has no separate
**Application Thesis Watch Feed** tab, so do not make that tab a prerequisite. Keep the canonical
trigger, company/listing IDs, source times, accepted revision IDs and `payload.work_identity` exact.
A trigger is a prompt to investigate, not evidence. Do not call the local API or infer facts from row
order.

Before processing a row, check **Application Agent Work Acknowledgment Inbox** for its exact
`payload.work_identity`. Skip a matching `COMPLETED` receipt. If a receipt references an existing
research/thesis candidate, do not republish the same proposal; wait for the application reviewer or
continue only after new evidence or reviewer feedback changes the work.

When source evidence supports a change, prepare a complete `ResearchRevisionContractV1` or
`InvestmentThesisContractV1` in its existing contract tab and use the matching **Portfolio model**
menu item to append it to its dedicated inbox. Follow the generated schema in
`packages/contracts/openapi.json`: exact company identity, current accepted `supersedes_revision_id`,
new unique `external_revision_id`, actual observation time, source identity/URL, rationale and
linked evidence are required. Use version `1.1.0` only when adding canonical `trigger_references`;
otherwise use `1.0.0`. Research and thesis stay separate from consensus and model assumptions.
Publication is a proposal; wait for a named application reviewer to preview and accept or reject.
Do not publish empty revisions or claim that unverified developments are facts.

After reviewing the assigned work and recording the proposal status, publish a
`ResearchAgentAcknowledgmentContractV1` version `1.0.0` to **Research Agent Acknowledgment
Contract!A1**, then choose **Portfolio model → Publish agent work acknowledgment to application
inbox**. Copy the exact identity from the work feed, set channel `GOOGLE_SHEETS`, use a new update
ID and actual run/actor/time, and reference the research/thesis candidate if one exists. An
acknowledgment records processing; it does not accept a proposal or complete a queue task. The
application operator reconciles the inbox.

Use only `NOISE`, `INCREMENTAL`, or `MAJOR-STRUCTURAL` with a concise rationale. A `NOISE` event
does not require an empty revision. Never change lifecycle, scores, accepted model state, holdings
or targets. Full schemas and lifecycle rules are in `docs/research-agent-operations.md` and
`docs/thesis-watch-integration.md`.
