# Capability roadmap and execution ledger

Updated 2026-11-08. [Product vision](docs/PRODUCT_VISION.md) owns the North Star.
[Architecture](docs/architecture/personal-universe.md) owns shared-platform boundaries.
[Documentation index](docs/README.md) routes contracts and runbooks.

## Execution cursor

| Field                       | Current value                                                                                                    |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Active checkpoint           | C2.3 guided ledger onboarding — INTEGRATE; release BLOCKED. [Handoff](docs/ACTIVE_WORKSTREAM.md)                 |
| Branch / PR                 | `codex/ledger-opening-onboarding`, synchronized with main `e070406`; integration PR pending                      |
| Implementation              | Guided opening, activity and ending reconciliation LOCAL_VERIFIED                                                |
| Next ready substantial task | Complete provider-control verification and coordinated release review                                            |
| Parallel owner gate         | Release recovery, deployment unfreeze, provider activation and financial decisions retain separate approvals     |
| Integration rule            | Freeze completed PRs; continue independent work from main or track stacked dependencies; preserve all local work |

Integration review added exact listing lookup for an unexpected ending-only
position. The preview treats an unexplained observation as a blocking mismatch,
does not infer a trade, and rejects changed lookup identity. Read-only Neon and
the repository attestation match `b59f16c8a203`; current hosted release controls
remain unverified. The new API endpoint must precede the frontend at release.
Integration checks passed `npm run check`, 452 isolated PostgreSQL tests (4 skipped),
48 managed desktop/mobile tests and two real-API browser journeys. An independent
review found no authorization or financial-integrity defect in the inspected paths.

The current BUILD fixes the Next.js read-only proxy for exact listing search and
verifies the guided opening → non-anchor purchase → ending → saved review journey
against real FastAPI and a disposable PostgreSQL fixture. Desktop cancels its
synthetic decision; mobile explicitly confirms it. Both retain the observed
holdings/targets fingerprint. Proxy auth, TLS, query and response checks pass in
focused tests. Hosted behavior and production release remain unverified.

The current BUILD connects exact non-anchor listing search to activity and ending
review without changing the opening anchor. It compares selected identities with
the native preview, rejects missing or changed consumed identities, and displays
all hash-bound identities including activity-only listings. Lookup names, share
class and demo status are context rather than hash-bound facts. Verification passed
176 focused web tests, three isolated PostgreSQL/API tests and 48 synthetic
desktop/mobile journeys; production integration and release checks remain pending.

The non-anchor listing lookup API supports bounded, exact ticker searches with
security/company/venue identity, demo and unsupported-currency indicators. The
lookup does not change the opening anchor. Two isolated PostgreSQL/API tests pass,
including a non-anchor preview and 50/51 result boundary. Guided selection and
identity-drift review were integrated in the following BUILD.

The current BUILD adds guided paired security transfers for verified anchor
listings. Both legs retain independent source evidence and exact quantities;
the user acknowledges unavailable acquisition basis and the API validates the
match and source holdings. Download, restoration and ending review preserve the
packet. Focused verification passed 170 web tests, three isolated PostgreSQL API
cases and 40 synthetic desktop/mobile journeys. No schema or production changes.

The current BUILD adds guided internal cash transfers with independently sourced
debit and receipt legs. Exact values and evidence survive download, restoration
and ending review; the API verifies matching currency, amount and booking instant.
Focused verification passed 157 web tests, three isolated PostgreSQL transfer API
cases and 38 synthetic desktop/mobile journeys. No schema or production changes.

The current BUILD adds source-evidenced dividends to the guided review. Users
enter the received currency, gross cash, explicit fees and withheld taxes without
assuming an FX conversion; native API replay validates the receipt. Downloaded
reviews and ending observations retain the dividend evidence. Focused verification
passed 146 web tests, 17 isolated PostgreSQL/API tests and 36 synthetic desktop/mobile
journeys; the dividend flow was rerun after the final wording change. No schema or production changes were made.

The current BUILD adds source-evidenced purchases and sales for verified anchor
listings to the existing read-only ledger review. It retains exact text and evidence
through download and restoration, with explicit dates, fees and taxes; native API
replay remains authoritative. Listing expansion, dividends and transfers remain.
Focused verification passed 136 web tests, 16 isolated PostgreSQL/API tests and
34 synthetic desktop/mobile journeys. No schema or production changes were made.

The latest BUILD restores a revalidated guided ending packet for editing, including
ending-only mismatches. It preserves the original source on discard, retains exact
amounts and evidence, and requires renewed cutoff confirmation. Unsupported or
lossy packets remain in the file workflow. Guided trade and dividend entry remains.
Focused verification passed 123 web tests and 32 synthetic desktop/mobile browser
cases, plus build, typecheck, lint and documentation checks.

The prior BUILD adds independently evidenced ending observations to reviewed
opening and supported cash packets. Each account starts with empty ending rows,
explicit zeroes remain distinct from missing observations, and the existing API
owns reconciliation. Discarding the ending draft returns the prior packet for
revalidation. At that checkpoint trade/dividend entry and guided restoration remained.
The preview also checks cutoff and ending timestamps at full fractional precision.
Focused verification passed 120 web tests, 15 isolated PostgreSQL/API cases and
28 synthetic desktop/mobile browser cases, plus build, typecheck and lint.

The prior BUILD restores supported cash activity from an unchanged downloaded
packet after the API revalidates it against the current anchor. Record identities,
evidence and exact amounts survive replay. Unsupported activity or additional
fields fail the guided restore without losing the original file. The
increment passed 114 focused web tests and 14 synthetic desktop/mobile browser
cases, along with typecheck, build, focused lint and documentation checks.

The prior BUILD adds source-evidenced cash deposits, withdrawals, fees and taxes
to a reconciled opening, with explicit account, booking timestamp, sequence and
review cutoff. Native preview results now show projected account/portfolio balances.
At that checkpoint guided trades, dividends, transfers and ending statements remained upcoming. The
opening and activity drafts cannot be switched implicitly.
Focused verification and the exact next step are recorded in the active handoff.

The prior BUILD adds restoration of a previously downloaded opening packet into
the guided form. Restoration preserves account IDs, exact decimal text and evidence,
requires fresh date confirmation, and rejects packets whose data cannot be retained
by this form. A failed replacement clears the previous review and retains the draft.
Focused verification passed 98 web tests, ten desktop/mobile browser cases, the
production build, typecheck, lint and documentation checks. Continue with guided
settled activity and ending statements.

Opening-balance onboarding `18f1f15` lets the investor enter evidenced accounts,
exact listing quantities and currency cash, review native reconciliation and
download/replay the same private packet. Edits invalidate earlier results and reset
the source-date acknowledgement. Focused checks pass 96 web, 67 native ledger units,
13 isolated PostgreSQL/API cases and six desktop/mobile browser cases with light/dark
visual review. Typecheck, production build and focused lint pass. No schema,
production, provider or investment change is included. The new branch preserves
the predecessor worktrees and owner edits. PR #29 merged during BUILD and was
integrated without conflicts as `813651e`. The focused checks, production build,
desktop/mobile journeys and documentation checks passed again after the merge.
Both offline schema-gate modes match `b59f16c8a203` with no pending revisions;
this records repository compatibility with the attestation, with hosted release
configuration/freshness verification reserved for INTEGRATE.

The historical market-data reliability engineering checkpoint is IMPLEMENTATION_COMPLETE
and LOCAL_VERIFIED. Company Explorer and Operations expose source conflicts, returned-row
search, published schedule evidence, receipt diagnostics and bounded checkpoint
reconciliation. Prior BUILD evidence remains in the
[historical handoff](docs/history/market-history-build-through-2026-11-08.md).
PR #29 merged as `e070406` on November 8; its dated evidence and outstanding
release-control gates remain in the historical handoff. C2.2 remains operationally partial until
separately authorized live enrichment and monitored refresh acceptance.
`npm run check`, 112 relevant PostgreSQL cases across selection/rerun and the managed
browser suite passed. Browser evidence is 95 passed and 35 explicit skips. Independent
review tightened alert evidence and added HTTP authentication/read-only coverage.

Fresh November 8 read-only verification passes for the exact Neon target at
`b59f16c8a203`, all 98 tables and mapped metadata without drift. Accepted portfolio
counts and the 100% target total match the baseline. The earlier connection failure
is resolved using the documented process-local CA bundle. Render is live at
`aef3572`, uses `checksPass`, has healthy readiness and disabled write/background
controls. Effective main rules enforce PRs and all three strict CI checks.
Classification is CONFIGURATION_REQUIRED pending current Vercel release-control
evidence and Blueprint sync confirmation. The read-only market preview resolves
22/22 holdings and two FX pairs across 24 planned scopes. Enrichment execution
retains the owner-reviewed window, budget and recovery prerequisites.

Historical release evidence follows. PRs #27 and #28 are merged into main. The owner-authorized Render release of `aef3572` is healthy;
Vercel reported Ready but production alias and enforcement remain unverified. Render auto-deploy and
Blueprint sync remain disabled; retain all separate production activation and recovery gates.

Historical November 8 incident evidence identified a healthy old Render deployment (`395f842`),
new Vercel frontend (`deda2ce`) and Neon still at `9f2a6d4c81b7`. Ledger reads fail
with 404; canonical portfolio counts remain intact. A fresh populated-state recovery
point and separate migration/deployment authorization are required. The
[release runbook](docs/deployment-and-migrations.md) records the exact plan, CI
sequencing cause and offline release gate. The marker then recorded the old schema;
the initial investigation made no production/provider change. Focused checks passed 16 deployment,
55 readiness/preflight and three isolated migration/replay tests, plus docs/privacy.

Owner-authorized recovery phase 1 passed on November 8. Render Auto-Deploy Off
and Blueprint Auto Sync No are verified; Vercel production builds are frozen with
Preview builds allowed. Exactly one fresh populated-state recovery was created and
verified against production across all 95 tables, schema and data fingerprints,
with zero differences. Phase 2 then passed both existing read-only CLI commands
from a separate clean main worktree at `deda2ced13df8ef0874df2727cca0d050ab6c164`,
using the new recovery secret only in process memory. All 95 schema/data fingerprints
and migration ownership/privileges were reverified; write authorization remains
disabled. Planned scope adds three tables/two indexes and updates Alembic metadata;
accepted data stays unchanged. Recovery freshness ended at 18:19:38 CET on November 8,
with branch expiry November 15 at 14:18:37 CET. Exact evidence stays private. At
that checkpoint migration and deployment still needed separate owner approval.

**Incident resolution, November 8.** The authorized migration reached `b59f16c8a203`
and the single authorized Render deployment of `deda2ce` restored health. The owner
confirmed frontend readback and portfolio reconciliation reported zero differences.
Production freezes remain active. The release gate uses the verified schema; Vercel
requires independently enforced GitHub Deployment Checks before safe activation.
The earlier incident and preflight observations above are historical. The next
price/FX step is the existing target-bound read-only held-listing preview, followed
by a separately approved bounded provider scope. No provider request is authorized.

The current populated recovery branch expires November 15 at 14:18 CET; it is not a
durable backup. Local PostgreSQL 18 backup/restore clients were version-checked, but
the existing archive toolkit rejects production sources, and no production archive
or isolated restore rehearsal has been verified. The release runbook identifies the
owner's retention choices and separately authorized recovery work. Twenty-one focused
release and local-tool checks, `npm run check`, and three synthetic PostgreSQL
archive/restore integration cases pass. The focused 79-case ledger integration
selection and six authenticated desktop/mobile browser checks also passed. The full
PostgreSQL CI job passed for PR #27. These results do not establish production readiness.

## Where we are

| Outcome                                  | Actual state                                                                                                                                                                |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M1 / C0 minimal canonical portfolio      | PRODUCTION_VERIFIED for the recorded Nov 7 baseline, including 22 positions and two cash currencies                                                                         |
| C1 model lifecycle and sensitivity       | Implemented/local verification. First accepted production P-GOOGL revision remains an owner investment decision                                                             |
| C2 daily prices/FX and ledger transition | Implemented/local verification. Real enrichment, refresh activation and source/ownership cutover require separate execution                                                 |
| C3 SEC facts/filings                     | Implemented/local verification. Reviewed issuer mappings and actual coverage remain operational prerequisites; international and licensed consensus coverage remain partial |
| C4 actionable decisions                  | Existing engines/UI depend on eligible accepted models, market facts, scores and research evidence                                                                          |
| C5 operations and delivery               | Guarded workers, recovery preflight, CI classification and authenticated browser fixtures implemented; combined release checks pass; hosted operational proof remains gated |
| C6/C7 App Hub and additional apps        | Planned after useful Portfolio workflows and operational safeguards                                                                                                         |

Merged PR #26 includes the unchanged PR #25 receipt adapter, the preserved CI
classification correction (`18930ac`, `f72729e`) and DCF sensitivity/authenticated
proxy work through `78dcf1b`. The predecessor history remains intact. The [dated evidence](docs/history/data-ledger-build-through-2026-11-08.md)
preserves each predecessor's scope and checks. All branches, stash and private
source artifacts are preserved.

**Release prerequisite.** This code requires additive migrations
`9f2a6d4c81b7` → `a832e94d6f10` → `b59f16c8a203`. Production was verified at
`b59f16c8a203` after the authorized recovery; reverify it before future operations. Before releasing schema-dependent
code, follow the [native-provider freeze, current-state recovery and guarded migration
procedure](docs/deployment-and-migrations.md). The historical empty pre-import
recovery branch does not protect accepted holdings. Schema deployment does not
activate ingestion, transfer ownership or accept models. Each retains its own gate.

Combined quality verification passes 307 web and 831 API unit checks with two
Windows-specific skips. Managed production-browser regression passes 89 cases
with 29 explicit fixture/live-only gates; ten real FastAPI/PostgreSQL browser
journeys also pass. Local PostgreSQL
passes 376 cases with four privilege-dependent skips. Linux CI passes all 380 and
833 unit cases. Code `a952d60` passes all three [CI jobs](https://github.com/paulzwecker/portfolio-app/actions/runs/42471476408)
and Vercel Preview. Require the latest [PR checks](https://github.com/paulzwecker/portfolio-app/pull/26/checks)
for the recorded integration. PR #26 merged as `deda2ce`; cloud deployment and
migration status remain unverified in this BUILD run.

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
is included in merged PR #26. This review adds repository
evidence, not a fresh live inventory.
Historical local reports and disabled configuration cannot prove hosted automation.
Reverify target, coverage, source rights and controls before activation.

| Capability                           | Implemented / verified outcome                                                                                                                                 | Outstanding outcome                                                                                                                                                                                                                                                                                            |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity, holdings, cash, targets    | OPERATIONALLY_VERIFIED for M1 minimal scope, receipts, zero reconciliation differences and owner UI readback                                                   | Ongoing source synchronization and decision-grade valuation                                                                                                                                                                                                                                                    |
| Prices and FX                        | Adapters, bounded backfill, exact crosswalks, raw provenance and dated observations LOCAL_VERIFIED; C2.1 mapping preview PRODUCTION_PREVIEW_VERIFIED on PR #25 | Production observations were zero at the recorded check. Complete the merged release gates, authorize backfill, reconcile actual EUR valuation and prove incremental refresh                                                                                                                                   |
| SEC fundamentals and filings         | Company Facts/submissions, amendments, accession/provenance and financial explorer LOCAL_VERIFIED                                                              | Zero production facts/documents/reviewed CIK mappings at C2.1. Review issuer coverage; non-SEC coverage PARTIAL. Filing-body download is outside the existing bootstrap. [Contract](docs/fundamentals-source-bootstrap.md)                                                                                     |
| Consensus                            | Provider-specific snapshots, annual/quarterly FMP adapter, revision/continuity rules and tests implemented                                                     | FMP opt-in is DISABLED by default. Provider rights, issuer mapping, credentials and live coverage UNVERIFIED; historical estimate coverage cannot be invented. [Contract](docs/consensus-estimates.md)                                                                                                         |
| Corporate actions                    | Split/dividend provider evidence and separate adjusted/native price fields LOCAL_VERIFIED                                                                      | Events remain unverified; mergers/spinoffs/other unsupported actions and account-level processing need reviewed contracts. Provider dividends do not establish received cash or withholding. [Semantics](docs/historical-market-data-bootstrap.md#corporate-actions-and-adjustment-semantics)                  |
| Independent native models            | Three methods LOCAL_VERIFIED, real P-GOOGL package parity and recorded production preview, merged publication foundation                                       | First accepted production-native model has no recorded acceptance evidence. Dated assumptions, fiscal alignment and method review remain owner-gated. [Contract](docs/model-publications.md)                                                                                                                   |
| Thesis, research, assessments        | Implemented / LOCAL_VERIFIED claims, evidence, contradictions, histories and review                                                                            | Representative real research-to-thesis-to-model workflow and population UNVERIFIED. [Contract](docs/research-to-model.md)                                                                                                                                                                                      |
| Rankings, allocation, Execution Pace | Implemented / LOCAL_VERIFIED engines and decision UI                                                                                                           | Eligible current models, market facts, lifecycle, independent scores and confirmed holdings. Multi-model ambiguity stays blocked until approved policy. [Semantics](docs/return-semantics.md)                                                                                                                  |
| Alerts and temporal history          | Implemented in-app attention/trigger/history views                                                                                                             | Real source-backed coverage UNVERIFIED. Notification delivery MISSING and channel/policy undecided. [Contract](docs/attention-center.md)                                                                                                                                                                       |
| Exposure                             | Company/listing/cash composition and concentration PARTIAL                                                                                                     | Sector/geography/business-model classifications and broader exposure coverage need canonical sources. [Limits](docs/portfolio-dashboard.md)                                                                                                                                                                    |
| Cloud operations and security        | Durable manual jobs, dependency steps, locks/cooldowns/retries, heartbeat, sync receipts and Operations UI LOCAL_VERIFIED                                      | Recurring/cloud/manual/Sheets controls are disabled in the deployment template; hosted configuration needs reverification. No scheduled worker is configured there. Current-state recovery, bounded provider-only activation and monitoring require operational proof. [Runbook](docs/recurring-operations.md) |
| Transaction ledger and accounts      | PARTIAL. Opening/activity, v2 dividend/withholding/tax and reviewed publication LOCAL_VERIFIED against canonical snapshots                                     | Ending/account reconciliation and review UI are locally verified. Durable candidate/review/correction API LOCAL_VERIFIED; production publication activation, normalized accounts, FX, in-transit/cross-listing transfers and corporate-action accounting remain outstanding                                    |
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

| Slice / status                                                        | Dependencies and meaningful acceptance                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| C2.1 Held mapping and recovery preview — VERIFIED on candidate PR #25 | 22/22 held mappings, required FX allowlisted, read-only exact-target preview and current schema/count evidence. Zero provider calls/writes. Included in merged PR #26; the old recovery branch protects only the pre-import state                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| C2.2 Daily portfolio data — PARTIAL / BUILD                           | C0, reviewed #25 receipt fix, current recovery and approved scope. Bounded backfill → exact-listing prices/dated FX → EUR holdings/cash/weights/gaps → source drill-down. Reconcile all reviewed held instruments and native cash; missing data stays visible. Desktop/mobile readback, two authorized hosted refresh cycles including restart, synthetic outage/rate-limit/partial tests and durable last-success/retry/coverage prove the outcome. Reuse manual jobs and one-cycle runners; provider-only unattended activation needs separate approval                                                                                                                                                                                                                                              |
| C3.1 SEC statements and filings — PARTIAL / BUILD                     | Portfolio-scoped bootstrap and filing-before-facts recovery LOCAL_VERIFIED with synthetic Financials/filings API readback. Verify real CIK identity/evidence and held/Watchlist scope, review international gaps and prove incremental per-issuer freshness/coverage in the research workflow. Preserve amendments, accessions, units, fiscal periods and source dates. Reviewed mapping writes and hosted ingestion/readback retain separate authorization                                                                                                                                                                                                                                                                                                                                            |
| C3.2 Permitted consensus/international coverage — SOURCE-GATED        | Reviewed provider rights, identities, coverage and retention precede requests. Prove representative annual/quarterly series, currencies, fiscal periods, analyst coverage, revision history and missing-data behavior. Distinguish current snapshots from genuine estimate history and external consensus from agent forecasts                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| C2.3 Ledger foundation and safe cutover - PARTIAL / BUILD             | Opening accounts + settled buy/sell, deposit/withdrawal/fee -> exact position/cash projection and opening reconciliation LOCAL_VERIFIED through read-only PostgreSQL/API. Ending/account reconciliation and private-file review UI are locally verified. Durable candidate/review/correction API locally verified. Explicit decision/history UI locally verified. Dated publication/readback locally verified. Publication approval and v2 income/tax and paired cash/security-transfer scope shipped in merged PR #27. Guided source-evidenced opening, activity and ending review are LOCAL_VERIFIED; perform the milestone integration review next. Preserve snapshots/targets. Production requires reviewed account/basis/source scope, schema/ownership/import authorization and current recovery |
| C2.4 Broker imports and accounting — MISSING                          | C2.3 and reviewed lot/fee/tax/FX policy. One real broker format first. Preview → map → deduplicate → accept → statement reconciliation, with rollback/replay/conflict tests. Purchases/sales, dividends/withholding, fees/taxes, cash/security transfers and FX need provenance. Cross-account moves carry evidenced basis; unknown basis produces unavailable gains. Re-import must preserve positions and targets                                                                                                                                                                                                                                                                                                                                                                                    |
| C2.5 Genuine performance — MISSING                                    | C2.3 complete flows plus C2.2 dated valuations/FX and verified action handling. Prove TWR and dated XIRR against independent fixtures, including same-day flows, transfers, retained/withdrawn dividends, fees/taxes, FX, zero opening value, missing valuations and absent/ambiguous IRR roots. Since-cutover coverage may precede full lot history. Hosted return drill-down must reproduce inputs and clearly label coverage, timing and net/gross methodology                                                                                                                                                                                                                                                                                                                                      |
| C5.1 Provider-only cloud operation — CROSS-CUTTING                    | C2.2/C3 need explicit cadence, source scope, request/storage limits, least privilege, current recovery and separately approved scheduling. Reuse existing durable jobs/locks/backoff and one-cycle entrypoint. Prove sleeping-runtime/restart recovery, overlap prevention, partial failures, data freshness and alerts. Broad worker activation must not silently enable Sheets writes, model/research acceptance, target changes or unrelated decision jobs                                                                                                                                                                                                                                                                                                                                          |

**C2.2 independent BUILD:** `codex/market-history-coverage` adds explicit
normalized-batch date-span evidence to historical price/FX receipts. It does not
infer missing trading sessions or change provider/run status. One returned quote or
a completed checkpoint does not establish window completeness. Synthetic unit and
isolated PostgreSQL verification are recorded in the active handoff. This work is
independent of the design PR; production ingestion and release remain owner-gated.
Read-only reconciliation now rejects missing completed-batch provenance and rows
outside the frozen subject, time window or historical price scope. This verifies
receipt integrity, not expected-session completeness; 13 focused unit and 21 isolated
PostgreSQL cases pass. Next: establish reviewed session-aware coverage evidence.
The next increment verifies retained raw provider bytes and identity as part of
reconciliation, with an explicit per-payload work limit. Fourteen unit and 24
isolated PostgreSQL cases pass; live-source and production coverage remain unverified.
Price-move attention now uses only information known at evaluation time and rejects
ambiguous, corrected or incompatible close pairs. Its label no longer asserts
unverified exchange-session adjacency. Nine focused units and 12 isolated PostgreSQL
cases pass. Review real-session coverage before enabling complete-history claims.
Company historical analytics now expose their observed date span and explicitly state
that exchange-session coverage is unassessed, including for older API responses.
Synthetic API/DB, web and responsive browser checks are recorded in the handoff;
no trading calendar or production coverage is inferred.
History analytics and charts now fail closed on duplicate dates or incompatible
provider, symbol or currency streams; source rows remain inspectable. Focused local
checks pass, including responsive conflict-state coverage. Session completeness,
source adjustment consistency and live ingestion remain unverified.
The conflict state now identifies the selected source streams, their date spans and
duplicate dates, allowing review even when the relevant rows are outside the recent
observation list. This is local evidence, not a provider reconciliation approval.
The inspection view now searches all returned observations independently of the
chart range, displaying exact close text, source symbol and adjustment basis in
responsive table/cards. It does not assert that the selected history includes every
provider observation or every market session.
Price and FX provider normalization warnings now persist into run reports and make
affected refreshes partial. Operations explains the warnings; legacy receipts with
unrecorded warning evidence remain explicitly unknown. This is locally verified,
not live provider coverage or approval to ingest.

## Immediate priorities and gates

1. **Daily valued portfolio with reliable refresh.** PR #26 merged with C2.1's
   receipt fix and C2.2 implementation. Complete the
   current-state recovery, schema and deployment gates before authorized backfill
   and hosted valuation/refresh reconciliation. Two monitored refresh cycles and
   separately approved scheduling establish the remaining operational outcome.
2. **Usable transaction accounting.** Merged PR #27 delivers the bounded ledger
   and guarded review/publication lifecycle. The current C2.3 BUILD makes evidenced
   opening accounts and balances usable through the UI. Extend guided entry to
   settled activity and ending statements, with exact server reconciliation and
   source evidence. Broker imports, lot/FX/performance policy and real account/source
   cutover remain follow-ons. Preserve accepted holdings, strategic targets and
   explicitly unavailable acquisition basis/gains.
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

- C2.3 `bf9f184` ending-statement reconciliation passes 79 focused checks (67 unit and
  12 isolated PostgreSQL/API). Account/portfolio comparisons bind ending evidence,
  time and exact listing identities, retaining missing/zero and legacy v1 hashes.
  Missing empty accounts and equal-total/wrong-account cases remain blocked.
  The private-file Portfolio review now passes 71 web/proxy cases and 16 fixture
  checks. Four actual-API desktop/mobile journeys and repeat screenshots verify
  exact values, missing zero rows, source/focus, scoped account differences, stale
  files and request cancellation with unchanged protected-state hashes. Independent
  review corrected UUID display casing and contradictory ready-status handling.
  Proxy forwards original financial text with existing origin/auth gates and a
  bounded UTF-8 payload. Types, lint, formatting, generated contracts and docs pass.
  Screenshots stay in ignored `.cache/c2.3-ledger-review*`. This is LOCAL_VERIFIED
  with synthetic data. Durable records, acceptance and cutover remain pending.

- C2.3 `43d1ed8` adds the versioned settled-ledger core. The read-only API increment
  binds current snapshot and listing/source identity hashes, retains anchor recording
  time and projects exact native balances. Forty unit, nine isolated PostgreSQL/API
  and 18 existing contract cases pass (67 total). Repeated API replay and all rejected
  paths preserve snapshot/targets, counts and sequences. Injected DML is rejected by
  PostgreSQL. Both original writable and read-only pooled settings are retained.
  Independent review found and resolved backdated settlement and pooled readonly-reset
  defects. Source-local date/offset, intermediate shorts/overdrafts, zero/missing,
  stale anchors, companyless ETFs, source duplicates and aggregate limits are covered.
  Types, lint, formatting and generated contracts pass. Web types and documentation
  links pass. This is LOCAL_VERIFIED with synthetic data. Durable ledger/cutover,
  ending-statement reconciliation, review UI, accounting and performance remain open.
  [Contract and private-file workflow](docs/portfolio-ledger.md).

- C3.1 `1356944` company-scoped SEC admission reuses verified positive holdings from the
  current complete snapshot independently of lifecycle. Only the two SEC jobs gain
  this path. Snapshot provenance, explicit retry checks and disabled/authenticated
  API behavior are covered. Twenty admission/manual API cases and 27 existing
  incremental/portfolio-scope regressions pass in isolated local PostgreSQL schemas.
  Future effective/recording times, zero/missing quantities, ambiguous portfolios,
  unmapped blocked outcomes and unchanged holdings/targets/lifecycle are verified.
  Strict types and independent backend review pass. Shared Company Explorer and
  company-focused Operations controls consume backend eligibility and execution mode.
  Eight mixed/outage desktop/mobile journeys pass across the two fixtures. The four
  final outage journeys cover delayed polls, scoped submission, partial/failed status,
  cooldowns and terminal refetch. Enabled submissions use synthetic HTTP receipts;
  real SQL/API/worker execution is covered by the PostgreSQL tests. Browser serving
  stays read-only with unchanged protected-state hashes. Eighty focused web cases,
  strict types, lint, formatting, contracts and documentation checks pass. Independent
  frontend review exposed a polling race, corrected with cancellation/serialization
  and a delayed-response regression. Repeated screenshot inspection confirms exact
  job/lifecycle labels and mobile readability. Evidence remains in ignored
  `.cache/c3.1-company-refresh*`. Real issuer coverage and hosted execution remain gated.

- C3.1 `197254a` issuer filing receipts retain response, accepted/reused and
  quality counts in the existing immutable batch reconciliation. Exact scope and
  CIK checks protect replay. History deferrals remain per-issuer execution evidence.
  The 79-case focused source/coverage/bootstrap regression and 15 incremental-worker
  cases pass. Mixed batches preserve a valid issuer's result,
  while missing, clean-empty, conflicted and deferred outcomes remain distinct.
  Legacy receipts are preserved. Independent static review has no findings.
  Six mixed/outage desktop/mobile journeys and repeat inspection verify valid issuer
  results beside another issuer's gap. Browser writes remain zero and protected
  state hashes match. Eighteen web tests, types, lint, formatting, contracts and
  documentation checks pass. Both fixtures removed their own schemas on normal
  shutdown. Local production-write/ingestion/job/polling flags remain disabled.
  This is LOCAL_VERIFIED; reviewed real mappings and hosted execution stay gated.

- C3.1 `4cb4870` company coverage includes incremental run/attempt IDs, trigger, frozen
  scope counts and separate batch/issuer outcomes. Attribution uses stored issuer
  evidence; aggregate multi-issuer filings remain unreported per issuer. Failed
  attempts cannot advance retained-data dates. The shared Financials/Research/
  Operations panel and drawer expose these outcomes. Compact status follows newer
  bootstrap/refresh activity and keeps historical details inspectable. Eighteen web
  unit/proxy cases and six real-API desktop/mobile journeys pass, with zero browser
  writes and unchanged protected-state hashes. Repeated screenshots were inspected
  after moving technical codes into details. Independent review corrected zero-row
  integrity conflicts to DATA_CHECK; clean empty responses remain unavailable.
  The final 45-case API/scope/fixture regression passes after that correction.
  Typed contracts, strict types, lint, formatting and documentation checks pass.
  This is LOCAL_VERIFIED using synthetic data. Multi-issuer filing outcomes without
  direct issuer evidence remain explicit gaps, with no inferred successes/failures.

- C3.1 `af8c847` incremental SEC selection reuses the reviewed held/Watchlist scope in
  scheduled and existing manual steps, independently of held issuers' lifecycle.
  Domain/day and manual-request scopes freeze identity evidence and mapping hashes
  across retries/restarts. Actual mapping drift blocks provider calls; additions
  stay outside prior scopes. The budget is 30 mapped issuers and five new history
  files per filings attempt. Deferred history remains partial. Scheduled transient
  recovery retains the 15-minute cooldown/two-replay limit. Terminal/exhausted runs
  cannot recapture a wider same-day scope, and manual runs do not suppress scheduled
  scope. Real synthetic SEC payloads reach exact Financials/filing API readback while
  holdings, cash, targets and lifecycle remain intact. Existing Operations ledgers
  record attempts. Fifteen isolated scope cases and 107 existing regressions pass,
  followed by four deterministic-clock reruns. Review fixed abandoned claims skipping
  interruption detection and tested mapping drift between transport attempts.
  Strict types, lint, formatting, contracts and documentation checks pass. Local
  production-write/ingestion/manual/recurring/sync/FMP flags and Sheets polling are
  disabled. This is LOCAL_VERIFIED only. Company coverage still needs incremental
  per-issuer outcomes; actual CIK review and hosted activation remain owner-gated.

- C3.1 current per-company SEC coverage is LOCAL_VERIFIED through Financials,
  Research and focused Operations. Shared drawers expose retained facts/filings,
  missing metric types, mapping evidence, separate economic/filing/retrieval/record
  dates and issuer-specific bootstrap state. Failed bootstraps retain data and show
  compact warnings. Historical Financials hides current-only coverage. Fifty-one
  focused API/fixture/bootstrap checks and 58 web unit/proxy cases pass. Six actual
  API desktop/mobile journeys plus two refined missing-data reruns preserve state
  with zero browser writes. Repeat screenshots were inspected. Browser review fixed
  Company Explorer query/tab synchronization, and two existing composition cases
  pass with explicit editor closure. Bootstrap fixture starts remain serial under
  the shared advisory lock; bounded normal cleanup preserves existing test schemas.
  Source payloads are synthetic. Hosted coverage remains unverified. Next address
  scheduled/manual per-issuer diagnostics alongside the newly scoped refreshes,
  preserving lifecycle and existing guards.

- C3.1 adds explicit `db:bootstrap-fundamentals -- preview/prepare --portfolio-id`
  selection using the exact portfolio's current complete snapshot and explicit
  Watchlist. Held issuers lead, multiple listings deduplicate to one issuer, and
  missing CIKs/companyless ETFs remain disclosed. Lifecycle is preserved. Frozen
  selection survives later holdings/lifecycle changes, while mapping drift stops
  provider access. Resume now uses the prepared mapping order instead of letting
  lifecycle ordering invalidate an unchanged identity hash. Independent outage
  review found Company Facts could run during its issuer's filing retry cooldown.
  The checkpoint selector now enforces that dependency while allowing other issuers
  to progress. Twelve scope checks plus 107 existing bootstrap/source/write-guard
  regressions pass, including isolated importer → Financials/filings API readback,
  exact decimals, reconciliation, portfolio isolation, mapping drift, frozen replay,
  cooldown recovery and unchanged holdings/targets. Strict types, lint, formatting,
  contracts and documentation links pass. This is synthetic/local evidence.
  Reviewed real CIK mappings, per-issuer operating visibility and hosted coverage
  remain outstanding. Operator scope commands are in the
  [SEC runbook](docs/fundamentals-source-bootstrap.md#choose-the-issuer-scope).

- C2.2 actual-API browser rehearsal is LOCAL_VERIFIED for unpriced, FX-outage and
  valued states on desktop/mobile. Synthetic stock/standalone-ETF/FX payloads pass
  through the real importer, PostgreSQL, API and web proxy. Sixteen fixture
  safety/integration tests pass. The six scenario/device journeys preserve exact
  holdings/cash/targets, record zero browser writes and retain protected-state hashes.
  Visual review exposed squeezed company names in allocation gaps. The corrected
  layout uses compact percentage/percentage-point display with exact input text
  available, and a second desktop/mobile inspection passes. Three regression unit
  cases cover precision, zero and missing values. The final focused checks pass
  five web unit tests, 18 UI/browser regressions, strict types, lint, formatting,
  generated contracts and documentation links. Windows interrupt cleanup proved
  unreliable, so bounded normal shutdown is tested and verified. Two interrupted
  fixtures created during this run were identified and removed from the local test
  database; five pre-existing schemas remain preserved. Reproduction commands live
  in the [development runbook](docs/codex-cloud-development.md#portfolio-data-rehearsal).
  Hosted/provider activation remains unverified and owner-gated.

- C2.2 investor investigation now links Portfolio valuation gaps directly to the
  Operations market panel. Summary/diagnostics precede manual controls. A shared
  drawer exposes frozen scopes, attempt history, provider issues and backend-owned
  cooldown/eligibility, including corporate-action quality. Sixteen desktop/mobile
  fixture browser cases and four final reruns pass, with screenshot inspection
  before/after refinements, keyboard focus return, responsive overflow and zero
  write requests. Eighteen isolated API cases passed initially, followed by a
  14-case status/importer review regression that excludes manual replays from
  automatic eligibility. Nine focused web tests, strict types, lint and contracts
  pass. Evidence is synthetic/local. The actual-API browser rehearsal is recorded
  above; hosted activation remains separate. Second visual inspection fixed shared
  drawer placement and verified actual right-edge bounds. Six focused
  drawer/design-system reruns pass.
  Screenshots are retained in the ignored local cache.

- C2.2 diagnostics contract adds read-only per-domain scopes, attempt history and
  retry eligibility to the existing Operations status API, including separate
  corporate-action quality. Eligibility shares the worker policy and excludes old
  daily scopes. Eighteen isolated API/recovery/preflight checks and nine focused
  web checks pass, with strict types and generated contract checks. Desktop/mobile
  baseline review confirms diagnostics are buried below manual controls. Continue
  the focused presentation correction before declaring the investor journey verified.

- C2.2 preflight diagnostics now persist to existing ingestion run/attempt tables
  under the guarded market lock. Invalid sources, mappings and budgets reach the
  Operations API without provider calls or fact/portfolio changes. Unverified
  targets still reject diagnostic writes. Later valid scope checks record resolution
  while retaining original failure evidence and actual data freshness. Fixed status
  selection losing prior success/FX history after many blocked checks. Status follows
  attempt time when an older run retries. Seven isolated PostgreSQL/API cases pass.
  Diagnostic records reject provider replay and require
  a fresh scoped check. Focused worker/importer/guard regression passes 142 cases.
  Strict types, lint, documentation links/tests and whitespace checks pass.
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
  At that audit, persisted ledger/accounts, lots, broker imports and TWR/XIRR were
  absent. Current C2.3 preview evidence is recorded above. Price/FX and SEC
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
