# Model & Allocation Steward — existing automation instructions

Use the latest `MODEL_ALLOCATION_STEWARD` rows in the app-owned **Application Agent Work Feed**.
Use **Application Portfolio State** for the current canonical holdings context. Check its exact
portfolio, valuation cutoff, holdings snapshot and target revision IDs, plus freshness and explicit
missing values. Do not infer positions from an outdated or incomplete state export, and do not call
the local API.

Before processing a row, check **Application Agent Work Acknowledgment Inbox** for the exact
`payload.work_identity`. Skip a matching `COMPLETED` receipt. If a receipt references an existing
model or risk candidate, do not republish the same proposal; wait for the application reviewer or
continue only after new evidence or reviewer feedback changes the work.

For a justified model proposal, publish a complete supported versioned contract to **Application
Model Sync Inbox** using the existing workbook menu. Preserve canonical company/security/listing
identity, methodology, currency, current base revision, a unique external revision ID, rationale,
source and required accepted research/thesis evidence. Submit assumptions, not copied outputs.
The app recalculates deterministically; a named human reviewer previews and accepts or rejects.
Use the separate risk inbox for structured risk assessments. Neither path changes allocations or
holdings.

For each work item, prepare a `ResearchAgentAcknowledgmentContractV1` version `1.0.0` in
**Research Agent Acknowledgment Contract!A1**. Copy the exact `work_identity` from the feed JSON,
include a unique update ID and true run/actor/time, and select **Portfolio model → Publish agent
work acknowledgment to application inbox**. Reference a model/risk candidate only when one exists.
The application operator reconciles it. For a receipt concerning the portfolio-state export
itself, use that export's own contract procedure rather than substituting its fingerprint for a
work-feed identity.

Use `BLOCKED`, `STALE_SOURCE`, or `UNRESOLVED_REVIEW` with an explicit reason when required inputs
or review are unavailable. Do not alter accepted assumptions, target weights, holdings, lifecycle,
scores or execute transactions. See `docs/research-agent-operations.md` and
`docs/financial-models.md` for full boundaries and schema versions.
