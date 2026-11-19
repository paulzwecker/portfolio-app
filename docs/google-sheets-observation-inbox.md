# Google Sheets Observation Inbox → canonical proposal review

## Purpose

The **same typed proposal contracts** can arrive from an API agent or a Google
Sheets authoring workspace. PostgreSQL continues to own accepted metric
definitions, KPI actuals and management guidance. There is one approval
workflow. The bridge is intentionally narrow and disabled by default.

- It reads the configured spreadsheet with the existing **read-only** Sheets
  API client and double-capture consistency checks. No Apps Script execution,
  Sheet edits, additional provider, database table, or background worker.
- It validates `MetricDefinitionBatchV1`, `KPIObservationBatchV1` or
  `GuidanceObservationBatchV1` using the exact API/Pydantic contracts.
- It submits valid batches through the established
  `company_observation_proposals.submit()` function into the **same candidate
  table** as API-agent submissions. It never invokes preview/accept/reject.
- It keeps stable source-specific producer identity and exact
  `external_batch_id`: identical replays do not create duplicates; conflicting
  reuse of an ID is surfaced as a scan issue, never overwritten.
- Read limits: maximum **100 assembled contracts** per manual scan and the
  existing 1 MB contract cap. Bad rows do not block independent valid batches.
  No raw rejected cell contents or service-account credentials are returned.

## Workbook contract (one named tab, five columns)

Create the tab `Application Observation Inbox` on the *approved* workbook.
Column headers are for people; data begins at **row 2**. The bridge only reads
`A2:E5001` on this tab, not arbitrary workbook cells.

| Column | Field | Required content |
| --- | --- | --- |
| A | `publish_id` | Stable nonempty ID grouping the chunks of one batch |
| B | `external_batch_id` | Exactly matches the batch JSON `external_batch_id` |
| C | `chunk_index` | 1-based ordinal |
| D | `chunk_count` | Total chunks for the batch |
| E | `json_chunk` | Portion of a complete UTF-8 JSON batch |

For a short single-cell batch: C = `1`, D = `1`, E = the entire JSON text.
For a longer batch, split the complete JSON across sequential chunks with the
same A/B values. The reader assembles each batch, validates contiguous chunk
indices, and independently verifies that the tab has not changed during read.
Reuse `publish_id` and `external_batch_id` on retries; do **not** change
content under an existing batch ID. To propose a correction, create a new
external batch ID and supply explicit canonical supersession identity in the
typed payload. Never remove a previously accepted record.

The JSON must be exactly the same contract accepted by
`POST /v1/company-observation-proposals`: canonical company UUID, type and
version `1.0.0`, source-backed rows, exact **decimal strings**, authored
timestamp and rationale. See [company observation proposals](company-observation-proposals.md).
The test batch builders in `apps/api/tests/test_observation_sheet_sync.py`
provide isolated examples; no private investment data is stored in Git.

## Manual activation and review

By default both `OBSERVATION_PROPOSALS_ENABLED` and
`OBSERVATION_SHEETS_INBOX_ENABLED` are `false`. Enabling the bridge without
the canonical proposal service is a configuration error.

When independently approved by the owner, configure the following **outside
Git**:

```text
OBSERVATION_PROPOSALS_ENABLED=true
OBSERVATION_SHEETS_INBOX_ENABLED=true
GOOGLE_SHEETS_SPREADSHEET_ID=<exact approved workbook ID>
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=<private credential path>
GOOGLE_SHEETS_OBSERVATION_TAB=Application Observation Inbox
```

Only a broad, authenticated operator request to

```http
POST /v1/google-sheets-observation-sync/check
```

can trigger the scan. It is not exposed through the scoped read token or the
observation-agent submission token. Hosted production proposal writes also
require the existing owner production-write authorization; **this PR does not
enable it**. There is no recurring poll.

The response is `ObservationSheetCheck` with `status`
(`SUCCEEDED`, `PARTIAL`, `SOURCE_UNAVAILABLE` or `SYNC_IN_PROGRESS`),
counts, bounded issue codes and newly created proposal UUIDs. A source outage
does not mutate accepted state. A second scan of unchanged content returns
replayed counts. The proposal table contains the immutable candidate and
source producer fingerprint for audit.

To review, use the **existing** reviewer-role endpoints:
`GET /v1/company-observation-proposals` followed by
`POST /v1/company-observation-proposals/{id}/preview` and deliberate reviewer
`accept` or `reject` with the preview fingerprint and decision note.
`OBSERVATION_ACCEPTANCE_ENABLED` remains a separate disabled-by-default gate.

## Validation / boundaries

Tests use a fake read-only Sheets client and isolated PostgreSQL database to
verify valid candidate ingestion, exact replay, malformed chunks, reuse of an
external batch ID with different content, missing definitions and acceptance
only through the existing reviewer service. No real Sheet is read or edited.
No production migration, credentials, Google account, provider subscription
or live acceptance is activated by this development slice.
