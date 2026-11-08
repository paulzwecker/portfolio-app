# Active workstream

## Personal Universe design system — INTEGRATE

The independent `codex/personal-universe-design-system` worktree starts at current
main `685fa7a` after merging [PR #27](https://github.com/paulzwecker/portfolio-app/pull/27)
which contains the separate ledger/release work. Owner reference screenshots stay untracked
in the original workspace. The shared token palette, accessible appearance selector,
interactive component reference and Portfolio holdings search are locally verified.
The design contract is [here](design/design-system-and-frontend-architecture-11b.md).
`npm run check` passed (314 web tests, 899 backend units, two skips). Managed browser
regression passed 91 tests with 35 explicit fixture/live-only skips. Synthetic
desktop/mobile screenshots were visually reviewed outside Git; appearance, search,
drawer keyboard handling and 320 px overflow checks pass. The full production
release and recovery controls remain separate. [PR #28](https://github.com/paulzwecker/portfolio-app/pull/28)
requires CI and owner review; keep production frozen. No production action.

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

The [release runbook](deployment-and-migrations.md) records evidence, exact
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
Exact contracts live in the [ledger reference](portfolio-ledger.md).

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
[native release/migration controls](deployment-and-migrations.md), with fresh
current-state recovery protecting accepted holdings before separately authorized
migration/deployment. The empty pre-import recovery branch is insufficient.
Production writes, provider activation, source ownership and model acceptance keep
separate gates. Local production/rehearsal/background flags stay disabled.
Highest-value operational follow-up remains held-listing price/FX enrichment and
two monitored refresh cycles, followed by reviewed SEC identities and coverage.

## Independent C2.2 history coverage — BUILD

`codex/market-history-coverage` starts at main `685fa7a` and is independent of the
completed, owner-review design PR #28. Historical bootstrap receipts now distinguish
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
No production or provider operation ran. Next: establish reviewed session-aware
source validation before claiming complete history; separately approve live ingestion.
