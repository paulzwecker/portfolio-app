# Google Sheets model authoring adapter

This folder provides a reviewable Google Sheets authoring adapter for canonical
model contracts: `FinancialModelContractV1` (`1.0.0`–`1.2.0`) for DCF and
`AdditionalModelPortableContractV2` (`2.0.0`–`2.1.0`) for owner-cash-flow and residual-income
models. PostgreSQL remains canonical. The bound script does not call the application
or recalculate outputs. It edits tabs only in the currently open workbook, serializes
the method-specific assumptions to JSON, and its explicit publish action appends that
JSON to the same workbook's inbox. The application reads the inbox through its
read-only Sheets API integration and requires human review before acceptance.

The existing ChatGPT research automations use the app-owned **Application Agent Work Feed** for
bounded role work and its nested JSON for trigger/company context. **Application Portfolio State**
supplies a separate read-only portfolio snapshot. An operator manually publishes the Agent Work
Feed at `/model-sync`; its versioned rows are append-only and a delivery receipt is recorded only
after read-back. The connected workbook currently has no separate **Application Thesis Watch Feed**
tab, and external role instructions do not require it. The three role-specific instruction files
provide copy-ready operating text. Off-host automations must use the workbook inboxes and must not
call the local API or receive its credentials. Research, thesis, risk and model proposals each keep
their separate contract and require explicit review.

## Set up a workbook

1. In the Company Explorer's external-authoring section, select **Export Sheets
   contract** for an accepted DCF, owner-cash-flow or residual-income model.
2. Create or open a Google Sheet.
3. Ensure your user account has edit access to the workbook. Open **Extensions → Apps Script**, paste
   [`CanonicalModelContract.gs`](CanonicalModelContract.gs), save, then reload the
   spreadsheet. The script needs only the active spreadsheet's edit permission.
4. Choose **Portfolio model → Load exported contract JSON** and paste the downloaded
   file's contents into the dialog. The adapter stores a compact copy in
   `Contract!A1` without splitting its lines across cells.
5. Use **Portfolio model → Build editable input tabs**. The adapter creates
   `Base Inputs`, `Scenario Inputs`, and `Revision`; it also creates `Year Inputs`
   for owner-cash-flow models (30 scenario/year rows). Residual-income models have
   no editable year table because the application derives the ten-year ROE fade
   from starting and mature ROE. The `Contract` sheet retains the exported base.
6. Edit only the candidate input and revision cells. Keep decimal values in plain
   decimal notation and leave them as text; do not add formulas or currency
   conversions. The sheet stores assumptions, not accepted calculations.
7. Use **Portfolio model → Write edits back to contract JSON**.
8. To keep the file handoff, copy the updated JSON from `Contract!A1` and preview it
   in the matching Company Explorer model. For direct sync, choose **Portfolio
   model → Publish candidate to application inbox** instead. It appends a chunked
   contract record to `Application Model Sync Inbox` without changing older entries.
9. In `/model-sync`, check for changes, preview the candidate and inspect assumption
   and recalculated-output differences. A named reviewer must explicitly accept a
   `READY` candidate; the app never auto-accepts a model change.

For `1.2.0` and `2.1.0`, first publish the supporting forecast, research revision or
thesis development through its canonical research contract. Then fill the model
contract's `proposal` block (`author_id`, `authored_at`, `source_reference`) and
`supporting_evidence` list with canonical UUID references and a relationship
(`SUPPORTS`, `CONTRADICTS` or `CONTEXT`). Cite only records for the model's company
and, when security-scoped, the same security. The proposal rationale explains the
agent's interpretation; the cited canonical records remain distinct observations.
The application rejects missing, unpublished, unknown or mismatched evidence before
it offers the candidate for acceptance. The preview presents evidence beside the
deterministic model diffs, and accepted model history retains those references and
the proposal author. A human reviewer still has to compare and accept the change.

The API rejects invalid ranges, invalid scenario probability totals, malformed years,
missing rationale for changed assumptions and contracts based on a superseded
application revision. DCF v1 also checks the exported base-calculation snapshot. A
conflict requires a fresh export and deliberate reapplication of external edits.
Re-importing the exact accepted JSON is idempotent. After acceptance, export again
before another Sheets edit so the next candidate has a new external revision
identity.

The live reader service account has Viewer access only; the bound Apps Script runs
under the spreadsheet user's separately granted edit permission. The live reader
configuration and least-privilege service-account setup are in
[`docs/google-sheets-sync.md`](../../docs/google-sheets-sync.md). Apps Script and the
Google connection remain optional for normal application use. The application is
usable without Google accounts, Apps Script permissions, a live Sheets connection
or network access to Google services.

## Risk assessment publication

Keep the agent's risk research separate from ongoing workbook research and all
numeric application scores. Prepare a complete `RiskAssessmentContractV1` version
`1.0.0` JSON object in `Risk Assessment Contract!A1` only after reviewing the latest
**Application Portfolio State** publication. The contract must copy its exact
portfolio ID, state fingerprint, holdings snapshot ID, target revision ID (use JSON
`null` if there is no accepted target), portfolio-state contract version and
valuation cutoff. Provide stable stream and external revision IDs, author/source
identity, authored/publication timestamps, coverage, summary and rationale.

Use **Portfolio model → Publish risk assessment to application inbox**. The adapter
appends to the separate **Application Risk Assessment Inbox** in the same
five-column chunk format as the model inbox. It does not edit model contracts or
portfolio state. Exact replay is ignored. Reusing an external revision ID with
different or incomplete content is rejected; publish a new external revision ID
that supersedes the last accepted risk revision instead.

Each finding needs a unique stable key, scope, category, severity, confidence,
status, change direction, description and rationale. Use `COMPANY` scope with a
canonical company ID for an issuer-specific item. Use `PORTFOLIO` scope for
concentration, currency, geographic or other portfolio exposure items; set a
company ID when an issuer is specifically implicated, otherwise use `null`.
Distinguish qualitative judgment from deterministic exposure calculations.
Evidence should reference a canonical filing/fact/thesis record, a stable external
source identifier, or an HTTPS source URL. Mark partial coverage and explain it;
never interpret omitted findings as a pass. The application validates and previews
the contract, checks whether the cited portfolio baseline is still current, and
waits for explicit reviewer acceptance. A stale/incomplete baseline stays marked
and requires reviewer acknowledgement. An assessment cannot change holdings,
targets, models, canonical Risk scores or Execution Pace.

## Research and thesis publication

Research forecasts and thesis opinions publish to separate contract tabs and
separate application-owned inboxes. Put one complete `ResearchRevisionContractV1`
version `1.0.0` or `1.1.0` JSON object in `Research Revision Contract!A1`, or one complete
`InvestmentThesisContractV1` version `1.0.0` or `1.1.0` JSON object in
`Investment Thesis Contract!A1`. Then use **Portfolio model → Publish research
forecast to application inbox** or **Publish investment thesis to application
inbox**. Each action appends to its own five-column inbox and leaves earlier
publications in place. Exact replay is ignored; changed content requires a new
external revision ID. The application captures each contract in its candidate
queue, previews it through the existing canonical service and waits for a named
reviewer to accept or reject. It does not turn forecasts into analyst consensus
or thesis opinions into model assumptions. Research contracts require at least
one source evidence item; thesis contracts require evidence on at least one
claim. The copy-ready agent instruction block is
[`ResearchThesisAgentInstructions.md`](ResearchThesisAgentInstructions.md).

Before researching a new trigger, read `work_item_json.payload.trigger` and
`work_item_json.payload.context` from the matching `Application Agent Work Feed`
row. The connected workbook currently has no separate Thesis Watch tab. Version
`1.1.0` research/thesis proposals can cite a canonical trigger through
`trigger_references` while retaining independent source evidence. For `NOISE`, do
not publish an empty revision. Publication is not acceptance; wait for the
application reviewer.

External agent roles use the versioned `ResearchAgentWorkContractV1` and
`ResearchAgentAcknowledgmentContractV1` described in
[`../../docs/research-agent-operations.md`](../../docs/research-agent-operations.md).
Use the role-specific instructions for the
[`Data & Universe Steward`](DataUniverseStewardInstructions.md),
[`Portfolio & Thesis Sentinel`](PortfolioThesisSentinelInstructions.md), or
[`Model & Allocation Steward`](ModelAllocationStewardInstructions.md).
For any role work row, copy `payload.work_identity` exactly, set
`delivery_channel` to `GOOGLE_SHEETS`, and use **Portfolio model → Publish agent
work acknowledgment to application inbox**. This appends to
`Application Agent Work Acknowledgment Inbox`; an application operator manually
runs `POST /v1/google-sheets-agent-operations/check` to reconcile it. Receipts do
not accept proposals or close research-queue tasks.
