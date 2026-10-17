# Research Coverage & Review Queue

`/research-queue` answers which research review is due from current canonical
state. It is a derived queue, not a project-management system: the application
does not persist generated tasks or infer investment decisions. It stores only
analyst completion records, each with the exact source snapshot and condition
fingerprint reviewed.

## Supported review needs

| Queue type            | Trigger                                                                                                                                                                                                                                             |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CANDIDATE_STAGE`     | An explicit Candidate has no pipeline revision yet, or its current stage/gate still needs a documented next action or recommendation review. No stage is inferred from workbook data.                                                               |
| `THESIS_REVIEW`       | A Portfolio or Watchlist company has no published thesis, or the latest published thesis is at least 365 days old. The cadence is an operational review reminder, not an investment rule.                                                           |
| `THESIS_QUESTION`     | A claim on the latest published thesis remains open or under review.                                                                                                                                                                                |
| `MATERIAL_EVIDENCE`   | A source filing/publication dated within the last 30 days has not been linked to accepted research, thesis, Candidate gate or risk evidence; or the latest accepted research revision is not yet cited by downstream Candidate/model/thesis review. |
| `RESEARCH_TRIGGER`    | A captured canonical event (model revision, valid estimate revision, corrected reported fact, linked thesis risk/catalyst evidence, risk finding, or filing not already represented by a recent material-evidence card) needs explicit review.      |
| `MODEL_REUNDERWRITE`  | Accepted research or thesis evidence recorded after the current accepted model revision is not linked to that model revision, or the model revision is at least 365 days old. This asks for review and never edits assumptions.                     |
| `MODEL_INTEGRITY`     | The latest model migration/parity assessment is not `PARITY_PASS`, or the current accepted revision has missing/incomplete normalized outputs.                                                                                                      |
| `STRUCTURAL_RISK`     | A company finding in the latest accepted risk assessment is `HIGH` or `CRITICAL` and remains `UNDER_REVIEW`.                                                                                                                                        |
| `WATCHLIST_READINESS` | A Watchlist company's current canonical durability/quality assessments, native outputs or Watchlist Rank state call for review, or those inputs have not yet received an explicit readiness assessment.                                             |

New primary documents and research observations are not called material by an
AI or a generic rules engine. The initial document rule is deliberately narrow:
recent unreferenced canonical documents create a review item; accepted research
that cites a document removes that item. Review priority is lifecycle first
(Portfolio, Watchlist, Candidate), then explicit task class. Candidate items use
Research Rank position before name as the tie-breaker. Watchlist and Portfolio
investment ranks do not reorder lifecycle priority.

## Completion and history

Every generated item has a stable task ID and a fingerprint of its current
triggering state. Completing an item stores the reviewer, optional note, exact
task/source snapshot and completion time. Exact completion replay is idempotent.
If the source condition changes before completion, the API returns HTTP 409 and
requires a refresh. If genuinely new evidence changes a completed condition, a
new fingerprint reopens review while the old completion remains in history.
Completed records are append-only and retain their original reasons and source
references.

Completion means only that the indicated review was performed. It does not alter
research/thesis/model revisions, scores, lifecycle, ranking runs, holdings,
strategic targets or Execution Pace. Queue actor names are currently explicit
local-review attribution; authorization is outside the application's present
local-development model.

## API and UI

- `GET /v1/research-queue` derives current needs. Optional `lifecycle`, `search`
  and `include_complete` parameters filter the result.
- `GET /v1/research-queue/history?limit=100` reads the immutable completion log.
- `POST /v1/research-queue/{task_id}/complete` records a current completion with
  `condition_fingerprint`, `completed_by` and optional `completion_note`.

The responsive `/research-queue` page shows lifecycle/task priority, explicit
reason and trigger, responsible workflow, source timestamps, links and a compact
completion history. It links Candidates to their pipeline and all other items to
Company Explorer. Review of evidence remains an analyst task; the queue does not
claim that deterministic eligibility is an analyst conclusion.

The API is suitable for an external research agent to read queue items and source
context. Milestone 8C supplies role-specific delivery receipts and versioned
acknowledgments; they remain distinct from queue completion. See
[`research-agent-operations.md`](research-agent-operations.md) for role boundaries
and the acknowledgment contract.

The event-trigger layer adds a manual scan operation. It reuses Attention Center
event selection, stores idempotent trigger captures, and creates linked queue work
where a current 7H item does not already represent the same filing. Completion
state is resolved from the existing immutable queue completion record. See
[`research-triggers.md`](research-triggers.md) for event identities, point-in-time
rules, correction behavior and unsupported guidance detection.

## Limits

The annual thesis/model cadence and 30-day filing lookback are simple, explicit
operating thresholds; they can be changed in the domain module when operating
experience supports a better cadence. Only currently modeled triggers appear.
The queue does not generate model or thesis work from absent legacy assumptions,
does not determine whether a filing is material to intrinsic value, and does not
create research priority from expected return. Candidate stage progression stays
in the Candidate Pipeline, and Watchlist readiness stays separate from lifecycle
promotion or Portfolio admission.
