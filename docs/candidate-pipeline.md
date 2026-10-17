# Candidate Research Pipeline

The Candidate Pipeline records research work for companies whose explicit
lifecycle is `CANDIDATE`. It makes the documented research progression visible
without treating research completion as investment lifecycle, an investment rank,
or Portfolio admission.

## Progression and decisions

The ordered stages are:

1. Discovery
2. Initial Screen
3. Quality / Durability
4. Fundamental Compounding
5. Deep Dive
6. Recommendation

Each revision is a complete snapshot of the stage, all five gate outcomes,
rationale, unresolved questions, next action, author, source, and effective time.
Moving forward is sequential and requires the preceding gate to be explicitly
`PASS`. `NOT_ASSESSED`, `INCOMPLETE`, `DATA_CHECK`, and `FAIL` remain visible and
do not pass a gate. Research can be reopened at an earlier stage by recording a
new revision; prior decisions remain in history.

The hierarchy stays explicit: Durability, Compounder Quality, credible normalized
per-share compounding of at least 15%, valuation / Expected IRR, then portfolio fit.
The Quality / Durability gate requires the latest assessed 10Y Durability and
Compounder Quality records as evidence. The canonical score dimensions have no
documented numeric pass cutoff, so the pipeline does not invent one. The
Fundamental Compounding gate requires a current complete normalized model output
with Forward Fundamental CAGR of at least 15% and a reviewer attestation that the
linked output is normalized per share. The API validates this against canonical
model output; it does not calculate CAGR. A missing or stale model output remains
incomplete.

An explicit `DROP` recommendation can be recorded as soon as a gate fails. A
`WATCHLIST` or `INCUBATE` recommendation is available at Recommendation only after
all five gates pass. These are research recommendations: accepting one does not
change lifecycle, targets, holdings, model assumptions, or ranking runs. A
separate explicit lifecycle decision is required to move a company to Watchlist or
Drop.

## State, evidence, and history

The API stores append-only `candidate_pipeline_revisions`,
`candidate_pipeline_gate_assessments`, and `candidate_pipeline_evidence` rows.
Every revision snapshots all gates and links typed evidence to same-company
research revisions, thesis revisions/claims, score assessments, native or
normalized legacy model outputs, source documents, or HTTPS source URLs. Evidence
links preserve whether a source supports, contradicts, or contextualizes the
assessment.

Each write includes a unique submission ID and expected prior revision. Exact
replay is idempotent; reuse of an ID with changed content or a stale base returns
a conflict. Recorded history is immutable. Effective times must have an explicit
timezone and cannot be future dated. Pipeline writes are rejected unless current
lifecycle is explicitly `CANDIDATE`.

The queue distinguishes `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, and `COMPLETE`.
It shows the current research stage, failed/incomplete gate context, existing
Candidate High/Low tier and persistent priority seed, and the latest available
Research Rank entry. Queue order follows that rank position, with unranked
Candidates still visible afterward by company name. Research Rank retains its own
documented formula; pipeline completeness and gate outcomes do not alter it.

## Existing data and migration boundary

The existing imported Candidate tier/priority records, lifecycle, Research Rank
runs, scores, models, research revisions, thesis revisions, and source documents
remain their canonical source domains and can be linked from a new gate assessment.
The legacy workbook does not provide authoritative stage/gate history suitable for
this pipeline. Existing Candidates therefore begin as `NOT_STARTED`; the app does
not infer research completion from workbook tabs, models, scores, or thesis
presence. No historical pipeline outcomes were fabricated or backfilled.

## API and UI

- `GET /v1/candidate-pipeline?search=...` returns the Candidate queue.
- `GET /v1/companies/{company_id}/candidate-pipeline` returns one Candidate's
  current state, immutable history, and same-company evidence choices.
- `POST /v1/companies/{company_id}/candidate-pipeline-revisions` appends a full
  revision.

The responsive `/candidates` page filters and explains the queue, records all gate
states and evidence, and shows revision history. The page does not make investment
decisions on the user's behalf. External Sheets/research agents can use the same
versioned append-only API through a future explicit publication bridge; they must
not write lifecycle or Portfolio state as a side effect.

Candidate stage and unresolved gate work also appears in the cross-lifecycle
[Research Review Queue](research-queue.md), ordered by Research Rank after the
Portfolio and Watchlist workload. Completing a queue review does not advance the
Candidate stage or apply its research recommendation.
