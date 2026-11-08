# Capability roadmap and execution ledger

Updated 2026-11-08. [Product vision](docs/PRODUCT_VISION.md) owns the North Star.
[Architecture](docs/architecture/personal-universe.md) owns shared-platform boundaries.
[Documentation index](docs/README.md) routes contracts and runbooks.

## Execution cursor

| Field                       | Current value                                                                                                                                                                                             |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Active checkpoint           | C1.3 read-only native DCF sensitivity — BUILD. [Handoff](docs/financial-models.md#current-build-checkpoint)                                                                                               |
| Branch / PR                 | `codex/native-dcf-sensitivity`, from merged main `395f842`. Local BUILD branch                                                                                                                            |
| Implementation              | Revision-bound nine-cell API LOCAL_VERIFIED. Responsive valuation workspace in progress                                                                                                                   |
| Next ready substantial task | Verify scenario switching, unavailable cells, stale responses and desktop/mobile presentation; commit the complete local slice                                                                            |
| Parallel owner gate         | Completed [PR #25](https://github.com/paulzwecker/portfolio-app/pull/25) and [PR #26](https://github.com/paulzwecker/portfolio-app/pull/26) await review/merge. C1 investment acceptance remains separate |
| Integration rule            | Keep completed PRs stable. Reconcile this independent slice and the preserved CI correction with latest main at the integration gate                                                                      |

PR #24 is merged as `395f842`. The completed data/ledger PR #26 stays frozen.
The independent PostgreSQL test-classification correction is preserved on
`codex/ci-database-test-coverage` in `18930ac` and `f72729e`, with its verified
handoff in that branch's testing reference. This branch adds a user-facing C1
review capability independently of the pending schema/data work.

C1.3's API calculates nine hypothetical fair-value combinations with the existing
UFCF engine and accepted inputs. It requires an exact current revision, preserves
probabilities/operating inputs/tail assumptions, and exposes invalid combinations
as unavailable. Nineteen focused backend checks pass, including an API test under
PostgreSQL read-only enforcement on verified loopback PostgreSQL 18.3. Accepted
model readback is unchanged. Focused strict typing passes. This evidence establishes
local calculation and read semantics; responsive browser verification is next.

## How to choose work

Choose a reasonably substantial ready slice of the highest-value incomplete
capability below. Inspect its actual code, data, source rights and approvals first.
Deliver an end-to-end user outcome with reconciliation and readable failure states.
A new abstraction or preview layer needs a demonstrated missing capability.
An owner gate on one model does not block independent market/fundamental work.

Implementation means code exists. `LOCAL_VERIFIED` requires applicable isolated
checks. `LIVE_SOURCE_VALIDATED` requires actual source evidence.
`PRODUCTION_PREVIEW_VERIFIED` establishes a read-only proposal on a verified target.
`OPERATIONALLY_VERIFIED` / existing `PRODUCTION_VERIFIED` requires reconciled hosted
readback for the stated scope. `PARTIAL`, `MISSING` and `UNVERIFIED` describe gaps.
A capability may be locally verified while its production population is unverified.

## Evidence-backed capability inventory

This is a repository/evidence audit, not a new live-cloud inventory. The
[Nov 7 baseline](docs/production-canonical-baseline.md) verifies 209 companies,
23 securities/listings, 22 holdings, two currency-specific cash rows and 16 targets.
M1 imported no enrichment or models. That exclusion does not prove their current
live tables are empty. October local coverage reports cannot establish new Neon
coverage. Reverify target, source versions and actual counts before operations.

| Capability                           | Implemented / verified outcome                                                                                                         | Outstanding outcome                                                                                                                                                                           |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity, holdings, cash, targets    | OPERATIONALLY_VERIFIED for M1 minimal scope, receipts, zero reconciliation differences and owner UI readback                           | Ongoing source synchronization and decision-grade valuation                                                                                                                                   |
| Prices, FX, corporate actions        | Implemented / LOCAL_VERIFIED, bounded Yahoo/FX bootstrap, exact listings, checkpoints and action provenance                            | Production coverage/refresh UNVERIFIED. Action verification and FX/ADR exceptions remain explicit. [Contract](docs/historical-market-data-bootstrap.md)                                       |
| Statements, fundamentals, filings    | Implemented / LOCAL_VERIFIED SEC facts/submissions and financial explorer                                                              | PARTIAL international coverage. Production scope UNVERIFIED. [Contract](docs/fundamentals-source-bootstrap.md)                                                                                |
| Consensus                            | Implemented domain/adapter and local tests                                                                                             | Approved provider access/rights and live coverage UNVERIFIED. Keep unapproved FMP disabled. [Contract](docs/consensus-estimates.md)                                                           |
| Independent native models            | Three methods LOCAL_VERIFIED, real P-GOOGL package parity and recorded production preview, merged publication foundation               | First accepted production-native model has no recorded acceptance evidence. Dated assumptions, fiscal alignment and method review remain owner-gated. [Contract](docs/model-publications.md)  |
| Thesis, research, assessments        | Implemented / LOCAL_VERIFIED claims, evidence, contradictions, histories and review                                                    | Representative real research-to-thesis-to-model workflow and population UNVERIFIED. [Contract](docs/research-to-model.md)                                                                     |
| Rankings, allocation, Execution Pace | Implemented / LOCAL_VERIFIED engines and decision UI                                                                                   | Eligible current models, market facts, lifecycle, independent scores and confirmed holdings. Multi-model ambiguity stays blocked until approved policy. [Semantics](docs/return-semantics.md) |
| Alerts and temporal history          | Implemented in-app attention/trigger/history views                                                                                     | Real source-backed coverage UNVERIFIED. Notification delivery MISSING and channel/policy undecided. [Contract](docs/attention-center.md)                                                      |
| Exposure and performance             | PARTIAL company/listing/cash composition and concentration                                                                             | Broader classifications/exposure and genuine transaction-backed performance MISSING. [Limits](docs/portfolio-dashboard.md)                                                                    |
| Cloud operations and security        | Durable manual jobs, workers, sync receipts, CI, guards and model role separation locally verified. M1 authenticated readback recorded | Current-state recovery, hosted roles, monitoring, retention and workstation-independent job execution need operational proof. [Runbook](docs/recurring-operations.md)                         |
| Personal Universe                    | Existing design tokens, shell, typed contracts and shared web/API/DB footprint are foundations                                         | App Hub, app registry, reusable module template, unified personal sessions and second app MISSING. [Target](docs/architecture/personal-universe.md)                                           |

## Capability milestones and acceptance

C identifiers organize outcomes. Historical M/MP/R identifiers remain valid evidence
references through the linked ledgers. They do not create a second execution queue.

| Milestone                                 | Acceptance and dependencies                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C0 Canonical ownership baseline           | COMPLETE for M1 scope. Preserve accepted identities, holdings/cash/targets and receipts. Enrichment remains separate                                                                                                                                                                                                                                                                                                                     |
| C1 Trustworthy model lifecycle            | Existing M2/MP1/MP2 implementation. Review one real model's dated assumptions, establish approved base, prove published revision → native validation → independent review → immutable accepted revision → hosted history/readback. Verify replay/conflicts and separate computational parity from investment judgment. Owner acceptance and a current recovery point gate production operations                                          |
| C2 Useful daily portfolio                 | Build on C0. Reconcile current/historical exact-listing prices, dated FX and corporate-action evidence for reviewed holdings/Watchlist scope. Verify EUR value, weights, cash, strategic gaps, freshness and confirmation workflow on desktop/mobile. C2.1 previews/recovery assessment are ready independently of C1 acceptance. Ingestion/apply need separate authorization                                                            |
| C3 Source-backed business research        | SEC and reviewed international filings/statements, permitted consensus, source dates and fiscal/currency semantics. Populate representative claims, thesis breakers, questions and independent assessments with history and evidence. Review coverage and exclusions explicitly. Financials → thesis/research → valuation drill-down must work. Source rights and each ingestion/research acceptance gate their operations               |
| C4 Explainable investment decisions       | Depends on relevant C1–C3 inputs. Prove valid methodology cohorts, rankings, target/current allocation context, research queue, actionable alerts and Execution Pace with evidence and blockers. Verify agent publication/proposal → separate reviewer decision. Preserve actual decision inputs/history. Genuine performance and broader exposures require their source history/classifications and remain visible gaps until supported |
| C5 Operational maturity                   | Cross-cutting from C1 onward. Before writes verify authenticated authority, current-state recovery and rollback. Before unattended jobs prove bounded cloud execution, idempotent retries, retention, monitoring, failure recovery and costs without a Windows workstation. Verify current hosted roles, production read-only journeys and restore in disposable infrastructure. Policy/scheduling activation stays owner-gated          |
| C6 Shared foundations and private App Hub | Follows useful Portfolio C1–C4 scope and sufficient C5 safeguards. Extract proven generic UI/auth/API/DB patterns incrementally. Deliver authenticated app registry/launcher and app-scoped navigation/permissions while preserving Portfolio deep links, ownership and regression coverage. Prefer the existing shared stack. Earlier foundation work needs a concrete Portfolio consumer                                               |
| C7 Additional personal apps               | After C6, prove one useful second app with an authenticated complete workflow, app-owned data/migrations, audit and cross-app tests on the shared deployment. Add a generator/template when proven repetition warrants it. Review any infrastructure split against cost/isolation evidence                                                                                                                                               |

## Immediate priorities and gates

1. **Daily portfolio data.** C2.1 assesses current held-listing mappings, prices,
   dated FX, ADR/action evidence, bounded ingestion scope and current-state recovery
   read-only. Reuse existing tools. After separate authorization, reconcile actual
   values/weights and verify the investor journey. This can advance during C1 review.
2. **First real model lifecycle.** C1.2 uses private P-GOOGL review evidence to
   resolve dated assumptions/fiscal/method issues. The recorded recommendation is
   DEFER. Preserve it until an explicit owner decision. MP2.1 preflight is locally
   verified in PR #24. Real onboarding still needs reviewed source/base and acceptance.
3. **Company evidence to decisions.** C3 first verifies issuer coverage and a bounded
   filings/fundamentals plan, then proves a real thesis/research/assessment workflow.
   Consensus needs permitted access. Feed C4 only through approved domain inputs.

C5 is a prerequisite within each applicable priority. The recorded pre-import
recovery branch expires **2026-11-14 09:54 CET** and predates accepted holdings.
It is not evidence of recoverability of the current canonical portfolio. Reverify
retention and prepare an owner-approved current-state recovery procedure before
further production writes. No branch creation/restore is authorized by this plan.
Automatic promotion (historical MP3) follows proven reviewed history and an explicit
policy decision. It has lower priority than useful market, research and decision coverage.

## Evidence and upkeep

- [Production baseline](docs/production-canonical-baseline.md) owns M1 scope and recovery history.
- PR #23 merged with independent models/publication review and passing CI. PR #24
  contains MP2.1 preflight on `c7b9fb2` with passing [CI](https://github.com/paulzwecker/portfolio-app/actions/runs/42395071764), isolated tests and private replay semantics.
- Owner-requested vision/capability alignment on 2026-11-07 inspected code and dated
  evidence, corrected stale release/auth/migration claims and preserved the prior
  ledger. Independent review, 134-file link validation, documentation tests, five
  deployment-policy tests and whitespace checks pass. This assessment is read-only
  and establishes no new live production coverage.
- [Ledger through MP2.1](docs/history/roadmap-through-mp2-preflight-2026-11-07.md)
  preserves detailed implementation/test evidence. [Original ledger](docs/history/roadmap-through-mp1.md)
  preserves earlier task definitions. Dated reconciliation reports retain their original scope.

After each substantial slice, update this cursor and the affected capability row
with evidence, limitation and next ready action. Keep commands in runbooks, outcomes
in the vision, boundaries in architecture and long results in dated history.
Reassess C1–C7 at integration. Keep completed PRs stable for owner review. A green
PR never grants production, source-edit, acceptance, migration or activation authority.
