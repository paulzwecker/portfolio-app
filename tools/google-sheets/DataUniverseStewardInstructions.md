# Data & Universe Steward — existing automation instructions

Use the latest `DATA_UNIVERSE_STEWARD` rows in the app-owned **Application Agent Work Feed** as
your work list. Use only the company/listing/provider identity and source timestamps in each
`work_item_json`. Review freshness, ingestion and mapping context against
`docs/external-data-operations.md`. Do not call the local API, invent observations, identity
mappings or dates, or place credentials in the workbook.

Before processing a row, check **Application Agent Work Acknowledgment Inbox** for the exact
`payload.work_identity`. Skip a matching `COMPLETED` receipt. If a prior receipt is unresolved, do
not repeat unchanged research; continue only when new source evidence or an application/operator
update changes the work.

There is no generic factual-observation submission contract. Report what you verified, the exact
source URL and any unresolved mapping/blocker in a `ResearchAgentAcknowledgmentContractV1`
version `1.0.0`. Copy `agent_role`, `work_type`, `work_key`, `work_fingerprint` and
`delivery_channel` verbatim from `payload.work_identity`. Use a unique `external_update_id`, your
real run and actor identity, and the true observed timestamp. Put the complete JSON in
**Research Agent Acknowledgment Contract!A1**, then choose **Portfolio model → Publish agent work
acknowledgment to application inbox**. Use `COMPLETED` only when the specific review is complete;
otherwise use `IN_PROGRESS`, `BLOCKED`, `SOURCE_UNAVAILABLE`, or `UNRESOLVED_REVIEW` with a
specific reason. The application operator reconciles the inbox. Canonical facts still enter only
through supported provider/import pipelines.

Do not author thesis opinions, model assumptions, scores, lifecycle changes, holdings or strategic
targets. See `docs/research-agent-operations.md` for the full contract and role boundaries.
