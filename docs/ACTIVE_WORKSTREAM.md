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

## Current build increment

Cloud market correction now pins a repeatable-read canonical scope, exact listing
keys, required FX and one reviewed crosswalk object/hash. It uses 90 inclusive
calendar dates and rejects scopes over 30 listing/pair subjects before claims or
provider access. Existing transport/run retry limits give a conservative upper
bound of 12 HTTP attempts per subject. Legacy development/model FX behavior is
retained outside this cloud path. Frozen replay rejects changed mapping bytes or
replacement filters. Eight scope/replay tests and 26 adapter regressions pass.

## Next build steps

1. Prove synthetic refresh → EUR valuation and Operations/API readback through the
   actual importer, including replay, source changes, outage/partial results and
   unchanged holdings/targets. Use `test_cloud_market_refresh.py` and existing
   synthetic Yahoo fixtures. Inspect desktop/mobile when UI changes.
2. Finalize any remaining scope/retry/freshness gaps before the milestone's
   INTEGRATE gate. The 90-date/30-subject policy is a local release proposal,
   pending explicit review and authorization before production activation.

Keep tests focused during BUILD. Comprehensive quality, browser review and one PR
belong to the completed milestone's INTEGRATE gate. Production backfill/scheduling,
current-state recovery, source/model acceptance and migrations need separate authorization.
