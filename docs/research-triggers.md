# Research Event & Trigger Engine

## Purpose

The trigger layer records deterministic source events that can create research
work. It captures events from canonical histories; it does not interpret their
investment meaning, write model assumptions, or produce recommendations.

```text
Canonical source records
  → existing Attention Center materiality rules
  → append-only ResearchTrigger capture
  → Research Review Queue task and completion history
```

The Attention Center remains a read-only composition. The trigger table adds a
durable capture of what the application detected, while the 7H queue remains the
place where a reviewer records that work was completed.

## Supported triggers

The refresh operation reuses Attention Center selection rules for:

- New current filings and earnings releases. A filing is a prompt to review the
  source, not a conclusion that the filing changes the thesis.
- Accepted native model revisions, including documented material Expected IRR
  changes. Accepted model revisions are inherently material under the current
  Attention Center policy.
- Same-provider consensus changes that meet the existing 5% rule and have clean,
  comparable observations in the selected provider stream.
- Newly accepted high or critical risk findings marked `NEW` or `WORSENING`.

Two narrow detectors fill gaps in that feed:

- Reported-fundamental observations labeled `POTENTIAL_RESTATEMENT` or
  `AMENDED_FILING` create a review trigger. `POTENTIAL_RESTATEMENT` remains a
  data-quality label; it is not treated as proof of a formal issuer restatement.
- Evidence newly linked to an active thesis `PRINCIPAL_RISK`, `THESIS_BREAKER`,
  or `CATALYST` claim creates a trigger. The source fact and the author's
  `SUPPORTS`, `CONTRADICTS`, or `CONTEXT` relationship remain distinct.

There is no canonical guidance-observation domain or documented guidance
materiality rule yet, so the trigger engine does not infer guidance events from
filing text. It also does not invent thresholds for ordinary reported-fact
changes. Due thesis reviews, open thesis questions, model re-underwriting,
model-integrity checks, Candidate stages, and Watchlist readiness continue to
come from their existing 7H queue detectors rather than being copied into a new
trigger rule set.

## Identity, replay and corrections

Each record has a stable `event_key` based on canonical source identity and a
content fingerprint. Repeating an identical refresh creates no new trigger. If
the source content for the same event key changes, the engine appends a new
version and retains the earlier capture. A new corrected observation has its
own canonical record identity and remains linked to the observation it
supersedes.

For source documents and consensus or reported-fundamental observations, an
explicit canonical supersession marks the earlier trigger `SUPERSEDED` and
removes its open queue task. The earlier trigger and any review completion stay
in history. A filing amendment without a `supersedes_document_id` is not assumed
to replace the original filing.

## Time and processing state

The capture preserves source `effective_at`, `source_observed_at`, and
`source_recorded_at` separately from `detected_at`. An absent publication date
stays null; the record time is retained. A historical refresh excludes source
rows recorded after its `as_of` cutoff, even when their effective date was
backdated. Queue completion is also filtered by its recorded completion time.

`processing_state` is derived from the trigger version and its linked
ResearchQueue completion:

- `OPEN`: a queue task was linked and has no completion or correction known by
  the requested `as_of` time.
- `REVIEWED`: the exact queue condition has an immutable completion record.
- `SUPERSEDED`: a later content version or explicit canonical source correction
  recorded by the requested `as_of` time replaces this trigger.
- `STALE`: no queue task was linked to the captured trigger.

This reuses 7H's `(task_id, condition_fingerprint)` completion identity instead
of maintaining a second mutable review status.

## Operations and API

Trigger capture remains explicit on the API, but the local recurring operations worker calls the
same refresh service hourly with a bounded 30-day lookback. It does not run during a GET. The
manual operation below remains available for an immediate scan.

- `POST /v1/research-triggers/refresh?lookback_days=30` captures eligible source
  events and links them to queue tasks. `lookback_days` may be 1–365 and can be
  narrowed with `company_id` or a timezone-aware `as_of`.
- `GET /v1/research-triggers` lists captured versions, provenance, queue linkage,
  and derived processing state. It supports `company_id`, `trigger_type`,
  `processing_state`, `as_of`, `limit`, and `offset` filters. A filtered page is
  sliced after processing state is derived, so OPEN items are not hidden by a
  page of newer completed events.
- `GET /v1/research-triggers/{trigger_id}/context` returns exact company/security/
  listing identity, captured trigger times, current accepted research/thesis state,
  current model revisions/outputs/evidence and prior accepted trigger publications.
- `GET /v1/research-queue` includes current trigger tasks. Review completion uses
  the existing `/v1/research-queue/{task_id}/complete` operation.

The Research Queue page exposes a “Scan for new triggers” action. A trigger
linked to an existing recent unreferenced-filing task reuses that card rather
than creating a duplicate.

Recurring trigger scans also refresh the derived research queue once per hour. Repeated scans are
idempotent by source identity and condition fingerprint. Job status and failures are visible in
the `/model-sync` operations card and `GET /v1/recurring-operations/status`.

The Research Queue also offers a manual **Publish trigger page to Sheets** action.
It appends at most 50 OPEN trigger/context rows per request to the fixed,
application-owned `Application Thesis Watch Feed` tab. The feed is append-only;
exact context replays add no rows, changed accepted context adds a new snapshot,
and older rows remain in place. The writer refuses an unowned or modified target
and verifies each write by read-back. The external agent can consume the bounded
handoff from its workbook without reaching the local API. This publication does
not create or accept research, thesis, or model revisions.

## Limits

The 30-day default is the same conservative source window used by current
Attention Center and queue filing review. A backfilled filing whose publication
date is older than the selected lookback will not be treated as newly published.
Consensus triggers require valid same-provider history and therefore cannot
appear for sources without sufficient point-in-time observations. Filing
presence, an estimate revision, and a linked thesis claim do not by themselves
state whether a company's economics improved or deteriorated.

No LLM, text interpretation, financial-model recalculation, ranking run, target
change, lifecycle transition, or execution recommendation is performed.
