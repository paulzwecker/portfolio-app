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
  and at most 30 listing/pair subjects. Existing retries imply at most 12 transport
  attempts per subject in one invocation. Legacy model FX behavior is retained.
- Real synthetic Yahoo payloads now pass through normalization and the existing
  database importer into Portfolio/Operations HTTP readback. Exact EUR totals,
  snapshot/cash/target preservation, fresh-connection replay, FX outage and recovery
  on the next UTC cycle are covered. Captured mappings survive a file change during
  fetch, while invalid subsequent source captures stop before new records.
- Fixed replay reporting to reuse the captured request scope. Explicit listing
  scope keeps unrelated companies outside its diagnostics while legacy full-universe
  gaps remain visible. Focused regression passed 84 cases, with strict types/lint.

## Next build steps

1. Resolve bounded same-day recovery using the existing run/attempt/replay records.
   Current same-scope terminal failures are reused until the next UTC cycle or an
   explicit operator retry. Preserve source hashes, retry caps and provider budgets.
2. Make cloud preflight blockers visible durably in Operations. They currently
   return a safe CLI failure code before ingestion claims, leaving prior run status
   intact. Reuse existing operational ledgers rather than adding a job framework.
3. Review the synthetic investor journey and data/freshness presentation, then use
   INTEGRATE once the local milestone is complete. The 90-date/30-subject policy
   requires explicit review before production activation. Actual hosted cycles,
   current-state recovery and provider coverage remain separately gated.

Keep tests focused during BUILD. Comprehensive quality, browser review and one PR
belong to the completed milestone's INTEGRATE gate. Production backfill/scheduling,
current-state recovery, source/model acceptance and migrations need separate authorization.
