# Explicit financial-model publications

Implemented and locally verified, merged in PR #23. Current rollout evidence and
owner gates are recorded in [ROADMAP.md](../../../ROADMAP.md).

## Context

The owner selected Google Sheets as the current agent modeling workspace and the
application as the canonical investment interface. Existing portable contracts,
native engines, sync candidates, run history and reviewer controls already serve
this boundary. Historical P-GOOGL packages preserve useful source evidence while
their assumptions remain under investment review.

## Decision

Wrap the existing evidence-capable method contracts in a producer-neutral,
versioned publication envelope. Freeze the exact contract text and SHA-256, an
explicit publication timestamp and four source fair values. The Sheets adapter
publishes a completed block using the existing inbox protocol. Discovery checks
stable source identity and two complete bounded reads. A shared transaction lock
serializes manual and worker discovery.

Reuse native preview and import services for identity, units, ancestry, evidence,
calculation and acceptance. Published fair-value parity gates both preview and
acceptance. Immutable external revision identities survive later revalidation.
Existing raw candidate records retain the complete envelope and source hashes.

## Alternatives and consequences

Per-company import scripts would duplicate financial mappings and couple the
application to source coordinates. Full-workbook capture would impose unrelated
validation and acquisition cost. A new orchestrator would overlap the existing
worker and run ledger. The chosen boundary reuses the installed services and
allows future producers to deliver the same contract as JSON.

The first slice requires an existing accepted canonical base. First-model seeding
uses the existing separately guarded workflow. The envelope compares four fair
values, while legacy package validators retain their richer projection parity.
The bounded inbox scan costs four reads. Incremental cursors and retention follow
measured operational needs.

## Verification and rollout

Synthetic two-company tests cover capture, typed replay, evidence, native parity,
revision conflicts, rejected responses, transaction rollback and concurrent scans.
Existing review controls and canonical services own acceptance. Real workbook
installation, first model acceptance and production discovery each require their
corresponding owner authorization. A future automatic-promotion policy requires
design, tests and explicit approval before activation.

Legacy bare portable contracts remain readable. Reversal consists of retaining
their reader while deferring new publication producers. The envelope requires no
schema transition. The detailed contract is [model-publications.md](../../model-publications.md).
