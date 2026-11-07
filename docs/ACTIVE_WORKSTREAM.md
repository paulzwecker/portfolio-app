# Active workstream

## C2.2 — Daily Portfolio Data (BUILD)

- Branch `codex/portfolio-data-ledger-capabilities`, based on main `395f842`.
- PR #25 is complete and awaiting owner review. Keep it frozen. Integrate its
  receipt compatibility fix after owner merge; preserve this branch's capability roadmap.
- Objective: provider-only cloud refresh → durable outcomes → trustworthy portfolio
  valuation/freshness, reusing existing adapters, jobs and domain calculations.

## Completed build increments

- `1e70d66` adds provider-only recurring cycles with existing locks/cadences/receipts,
  optional FMP and preserved manual queue/unrelated tables.
- Cloud CLI defaults to `--scope market-data`. `provider-data` adds due SEC and
  explicitly enabled FMP. `all-operations` explicitly selects the full legacy cycle.
  Cloud calls retain configured proxy routing and print safe status/class summaries.
- Partial/nested failures exit nonzero. Fixed an unset retry-delay variable after
  provider exceptions and protected another instance's heartbeat during overlap.
- Focused worker/guard/market regression passed 106 cases. Final cloud regression
  passed 27 cases. Strict types passed for five files, plus lint, formatting,
  documentation links and whitespace checks.
  Existing detailed outcomes remain in database run ledgers. No UI changed.

## Current verified increment

- `34b0175` pins a repeatable-read canonical scope, listing keys, required FX and
  reviewed crosswalk object/hash. Cloud corrections use 90 inclusive calendar dates
  and at most 30 listing/pair subjects. Legacy model FX behavior is retained.
- Real synthetic Yahoo payloads now pass through normalization and the existing
  database importer into Portfolio/Operations HTTP readback. Exact EUR totals,
  snapshot/cash/target preservation, fresh-connection replay, FX outage and recovery
  on the next UTC cycle are covered. Captured mappings survive a file change during
  fetch, while invalid subsequent source captures stop before new records.
- Fixed replay reporting to reuse the captured request scope. Explicit listing
  scope keeps unrelated companies outside its diagnostics while legacy full-universe
  gaps remain visible. Focused regression passed 84 cases, with strict types/lint.
- `a4d0ec8` reclaims only retryable failed/partial domains after a
  15-minute cooldown, within the original frozen scope and three-attempt ledger
  budget. One attempt per invocation bounds transport work to four tries per subject.
  Successes stay reused; interrupted claims recover through the existing history.
  Fixed terminal runs being incorrectly reclassified as interrupted after four hours.
  Focused recovery/importer regression passes 33 cases, including five isolated
  recovery scenarios, scope escape and retained-success checks. Strict types and
  lint pass. No production execution occurred.
- Preflight blockers now persist under the guarded market advisory lock to existing
  ingestion runs/attempts. Operations keeps previous success and other-domain history,
  including after more than 40 failures. Corrected scopes resolve active diagnostics
  without rewriting their original failures or advancing data freshness. Seven isolated
  PostgreSQL/API cases cover mappings/budgets/source errors, guard rejection and
  unchanged provider/portfolio facts. No schema or public API contract changed.
  Diagnostic replay requires a fresh cloud scope check. The focused 142-case
  worker/importer/guard regression, strict types, lint and documentation checks pass.
  Second-pass review corrected status ordering to follow an older run's newer
  attempt. The dedicated case checks both Operations and external-ingestion status.
  The final 36-case preflight/importer rerun passes after replay/order corrections.

## Next build steps

1. Review the synthetic investor journey and data/freshness presentation, then use
   INTEGRATE once the local milestone is complete. The 90-date/30-subject policy
   requires explicit review before production activation. Actual hosted cycles,
   current-state recovery and provider coverage remain separately gated.
2. After owner merge of #25, integrate its receipt adapter and preserve both sets
   of roadmap evidence. Complete local acceptance before the milestone PR gate.

Keep tests focused during BUILD. Comprehensive quality, browser review and one PR
belong to the completed milestone's INTEGRATE gate. Production backfill/scheduling,
current-state recovery, source/model acceptance and migrations need separate authorization.
