# Active workstream

## C2.3 guided ledger onboarding — BUILD

Branch `codex/ledger-opening-onboarding` contains implementation `18f1f15` and
merge `813651e` from updated main `e070406` ([merged PR #29](https://github.com/paulzwecker/portfolio-app/pull/29)).
The owner edits, predecessor branches/worktrees and private source artifacts remain
preserved. No new PR has been opened for this BUILD increment.

Completed PRs stay frozen for owner review. Continue independent milestones from
updated main, or record an explicit stacked branch when a dependency is unmerged.
Fetch and reconcile remote merges at the start of each run while preserving work.

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

The latest BUILD restores the form's unchanged downloaded opening packet for the
current anchor, preserving account IDs and exact decimal text. It rejects packets
containing activity, ending statements or additional fields, and asks for the
date acknowledgement again. A pending older document hash cannot overwrite a newer
hash after restoration. Continue with guided activity and ending observations.
Verification passed 98 focused web tests and ten managed desktop/mobile browser
cases using synthetic data. Typecheck, production build, focused lint and docs
checks passed. The mobile light-theme layout was visually inspected.

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
