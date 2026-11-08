# Model publications

## Authority and architecture

Google Sheets is the current modeling workspace for finance agents. PostgreSQL
owns accepted canonical model revisions. Agents publish completed contracts and
the application captures proposals through the existing model sync inbox.
Method-specific native engines calculate the candidate. Reviewers decide on
acceptance using the existing preview, evidence and base-revision safeguards.

The source adapter reads fixed publication rows. Canonical model contracts contain
identity, inputs, units, methodology, evidence and revision ancestry independently
of worksheet coordinates. Future producers can emit the same publication JSON.
Existing P-GOOGL v1 evidence remains an immutable compatibility path. Its disputed
assumptions remain owner-gated.

## Publication v1 contract

`FinancialModelPublicationV1` wraps a complete existing portable model contract.
It declares version `1.0.0`, state `PUBLISHED`, a publication timestamp,
`contract_json` containing the exact frozen UTF-8 contract text, and its
`contract_sha256`. The nested contract carries canonical identity, external
revision identity, base revision, rationale, author and supporting evidence.
New publications require evidence-capable versions `1.2.0` or `2.1.0`.
Numeric financial values use decimal strings. The envelope also records four
published fair values for independent comparison with native candidate outputs.
The comparison uses the existing parity tolerance of `1e-7` model-currency units
per share. Current-price returns use canonical eligible market observations.

Publication requires an explicit author action after completing the model. A
draft or a changed payload hash fails validation. Publication hashes establish
content integrity. Source access and configured identity establish provenance.
Producer assertions retain their provenance through the existing inbox record.

Publication v1 compares four source fair values with the native candidate.
Projection and return-stream parity remain in legacy captured-package validators
where available. Existing bare portable inbox contracts remain compatible.

Emit the publication JSON Schema offline.

```powershell
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.model_publications
```

## Capture and review lifecycle

The Sheets adapter appends the publication using the existing five-column chunk
protocol in `Application Model Sync Inbox`. It freezes a contract as text and
performs one bounded row write. It never imports ordinary model tab edits.
Discovery reads the bounded inbox twice around stable workbook/tab identity.
Both row sets and source structure must match. A mismatch or unavailable response
records a failed run and leaves previously captured candidates available.
This establishes an observed consistent source state. Sheets provides no
transactional snapshot guarantee across these requests.

Existing sync tables retain raw text, raw hash, semantic fingerprint, source row,
first/last observation, status and run diagnostics. A source-scoped transaction advisory lock covers worker and manual discovery.
Concurrent scans record `SYNC_IN_PROGRESS` without provider requests. Exact replay
reuses a candidate.
Source revision IDs are scoped to their canonical model. Changed content under a
reused model revision ID produces a conflict. Independent methods on one company
can share a producer label. The Sheets adapter tests replay per publish block. Preview and
acceptance replay the same frozen contract and recalculate native outputs.
Published fair-value mismatch blocks readiness and acceptance. Review decisions,
evidence, concurrency checks and immutable history use existing services.

The candidate API exposes the reviewed preview SHA-256 and typed publication
evidence containing all four exact published/native fair values, signed differences
and their tolerance checks. Missing native values retain `UNAVAILABLE`. The
reviewer panel presents this comparison with model currency, publication time and
frozen contract identity. Calculation agreement and investment acceptance remain
separate review decisions.

Acceptance of a publication requires the caller's `preview_fingerprint` to match
the stored preview, followed by fresh native validation in the transaction. A
different reviewer refreshing the candidate invalidates an older tab's approval.
A fresh calculation that differs from the reviewed preview returns the updated
candidate for another explicit review. The UI preserves the unresolved rationale
and reports the actual outcome. Previously accepted candidates replay their
recorded decision. Older bare portable-contract callers may omit the fingerprint
for compatibility; the current web review always supplies it.

## Scope and operation

MP1 is an isolated, fixture-verified publication-to-proposal workflow for existing
canonical models. The first accepted model still needs the separately guarded
seed workflow. A publication references that accepted base. Companies sharing a
method use the same contract and adapter. Methodology-specific engines remain
separate.

Use the existing Operations model-sync page to check for changes, inspect runs,
preview candidates and review decisions. Existing manual and recurring operations
remain the single scheduler. Local discovery and review may persist operational
records, so production discovery also requires separately scoped authorization.
Leave polling and production ingestion disabled during rollout.

The existing row/byte/chunk limits bound each scan. The first slice reads only
the publication inbox, retaining the 5,000-row limit. Incremental cursors or
metadata caching require a later measured workload and retention design. Full
workbook downloads are unnecessary.

## Rollout and future promotion

1. Merge the fixture-verified protocol and adapter after review.
2. Review a real method template and canonical base, then authorize workbook
   adapter installation and explicit source publication separately.
3. Capture and review a real candidate under production target guards and verify
   its immutable inputs, native outputs, provenance and conflicts.
4. Authorize any production acceptance for the exact candidate and current preview.
5. Design and test promotion policy using the reviewed history. Specify materiality,
   evidence freshness, method changes, conflicts, quotas, failure recovery and audit.
6. Obtain separate policy and activation approval before unattended promotion.

Existing Google Sheets contracts, agent APIs, role separation, UI and database
guards continue to own their current boundaries. No new service, database table
or scheduler is required for this publication envelope.

## Author and operator instructions

### Read-only file preflight

A frozen `FinancialModelPublicationV1` JSON file from a reviewed publisher can be
checked before inbox discovery creates operational records. Keep it in private
storage outside the checkout. The outer publication file hash and its nested
contract hash are separate integrity checks. Use the exact reviewed file hash.

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
$publication = '<private-frozen-publication.json>'
$publicationHash = '<reviewed-64-character-file-sha256>'

npm run db:preflight-model-publication -- inspect `
  --publication $publication --publication-sha256 $publicationHash --store $store

npm run db:preflight-model-publication -- preview `
  --publication $publication --publication-sha256 $publicationHash --store $store `
  --target-environment production
```

`inspect` validates the existing publication and nested method contracts offline.
`SCHEMA_VALID` confirms their structural and mathematical input constraints.
`preview` requires the configured target environment to match the explicit flag.
It uses the existing exact Neon identity, TLS, schema and Alembic-head verification
with SELECT privileges and production-write authorization disabled. Native preview
queries run in repeatable-read, read-only transactions behind the mutation guard.
Both commands write only a private append-only report under
`model-publication-preflight/runs/<run-id>.json`. Terminal output contains a status,
run ID and publication hash. The report preserves the exact source JSON, target
identity and native differences. Re-encoding `publication_json` as UTF-8 reproduces
the reviewed file hash. Local targets carry no Neon identity attribution.

`READY_FOR_REVIEW` establishes canonical compatibility and source/native fair-value
parity for that frozen file. Reports explicitly record `FROZEN_FILE_ONLY` and
`acceptance_authorized=false`. Check live source freshness and provenance separately.
The report is evidence for onboarding review. Existing discovery, current preview
and explicit acceptance still own the subsequent review workflow.
Inbox transport consistency and competing captures are checked during discovery.
The file report explicitly records `inbox_capture_checked=false`.

`MISSING_CANONICAL_MODEL` requires a reviewed first-model seed through the existing
guarded package path. An existing P-GOOGL captured package remains a distinct
initial-seed contract. This command accepts the publication envelope only and
preserves all identity and model-acceptance gates. Native validation conflicts,
stale bases, evidence errors and parity mismatches block readiness. Target/schema
verification failures stop before domain preview. It has no apply operation.

### Source publication and review

1. Export the existing portable contract from an accepted canonical model.
2. Complete candidate assumptions, a new source revision ID, rationale, author and
   canonical evidence references using the existing bound Apps Script input tabs.
3. Create `Published Fair Values` with headers `bear_fv`, `base_fv`, `bull_fv`,
   `weighted_fv` in A1:D1. Place completed source model values as plain decimal
   text in A2:D2, in model currency per listing share with sufficient precision
   for the `1e-7` comparison. Currency symbols and separators fail validation.
4. Write candidate edits back to `Contract!A1` and use the explicit publish menu.
   The script hashes the frozen UTF-8 text, adds the publication timestamp and
   fair values, takes a document lock and appends one chunk block. Repeating the
   same content is skipped. Changed content needs a new external revision ID.
5. In an authorized isolated environment, use Operations / Model sync to check
   for changes. Run history shows failures and replay counts. Preview shows
   native input/output differences and parity failures. Review and acceptance
   use the established explicit controls.

The fair-value staging range belongs to the source adapter. Canonical consumers
use the typed envelope independently of source coordinates. A future producer can
supply the same envelope with its frozen portable contract JSON. This milestone
requires separate operator installation before the workbook script can be used.

The scan uses four bounded Google requests and the existing worker cooldown and
manual controls. It reads only the configured inbox. Future cursor or retention
work must preserve raw evidence before pruning a full inbox. Sleeping-runtime
worker activation remains operator-controlled.

Response validation requires the complete requested range while permitting omitted
trailing empty rows. Both row sets and source identity must match.
[Google Sheets ValueRange reference](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values)

The architectural rationale is recorded in [decision 001](architecture/decisions/001-explicit-model-publications.md).

A corrected inbox revision label can recapture the same immutable contract after
a source metadata error. The original invalid record stays available. Older invalid
capture keys retain compatibility through a separate verified-source namespace.
[Independent-model decision](architecture/decisions/002-independent-company-models.md)
