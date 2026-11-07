# Capability roadmap and execution ledger

Updated 2026-11-07. [Product vision](docs/PRODUCT_VISION.md) owns the North Star.
[Architecture](docs/architecture/personal-universe.md) owns shared-platform boundaries.
[Documentation index](docs/README.md) routes contracts and runbooks.

## Execution cursor

| Field                       | Current value                                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Active checkpoint           | C2.2 provider-only cloud refresh — BUILD. [Handoff](docs/ACTIVE_WORKSTREAM.md)                                                                      |
| Branch / PR                 | `codex/portfolio-data-ledger-capabilities`, from main `395f842` (PR #24 merged)                                                                     |
| Implementation              | PARTIAL / BUILD. Bounded importer → EUR valuation/Operations API readback, same-day recovery and durable preflight monitoring locally verified      |
| Next ready substantial task | C2.2 local investor-journey and freshness presentation review, then milestone integration when its local acceptance is met                          |
| Parallel owner gate         | C1.2 P-GOOGL assumptions/base acceptance; C2 cutover/accounting policy and separately authorized production operations                              |
| Integration rule            | Keep completed PR #25 stable during review. Retain this local audit for the next cohesive implementation checkpoint; no minor documentation-only PR |

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
The recorded C2.1 read-only assessment in [PR #25](https://github.com/paulzwecker/portfolio-app/pull/25)
subsequently verified zero prices, FX, corporate actions, fundamentals, filings,
models and reviewed CIK mappings on the production target. Its candidate-code
preview resolved all 22 held listings and DKK/EUR plus USD/EUR; the receipt adapter
is awaiting merge. This review adds repository evidence, not a fresh live inventory.
Historical local reports and disabled configuration cannot prove hosted automation.
Reverify target, coverage, source rights and controls before activation.

| Capability                           | Implemented / verified outcome                                                                                                                                 | Outstanding outcome                                                                                                                                                                                                                                                                                            |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity, holdings, cash, targets    | OPERATIONALLY_VERIFIED for M1 minimal scope, receipts, zero reconciliation differences and owner UI readback                                                   | Ongoing source synchronization and decision-grade valuation                                                                                                                                                                                                                                                    |
| Prices and FX                        | Adapters, bounded backfill, exact crosswalks, raw provenance and dated observations LOCAL_VERIFIED; C2.1 mapping preview PRODUCTION_PREVIEW_VERIFIED on PR #25 | Production observations were zero at the recorded check. Apply #25 through owner review, authorize backfill, reconcile actual EUR valuation and prove incremental refresh                                                                                                                                      |
| SEC fundamentals and filings         | Company Facts/submissions, amendments, accession/provenance and financial explorer LOCAL_VERIFIED                                                              | Zero production facts/documents/reviewed CIK mappings at C2.1. Review issuer coverage; non-SEC coverage PARTIAL. Filing-body download is outside the existing bootstrap. [Contract](docs/fundamentals-source-bootstrap.md)                                                                                     |
| Consensus                            | Provider-specific snapshots, annual/quarterly FMP adapter, revision/continuity rules and tests implemented                                                     | FMP opt-in is DISABLED by default. Provider rights, issuer mapping, credentials and live coverage UNVERIFIED; historical estimate coverage cannot be invented. [Contract](docs/consensus-estimates.md)                                                                                                         |
| Corporate actions                    | Split/dividend provider evidence and separate adjusted/native price fields LOCAL_VERIFIED                                                                      | Events remain unverified; mergers/spinoffs/other unsupported actions and account-level processing need reviewed contracts. Provider dividends do not establish received cash or withholding. [Semantics](docs/historical-market-data-bootstrap.md#corporate-actions-and-adjustment-semantics)                  |
| Independent native models            | Three methods LOCAL_VERIFIED, real P-GOOGL package parity and recorded production preview, merged publication foundation                                       | First accepted production-native model has no recorded acceptance evidence. Dated assumptions, fiscal alignment and method review remain owner-gated. [Contract](docs/model-publications.md)                                                                                                                   |
| Thesis, research, assessments        | Implemented / LOCAL_VERIFIED claims, evidence, contradictions, histories and review                                                                            | Representative real research-to-thesis-to-model workflow and population UNVERIFIED. [Contract](docs/research-to-model.md)                                                                                                                                                                                      |
| Rankings, allocation, Execution Pace | Implemented / LOCAL_VERIFIED engines and decision UI                                                                                                           | Eligible current models, market facts, lifecycle, independent scores and confirmed holdings. Multi-model ambiguity stays blocked until approved policy. [Semantics](docs/return-semantics.md)                                                                                                                  |
| Alerts and temporal history          | Implemented in-app attention/trigger/history views                                                                                                             | Real source-backed coverage UNVERIFIED. Notification delivery MISSING and channel/policy undecided. [Contract](docs/attention-center.md)                                                                                                                                                                       |
| Exposure                             | Company/listing/cash composition and concentration PARTIAL                                                                                                     | Sector/geography/business-model classifications and broader exposure coverage need canonical sources. [Limits](docs/portfolio-dashboard.md)                                                                                                                                                                    |
| Cloud operations and security        | Durable manual jobs, dependency steps, locks/cooldowns/retries, heartbeat, sync receipts and Operations UI LOCAL_VERIFIED                                      | Recurring/cloud/manual/Sheets controls are disabled in the deployment template; hosted configuration needs reverification. No scheduled worker is configured there. Current-state recovery, bounded provider-only activation and monitoring require operational proof. [Runbook](docs/recurring-operations.md) |
| Transaction ledger and accounts      | MISSING. Runtime stores observed listing quantities and per-currency snapshot cash                                                                             | Purchases/sales, dividends, taxes/fees, deposits/withdrawals, paired transfers/FX and brokers/accounts need typed accounting and reconciled cutover                                                                                                                                                            |
| Cost basis and gains                 | MISSING. Optional cost-basis fields in early design are not ORM/API features                                                                                   | Evidenced lots, declared allocation/fee/tax/FX policy and realized/unrealized gains; unknown basis stays unavailable                                                                                                                                                                                           |
| Broker imports                       | MISSING. Workbook holdings import is implemented for snapshots                                                                                                 | One reviewed broker format first, immutable raw provenance, mapping/deduplication, preview, conflicts, atomic acceptance and statement reconciliation                                                                                                                                                          |
| Portfolio performance                | MISSING. UI and decision evaluation explicitly report unavailable                                                                                              | TWR/XIRR engines, flow/valuation timing, income/expense treatment, dated FX, coverage and benchmark semantics; model IRRs and price-only charts do not supply these                                                                                                                                            |
| Personal Universe                    | Existing design tokens, shell, typed contracts and shared web/API/DB footprint are foundations                                                                 | App Hub, app registry, reusable module template, unified personal sessions and second app MISSING. [Target](docs/architecture/personal-universe.md)                                                                                                                                                            |

## Capability milestones and acceptance

C identifiers organize outcomes. Historical M/MP/R identifiers remain valid evidence
references through the linked ledgers. They do not create a second execution queue.

| Milestone                                 | Acceptance and dependencies                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C0 Canonical ownership baseline           | COMPLETE for M1 scope. Preserve accepted identities, holdings/cash/targets and receipts. Enrichment remains separate                                                                                                                                                                                                                                                                                                                     |
| C1 Trustworthy model lifecycle            | Existing M2/MP1/MP2 implementation. Review one real model's dated assumptions, establish approved base, prove published revision → native validation → independent review → immutable accepted revision → hosted history/readback. Verify replay/conflicts and separate computational parity from investment judgment. Owner acceptance and a current recovery point gate production operations                                          |
| C2 Complete portfolio management          | Builds on C0. Deliver reconciled EUR valuation and monitored price/FX refresh, then broker/account activity, ledger-derived holdings, cost basis/gains and genuine TWR/XIRR. Preserve the verified snapshot and independent strategic targets. Staged acceptance follows below; production cutover, history import and activation remain owner-gated                                                                                     |
| C3 Source-backed business research        | Reviewed SEC/international issuer coverage, filings/statements, permitted consensus and refresh/coverage monitoring. Preserve fiscal periods, source timestamps, revisions and original evidence. Prove financials → thesis/research → independent valuation workflow. C3.1/3.2 below separate data readiness from research acceptance                                                                                                   |
| C4 Explainable investment decisions       | Depends on relevant C1–C3 inputs. Prove valid methodology cohorts, rankings, target/current allocation context, research queue, actionable alerts and Execution Pace with evidence and blockers. Verify agent publication/proposal → separate reviewer decision. Preserve actual decision inputs/history. Genuine performance and broader exposures require their source history/classifications and remain visible gaps until supported |
| C5 Operational maturity                   | Cross-cutting from C1 onward. Before writes verify authenticated authority, current-state recovery and rollback. Before unattended jobs prove bounded cloud execution, idempotent retries, retention, monitoring, failure recovery and costs without a Windows workstation. Verify current hosted roles, production read-only journeys and restore in disposable infrastructure. Policy/scheduling activation stays owner-gated          |
| C6 Shared foundations and private App Hub | Follows useful Portfolio C1–C4 scope and sufficient C5 safeguards. Extract proven generic UI/auth/API/DB patterns incrementally. Deliver authenticated app registry/launcher and app-scoped navigation/permissions while preserving Portfolio deep links, ownership and regression coverage. Prefer the existing shared stack. Earlier foundation work needs a concrete Portfolio consumer                                               |
| C7 Additional personal apps               | After C6, prove one useful second app with an authenticated complete workflow, app-owned data/migrations, audit and cross-app tests on the shared deployment. Add a generator/template when proven repetition warrants it. Review any infrastructure split against cost/isolation evidence                                                                                                                                               |

## Data and portfolio delivery slices

| Slice / status                                                             | Dependencies and meaningful acceptance                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C2.1 Held mapping and recovery preview — VERIFIED on candidate PR #25      | 22/22 held mappings, required FX allowlisted, read-only exact-target preview and current schema/count evidence. Zero provider calls/writes. Merge gate is open; the old recovery branch protects the pre-import state                                                                                                                                                                                                                                                                                                                                     |
| C2.2 Daily portfolio data — PARTIAL / BUILD                                | C0, reviewed #25 receipt fix, current recovery and approved scope. Bounded backfill → exact-listing prices/dated FX → EUR holdings/cash/weights/gaps → source drill-down. Reconcile all reviewed held instruments and native cash; missing data stays visible. Desktop/mobile readback, two authorized hosted refresh cycles including restart, synthetic outage/rate-limit/partial tests and durable last-success/retry/coverage prove the outcome. Reuse manual jobs and one-cycle runners; provider-only unattended activation needs separate approval |
| C3.1 SEC statements and filings — READY for local mapping/integration work | Verify CIK identity/evidence and supported held/Watchlist issuer scope. Review international gaps. Bounded facts/submissions import must preserve amendments, accessions, units, fiscal periods and source dates, then appear in Financials/Research. Idempotent incremental refresh and per-issuer freshness/coverage need local tests and authorized hosted readback                                                                                                                                                                                    |
| C3.2 Permitted consensus/international coverage — SOURCE-GATED             | Reviewed provider rights, identities, coverage and retention precede requests. Prove representative annual/quarterly series, currencies, fiscal periods, analyst coverage, revision history and missing-data behavior. Distinguish current snapshots from genuine estimate history and external consensus from agent forecasts                                                                                                                                                                                                                            |
| C2.3 Ledger foundation and safe cutover — MISSING                          | C0 anchor plus reviewed account/cutover policy. Build a typed opening-balance + manual-activity → exact position/cash projection → reconciliation → reviewed dated cutover workflow. Synthetic buy/sell, deposit/withdrawal and fee cases must match quantities/cash while snapshot/targets remain intact. Production requires schema/ownership/import approval; detailed boundary is in Portfolio architecture                                                                                                                                           |
| C2.4 Broker imports and accounting — MISSING                               | C2.3 and reviewed lot/fee/tax/FX policy. One real broker format first. Preview → map → deduplicate → accept → statement reconciliation, with rollback/replay/conflict tests. Purchases/sales, dividends/withholding, fees/taxes, cash/security transfers and FX need provenance. Cross-account moves carry evidenced basis; unknown basis produces unavailable gains. Re-import must preserve positions and targets                                                                                                                                       |
| C2.5 Genuine performance — MISSING                                         | C2.3 complete flows plus C2.2 dated valuations/FX and verified action handling. Prove TWR and dated XIRR against independent fixtures, including same-day flows, transfers, retained/withdrawn dividends, fees/taxes, FX, zero opening value, missing valuations and absent/ambiguous IRR roots. Since-cutover coverage may precede full lot history. Hosted return drill-down must reproduce inputs and clearly label coverage, timing and net/gross methodology                                                                                         |
| C5.1 Provider-only cloud operation — CROSS-CUTTING                         | C2.2/C3 need explicit cadence, source scope, request/storage limits, least privilege, current recovery and separately approved scheduling. Reuse existing durable jobs/locks/backoff and one-cycle entrypoint. Prove sleeping-runtime/restart recovery, overlap prevention, partial failures, data freshness and alerts. Broad worker activation must not silently enable Sheets writes, model/research acceptance, target changes or unrelated decision jobs                                                                                             |

## Immediate priorities and gates

1. **Daily valued portfolio with reliable refresh.** Review/merge the completed C2.1
   PR #25, then deliver C2.2 as the next highest-value integration milestone.
   Initial backfill and scheduling have separate authorization gates. Build/test
   provider-only operation and refresh observability locally while those gates wait.
2. **Transaction accounting foundation.** C2.3 can proceed independently in isolated
   tests while production data activation is gated. Resolve cutover/account evidence
   and lot/performance policy before promoting actual records. Keep the existing
   holdings anchor and targets authoritative until a reviewed ownership transition.
3. **Model and company evidence in parallel.** C1.2 retains the P-GOOGL DEFER decision
   until dated assumptions and methodology are owner-reviewed. C3.1 can prepare
   reviewed SEC identities and a filings/fundamentals slice independently. C3.2
   requires source rights. These feed C4 research/decision workflows; transaction
   development does not postpone the model-publication architecture.

C5 is a prerequisite within each applicable priority. The recorded pre-import
recovery branch expires **2026-11-14 09:54 CET** and predates accepted holdings.
It is not evidence of recoverability of the current canonical portfolio. Reverify
retention and prepare an owner-approved current-state recovery procedure before
further production writes. No branch creation/restore is authorized by this plan.
Automatic promotion (historical MP3) follows proven reviewed history and an explicit
policy decision. It has lower priority than useful market, research and decision coverage.

## Evidence and upkeep

- C2.2 preflight diagnostics now persist to existing ingestion run/attempt tables
  under the guarded market lock. Invalid sources, mappings and budgets reach the
  Operations API without provider calls or fact/portfolio changes. Unverified
  targets still reject diagnostic writes. Later valid scope checks record resolution
  while retaining original failure evidence and actual data freshness. Fixed status
  selection losing prior success/FX history after many blocked checks. Status follows
  attempt time when an older run retries. Seven isolated PostgreSQL/API cases pass.
  Diagnostic records reject provider replay and require
  a fresh scoped check. Focused worker/importer/guard regression passes 142 cases;
  strict types, lint, documentation links/tests and whitespace checks pass.
  Final preflight/importer rerun passes 36 cases after the replay/order corrections.
  Browser investor-journey review is the next BUILD step.
  Hosted activation and production data coverage remain unverified and owner-gated.

- C2.2 same-day recovery reuses the frozen run/scope, waits 15 minutes after a
  retryable failure and caps each domain at three persisted attempts. Each cloud
  invocation makes one domain attempt with at most four transport tries per subject.
  Successful domains remain reused. Isolated PostgreSQL checks cover outage,
  cooldown, exhausted budget, nonretryable identity errors, overlap and interrupted
  claims. Fixed interruption detection that could rewrite terminal runs after four
  hours; partial success timestamps and append-only attempt numbering are retained.
  Focused recovery/importer regression passes 33 cases, with strict types and lint.
  Durable preflight diagnostics are covered in the later increment above.

- C2.2 synthetic end-to-end increment verifies actual normalization/persistence,
  exact EUR valuation and Operations HTTP status, unchanged holdings/cash/targets,
  fresh-connection replay, FX outage and next-UTC-cycle recovery. Frozen source
  hashes persist through fetch and replay. Fixed scope recomputation during reused
  run reporting and retained full-universe coverage diagnostics. The focused
  84-case importer/runner/adapter regression passes. Later BUILD evidence above
  covers same-day recovery and durable preflight blocker visibility.

- C2.2 bounded-scope increment pins exact listing/FX keys and reviewed crosswalk
  bytes to the existing scheduled ledger. Cloud corrections cover 90 inclusive
  calendar dates and at most 30 subjects. Legacy model FX remains on its original
  path. Eight source/scope/replay checks and 26 adapter regressions pass, with
  strict types and focused lint. Continue the synthetic end-to-end readback proof.

- C2.2 BUILD increment: provider-only recurring cycles preserve existing locks,
  cadence and durable run records, with queued/unrelated workflows excluded.
  Two isolated PostgreSQL cases, focused lint and strict types pass. Cloud scopes
  now default to market/FX, with explicit broader choices, safe output and nonzero
  nested/partial failures. Exception retry and overlapping-heartbeat regressions
  are covered. The 106-case focused worker/guard/market run passed. Continue via
  the active handoff. Production execution and milestone integration remain gated.

- 2026-11-07 capability audit inspected ORM/API, Portfolio UI, provider adapters,
  manual/recurring/cloud runners, settings, Render template and existing tests.
  Ledger, accounts, lots, broker imports and TWR/XIRR are absent. Price/FX and SEC
  pipelines are locally tested, with production execution/automation still gated.
  The current holdings confirmation and independent target revision remain intact.
  Planned transition/performance policy is documented in Portfolio architecture,
  and the workbook ownership contract now identifies its future cutover boundary.
- Audit verification passed: 45 focused API checks, including isolated PostgreSQL
  snapshot valuation/target invariants and manual/recurring-job tests, one
  documentation test, five deployment-policy tests, 134-file link checks,
  formatting and whitespace checks. Independent read-only review approved the
  accounting transition and status claims. Tests exercise existing functionality;
  ledger/TWR/XIRR implementation is a future slice. This audit performed no new
  live data/worker verification. Preserve it for the next functional integration.
- PR #24 merged as `395f842`. Completed [PR #25](https://github.com/paulzwecker/portfolio-app/pull/25)
  retains C2.1 evidence and passing CI on `bf33e58`, including the full PostgreSQL
  suite. This audit branch contains no unmerged receipt-adapter code. Preserve
  both capability roadmap and C2.1 evidence when integrating #25.

- [Production baseline](docs/production-canonical-baseline.md) owns M1 scope and recovery history.
- PR #23 merged with independent models/publication review and passing CI. PR #24
  merged MP2.1 preflight on `c7b9fb2` with passing [CI](https://github.com/paulzwecker/portfolio-app/actions/runs/42395071764), isolated tests and private replay semantics.
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
