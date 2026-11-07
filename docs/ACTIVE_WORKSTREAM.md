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
- `a681b2e` persists preflight blockers under the guarded market advisory lock to existing
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

## Investor-journey increment

- `15959b1` exposes read-only scopes/attempts and shared backend retry eligibility.
  The UI links Portfolio to focused Operations diagnostics, with summary before
  manual controls and a source/attempt drawer. Previous-API IDs remain visible.
- Sixteen desktop/mobile fixture browser cases plus four final reruns pass, with
  zero write requests. Baseline and refined screenshots were visually inspected.
  Focus/Escape, overflow, null values, 22 exact positions, two cash currencies,
  cooldown/recovery, preflight, stale/running and exhausted states are covered.
  Local screenshots live under `.cache/c2.2-visual-review` and browser test results.
  Second visual inspection fixed the shared drawer's right-edge positioning. Six
  focused investigation/preflight/design-system reruns pass after the correction.
- Eighteen isolated API cases passed, followed by 14 status/importer regressions
  after review excluded manual replays from automatic retry eligibility. Nine web
  unit checks, strict types, lint and generated contracts pass. Browser requests
  use synthetic fixtures. Hosted data/scheduling are unverified and owner-gated.

## Actual-API rehearsal

`fd4ec9e` adds the bounded test-only API fixture. The actual-API rehearsal is
LOCAL_VERIFIED. Six unpriced/outage/valued desktop/mobile journeys use the real
importer, PostgreSQL, API and Next proxy with synthetic provider payloads.
They preserve exact holdings/cash/targets and protected-state hashes, with
zero browser writes or API errors. Sixteen fixture safety/integration cases pass.
Visual review found allocation-gap names squeezed by long decimal displays.
`443d93a` corrects the layout and retains exact-value titles. Three regression unit
cases pass, followed by repeat desktop/mobile screenshot inspection. Screenshots
remain in `.cache/c2.2-real-api`.
Final focused regression passes five web unit tests and 18 UI/browser cases, with
strict types, lint, formatting, generated contracts and documentation links current.
Bounded normal shutdown removes its own schema. Five pre-existing browser schemas
are preserved. Commands are in the
[development runbook](codex-cloud-development.md#portfolio-data-rehearsal).

## Next build steps

1. After owner merge of #25, integrate its receipt adapter and preserve both sets
   of roadmap evidence. Keep the completed PR frozen during owner review. Then
   enter INTEGRATE for comprehensive local checks and one cohesive C2.2 PR.
2. Review the 90-date/30-subject policy, provider scope, three-attempt/15-minute
   retry budget and expected holdings/cash reconciliation. Require a verified
   current-state recovery point and separate production authorization before any
   backfill or provider cycle. The old recovery point predates accepted holdings.
3. After explicit authorization, prove two hosted refresh cycles including restart,
   partial/failure visibility and investor readback. Scheduling/recurring activation
   remains a separate owner decision. No hosted cycles have run in this increment.

Keep tests focused during BUILD. Comprehensive quality, browser review and one PR
belong to the completed milestone's INTEGRATE gate. Production backfill/scheduling,
current-state recovery, source/model acceptance and migrations need separate authorization.
