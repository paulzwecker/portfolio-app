# Active workstream

## Personal Universe design system — BUILD

The independent `codex/personal-universe-design-system` worktree starts at current
main `deda2ce`; [PR #27](https://github.com/paulzwecker/portfolio-app/pull/27)
retains the separate ledger/release work. Owner reference screenshots stay untracked
in the original workspace. The shared token palette, accessible appearance selector,
interactive component reference and Portfolio holdings search are under review.
The design contract is [here](design/design-system-and-frontend-architecture-11b.md).
Next: complete focused light/dark and mobile verification, independently review,
then run integration checks and open a single design PR. No production action.

The following PR #26 context is retained as historical evidence; it was merged.

## Consolidated Portfolio release candidate — INTEGRATE

The owner requested latest-work consolidation on 2026-11-08.
Branch `codex/portfolio-data-ledger-capabilities` updates the existing
[PR #26](https://github.com/paulzwecker/portfolio-app/pull/26), based on main `395f842`.
It includes the original PR #26 scope, PR #25's receipt adapter through `7d4ce2e`,
the CI-classification branch through `f72729e`, and native sensitivity/authenticated
proxy verification through `78dcf1b`. All predecessor branches and commits remain.
PR #25 stays separately reviewable; its dependency is included in this candidate.

## Product position

- M1/C0 minimal canonical holdings, cash and strategic targets are production-verified
  for the recorded Nov 7 baseline. Preserve that accepted state.
- C2.1/C2.2 bounded market/FX refresh and C3.1 SEC coverage workflows are implemented.
  Current production observations, issuer mappings and operational cycles require
  their own live verification and execution approval.
- C2.3 reconciled ledger candidates/reviews and separately confirmed whole-portfolio
  publication are implemented. Account/source/basis review and ownership activation
  retain separate gates. Dividends, transfers, broker imports, cost basis/gains and
  TWR/XIRR remain future work.
- C1.3 read-only native DCF sensitivity is implemented, including exact revision
  forwarding and authenticated Next.js → verified HTTPS fixture → UI tests.
  P-GOOGL investment acceptance remains an owner decision.
- C5.2 restores 32 database cases omitted by prior CI selection and enforces explicit
  classification. Managed authenticated fixtures use child-only credentials and
  an ephemeral loopback test CA. Personal Universe extraction/App Hub follows a
  useful Portfolio application and sufficient operating safeguards.

## Verification state

Combined `npm run check` passes with 307 web and 831 API unit cases, two local
Windows-specific skips, strict types (211 backend files), lint/format, generated
contracts, source policy, script tests and production build. The skips are Windows
symlink creation and POSIX-only credential modes. Managed production-mode browser
regression passes 89 cases with 29 explicit fixture/live-only skips. Ten additional
real FastAPI/PostgreSQL desktop/mobile journeys pass across valued Portfolio,
ledger preview and SEC data, preserving protected-state hashes. The local full
PostgreSQL sweep passes 376 cases with four privilege-dependent skips (CREATEDB /
CREATEROLE). Linux CI passes all 380 PostgreSQL cases and all 833 unit cases.

Conflicts were resolved by retaining the
ledger ownership validators, SEC endpoints and exact sensitivity model/revision
checks together. OpenAPI/TypeScript contracts are regenerated from the merged API.
The [dated evidence](history/data-ledger-build-through-2026-11-08.md) preserves
predecessor checks, historical source/production previews and their limitations.
Independent contract review preserves every original release API path/schema and
adds only one sensitivity endpoint and three output schemas. AST review preserves
130 test function bodies in the ten classification modules. Integration review
also disables the newly combined real-API opt-ins in managed synthetic mode, with
five isolation/cleanup checks passing. Code `a952d60` passes all three
[GitHub CI jobs](https://github.com/paulzwecker/portfolio-app/actions/runs/42471476408)
and Vercel Preview. Require the latest PR-head checks before owner review/merge.
Local PostgreSQL checks use independently verified loopback `_test` infrastructure
and disposable schemas. Private source packages and diagnostics stay outside Git.

## Release prerequisite and owner gates

1. Review the consolidated PR and its latest GitHub/Vercel checks.
2. Before merging schema-dependent code, verify native provider deployment freezes,
   current production identity/head/counts and a fresh recovery point protecting
   accepted holdings/targets. Follow the existing
   [deployment/migration procedure](deployment-and-migrations.md).
3. The exact additive chain is `9f2a6d4c81b7` → `a832e94d6f10` → `b59f16c8a203`.
   The last recorded production head is `9f2a6d4c81b7`; current cloud state is
   unverified in this consolidation. Recovery creation, production migration and
   deployment require separately scoped authorization. The historical pre-import
   branch contains empty canonical state and cannot protect the accepted portfolio.
4. After approved migration, verify schema/metadata and unchanged accepted records
   before the matching native deployments. Verify exact code SHA, Render readiness,
   authenticated Vercel health and read-only investor journeys before acceptance.
5. Keep ingestion, manual/recurring operations, Sheets polling and production-write
   authorization disabled. Data population, model acceptance and ledger ownership
   each need their own reviewed scope and approval.

The highest-value operational follow-up is held-listing price/FX enrichment with
two monitored refresh cycles, then reviewed SEC identities/coverage. Current recovery
and execution approvals gate those operations. Use the [ledger contract](portfolio-ledger.md),
[recurring operations](recurring-operations.md) and
[SEC bootstrap](fundamentals-source-bootstrap.md) for domain behavior and commands.
