# Data and ledger BUILD evidence through 2026-11-08

Historical evidence from the active workstream through `349f699`. Results apply to
the recorded synthetic fixtures and checkouts. Current instructions and integration
status live in [ROADMAP.md](../../ROADMAP.md) and the
[active handoff](../ACTIVE_WORKSTREAM.md). Hosted activation remains separately gated.

## Current ledger increment

`a11272a` and `79ae274` add explicit, hash-bound whole-portfolio publication review in the
saved-candidate workspace. Read-only plan/authority routes and guarded publish
proxy verify source/candidate/review/portfolio identity, exact decimal text,
previous publication and snapshot receipt provenance. Rationale, four independent
owner attestations, the complete typed phrase and a separate confirmation precede
one submission. Reload is disabled while that submission is pending. Rejected or
ambiguous outcomes clear approvals and fetch read-only state. A lost response after
commit recovers its exact receipt; no mutation retry runs automatically.

135 focused web checks, 45 PostgreSQL/API/fixture checks, types, scoped lint/mypy
and docs/contracts pass. Actual desktop and mobile publication journeys run against
fictional accepted packets in separate loopback `_test` schemas. Only the exact
seeded candidate publish route can write compiled inserts to its four snapshot/
publication tables. Other writes remain denied. Original opening, strategic targets
and other table counts match before/after. Desktop confirms normally; mobile loses
the response after a real isolated commit and verifies readback without a retry.
Screenshots were inspected under ignored test-results and `.cache/c2.3-publication`.
Review fixed unknown-network messaging and historical before/after labels.
This is LOCAL_VERIFIED, with milestone-wide integration still pending.

Next use INTEGRATE for the coherent C2.2/C3.1/C2.3 local implementation milestone.
Recheck #25's owner merge and integrate its receipt fix without losing this roadmap;
keep that complete PR frozen while it waits. Run comprehensive checks once at this
gate, review scope and open one cohesive PR. Production account/basis/source review,
current-state recovery, migration, publication and provider activation retain their
separate owner gates. C2.4 accounting and C2.5 performance remain future work.

### Earlier ledger BUILD evidence

`71dee7e` implements explicit whole-portfolio holdings publication. The backend
initially passed 46 focused checks (23 publication, 21 storage and two workbook-lock).
Follow-up verifies 27 publication/provenance checks and existing API/fixture/import
regressions. A 99-case run exposed one pre-existing random-listing test assumption;
selecting the common share explicitly fixed it. The affected identity-lock test and
27 publication cases pass together (28/28). No checks were weakened.

`portfolio-ledger-publication-v1` has a read-only, hash-bound before/after plan,
exact typed confirmation, previous-publication and ownership/scope/recovery/holdings
acknowledgements. Atomic publication creates a canonical snapshot and immutable
receipt. UTC-normalized receipt times retain stable replay across DB timezones.
The original opening stays pinned for later packets. Manual/observed writes are
blocked after transfer; workbook previews report `HOLDINGS_OWNERSHIP_TRANSFERRED`.
Same-cutoff publication needs later source evidence, preserving snapshot uniqueness.
Migration `b59f16c8a203` follows `a832e94d6f10`. Downgrade fails once history exists.

Portfolio receives explicit, time-scoped ownership metadata, displays the original
opening/publication and routes ledger-owned holdings to history. Manual editing
controls are hidden. Contradictory or missing ledger provenance fails closed.
101 focused web checks and two actual-API desktop/mobile journeys pass; repeated
screenshots were inspected under ignored `apps/web/test-results`. Browser serving
is SQL read-only after pre-seeding a synthetic publication in a loopback `_test`
random schema. Canonical state hashes match and HTTP mutation remains blocked.
Fixtures shut down normally and remove only their own schemas. Types, focused
lint/mypy, contracts and documentation checks pass. This is LOCAL_VERIFIED.

The publication UI follow-up is verified above; milestone integration remains next. Real account/source scope, current-state recovery, production migration,
source-ownership authorization and execution retain owner gates. The current
recovery branch from M1 predates accepted holdings and cannot protect this transfer.

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
cutover, cost lots and performance remain outstanding. Commands and scope are in [the ledger contract](../portfolio-ledger.md).
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
Operational details are in [the worker runbook](../recurring-operations.md#held-issuer-sec-refresh).

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
Commands are in [the SEC runbook](../fundamentals-source-bootstrap.md#choose-the-issuer-scope).

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
[development runbook](../codex-cloud-development.md#portfolio-data-rehearsal).

## C2.1 recorded readiness evidence — 2026-11-07

- Live read-only target/control-plane checks verified the current production
  identity, `public` schema, head `9f2a6d4c81b7` and unchanged minimal counts.
  Prices, FX, corporate actions, fundamentals, source documents and models are
  absent. Private reports retain exact inventory and target evidence.
- Fixed a confirmed receipt-format incompatibility: provider readiness expected
  root reconciliation, while minimal Sheets v1 stores it in a linked legacy
  report. The adapter validates exact versions, hashes, identities and all domain
  evidence without editing receipts or changing production authorization.
- The existing production-target read-only market preview changed from
  `BLOCKED_CANONICAL_IMPORT` to `READY`: 22/22 held mappings, DKK/EUR and USD/EUR,
  no mapping blockers, zero provider requests and zero database writes. The
  one-year planning window is 2025-11-07 through 2026-11-06. SEC preview now
  recognizes the baseline but correctly blocks on zero reviewed CIK mappings.
- At that assessment recovery was ready, expiring 2026-11-14 09:54 CET, with the empty
  pre-import state. A separately authorized current-state recovery point is
  required before future writes. Local TLS required a process-only trusted CA
  selection, preserving `verify-full`; persistent settings were unchanged.
- Verification passed: full `npm run check` (169 web tests, 694 API unit tests,
  two environment-specific skips, strict types, contracts and production build),
  154 focused tests including 22 isolated PostgreSQL cases, documentation links
  and Git whitespace checks. The focused suite passed serially after an earlier
  parallel run encountered a local PostgreSQL connection timeout. An independent
  security/correctness review approved the adapter and regression coverage.
- CLI/backend scope; existing frontend tests/build passed. Provider availability,
  price quality and refreshed browser valuations await separately authorized real
  ingestion. Next action: CI and owner review of PR #25, then current-state recovery
  and a bounded execution decision. Production ingestion remains unauthorized.
- Commits `0324ba7` (receipt adapter/tests) and `b799093` (coverage/recovery
  runbook) form this independent integration checkpoint. When integrating PR #24
  and #25, retain its capability roadmap plus this verified C2 outcome.

## C5.2 database classification BUILD evidence

C5.2 found 32 ordinary PostgreSQL casesin 28 functions without integration markers.
CI's unit job skipped them without TEST_DATABASE_URL, while the PostgreSQL job's
marker selection omitted them. Explicit markers restore financial-statement,
consensus/history, source-evidence, scheduler and manual-refresh checks. All 32
pass on verified loopback PostgreSQL 18.3 using only random disposable schemas.
Test bodies and financial assertions are preserved. Collection now selects 643 unit
cases with zero PostgreSQL consumers before the guard increment. The completed
collection/runtime guard now selects 649 unit and 178 integration cases. Six
synthetic pytest-subprocess regressions and 71 focused unit checks pass without a
usable database, plus all 32 classified PostgreSQL cases with the guard active.
Dynamic requests fail before missing-DB skips. Source-bound tests retain their
separate privacy/opt-in policy. Types, scoped lint/format, source policy, docs and
whitespace pass. Combined-baseline and remote CI verification remain for INTEGRATE.

## Pre-consolidation integration checkpoint — 2026-11-08

| Field                       | Current value                                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Active checkpoint           | C2.2/C3.1/C2.3 local release candidate - INTEGRATE. [Handoff](../../docs/ACTIVE_WORKSTREAM.md)                                        |
| Branch / PR                 | `codex/portfolio-data-ledger-capabilities` / [PR #26](https://github.com/paulzwecker/portfolio-app/pull/26), from main `395f842`      |
| Implementation              | LOCAL_VERIFIED workflows. Full quality/build and browser checks pass; PR checks govern integration. Hosted activation remains pending |
| Next ready substantial task | Owner review of #25/#26 after CI. Integrate #25 after owner merge, then prepare the gated C2.2 operational slice                      |
| Parallel owner gate         | C1.2 P-GOOGL assumptions/base acceptance; C2 cutover/accounting policy and separately authorized production operations                |
| Integration rule            | Keep completed PRs stable during review. #26 is the cohesive local milestone integration boundary; production gates remain separate   |

Owner-requested consolidation now includes PR #25's exact minimal-receipt adapter
and its unchanged source-binding/reconciliation tests. Its dated read-only coverage
assessment is preserved in the [integration history](../../docs/history/data-ledger-build-through-2026-11-08.md#c21-recorded-readiness-evidence--2026-11-07)
and [ingestion runbook](../../docs/production-data-ingestion-operations.md). PR #25 remains
separately reviewable; its commits are included in this candidate. The CI-classification branch is now integrated with its collection/runtime
guards. Sensitivity and authenticated proxy fixtures are next before combined checks.

Integration review corrected the pre-ledger bootstrap path and added all ledger
history to the recovery inventory. `9048c47` also pins the existing read-only release
preflight to the current target and reviewed `9f2a6d4c81b7` → `b59f16c8a203` range.
The full quality/build command passes with 294 web checks and 810 API unit checks
(two Windows skips). Browser evidence covers 71 regression and ten actual-API
journeys. The pre-fix DB sweep found one regression among 341 selected cases; its
corrected path and 34 schema/publication checks pass. Final CI must exercise the
complete updated PostgreSQL suite, including local privilege-dependent skips.
[Handoff](../../docs/ACTIVE_WORKSTREAM.md) records evidence, release prerequisites and
[earlier BUILD history](../../docs/history/data-ledger-build-through-2026-11-08.md).
Linux CI additionally identified the Docker-published test service's non-loopback
server address. Test-only container/image/address/port attestation now preserves
exact identity verification, with 23 focused safety cases passing. The complete
CI rerun remains the merge gate. Hosted source freshness, ingestion, schema/cutover
and model acceptance remain gated.

`a11272a` adds scoped publication plan/ownership/publish proxy contracts and the
explicit whole-portfolio approval UI. The workflow is LOCAL_VERIFIED through 135
focused web checks, 45 PostgreSQL/API/fixture checks and actual desktop/mobile
publication journeys. Source-bound confirmations, conflicts, exact decimal readback
and lost-response recovery pass. Second-pass review corrected sanitized network
messaging and historical plan labels. The original opening and strategic targets
remain intact in synthetic rehearsals. [Handoff](../../docs/ACTIVE_WORKSTREAM.md) records
fixture safeguards and scope. Milestone-wide integration checks remain pending.

C2.3 saved-candidate decisions/history are LOCAL_VERIFIED. Ninety focused web,
43 API/fixture checks and four repeated real-API desktop/mobile journeys pass.
Source/receipt scope, explicit confirmations, corrections, rejection, immutable
history and ambiguous-commit readback are covered. [Handoff](../../docs/ACTIVE_WORKSTREAM.md)
records the guarded fixture and canonical-state evidence. Dated cutover and
production activation retain their owner gates.

`71dee7e` adds explicit whole-portfolio ledger publication, immutable snapshot
lineage and writer ownership guards. Publication/provenance, migration, replay,
concurrency, rollback, stale approvals and canonical API readback are locally verified.
The source UI displays the ledger owner and original opening, with manual snapshot
editing replaced by history navigation. Focused web checks and real desktop/mobile
read-only journeys pass. Detailed evidence and next scope are in the
[handoff](../../docs/ACTIVE_WORKSTREAM.md). Migration `b59f16c8a203` follows `a832e94d6f10`.
Populated ownership prevents downgrade. Same-cutoff publication and full workbook
apply after transfer remain explicitly blocked. Real source scope/recovery and
production activation retain separate gates.

### Current BUILD evidence

`a7557b0` C2.3 storage is LOCAL_VERIFIED through 21 isolated PostgreSQL checks.
Additive revision `a832e94d6f10` follows `9f2a6d4c81b7`, creating immutable
candidate packets and terminal review receipts. Same-portfolio ancestry, request
and accepted-revision uniqueness, rollback, replay and migration compatibility pass.
The source-bound stage/review/correction API passes focused unit, PostgreSQL/API,
authorization and contract checks. Independent review corrected workbook writer
lock ordering and retained-ORM identity freshness, with targeted regressions.
Exact tested counts and the next task are in [the handoff](../../docs/ACTIVE_WORKSTREAM.md).
The browser decision/history and dated publication/readback follow-ups are locally
verified above. Real ownership activation remains outstanding. Production migration,
current-state recovery and activation remain separately authorized gates.

Prior head `2c1b5aa` subsequently passed all three CI jobs and Vercel Preview in [run 42440104834](https://github.com/paulzwecker/portfolio-app/actions/runs/42440104834). This archived checkpoint preserves earlier pending-verification wording in its original context.

## C1.3 authenticated sensitivity BUILD evidence — 2026-11-08

| Field                       | Current value                                                                                                                                                                                             |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Active checkpoint           | C1.3 authenticated proxy-path verification — BUILD. [Handoff](../../docs/financial-models.md#current-build-checkpoint)                                                                                    |
| Branch / PR                 | `codex/native-dcf-sensitivity`, from merged main `395f842`. Local BUILD branch                                                                                                                            |
| Implementation              | C1.3 complete proxy path LOCAL_VERIFIED with authenticated production-mode desktop/mobile fixtures                                                                                                        |
| Next ready substantial task | Owner review/merge PRs #25/#26; integrate this completed slice and CI classification against updated main at one reviewed milestone gate                                                                  |
| Parallel owner gate         | Completed [PR #25](https://github.com/paulzwecker/portfolio-app/pull/25) and [PR #26](https://github.com/paulzwecker/portfolio-app/pull/26) await review/merge. C1 investment acceptance remains separate |
| Integration rule            | Keep completed PRs stable. Reconcile this independent slice and the preserved CI correction with latest main at the integration gate                                                                      |

PR #24 is merged as `395f842`. The completed data/ledger PR #26 stays frozen.
The independent PostgreSQL test-classification correction is preserved on
`codex/ci-database-test-coverage` in `18930ac` and `f72729e`, with its verified
handoff in that branch's testing reference. This branch adds a user-facing C1
review capability independently of the pending schema/data work.

PR #25's conflict repair is complete at `7d4ce2e`, passing all three CI jobs and
Vercel Preview. PRs #25/#26 remain open and stable for owner review. Their actual
merge state was rechecked before resuming this independent branch.

Normal-entrypoint review found three missing sensitivity proxy pieces: allowlist,
base-revision query forwarding and response validation. Earlier mocked browser
requests hid that defect. Commit `32eb94f` fixes the exact model/revision read path,
rejects missing/ambiguous base IDs, preserves sanitized conflicts and denied writes,
and retains HTTPS plus separate web/API credentials.

Commit `17ca4c1` adds an authenticated production-mode fixture on the existing
browser driver. Twenty-four desktop/mobile checks pass, including real Next.js
auth → HTTPS source → validated sensitivity → UI. Negative cases cover anonymous/
incorrect access, stale revision, malformed output, denied writes, server-token
separation, untrusted CA and wrong hostname. Two default development-mode browser
regressions also pass. Actual proxy screenshots were visually inspected.

Final focused verification passes 68 web checks, 20 backend checks (including
read-only PostgreSQL and fixture TLS), five Node isolation/cleanup checks, deployment
and source-policy checks, generated contracts, scoped lint/format and docs links.
The ordinary production build and frontend types pass; changed Python files pass
strict typing. Independent review tightened child-only write-authorization controls
and temporary-file cleanup. Synthetic fixtures establish local behavior. Full
combined-baseline/remote CI and hosted model readback remain unverified. Production
model acceptance retains its owner gate. Keep completed PRs stable for review.

## Original PR 26 handoff before owner-requested consolidation

# Active workstream

## Data and ledger local release candidate — INTEGRATE

- Branch `codex/portfolio-data-ledger-capabilities`, based on main `395f842`.
- Completed PR #25 remains frozen for owner review. Its receipt adapter is required
  before real provider previews on the minimal production baseline. Integrate after
  owner merge, preserving this branch's capability roadmap.
- [PR #26](https://github.com/paulzwecker/portfolio-app/pull/26) is the cohesive local
  implementation integration boundary. Require all checks, then freeze it for owner
  review. Hosted coverage and ownership activation remain owner-gated.

## User workflows delivered locally

- C2.2 bounded provider-only market/FX cycles, frozen correction/retry scopes,
  durable diagnostics and inspectable Portfolio/Operations valuation gaps.
- C3.1 held/Watchlist SEC scopes, filing-before-facts recovery, per-issuer provenance,
  coverage and company-scoped refresh eligibility with visible terminal outcomes.
- C2.3 exact account opening/settled activity/ending reconciliation, immutable saved
  candidates and explicit accept/reject/correction history. A separate, hash-bound
  whole-portfolio publication command produces canonical holdings and an ownership
  receipt. Manual/observed and full-workbook writers are blocked after cutover.
  Original opening and strategic targets retain independent provenance/authority.
- Browser controls require rationale, evidence/recovery acknowledgements and exact
  typed publication confirmation. Ambiguous responses recover through read-only
  receipts and clear approval inputs. Mutation retries remain explicit.

Detailed increment results are in the
[dated BUILD evidence](../history/data-ledger-build-through-2026-11-08.md).

## Integration findings and verification

- Main, open PRs, clean feature lineage and public repository visibility verified.
- The disposable loopback `_test` server is PostgreSQL 18.3 with matching client
  tools. Tests use random isolated schemas and a process-only test DATABASE_URL.
  The local role lacks CREATEROLE/CREATEDB, leaving privilege-dependent tests for CI.
- Full `npm run check` passes, including 294 web checks, 810 API unit checks with two
  Windows-specific skips, strict types, formatting/lint, repository policy,
  generated contracts, script tests and production build. Toolchain pins match.
- The pre-fix full PostgreSQL sweep passed 336 checks with four privilege skips
  and found one historical-schema bootstrap regression. That defect is corrected
  and both reviewed old heads pass. Thirty-four distinct schema/publication cases
  and 46 release-safety checks pass after correction. Missing ownership storage at
  current/unknown/intermediate ledger revisions blocks writes; existing ownership
  wins over an older schema marker. CI must rerun the complete current suite.
- Browser regression passes 71 enabled desktop/mobile checks; 29 fixture/live-only
  checks are gated. Eight actual-API SEC/ledger journeys and two dedicated valued
  Portfolio journeys pass with unchanged protected-state hashes. A wrong-fixture
  selection was rejected by the Portfolio test and rerun against its declared
  market fixture. Screenshots inspected; ignored evidence stays in
  `.cache/milestone-integration`. Both fictional schemas shut down normally.
- Recovery inventory now includes all three ledger tables. The read-only production
  migration preflight is pinned to the current project and `9f2a6d4c81b7` →
  `b59f16c8a203`, with fresh recovery, exact confirmation and write controls retained.
  The runbook separates database verification from post-deployment readiness.

The first Linux PostgreSQL run exposed a test-harness identity mismatch through
Docker port publishing. The fixture now attests the existing CI PostgreSQL 18
container, its running state, server address and exact loopback-published port
using the existing container ID. Remote/overridden URLs, mismatched ports, images,
addresses and missing metadata fail closed. Production verification continues
through the existing database-target guard. Fifty-one focused fixture/storage
checks and strict mypy pass before the full CI rerun.

## Release and next action

1. Require PR #26's GitHub quality/PostgreSQL/Windows checks and Vercel Preview.
   Keep passing implementation frozen during owner review; avoid new feature work
   on this completed PR. The full local quality/build and browser checks are
   complete. Linux CI supplies the final full DB rerun and privileged role/restore
   coverage. Current check results remain visible on the PR.
2. Owner reviews/merges #25 first. Integrate its receipt fix after merge, resolve
   roadmap conflicts semantically and reverify the milestone PR before owner merge.
3. Before merging schema-dependent code, independently verify native deployment
   freezes, current production head/counts and a fresh current-state recovery point.
   Use the reviewed [deployment/migration runbook](../deployment-and-migrations.md).
   This branch adds `a832e94d6f10` then `b59f16c8a203`; production was last verified
   at `9f2a6d4c81b7`. Recovery creation, migration and deployment require authorization.
4. Highest-value operational follow-up is held-listing price/FX enrichment and two
   monitored refresh cycles including restart. Real SEC identities/coverage and
   ledger account/basis/source review are separate prerequisites. Provider scope,
   scheduling, source ownership, imports and investment/model acceptance retain
   independent owner gates. C2.4 accounting and C2.5 performance remain outstanding.

Use [the ledger contract](../portfolio-ledger.md), [recurring operations](../recurring-operations.md)
and [SEC bootstrap](../fundamentals-source-bootstrap.md) for behavior/commands.
