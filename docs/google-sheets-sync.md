# Google Sheets model synchronization

PostgreSQL remains canonical for accepted financial-model assumptions, projections,
outputs, portfolio holdings, targets and revision history. Google Sheets is a reviewed
external authoring surface and receives published copies of current portfolio and
bounded Thesis Watch context.
The application reads only the explicit, append-only **Application Model Sync Inbox**
and **Application Risk Assessment Inbox**, plus the research/thesis inboxes and acknowledgment
inbox. It writes only the fixed,
application-owned **Application Portfolio State**, **Application Thesis Watch Feed**, and
**Application Agent Work Feed** tabs. It
does not scan model worksheets, formulas, named ranges, dashboards or the workbook's
legacy `Model Contract` reference tab.

The portable contracts remain the existing versioned boundaries:

| Contract                                              | Supported methodologies                           |
| ----------------------------------------------------- | ------------------------------------------------- |
| `FinancialModelContractV1` (`1.0.0`–`1.2.0`)          | `UFCF_DCF_10Y_FADE`                               |
| `AdditionalModelPortableContractV2` (`2.0.0`–`2.1.0`) | `OWNER_CASH_FLOW_10Y`, `RESIDUAL_INCOME_10Y_FADE` |

No other contract version or method is inferred from workbook layout. Contract
identity, exact valuation listing, currency, base revision and deterministic
recalculation are checked by the existing preview/import services. Sheets output
cells never become accepted application outputs.

External research-agent publication is a separate domain boundary from this model
inbox. Structured investment-thesis snapshots use `InvestmentThesisContractV1`
through `POST /v1/investment-thesis-revisions`, with company-scoped evidence links
and their own stale-base/replay rules. They do not enter financial-model acceptance
or the model inbox. See [investment-thesis.md](investment-thesis.md).

For versions `1.2.0` and `2.1.0`, a Sheets model proposal must include a proposal
author, authored timestamp, source reference and at least one reference to an
already published research revision, research forecast, thesis revision or thesis
claim. The reviewer sees these links alongside the deterministic input, projection
and output diffs. Acceptance stores the author and evidence links on the new
immutable model revision; the inbox separately preserves the reviewer and decision
note. Research records remain separate from agent interpretation and proposed model
assumptions. See [research-to-model.md](research-to-model.md) for the full sequence.

Risk assessments use a separate versioned `RiskAssessmentContractV1` and inbox.
They retain qualitative judgments against an exact published portfolio snapshot
and target revision. They are not canonical Risk scores or deterministic exposure
calculations and cannot modify portfolio or model state. See
[risk-assessments.md](risk-assessments.md).

## Workbook inbox contract

The workbook adapter in `tools/google-sheets/CanonicalModelContract.gs` adds an
explicit menu action, **Publish candidate to application inbox**. It appends the
portable JSON from `Contract!A1` as chunks in `Application Model Sync Inbox`:

| Column | Meaning                                               |
| ------ | ----------------------------------------------------- |
| A      | Unique publish-block ID                               |
| B      | External model revision ID from the portable contract |
| C      | 1-based chunk index                                   |
| D      | Total chunk count                                     |
| E      | Contract JSON chunk, at most 40,000 characters        |

The inbox is append-only through the adapter. A repeated exact publication is
detected in the script; the API also deduplicates it by a canonical JSON SHA-256
fingerprint. A reused external revision ID with changed content is captured as a
conflict. Incomplete/duplicate chunks are retained as invalid evidence. The reader
checks at most 5,000 inbox rows and never evaluates formulas. At 1 MB per contract
and 100 chunks, the contract size limits are explicit rather than silently
truncating cells.

To author a model, export its versioned contract from Company Explorer, load it with
the existing Apps Script adapter, build its method-specific editable inputs, and
write the edits back to the contract. Then publish the candidate to the inbox. For
multiple models, work one candidate at a time; the adapter's input tabs are a
working area, while the inbox retains published candidates. Export a fresh contract
before starting another revision so it receives a new external revision ID and
current canonical base.

The research agent publishes a complete `Risk Assessment Contract!A1` snapshot to
the separate **Application Risk Assessment Inbox** using **Publish risk assessment
to application inbox**. This uses the same five-column chunk protocol, with its own
candidate/run history and explicit review. It does not publish ordinary working
edits or overwrite the model inbox.

## Local authentication and setup

The model and risk inbox readers use the
`https://www.googleapis.com/auth/spreadsheets.readonly` scope. Portfolio publication
uses the same configured service-account key with the
`https://www.googleapis.com/auth/spreadsheets` scope. To enable publication, share
only the configured workbook with that service-account email as **Editor**. The
secret JSON key must remain outside the repository; settings reject a credential path
inside this checkout. A read-only Viewer grant continues to allow inbox reads but
cannot publish portfolio state or a Thesis Watch handoff. Those two manual
operations need Editor access; the API writer remains fixed to its allowlisted
application tabs.

Google grants Sheets access at the spreadsheet level rather than restricting it to
one tab. Editor access therefore also allows the service account to edit other tabs
at the Google permission layer. The publisher enforces the narrower application
boundary in code: it has no caller-supplied tab or range and writes only to the three named
application-owned output tabs. Each publisher validates its own marker/version before writing.
It refuses to replace a populated target tab
unless its ownership marker and contract version match. Existing model tabs, the
inbox, research tables and Apps Script workflows are not write targets.

1. In Google Cloud, enable the Google Sheets API, create a dedicated service
   account, and create its JSON key. Save the key outside the repository, for
   example `%LOCALAPPDATA%\PortfolioResearch\google-sheets.json`.
2. Share only the intended spreadsheet with the service account as Viewer for
   inbox reading. For manual portfolio publication, change that workbook grant to
   Editor; no other Drive files should be shared with the service account.
3. Set these values in the ignored repository `.env` (or the API process
   environment):

   ```dotenv
   GOOGLE_SHEETS_SPREADSHEET_ID=the-explicit-spreadsheet-id
   GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=C:\Users\you\AppData\Local\PortfolioResearch\google-sheets-reader.json
   GOOGLE_SHEETS_SYNC_TAB=Application Model Sync Inbox
   GOOGLE_SHEETS_POLL_SECONDS=3600
   ```

4. Run `npm run db:migrate`, then `npm run dev`.
5. Open `/model-sync`, use **Test workbook connection**, and confirm the configured
   inbox tab exists. The test reports workbook access separately from inbox setup.
6. Install/update the Apps Script adapter in the workbook and publish one
   reviewed model or risk contract candidate. Use **Check for changes** in the
   sync review page. Risk assessments have a dedicated reviewer area and require
   explicit acknowledgement when their portfolio baseline is stale.

The `/model-sync` page also offers **Publish portfolio state**. Select the canonical
portfolio and publish manually after reviewing the valuation status shown in the
result. The API creates `Application Portfolio State` if it is absent. If the tab
already has content without the application's marker, publication stops without
writing. The call updates the owned table in one Sheets batch request, then reads it
back and verifies the content. Repeating an unchanged publication returns
`UNCHANGED` and performs no cell write.

The spreadsheet ID is required and is never discovered by broad Drive search from
the backend. The backend uses only the configured ID, the fixed inbox ranges and
the two fixed application-owned output tabs. The local
Drive connector used to identify the intended file during setup is separate from
the application's service-account credentials.

## Review and revision semantics

Each poll records an immutable sync-run result and captures each unique published
contract with source spreadsheet, tab/cell row, URL, content fingerprint, external
revision ID, method, model currency, valuation listing, base revision, rationale and
first/last observed times. A supported contract starts `PENDING`; the review page
asks the existing domain service to preview it. The preview shows assumption,
year-by-year projection and normalized valuation output differences, then returns explicit `READY`, conflict,
invalid-base, rationale-required or no-change states.

Acceptance requires a named reviewer and a current `READY` preview. The app
recalculates again immediately before import. If the current preview has changed,
the new differences must be reviewed before another acceptance attempt. Acceptance
uses the existing locked, optimistic-base append operation and stores the source
workbook URL in revision provenance. Accepted/rejected inbox decisions are final;
an identical replay does not create another canonical revision. No investment
assumption change is automatically accepted.

The backend does not treat Google Sheets values as consensus. Agent-written model
assumptions remain part of a reviewed model revision, distinct from third-party
consensus-estimate observations. Separate agent-authored forecasts and company
assessments can be published through the versioned
[`ResearchRevisionContractV1`](research-forecasts.md) at `POST
/v1/research-revisions`; they do not become model assumptions, consensus or scores.
The research agent needs application API access but no database access. The research
contract has its own source and revision identity and can be read from Company
Explorer history. See [`research-forecasts.md`](research-forecasts.md) for identity,
period, currency, availability and point-in-time requirements.

## Operations and limitations

`POST /v1/google-sheets-sync/connection-test` verifies access and tab presence.
`POST /v1/google-sheets-sync/check` performs one read-only poll and records its run.
`GET /v1/google-sheets-sync/candidates` lists pending and historical decisions;
each candidate has preview, accept and reject operations. The Company's existing
model history and output refresh after acceptance through the same revision domain.

Risk sync uses `/v1/google-sheets-risk-sync/*` for connection checks, inbox capture,
preview and explicit acceptance/rejection. Accepted assessments are append-only in
a separate domain and are available through the Portfolio and Company Explorer
read APIs. Stale baselines require reviewer acknowledgement and remain marked stale;
no assessment is automatically accepted.

Agent-authored research forecasts/assessments and investment-thesis revisions use
two separate append-only tabs: `Application Research Inbox` and
`Application Thesis Inbox`. Their compact authoring cells are `Research Revision
Contract!A1` and `Investment Thesis Contract!A1`; the bound script publishes
complete `ResearchRevisionContractV1` or `InvestmentThesisContractV1` contracts
version `1.0.0` or `1.1.0` to the matching inbox. Version `1.1.0` may include
`trigger_references` with canonical trigger IDs, the existing classification and
rationale. It uses the same five-column chunk
protocol and fixed-range read-only API integration as the model and risk inboxes.
The application never scans research/model tabs. Each inbox block is captured
with its source row, raw content and fingerprint, then validated and previewed
through the existing research or thesis domain service. Company/security identity,
source ownership, evidence and the optimistic supersession base are checked by
those canonical publishers. A named reviewer must explicitly accept or reject a
valid candidate; acceptance calls the same publisher used by the direct API and
creates the ordinary immutable research/thesis revision. Replays of the exact
contract reuse the candidate/revision, while a reused external revision ID with
different content or a stale base is visible as `CONFLICT`. Missing evidence and
unsupported schemas remain `INVALID` queue items. Acceptance never writes to
consensus, model assumptions, scores, lifecycle or portfolio state.

The UI review queue is available under `/model-sync`. Its candidate history records
the review identity, note, source row, exact contract hash and canonical revision
ID. The API uses `/v1/google-sheets-research-sync/*` for status, connection test,
check, runs, candidates, preview, accept and reject. This sync path requires at
least one evidence item on a research revision, and evidence on at least one
thesis claim, in addition to the existing v1 schemas' own field validation. A
copy-ready instruction block for the workbook research agent is in
[`tools/google-sheets/ResearchThesisAgentInstructions.md`](../tools/google-sheets/ResearchThesisAgentInstructions.md).

The manual Thesis Watch handoff publisher can append bounded current trigger/context
records to the fixed **Application Thesis Watch Feed** tab. Its manifest uses
marker `PORTFOLIO_RESEARCH_THESIS_WATCH_FEED`, contract `1.0.0`, a content
fingerprint and publication time. Each row carries trigger identity/times, exact
company identity, source metadata, a context fingerprint and compact `context_json`
with exact securities/listings, the current accepted research/thesis revision per
stream, current model revisions/outputs/evidence, and prior accepted trigger
publications. Exact replays add no rows; changed context is appended, preserving
the earlier snapshot. The app rejects modified or unowned tabs and verifies writes
by read-back. Publish manually from Research Queue in pages of 50; no polling or
automatic review is enabled. The feed is a handoff, not permission to accept a
thesis or model change.

The three existing off-host ChatGPT automations receive role-specific work through the fixed
**Application Agent Work Feed**. The `/model-sync` page publishes up to ten items for one
allowlisted role at a time. The API appends a version `1.0.0` manifest and rows containing a
delivery ID, role, work type/key/fingerprint, `GOOGLE_SHEETS` channel, delivery time, status,
reason and complete `ResearchAgentWorkItemRead` JSON. It updates only its own manifest and
appends new rows. The database delivery receipt is recorded only after exact workbook read-back.
The feed refuses an unowned, altered, truncated or fingerprint-mismatched tab. Repeating a page
does not add duplicate rows. A successful feed write does not prove an agent read or processed
the row; processing is recorded separately through the acknowledgment inbox. Data, research,
thesis, model and risk contributions retain their separate existing contracts and inboxes.

The currently connected `Portfolio/Watchlist` workbook does not contain the separate
**Application Thesis Watch Feed** tab. Sentinel work rows in **Application Agent Work Feed** already
include `payload.trigger` and the full `payload.context`, so the existing external automation can
operate without that optional handoff tab. The connected workbook has been provisioned with the
research, thesis, risk and acknowledgment contract-entry tabs and the risk inbox.

The direct APIs used by local research pages do not currently require user authentication and the
development API binds to loopback. They are not an external-agent transport. Do not expose the
local API or put credentials in Sheets. The workbook is the supported off-host transport until
an authenticated gateway is separately introduced. There is no general factual-observation inbox:
Data & Universe Steward findings can be acknowledged with source and blocker details, while
canonical facts enter through supported provider/import pipelines.

With `RECURRING_OPERATIONS_ENABLED=true`, the `npm run dev` operations worker checks the model,
risk, research, thesis and acknowledgment inboxes hourly by default. Set
`GOOGLE_SHEETS_POLL_SECONDS=0` to disable that recurring poll. It never accepts a proposal.
The same polling process can be started manually when recurring operations are disabled:

```powershell
npm run db:sync-google-sheets -- --poll-seconds 300
```

The polling interval must be at least 60 seconds. Do not run this standalone poller while the
recurring worker is polling the same workbook. Each pass checks the model, risk, research, thesis
and acknowledgment inboxes and persists separate domain run records. The reader uses a bounded
range request per inbox, with credential and provider failures persisted as explicit `BLOCKED` or
`FAILED` run records. The service account must be able to read the spreadsheet and the Sheets API
must be enabled in its Cloud project. Worker health, last success and blockers appear on
`/model-sync` and at `GET /v1/recurring-operations/status`.

The canonical `Portfolio/Watchlist` workbook retains its legacy `Model Contract`
definition sheet; it is not the portable application input contract. The explicit
`Application Model Sync Inbox` tab uses the reader's five-column append protocol
(`publish_id`, `external_revision_id`, `chunk_index`, `chunk_count`,
`contract_json_chunk`). Existing legacy model tabs remain unparsed. The workbook's
`AGENTS.md` tab documents the publication and review procedure. The bound Apps
Script adapter runs with the spreadsheet user's edit permission and appends
complete contract payloads; the application reader remains read-only. The portfolio
publisher is a separate, manually invoked application operation and never accepts
holdings or target changes from Sheets.

## Portfolio-state contract

The exported tab is a flat, versioned table. Its first rows are a manifest containing
the marker `PORTFOLIO_RESEARCH_APPLICATION_STATE`, contract version `1.0.0`, a
`sha256:` content fingerprint and the time the current contents were published. Row
5 records the valuation cutoff used by that publication, row 6 stores the number of
data records, and row 8 contains the column names. Following rows use `record_type`
values:

- `PORTFOLIO`: portfolio and base currency; latest accepted holdings snapshot ID,
  effective and recorded times, source/actor/reason, confirmation freshness and age;
  current mark-to-market mode/cutoff/status/value; market and FX observation
  cutoffs; and accepted target revision ID, dates, source and reason.
- `POSITION`: company/security/listing IDs, ticker, venue, listing currency, quantity,
  listing-specific price and observed time, FX rate/time, native/base market value,
  weight, freshness and valuation status. Standalone listings remain separate rows.
- `CASH`: cash currency and balance, FX conversion, base value, portfolio weight and
  explicit valuation status.
- `COMPANY_ALLOCATION`: current issuer value/weight, target weight and allocation gap.
  `target_state` is `AUTHORED` even for an explicit zero target, or `MISSING` when no
  target was accepted. It does not infer or fill targets.

Unavailable numbers are blank cells paired with a status such as `PRICE_UNAVAILABLE`,
`FX_UNAVAILABLE`, `PORTFOLIO_TOTAL_UNAVAILABLE`, or the overview's incomplete
valuation status. The API supplies all values and weights; the publisher does not
recalculate them. Holdings snapshot times and market/FX times remain distinct, so
the table does not suggest that the positions were reconfirmed at valuation time.
The valuation cutoff is stored as the time of the last successful publish. The
fingerprint includes canonical values, revision identifiers, observation/source
timestamps, statuses and contract version, but omits only that request-time cutoff
and the publication timestamp so unchanged data replays without rewriting the tab.

The research agent should read only `Application Portfolio State`, validate the
marker and contract version, and treat `PORTFOLIO`, `POSITION`, `CASH` and
`COMPANY_ALLOCATION` rows as the current application-published context. It must not
write this state back into holdings or targets, and must keep the snapshot identity,
fingerprint, valuation cutoff and availability statuses with any derived research.

### Live verification on 2026-10-15

The configured workbook was verified as `Portfolio/Watchlist`
(`11DXXrAp4nuVAzLNSSrJ6ZXtT6RJo3Kk1MVEEORDdMHk`). The configured
`Application Model Sync Inbox` tab exists, and the service-account connection test
successfully read workbook metadata and the inbox. The application reads rows
`A2:E5001`. The publishing payloads were `FinancialModelContractV1` version
`1.1.0`, for `UFCF_DCF_10Y_FADE`.

Two GOOGL contracts were present concurrently and remained separately visible.
An authorized metadata/provenance-only r2 contract was previewed and accepted as
canonical revision 2, linked to external revision
`agent-sync-test-20261015-googl-r2` and base revision
`6bfae7e5-59d0-45ba-a193-79348e9f51ab`. Base and scenario assumptions and
projections matched revision 1; only revision rationale and source provenance
changed. The older r1 contract remained recorded as a stale-base `CONFLICT` after
r2 was accepted. Re-polling identified both existing contracts as unchanged and
created no duplicate revision. The accepted revision appears in Company model
history and as a traceable `MODEL_REVISION` Attention Center event.

Recalculation at acceptance time used the latest exact GOOGL listing quote, which
was stale under the application's freshness policy. The accepted revision
therefore retains a `PARTIAL` output state with Expected IRR and Weighted Upside
unavailable; this does not alter the accepted assumptions or earlier revision's
complete output snapshot. Refresh eligible GOOGL market data before relying on
current return figures.

In this local environment, outbound Google API requests failed when routed through
the configured dead `127.0.0.1:9` proxy. The live connection succeeded after
launching the API with `NO_PROXY`/`no_proxy` entries for `googleapis.com`,
`.googleapis.com` and `oauth2.googleapis.com`. Apply those exclusions to the API
process environment or repair the proxy configuration for routine synchronization.
No credentials were added to the repository. The optional poller is separate from
the API process and uses the same environment; a one-minute test poll detected no
new contract and no duplicate revision. A run may report `PARTIAL` when a recorded
candidate has a conflict, even though its retrieval succeeded.

### Portfolio-state publication

The same configured service account also passed the write permission check. Before
publishing, workbook metadata showed that `Application Portfolio State` did not yet
exist. The application created that fixed tab, published contract `1.0.0` for
portfolio `a58be2cb-24f2-5470-9aa4-6960344ec945`, and read it back through the Sheets
API. It returned `PUBLISHED` with 46 data records. The Drive connector independently
read back the marker, fingerprint, portfolio metadata and table header. A second
publication returned `UNCHANGED` with the same fingerprint and original publish
timestamp. The existing `Portfolio`, `Current Holdings`, `Target Architecture` and
model-inbox tabs remained present with their prior sheet IDs.

The exported snapshot was effective 2026-10-04 and marked stale at 11 days. Its
current mark-to-market status was `INCOMPLETE_PRICE_COVERAGE`; total portfolio value
and weights requiring a complete denominator remained blank. The export preserved
those states explicitly instead of carrying forward the legacy workbook's displayed
valuation. This verified integration and read-back, not complete portfolio valuation
coverage.
