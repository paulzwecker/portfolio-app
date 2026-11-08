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
[dated BUILD evidence](history/data-ledger-build-through-2026-11-08.md).

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
   Use the reviewed [deployment/migration runbook](deployment-and-migrations.md).
   This branch adds `a832e94d6f10` then `b59f16c8a203`; production was last verified
   at `9f2a6d4c81b7`. Recovery creation, migration and deployment require authorization.
4. Highest-value operational follow-up is held-listing price/FX enrichment and two
   monitored refresh cycles including restart. Real SEC identities/coverage and
   ledger account/basis/source review are separate prerequisites. Provider scope,
   scheduling, source ownership, imports and investment/model acceptance retain
   independent owner gates. C2.4 accounting and C2.5 performance remain outstanding.

Use [the ledger contract](portfolio-ledger.md), [recurring operations](recurring-operations.md)
and [SEC bootstrap](fundamentals-source-bootstrap.md) for behavior/commands.
