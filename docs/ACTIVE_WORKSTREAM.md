# Active workstream

## C2.3 guided ledger onboarding — BUILD

Branch `codex/ledger-opening-onboarding` contains implementation `18f1f15` and
merge `813651e` from updated main `e070406` ([merged PR #29](https://github.com/paulzwecker/portfolio-app/pull/29)).
The owner edits, predecessor branches/worktrees and private source artifacts remain
preserved. No new PR has been opened for this BUILD increment.

At `/portfolio/ledger`, the opening builder collects explicit evidenced accounts,
exact listing quantities and native-currency cash. A statement can be SHA-256
hashed locally or identified by an existing hash/reference. Drafts remain in page
memory. Submission reuses the authenticated read-only preview and its anchor/hash
checks. The source-date acknowledgement resets after edits. Download/re-upload
preserves exact financial text and account IDs. Separate saved-candidate decisions
retain their existing server authorization.

The opening workflow is LOCAL_VERIFIED with 96 focused web checks, 67 native ledger
unit tests, 13 isolated PostgreSQL/API cases and six managed desktop/mobile browser
checks. Synthetic light/dark screenshots were visually reviewed. Typecheck,
production build and focused lint pass. All selections passed again after merging
PR #29. Both offline schema-gate modes match `b59f16c8a203` with no pending range.
The new API regression checks v2 at the exact anchor boundary with zero
activity, deterministic replay and unchanged canonical state.

## Next increment and release boundaries

Add guided settled-activity and ending-statement entry to complete the existing
candidate review journey. Reuse the versioned ledger contract, server calculations,
immutable review packets and explicit decisions. Preserve the observed holdings,
strategic targets and unavailable acquisition basis. A reviewed first broker format,
lot/FX policy, historical completeness and genuine TWR/XIRR remain later work.

This increment adds no schema or provider configuration. Its milestone remains
BUILD. Review current hosted release controls at INTEGRATE before classifying
merge/deployment readiness. Price/FX enrichment, recovery operations, production
ledger cutover, model acceptance and provider activation require their own scope
and authorization. No production/provider operation ran in this BUILD.

[Ledger behavior](portfolio-ledger.md) owns this contract and workflow.
[The roadmap](../ROADMAP.md) owns priority. The previous market integration and
live-read evidence are preserved in the [dated handoff](history/market-history-build-through-2026-11-08.md).
