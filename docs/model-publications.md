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
first/last observation, status and run diagnostics. Exact replay reuses a candidate.
Changed content under a reused revision ID produces a conflict. Preview and
acceptance replay the same frozen contract and recalculate native outputs.
Published fair-value mismatch blocks readiness and acceptance. Review decisions,
evidence, concurrency checks and immutable history use existing services.

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
