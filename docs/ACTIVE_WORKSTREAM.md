# Active workstream

## C2.2 — Daily Portfolio Data (BUILD)

- Branch `codex/portfolio-data-ledger-capabilities`, based on main `395f842`.
- PR #25 is complete and awaiting owner review. Keep it frozen. Integrate its
  receipt compatibility fix after owner merge; preserve this branch's capability roadmap.
- Objective: provider-only cloud refresh → durable outcomes → trustworthy portfolio
  valuation/freshness, reusing existing adapters, jobs and domain calculations.

## Current increment

`run_recurring_cycle(provider_only=True)` runs SEC and explicitly enabled FMP jobs
with existing locks/cadences/receipts. It leaves the manual queue and Sheets,
research, agent-feed and decision workflows alone. Existing callers default to
their full cycle. Two synthetic PostgreSQL tests verify cadence, optional consensus,
queued work and unchanged counts outside worker/run tables. Focused lint/types pass.

## Next build steps

1. Add explicit cloud-runner scopes, safe status summaries and nonzero exit for
   nested failures/partial results. Respect configured cloud proxy routing.
2. Reconcile market startup scope with the reviewed held-listing/FX plan. Existing
   startup/scheduled paths add TWD/EUR for legacy model use and can cold-backfill
   ten years. Resolve explicit scope/resource policy before production activation.
3. Prove synthetic refresh → EUR valuation and Operations readback, including
   restart, partial/outage/retry behavior. Inspect desktop/mobile when UI changes.

Keep tests focused during BUILD. Comprehensive quality, browser review and one PR
belong to the completed milestone's INTEGRATE gate. Production backfill/scheduling,
current-state recovery, source/model acceptance and migrations need separate authorization.
