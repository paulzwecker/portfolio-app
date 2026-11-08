# Active workstream

## C2.3 — Ledger foundation (BUILD)

- Branch `codex/portfolio-data-ledger-capabilities`, based on main `395f842`.
- PR #25 is complete and awaiting owner review. Keep it frozen. Integrate its
  receipt compatibility fix after owner merge; preserve this branch's capability roadmap.
- Objective: evidenced opening balances and settled activity → exact position/cash
  projection → reconciliation, preserving the canonical snapshot and targets.
- C2.2 and the C3.1 scoped SEC slice are locally verified. Their hosted scopes and
  activation retain owner gates. C2.3 can progress independently while #25 waits.

## Current ledger increment

The new publication backend passes 46 focused checks (23 publication, 21 receipt
storage and two workbook-lock cases). `portfolio-ledger-publication-v1` previews
whole-portfolio effects read-only and requires an exact plan/previous publication,
typed confirmation and explicit ownership/scope/recovery/holdings acknowledgements.
Atomic publication appends a canonical snapshot and immutable lineage receipt.
The original opening remains pinned for later candidate reconstruction. Normal
snapshot writes are blocked after ownership transfer; workbook previews report
`HOLDINGS_OWNERSHIP_TRANSFERRED`. Same-date corrections require later source evidence
before publication, preserving the existing unique snapshot cutoff.
Migration `b59f16c8a203` follows `a832e94d6f10`, retaining existing data. Downgrade
fails closed once publications exist. Tests cover native quantities/currency cash,
current/historical API readback, replay/concurrency, rollback, stale source/base,
confirmation rejection, append-only lineage and ownership writer rejection.
Review normalized publication receipt times to UTC for timezone-independent hashes.
Source presentation/compatibility verification follows. Production remains gated.

`cbefcae` adds scoped history/detail/stage/review proxy contracts. The complete
saved-candidate UI is LOCAL_VERIFIED through 90 focused web checks, 43 API/fixture
checks (including the 26 receipt/review regressions) and four real-API desktop/mobile
journeys, repeated after fixes. Explicit rationale, source/account/basis checks,
per-activity correction acknowledgements and a separate hash-bound confirmation
lead to immutable receipts. Rejection, base-history navigation, source inspection,
private export and ambiguous commit readback work. Failed responses reset review
checks and refetch saved state; no mutation retries run automatically. Guard tests
preserve raw financial text, remote owner authentication, origin/size limits,
scoped response identity, exact decimal/zero states and contradictory-state rejection.

The optional `ledger-review` fixture verifies loopback `_test` identity before
creating its own schema. Its writer allows compiled inserts only into the two
ledger receipt tables in that schema. Other tables, updates, raw SQL writes, schema
changes and target overrides remain blocked; ordinary fixtures stay SQL read-only.
Canonical snapshot/targets/count hashes match before/after browser decisions.
Desktop/mobile screenshots were inspected under ignored `apps/web/test-results`.
Normal bounded fixture shutdown removed its own schema; both local servers stopped.
Review corrected accessible decision labels and unknown-outcome readback. Types,
ESLint, Ruff/mypy, generated contracts, formatting and documentation checks pass.
The browser slice is locally verified with synthetic data. Production migration,
authorization and ownership cutover remain outstanding.

`a7557b0` durable storage passes 21 isolated PostgreSQL checks. Migration
`a832e94d6f10` follows `9f2a6d4c81b7` and adds immutable candidate/review tables.
The stage/detail/list/explicit accept-or-reject API now retains exact packet and
preview hashes, account/source evidence and per-portfolio accepted revision history.
Full replacement corrections require exact changed/removed activity acknowledgements,
a current base and fresh matching opening/ending evidence. Replay creates no extra
receipts. Canonical snapshot/targets remain the application's reading authority.
Independent review corrected workbook refresh lock ordering and retained-ORM identity
freshness. Focused verification passes 164 distinct checks: 67 ledger unit,
12 existing PostgreSQL/API, 26 new review/API, 21 storage/migration, two lock
contention, two existing workbook/bootstrap integration, 18 domain contracts and
16 read-only browser-fixture safety checks.
Ruff/format, strict mypy, generated contracts, web types and documentation links pass.
SQL test targets were independently verified read-only as loopback `_test` before
using random, disposable schemas. Exact decimal/zero/ETF identity, source/base/hash
changes, concurrent replay, rejection, explicit corrections, stored-data integrity,
production guard rejection and post-flush rollback are covered. New API behavior
is LOCAL_VERIFIED with synthetic data. Browser decision controls remain pending.
Production migration, activation and cutover remain owner-gated. This increment
originally verified API/contracts. The browser follow-up above adds decision controls.

`bf9f184` ending-statement reconciliation passes 79 focused checks (67 unit and 12 isolated
PostgreSQL/API cases). Account and total comparisons preserve missing/zero, exact
decimals, evidence and ordering. Missing empty accounts block; matching portfolio
totals cannot conceal account differences. Golden opening-only v1 hashes retain
compatibility. Existing canonical state and read-only pool protection are verified.
The private-file Portfolio UI and proxy pass 71 focused web cases. Sixteen fixture
checks retain read-only SQL and block every non-read request except the exact
fixture portfolio's read-only preview. Four actual-API desktop/mobile journeys and
repeat screenshot inspection verify matching/missing zero balances, account scope,
evidence/focus, stale files and cancellation. Protected-state hashes match. Independent
review corrected uppercase UUID metadata and contradictory ready-status handling.
Source financial text is forwarded verbatim, with bounded UTF-8 and existing
origin/auth controls. Types, lint, formatting, generated contracts and docs pass.
Evidence stays in ignored `.cache/c2.3-ledger-review*`. Normal fixture shutdown
removes only each test-owned schema. This is LOCAL_VERIFIED with synthetic data.

`43d1ed8` adds the versioned settled-booking core. The read-only API increment is
LOCAL_VERIFIED through 40 unit, nine isolated PostgreSQL/API and 18 existing contract
cases (67 total). GET anchor and POST preview run read-only/repeatable-read and pin
snapshot content, recording time and canonical listing/source identity. Existing
writable/read-only pool settings are restored exactly. Injected DML is rejected.
Input/output replay, snapshots/targets, all table counts and sequences reconcile.
Reviewer findings corrected source-local settlement timing and pooled readonly
reset. Follow-up pool checks pass. Types, lint, formatting, generated contracts,
web types and documentation checks pass.

Opening reconciliation preserves explicit zeros and source/account evidence.
Trade cash uses observed gross amounts plus explicit fees/taxes, in listing
currency. Intermediate negative balances remain blocked after later recovery.
`OPENING_RECONCILED` describes the supported candidate preview. Source authenticity,
account allocation, settled-balance basis and cutover need operator review.
Durable review receipts are locally verified above. Decision UI, ownership
cutover, cost lots and performance remain outstanding. Commands and scope are in [the ledger contract](portfolio-ledger.md).
No production operation occurred. Local activation/write flags remain disabled.

## Current SEC increment

`1356944` company-scoped SEC admission and the read-only `refresh-options` contract are
LOCAL_VERIFIED. Twenty admission/manual API tests plus 27 existing incremental/
portfolio-scope regressions pass on isolated local schemas. Verified positive
holdings permit SEC-only work, retaining actual lifecycle and snapshot provenance.
Retries recheck eligibility. Other jobs retain prior lifecycle rules. Independent
backend review found no defects. Shared Company Explorer/Operations controls now
consume backend eligibility and execution mode, preserving disabled/operator states,
per-job cooldown and scoped request identity. Terminal outcomes refetch coverage.
Review corrected stale/overlapping polls using cancellation and serialization.
Eighty focused web tests, strict types, lint, formatting, contracts and documentation
checks pass. Eight mixed/outage desktop/mobile journeys pass across two fixtures;
the four final outage cases include slow polls. Enabled submissions/statuses are
synthetic HTTP receipts; PostgreSQL tests separately exercise real queue/worker
execution. Browser serving remains SQL read-only with unchanged protected-state
hashes. Both fixtures remove only their own schema on normal bounded shutdown.
Repeated screenshots were inspected under ignored `.cache/c3.1-company-refresh*`.
Local production-write, ingestion, recurring/manual/sync/FMP and polling flags
remain disabled. No hosted source or production execution occurred.

`197254a` adds issuer filing reconciliation to the existing batch ledger under
`sec-issuer-filings-v1`. It preserves per-issuer response/acceptance/reuse, conflicts
and quality, with execution-specific history deferrals. Old receipts stay intact.
The 79-case source/coverage/bootstrap regression and 15 incremental-worker cases
pass. Six mixed/outage desktop/mobile journeys and repeated screenshots verify
direct issuer results while another issuer has unsupported filings. Browser writes remain zero
and protected-state hashes match. Independent static review has no findings.
Screenshots stay in ignored `.cache/c3.1-issuer-filings`. Eighteen web unit cases,
strict types, lint, formatting, contracts and documentation checks pass. Both
fixtures removed only their own schemas on normal shutdown. Local production-write,
ingestion, recurring/manual/sync/FMP and polling controls are disabled. This slice
is LOCAL_VERIFIED with synthetic data; hosted provider scope remains unverified.

`4cb4870` adds incremental run/attempt IDs, trigger, frozen scope counts and separate
batch/issuer results to company coverage. The shared panel/drawer uses that contract
in Financials, Research and Operations. Compact status follows newer bootstrap/
refresh activity, preserving both histories in details. Attribution uses stored
issuer evidence, with unknown multi-issuer filing outcomes explicit. Retained-data
dates stay separate from execution. Eighteen web unit/proxy cases and six actual-API
desktop/mobile journeys pass with zero browser writes and unchanged state hashes.
Repeated screenshots were inspected under `.cache/c3.1-refresh-coverage` after
moving technical summary codes into details. Independent review fixed zero-row
integrity conflicts being classified as unavailable. The final 45-case API/scope/
fixture regression passes after that correction. Clean empty results stay unavailable. Contracts are current,
strict types and lint pass. Fixture shutdown removes only its own isolated schema.

`af8c847` incremental SEC refresh selects held issuers without requiring lifecycle,
then explicit Watchlist, through the existing scheduled/manual ingestion paths.
It reuses the bootstrap identity/holdings contract and existing durable attempts.
Domain/day and manual-request scopes freeze mappings, including manual steps across
midnight. Actual mapping drift blocks requests; later additions do not widen old
scopes. The budget is 30 mapped issuers and five historical files per filings
attempt. Deferred history stays partial. Existing transport retries remain bounded;
scheduled retries retain the 15-minute cooldown/two-replay daily budget. Terminal
and exhausted outcomes stay reused. Manual scopes remain separate from scheduled
ones. Review corrected abandoned runs skipping interruption detection.
Fifteen isolated scope tests and 107 existing regressions pass, followed by four
deterministic-clock reruns. Normal manual-queue execution, next-day/outage recovery,
concurrent requests and mapping changes between transport attempts are covered.
Exact Financials/filing readback preserves holdings/cash/targets and lifecycle.
Strict types, lint, formatting, contracts and documentation checks pass. All checked
local production-write/ingestion/manual/recurring/sync/FMP flags and Sheets polling
remain disabled. No hosted scope or provider execution occurred.
Operational details are in [the worker runbook](recurring-operations.md#held-issuer-sec-refresh).

`1beddc0` adds the current per-company `sec-coverage` read API. A shared panel and
source drawer now connect Financials/Research to company-focused Operations.
Counts and economic/filing/retrieval/recording dates remain distinct from bootstrap
attempt state. Historical Financials hides current coverage. Failed checkpoints
retain prior evidence and appear on the compact summary. Invalid identity URLs
are withheld. This increment passes 51 focused API/fixture/bootstrap tests and
58 web unit/proxy cases, plus six real-service desktop/mobile journeys and two
refined missing-data reruns. The existing Company Explorer composition passes
desktop/mobile after following its explicit Close editor interaction.
Browser review exposed a URL/tab mismatch. Company navigation now follows Next's
query state and preserves native History integration. Repeat screenshots were
visually inspected under `.cache/c3.1-source-coverage`. Fixtures use synthetic SEC
responses, real importers, PostgreSQL, API and proxy with read-only serving and
zero browser writes. Start fixtures serially to retain the database-wide bootstrap
lock. Normal bounded shutdown removes each test-owned schema.

`6c44a40` adds `db:bootstrap-fundamentals preview/prepare --portfolio-id`, selecting the exact
portfolio's current complete snapshot and explicit Watchlist. Held issuers are
prioritized independently of lifecycle, listing duplicates become one issuer,
and unmapped issuers/companyless ETFs remain explicit. Existing checkpoints,
guards, SEC importers and source hashes are reused. Resume retains prepared order
across lifecycle/holdings changes and rejects actual identity drift. Second-pass
outage review found facts could run during its issuer's filing retry cooldown.
That dependency is now enforced while other eligible issuers can progress.
Twelve scoped tests and 107 existing bootstrap/source/write-guard regressions pass.
They cover exact financial/filing API readback, reconciliation, unchanged holdings/
targets, portfolio isolation, missing CIKs, mapping additions/drift and outage/retry
recovery. Strict types, lint, formatting, contracts and documentation checks pass.
The slice is LOCAL_VERIFIED using synthetic data. Real issuer mapping evidence,
per-company freshness/coverage usability and hosted ingestion remain outstanding.
Commands are in [the SEC runbook](fundamentals-source-bootstrap.md#choose-the-issuer-scope).

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

1. Continue C2.3 with the dated ownership/cutover contract and isolated read-model
   integration. Pin the reviewed opening anchor, covered accounts, accepted candidate
   and cutover date. Preserve canonical snapshots/targets and require current-state
   recovery plus separate source-ownership/schema/write authorization before
   activation. Build the candidate path against synthetic fixtures first.
   Production schema/ownership/import changes remain owner-gated. This is the next
   high-value independent capability while #25 review and data activation wait.
   C3.1 real CIK evidence, international gaps and hosted validation stay outstanding;
   mapping persistence/provider ingestion require separate production authorization.
2. After owner merge of #25, integrate its receipt adapter and preserve both sets
   of roadmap evidence. Keep the completed PR frozen during owner review. Then
   enter INTEGRATE for comprehensive local checks and one cohesive C2.2 PR.
3. Review the 90-date/30-subject policy, provider scope, three-attempt/15-minute
   retry budget and expected holdings/cash reconciliation. Require a verified
   current-state recovery point and separate production authorization before any
   backfill or provider cycle. The old recovery point predates accepted holdings.
4. After explicit authorization, prove two hosted refresh cycles including restart,
   partial/failure visibility and investor readback. Scheduling/recurring activation
   remains a separate owner decision. No hosted cycles have run in this increment.

Keep tests focused during BUILD. Comprehensive quality, browser review and one PR
belong to the completed milestone's INTEGRATE gate. Production backfill/scheduling,
current-state recovery, source/model acceptance and migrations need separate authorization.
