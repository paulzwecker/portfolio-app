# Historical handoff through the market-history BUILD checkpoint

## Historical Personal Universe design system checkpoint

The independent `codex/personal-universe-design-system` worktree starts at current
main `685fa7a` after merging [PR #27](https://github.com/paulzwecker/portfolio-app/pull/27)
which contains the separate ledger/release work. Owner reference screenshots stay untracked
in the original workspace. The shared token palette, accessible appearance selector,
interactive component reference and Portfolio holdings search are locally verified.
The design contract is [here](../design/design-system-and-frontend-architecture-11b.md).
`npm run check` passed (314 web tests, 899 backend units, two skips). Managed browser
regression passed 91 tests with 35 explicit fixture/live-only skips. Synthetic
desktop/mobile screenshots were visually reviewed outside Git; appearance, search,
drawer keyboard handling and 320 px overflow checks pass. The full production
release and recovery controls remain separate. [PR #28](https://github.com/paulzwecker/portfolio-app/pull/28)
merged as `aef3572`; the independent C2.2 branch integrated it. Keep production
frozen. No production action was performed by this workstream.

The following ledger and release notes preserve historical evidence from PR #27.

## Historical C2.3 settled multi-account ledger checkpoint

The prior branch `codex/portfolio-ledger-income` was based on main `deda2ce`, the merge
of [PR #26](https://github.com/paulzwecker/portfolio-app/pull/26). The combined
work was merged in [PR #27](https://github.com/paulzwecker/portfolio-app/pull/27).
Preserve all predecessor branches, stash and private files.
Income was committed through `0a57454`, cash transfers through `c9f58d7`, and
security-transfer implementation starts at `35c902e`.

## Historical incident investigation and migration preflight

November 8 read-only investigation confirms Render rejected main `deda2ce` and
continues serving healthy `395f842`; Vercel production already serves `deda2ce`.
Owner health readback is OK, but the ledger page reports missing records and the
expected Render ledger-anchor endpoint returns 404. Candidate logs contain 85
schema mismatches. Neon remains `9f2a6d4c81b7`, with the accepted 209 companies,
22 positions, two cash rows and 16 targets totaling 1. The older recovery is empty
and predates import. Private full inventory and 11 canonical content fingerprints
are retained outside Git. Automated authenticated browser inspection was blocked.

The [release runbook](../deployment-and-migrations.md) records evidence, exact
read-only preflight and owner-gated freeze → fresh populated recovery → migration
→ reconciliation → native deployment. Repository-only schema attestation/gate is
LOCAL_VERIFIED with 16 deployment-policy checks, 55 readiness/preflight tests and
three disposable PostgreSQL migration/replay tests. Docs and privacy checks pass.
Applied migration history matches all 57 files in the live API commit.
At that checkpoint the marker remained at the old head, so `deploy` failed closed.
The initial investigation made no provider, recovery, schema or canonical changes.
Keep this correction on the same milestone branch; no separate minor PR.

Owner-authorized phase 1 subsequently passed at 14:21 CET on November 8. Render
Auto-Deploy Off and Blueprint Auto Sync No were already set and independently
verified. The Vercel ignore command was corrected to freeze production and retain
Preview builds. Exactly one new recovery branch clones populated production. All
95 public tables, schema and data fingerprints match; production before/after
comparison has zero differences. Existing read-only recovery guards pass, TLS
verify-full and credentials are verified, and effective Neon permission is ADMIN.
Full IDs, lineage/LSN, receipts, comparisons and next-preflight manifest stay in the
private incident store. The root .env recovery URL still identifies the older branch.

Phase 2 passed `db:production-preflight -- readonly` and `-- migration-preflight`
(exit 0) from a separate clean main worktree at full SHA
`deda2ced13df8ef0874df2727cca0d050ab6c164`. Pinned code paths and matching locked
dependencies were verified while reusing the existing runtime without syncing it.
New recovery secrets lived only in child environments. Independent comparisons
again match all 95 table counts/content/schema fingerprints against phase 1, and
the migration guard's full ownership/privilege inventory passes. An auxiliary script
quoting error was corrected before that comparison executed. Existing accepted
counts/receipts and target total remain intact. Expected scope is three empty new
tables, two indexes and the controlled Alembic version-row update to `b59f16c8a203`.

At the phase-2 checkpoint, the next action was separate owner approval of the
migration and matching API deployment. Recovery freshness ended November 8 at 18:19:38 CET;
expiry is November 15 at 14:18:37 CET. A future migration requires a fresh recovery
point and separate authorization. Restore remains unexercised; project PITR history is 24 hours.
All freezes and write/background restrictions remain in place. Private phase-2
reports retain exact identities and comparisons; the root .env remains unchanged.
The durable schema hook still needs reviewed integration/installation; preserve
the independent ledger INTEGRATE checkpoint and one cohesive PR.

## Incident resolution and release safety

The owner authorized one migration and one Render deployment. At 14:11 UTC on
November 8, production schema `b59f16c8a203`, Render `deda2ce`, health, owner
frontend readback and all 98 table fingerprints reconciled. Prior incident and
preflight sections above retain historical evidence. Production freezes remain
active. No source data or credentials are recorded here.

The local release attestation now reflects the verified schema. CI checks Vercel
configuration for freeze overrides, and tests exercise the actual ignored-build
hook. Eighteen focused deployment-policy tests, the documentation checks and three
source-data policy tests passed. The hook does not wait for main CI and a repository override can bypass the
project setting. Configure and verify Vercel GitHub Deployment Checks for all three
CI jobs before any owner-authorized unfreeze. Review the activation sequence and
limitations in the release runbook. Provider settings and a live failed-check test
remain owner-gated.

The recovery review confirmed the existing full-archive toolkit only accepts a local
source. PostgreSQL 18 `pg_dump` and `pg_restore` version probes passed locally; this
does not verify any production backup or restore. The populated Neon branch expires
November 15 at 14:18 CET and predates the current schema. The release runbook now
records retention, independently stored backup and isolated restore rehearsal gaps.
Twenty-one focused release/recovery checks pass. Owner decisions and separate
authorization are needed before establishing or rehearsing durable protection.
The comprehensive `npm run check` passed (899 backend units and 311 web tests;
two backend tests skipped). Three PostgreSQL archive/restore integration cases
passed separately on a disposable loopback PostgreSQL 18 cluster with required
test privileges. Both PowerShell wrapper smoke tests passed. A full 389-case
PostgreSQL integration run was started but not completed; retain the earlier
79-case ledger evidence below and require the complete selection in CI. The 79-case
ledger selection was independently rerun and passed; six managed authenticated
desktop/mobile browser checks passed against local synthetic services.

Next price/FX slice is the existing read-only, target-bound market-data preview of
all held listing crosswalks and required FX pairs using a reviewed date window.
Keep reports private. Provider requests, run preparation, writes and scheduling
require separate approval. Resume the ledger integration checkpoint below without
discarding it.

## Complete bounded scope

The existing preview → saved candidate → explicit review → separately confirmed
publication workflow supports v2 DIVIDEND, TAX, CASH_TRANSFER and SECURITY_TRANSFER.
Exact contracts live in the [ledger reference](../portfolio-ledger.md).

- Income uses observed settlement currency and explicit gross/fees/withholding.
  Native cash and quote currency retain their independent meaning.
- Paired transfers require two declared brokerage accounts and independent source
  records. Both legs match the same settled instant and exact amount/currency or
  listing/quantity. Evidence is duplicate-checked, hash-bound and reviewable.
- Cash transfers conserve portfolio cash; security transfers conserve portfolio
  quantities and all cash. Account-level reconciliation and chronological overdraft/
  short-position checks remain blocking, including full-transfer explicit zero rows.
- Security transfers require `basis_status=UNAVAILABLE`. Retain original lot/cost
  evidence privately for future reviewed accounting. Native dates/costs/gains stay
  unavailable. Cross-listing/ADR conversion, in-transit, external and FX transfers
  remain follow-on contracts. Fees/taxes need separately evidenced cash records.
- Candidate acceptance retains canonical snapshot/target authority. Publication
  keeps its independent typed confirmation, recovery/ownership attestations and
  database guard. No new schema migration is introduced by this branch.

## Verified checkpoint

- 135 focused ledger units pass. Exact precision, missing/zero states, matching
  legs, duplicate source keys, ordering, listing/basis rejection and conservation
  are covered. Historical v1 trade, v2 income and v2 cash-transfer replay matches
  every output field from `c9f58d7`; existing frozen v1/v2 hash tests pass.
- All 79 focused PostgreSQL API/review/publication/income/transfer cases pass in
  independently verified loopback `_test` schemas. They cover immutable previews,
  explicit review, publication/replay, rollback, source/identity drift, correction
  acknowledgements and malformed packets leaving no records or receipts.
- 79 web contract/proxy/publication cases pass. Both evidence records and original
  financial text survive inspection, staging and readback.
- Two real-API desktop/mobile security-transfer journeys pass, with exact ten-place
  quantities, account drill-down, unavailable basis and both source records. The
  protected canonical-state hash is unchanged during review. Visual inspection
  confirms readable wrapping and no horizontal overflow. The bounded fixture
  removed its own schema on normal shutdown. Earlier income/cash browser evidence
  is recorded in the preceding commits.
- Strict backend mypy passes 217 source/test files. Web lint/types, generated
  contracts, formatting, documentation links/tests and whitespace checks pass.
- Independent review preserves identity, evidence, financial/ownership separation
  and production authorization. This is synthetic/local verification only.

## Historical ledger integration review

The bounded settled-ledger and release-safety scope is IMPLEMENTATION_COMPLETE /
LOCAL_VERIFIED. PR #27 passed its three GitHub jobs and was merged. Provider activation and durable production recovery remain
separately authorized work. Broker imports, normalized account
management, lots/gains, FX/in-transit rules and genuine TWR/XIRR remain subsequent
capabilities with their own source/policy dependencies.

## Separate operational gates

Cloud state was reverified read-only above. The merged release's reviewed chain remains
`9f2a6d4c81b7` → `a832e94d6f10` → `b59f16c8a203`. Follow
[native release/migration controls](../deployment-and-migrations.md), with fresh
current-state recovery protecting accepted holdings before separately authorized
migration/deployment. The empty pre-import recovery branch is insufficient.
Production writes, provider activation, source ownership and model acceptance keep
separate gates. Local production/rehearsal/background flags stay disabled.
Highest-value operational follow-up remains held-listing price/FX enrichment and
two monitored refresh cycles, followed by reviewed SEC identities and coverage.

## Independent C2.2 history coverage — BUILD

`codex/market-history-coverage` started at main `685fa7a` and now includes the merged
design PR #28 at main `aef3572`. Historical bootstrap receipts now distinguish
checkpoint execution from expected-session coverage and report normalized date span,
distinct dates and maximum calendar spacing without treating holidays/weekends as
missing. Old receipts and unavailable responses retain unknown evidence. Current
quotes remain excluded, and temporal quarantine cannot report stale span dates.
Read-only reconciliation rejects missing completed-batch/source provenance, wrong
listing or FX pair, unexpected domains, current quotes, out-of-window rows and
price/FX observations after retrieval, independently of receipt fingerprints.
Legitimate unavailable checkpoints can remain without a batch. Focused checks pass:
13 unit and 21 isolated PostgreSQL integration cases, strict mypy and Ruff. They
cover sparse windows, missing versus zero, corrupt receipts and read-only replay.
The subsequent raw-evidence increment verifies provider/domain and decoded payload
SHA-256, flags corrupt gzip and explicitly fails closed when a per-payload 64 MiB
verification budget is exceeded. Fourteen focused units and 24 PostgreSQL cases pass,
as do Ruff and strict mypy. These checks establish integrity, not source accuracy.
The following attention-feed increment prevents later-known corrections/observations
from changing an earlier price alert and skips corrected days, duplicate day records
and incompatible provider, symbol, currency or adjustment pairs. Alert time is when
both inputs were recorded; wording states exchange sessions are unverified. Nine
focused units and 12 isolated PostgreSQL cases, Ruff and strict mypy pass. No API
schema or migration is required; alerts can be more conservative with mixed sources.
Company Explorer now exposes the distinct market dates, first date and maximum
calendar spacing of its analytics inputs. Coverage remains `NOT_ASSESSED`; the UI
explains that holidays and weekends are included and missing sessions are possible.
The additive API fields tolerate older responses, and an empty set remains distinct
from absent evidence. Focused checks pass: 56 web cases, nine Python cases including
two isolated PostgreSQL cases, generated contracts and strict types; the synthetic
browser journey checks the notice and overflow at 390 and 1440 pixels. No migration
is needed. This is LOCAL_VERIFIED, not live coverage or calendar validation.
After integrating PR #28, the history query rejects duplicate market dates,
provider/symbol/currency stream changes and missing or conflicting listing currency.
Conflicting analytics and line charts become unavailable while observations remain
inspectable; this does not certify adjustment consistency or session completeness.
Thirteen focused Python cases (six isolated PostgreSQL), 57 web cases, strict types,
contract generation and responsive browser checks pass for clean and conflicting
states at 390 and 1440 px. The Execution Pace fallback independently refuses
conflicted analytics; its 23 focused unit cases pass. No schema migration is introduced.
The latest increment adds a Company Explorer review disclosure for conflicting
provider/symbol/currency streams and duplicate dates from the actual calculation
window, including sources outside the recent table. Selected-input scope is explicit;
other provider observations are not represented. Thirteen focused Python cases
(six isolated PostgreSQL), 58 web cases, types and generated contracts pass. A
synthetic browser journey validates the disclosure at 390 and 1440 px.
Synthetic desktop/mobile screenshots were visually reviewed; the chart panel now
distinguishes market status from quote freshness and labels the independently sourced
regime date. No private source values or screenshots were committed.
The next increment removes the former silent 60-row inspection limit: all returned
observations are searchable by date, provider, symbol, currency or quality, without
changing the chart range. Exact stored decimal text and adjustment basis are visible
in the shared responsive table/cards. Fifty-nine focused web checks, strict types,
lint and the synthetic mobile/desktop browser journey pass; the journey finds an
older conflict outside the selected 90-day chart range. Screenshots were visually
reviewed locally. No API contract or migration changed in this increment.
The subsequent provider-quality increment preserves listing and FX normalizer
warnings, marks affected imports/refreshes partial and shows a plain-language
warning in Operations. Legacy checkpoints without captured warning evidence remain
explicitly unknown; warning-only checkpoints do not silently retry. Synthetic tests
cover warning retention, replay and a local importer-to-Operations API readback with
unchanged canonical ownership. Expected-session coverage remains unassessed.
Verification passed 44 focused backend units, four isolated PostgreSQL cases,
nine web checks, strict types/lint and a read-only synthetic Operations browser
journey at 390 and 1440 px. Synthetic screenshots were visually reviewed.
No production or provider operation ran. Next: establish reviewed session-aware
source validation before claiming complete history; separately approve live ingestion.

Current increment: selected daily closes with different or missing adjustment
descriptions now block price analytics and chart; the source review exposes each
description. Exact matching does not prove split consistency or session coverage.
Fourteen focused Python tests passed against disposable PostgreSQL schemas, including
adjustment drift, unavailable labels and point-in-time selection. Fifty-five web
contract/component tests, generated-contract verification, strict web and backend
types, web lint, and a synthetic desktop/mobile browser journey passed. No migration.
The separately authorized Render release is live on `aef3572`; Vercel reported
Ready but alias and deployed-check enforcement remain unverified. Render auto-deploy
and Blueprint sync remain off. This BUILD work performs no production operation.

The next increment adds a bounded 2026 NYSE published-schedule comparison for exact
`NYSE` venues. It shows absent scheduled closes and selected dates outside the
schedule, with source hash, as-of date, observation time and partial-window scope.
Results are review candidates, not proof of missing trades; unplanned closures and
halts remain unknown. Unknown venues/years and earlier knowledge cutoffs remain
unassessed. Twenty-one synthetic backend tests including isolated PostgreSQL cases,
56 web tests and a desktop/mobile browser journey pass. No migration or hosted
change. Next: review additional venue calendars and durable observation provenance
before expanding coverage or claiming complete sessions.

Current increment adds the independently sourced 2026 `NASDAQ` holiday schedule,
without assigning it to `XNAS`, Nordic or other ambiguous venues. Published NYSE
and Nasdaq source bytes and immutable manifests are retained locally outside Git
under `%LOCALAPPDATA%/PortfolioResearch/reference-calendars`; this is not a backup.
The displayed observation times now match those actual captures. Nasdaq's source
does not state an as-of date and the UI displays that uncertainty. Schedule dates
remain review candidates, not verified sessions or full history coverage.
Twenty-four focused backend tests including isolated PostgreSQL cases, 57 web
checks, contract/type/lint checks and a synthetic desktop/mobile browser journey
passed. No schema migration or hosted changes.

Current BUILD increment adds source-hashed 2026 Deutsche Börse Xetra schedule
review for exact `XETRA` and its explicitly evidenced MIC `XETR`; it does not
map `XFRA`. The source PDF and immutable manifest are retained in the same local
evidence store. Separate source capture time and unstated as-of date are preserved.
Twenty-nine focused backend tests including isolated PostgreSQL, 58 web checks,
contract/type/lint checks and a synthetic desktop/mobile browser journey passed.
No schema migration or hosted changes. Next: preserve schedule revision history
and handle later schedule updates without changing earlier point-in-time reviews.

Current increment retains an append-only reviewed schedule catalog, pins normalized
schedule fingerprints, and selects the latest unambiguous version known at the
requested cutoff. Missing pins, altered historical entries, duplicate IDs or equal
observation times fail closed. A synthetic correction preserves earlier replay in
unit and PostgreSQL-backed query tests. The Company view exposes the revision ID,
source hash and schedule hash; legacy responses remain supported. Thirty-four focused
backend tests including isolated PostgreSQL, an additional 16-case calendar unit
run, 58 web checks, type/contract/lint checks and a desktop/mobile browser journey
passed. No source revision was accepted or production changed. Next: connect bounded
schedule evidence to the historical bootstrap/Operations workflow without treating
unassessed venues or unplanned closures as complete coverage.

The latest BUILD connects the latest historical bootstrap to a read-only Operations
review. At most 30 alphabetically ordered listing checkpoints are reviewed; the
omitted count and FX checkpoint count are explicit. Completed checkpoints require
matching frozen/current identity, listing currency, batch digest/provider, and
eligible price provider/currency before comparing 2026 dates within the first/last
selected close. Results do not reconcile provider payloads, establish full requested
window coverage, confirm actual trading or assess FX. Unsupported schedules,
incomplete checkpoints and excessive dates remain explicit. Ten synthetic isolated
PostgreSQL cases, 52 web checks and a desktop/mobile browser journey passed; no
schema, receipt, hosted setting or production data changed. Next extend review to
the full requested scope and more explicitly reviewed venues while preserving these
boundaries; live ingestion and deployment remain separately authorized.

The next BUILD enables run-pinned page navigation in Operations, with 30 listings
per request and an offset cap of 10,000. It checks the returned run/page against the
request and fails closed on mismatches. Pages are separately checked live reads,
not a shared transactional snapshot. Additional venues, full requested-window
boundaries and FX remain unassessed. Ten isolated PostgreSQL cases plus a rerun
with a newer run inserted, 52 focused web tests, strict types, and a synthetic
desktop/mobile paging journey passed. No schema or hosted change was made.

The latest BUILD separately compares the requested bootstrap window with the
time-appropriate 2026 schedule and exposes leading/trailing date candidates in
Operations. The prior selected-close-span review remains unchanged. The window is
clipped to the schedule and known-day cutoff; outside dates and empty series remain
unassessed, and candidate dates never establish missing trades. No receipt, schema,
provider or production state changes. Next improve empty-batch investigation and
add venues only with reviewed source evidence. Verification: 18 schedule tests, 10
isolated PostgreSQL cases, 53 focused web tests, generated contracts, strict types,
and a synthetic desktop/mobile Operations journey; no full-suite run in BUILD.

The current increment distinguishes unavailable, failed and blocked checkpoints
from pending work and displays sanitized, nullable receipt counts for response,
normalization and provider failures. Missing or malformed evidence stays unrecorded;
payload reconciliation, schedule coverage and retry execution are not implied.
Next connect existing read-only source reconciliation evidence to the Operations
investigation and extend venue schedules only with reviewed provenance. Seventeen
isolated PostgreSQL cases include the synthetic importer no-data and transport-failure
paths; 54 web tests, strict types, contract checks and a desktop/mobile browser
journey passed. No production or provider request was made.

The current BUILD adds an explicitly requested, read-only checkpoint reconciliation
to Operations, reusing existing payload, fingerprint and scope checks with bounded
rows and bytes. The result is scoped to stored evidence, not provider truth or full
coverage. Missing receipts and work exceeding interactive limits remain explicit.
Next extend reviewed schedule venues and assess the end-to-end milestone boundary.
Thirty isolated PostgreSQL cases passed, including tampered raw bytes and row scope;
the intact-batch case was rerun with missing-receipt and size-limit checks. Seven
focused backend units, 56 web checks, strict types/contracts and a synthetic
desktop/mobile journey passed. No production or provider operation ran.

## Integration and read-only assessment, November 8

### Historical market-data reliability integration

Branch `codex/market-history-coverage` includes current `origin/main` at
`aef35724120d63d608d6ffdc6f10f88d41eff27f`. The working checkpoint before integration
was `f28b1e2`. Repository visibility is public. Preserve predecessor worktrees,
the owner edits and private evidence. [Draft PR #29](https://github.com/paulzwecker/portfolio-app/pull/29)
contains the cohesive checkpoint. Implementation review commit is `9bf466c`.

This engineering checkpoint delivers an investor investigation workflow through
Company Explorer and Operations. It includes source-stream/adjustment conflicts,
searchable returned observations, bounded schedule review, provider diagnostics,
run-pinned pagination and explicitly requested checkpoint reconciliation.

### Integration acceptance

- Verify ordinary entry points, API authentication and PostgreSQL read-only behavior.
- Run repository checks, relevant PostgreSQL integration tests and desktop/mobile
  browser coverage. Inspect synthetic screenshots and fix review findings.
- Confirm migration files and model metadata stay compatible with the production
  schema contract. Record fresh live evidence separately from the recorded marker.
- Publish one cohesive PR after local acceptance. Owner review controls merging.

The engineering checkpoint is IMPLEMENTATION_COMPLETE and LOCAL_VERIFIED.
`npm run check` passed with 333 web tests, 929 backend units and two skips.
Relevant PostgreSQL integration covered 112 cases across the initial selection
and a focused rerun after fixture corrections. The full managed browser run passed
95 cases with 35 explicit fixture/live-only skips. The affected Operations journey
passed again at desktop/mobile widths. Synthetic screenshots were visually reviewed.

The second-pass review added alert checks for known adjustment labels and listing
currency, plus HTTP authentication/read-only transaction coverage. It corrected
fixture URL/receipt typing, auth-mode configuration and a numeric-correction fixture
to retain its economic adjustment basis. Mypy passes all 223 source/test files.

### Release assessment

Current classification is **CONFIGURATION_REQUIRED** pending current Vercel
release-control evidence and Blueprint sync confirmation. The earlier Neon
connection failure is resolved by the runbook's process-local certifi CA bundle.
On November 8 at 19:49 UTC the existing read-only target guard verified the exact
production project, branch, endpoint and `neondb.public` with TLS `verify-full`.
Live Alembic is `b59f16c8a203`, all 98 tables are present and mapped metadata has
no drift. Both offline schema-gate modes pass with an empty pending range.

Accepted counts remain 209 companies, 23 securities, 23 listings, one portfolio,
one snapshot, 22 positions, two cash rows, one accepted target revision and 16
allocations totaling 100%. Source and canonical bootstrap receipts each count one.
Prices, FX and native model revisions each count zero. Private evidence remains
under `%LOCALAPPDATA%/PortfolioResearch/private-reports`.

Fresh Render read-only inspection found the intended `portfolio-api` service on
`main`, live deployment `dep-dbobrqbl550s7399afg0` at `aef3572`, and Auto-Deploy
enabled with `checksPass`. Render uses the expected Neon target, TLS verification
and `/health/ready`. Both health routes return 200. Authenticated API reads return
209 Universe companies, one portfolio and a ledger anchor with its snapshot.
All inspected write, ingestion and background flags are disabled. GitHub effective
main rules require PRs, conversation resolution and the three strict CI checks.
Vercel CLI/frontend credentials were unavailable. The requested dashboard evidence
is its production commit/plan, required checks, exact ignore command and Blueprint sync.

Follow the existing [deployment runbook](../deployment-and-migrations.md). Hosted
setting changes, live provider activation, recovery operations and model acceptance
retain separate owner approvals. C2.2's hosted ingestion and two monitored refresh cycles
remain outstanding operational acceptance criteria.

### Next action

Draft #29 awaits owner review and the remaining release-control evidence. The code
head `1587ce0` passed all three GitHub jobs and Vercel Preview in CI run 113.
Documentation updates retain focused checks and require latest-head CI readback.
Additional venue schedules
require reviewed source evidence. Detailed earlier evidence and production recovery
history remain in the [historical handoff](market-history-build-through-2026-11-08.md).

### Bounded enrichment planning

The existing production read-only preview is READY for all 22 held listings and
the two required FX pairs, DKK/EUR and USD/EUR. It reuses the earlier diagnostic
window November 7, 2025 through November 6, 2026 for comparison. The plan has 24
logical provider scopes and zero unresolved mappings. It made zero provider
requests and database writes. The immutable private report hash is
`1cd4ddf9815e068343ab67c4baeca2e18d5c6bbeecede1e132d38576fa3ebdf5`.
Owner review must establish the actual first-run window, provider/retry budget and
current-state recovery before separately authorizing execution.

Canonical behavior lives in [market data](../market-data.md),
[historical bootstrap](../historical-market-data-bootstrap.md),
[attention](../attention-center.md) and the [roadmap](../../ROADMAP.md).

PR #29 was merged as `e0704068e7b437cff4530eff35374da689b66155` on November 8 at 20:23:59 UTC. The merged code head `9f8d9f1` passed all three GitHub CI jobs and Vercel Preview. Provider-control evidence and live enrichment retain their separate operational gates.
