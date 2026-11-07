# Independent models within a company

Status is implemented for isolated verification on the publication feature branch.

## Identity and ownership

A company owns a collection of models. The current canonical identity is the
company, exact valuation listing and supported model type. Each model has its own
current revision pointer, immutable input history, evidence, output snapshots and
return-method definition. The existing uniqueness constraint permits distinct
methods on the same listing and the same method on different listings.

Source keys and producer revision labels are transport metadata. A source revision
label is unique within its canonical model. Independent models may both publish
`agent-r2`. Discovery and review resolve conflicts within the canonical model.
The immutable content fingerprint and existing replay keys remain the basis for
exact retries. Unknown model identity remains invalid.

## Publication recovery

The Sheets adapter reconstructs each publish block independently before testing
for repeat content. Two methods sharing a revision label remain separate blocks.
An invalid inbox row identity retains its original evidence. A correctly identified
new block can capture the same frozen financial contract for review. Compatibility
handling also supports older invalid captures whose key occupied the valid-source
namespace. Different financial content under the same model revision label remains
a conflict.

## Presentation and decisions

Company Valuation selects an exact model/listing. Its summary, history and editor
share that identity. The editor must be closed before switching models so draft
context stays explicit. Company Overview shows one output only when unambiguous,
otherwise directing the investor to model selection. Method-specific returns and
currencies remain visible.

The existing ranking/execution ambiguity gates remain the operational rule for
companies with multiple model candidates. A future company-level synthesis or
decision-model selection needs an explicit versioned contract, economic rationale,
currency/share-basis treatment, return comparability and owner approval. That work
has a separate design and investment-policy gate.

## Verification and compatibility

An isolated PostgreSQL test creates DCF, owner-cash-flow and residual-income models
for one fictional company, publishes a shared source revision label, verifies
native parity and advances each revision independently. It checks sibling outputs,
captured provenance, exact replay, conflicts and corrected transport metadata.
Browser tests cover exact-listing selection, editor scope, keyboard focus and mobile
layout. Existing method engines, database schema and production authorization remain
the owners of their established boundaries.

The durable contracts are [financial models](../../financial-models.md) and
[model publications](../../model-publications.md).
