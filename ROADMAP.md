# Personal Universe / Portfolio — Adaptive Delivery Roadmap

**Version:** 0.1 — proposed initial plan; **not** a statement of live repo readiness  
**North star:** `docs/PRODUCT_VISION.md`  
**Portfolio architecture:** `docs/architecture/portfolio-application.md`  
**Platform architecture:** `docs/architecture/personal-universe.md`

## Execution cursor — edit after EVERY subtask

| Field                   | Current value                                                                                                            |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Active milestone        | `M0` — Reconcile repository and establish loop                                                                           |
| Next task               | `M0.6` — Verify Actions after the migration-head assertion fix; then finalize the M0 PR state                            |
| Status                  | `IN_PROGRESS / POSTGRES_CI_FIX`                                                                                          |
| Current branch / commit | `codex/m0-integrated-release-candidate` / `3533b83`                                                                      |
| Last verified tests     | `npm run check`: pass; API 592 passed, 2 skipped; DCF source tests 2 passed; prior API integration 133 passed, 4 skipped |
| Latest PR               | [Draft PR #13](https://github.com/paulzwecker/portfolio-app/pull/13)                                                     |
| Primary blocker         | Corrected Actions rerun pending; prior PostgreSQL job used a stale Alembic-head expectation                              |
| Next approval gate      | No production migration, write, deployment or model acceptance without its separate explicit approval                    |

**Status legend:** `PLANNED`, `READY`, `IN_PROGRESS`, `BLOCKED`, `LOCAL_VERIFIED`, `LIVE_VERIFIED`, `PR_OPEN`, `MERGED`, `PRODUCTION_VERIFIED`. Mark a subtask complete only with evidence and test commands/results. A PR does not imply merge or deployment.

## How agents execute this roadmap

1. Read the cursor, relevant architecture/contract docs and Git status. Check whether the preceding work exists in the current branch.
2. Select the **next ready subtask**, not the easiest large refactor. Deliver the smallest coherent vertical slice; test, inspect, review once and correct defects.
3. After **each subtask**, edit its checkbox/status and evidence line, update cursor, log blockers/decisions and revise adjacent dependencies. Commit the roadmap update with the change (or alone for an accurate blocked-state update).
4. If a block requires owner authorization, stop that action; work on an independent task only when it does not compromise the milestone's coherence.
5. At a milestone gate: verify acceptance evidence, run all affected suites and UX checks, review security/privacy diff, assess vision alignment, push a feature branch and open a PR with test evidence. Record URL and status. **Do not automatically merge, deploy or apply a production change.**
6. Once a PR is merged or the owner explicitly permits the next integration branch, recheck repository reality, update the remaining plan and continue. Avoid stacking branches on unreviewed work without making dependencies explicit.
7. Limit self-editing of the long-term vision: agents may change future technical tasks, not fundamental financial policy, product mission, auth model or production authority without owner review.

## Milestone M0 — Reconcile repository and establish autonomous loop

**Objective:** A trustworthy baseline; all previous work protected, scoped and checkable.  
**Dependencies:** None. **Exit:** one reviewed integration PR, deterministic tests or documented residual failures, roadmap cursor accurate.

- [x] **M0.1** Inventory `git status`, branches, stashes, commits, untracked work, existing docs and CI. Preserve unrelated changes (`AGENTS.md`, `docs/architecture/` historically reported). Evidence: inventory with paths and owned work; never assume pasted milestone reports equal merged code.
  - Evidence (2026-11-01; inventory recorded in `a179433`): branch `codex/n1-model-release-candidate` at `261955d` when surveyed; the supplied docs were preserved and subsequently reconciled. Branch contained 23 commits ahead of `main`/`origin/main`, including M2/M5–M8 integration commits `d82535f`, `1be9a85`, and docs commit `2cde719`. One unrelated stash (`stash@{0}`, Task 8 readiness test isolation) and all listed recovery/task branches remain intact. CI exists at `.github/workflows/ci.yml`; source-data policy check passes and confirms excluded workbook/source paths are not in the CI checkout. The two workbook files are tracked from the initial commit but excluded by the CI sparse-checkout policy; no new private artifacts were staged. Local Alembic graph has the single head `9f2a6d4c81b7`; migrations from production head `6c2eaf0b8147` are chained through `b16d4f8a2c91`, `c17a0b9d4e62`, `3e5c8a1d7b42`, then `9f2a6d4c81b7`. No files or branches were reset, discarded or switched.
- [x] **M0.2** Adopt/reconcile this documentation kit with existing repo docs, without overwriting local modifications. Establish doc links, source-of-truth precedence and minimal `AGENTS.md`; preserve all scoped agent rules.
  - Evidence (2026-11-01; implementation commit `1275f7e`): added explicit links from README and root `AGENTS.md` to the vision, roadmap, platform architecture and Portfolio architecture; retained scoped web/API instructions and linked authoritative domain/model contracts. Clarified `docs/architecture.md` as the historical implementation snapshot through Milestone 2C. Kept proposed platform direction separate from implemented behavior, summarized the financial/model invariants that had been condensed from the prior root guidance, and preserved the provided documents' substantive content while reconciling links and precedence. `npm run format:check`, `git diff --check`, and documentation target existence checks pass. No code, model, migration or financial behavior changed.
- [x] **M0.3** Separate and commit outstanding identity bootstrap, model-package v2/v3, proposal API, migrations and workspace changes into reviewable commits; resolve generated-contract drift and Alembic graph. Preserve approved P-GOOGL package hash and proposed-state semantics.
  - Evidence (2026-11-01): inspected the committed implementation and migration history (`3b237b5` package v1, `d82535f` package templates/multi-archetype, identity bootstrap, proposal API and migrations, `1be9a85` reviewer workspace, `2cde719` contracts/operating docs); no outstanding application-code changes were present. `npm run contracts:check` reports current OpenAPI/TypeScript artifacts; Alembic reports one head `9f2a6d4c81b7` and linear production-to-local chain `6c2eaf0b8147 → b16d4f8a2c91 → c17a0b9d4e62 → 3e5c8a1d7b42 → 9f2a6d4c81b7`. Focused model/package/exporter/archetype/proposal/guard/migration suite: 71 passed, 2 skipped, 37 deselected. Revalidated private P-GOOGL package hash; `PARITY_PASS`, 30/30 projections and 22/22 output checks, `PROPOSED_SOURCE_REVISION`. The earlier backend integration commit combines several related features; it is preserved rather than rewritten. No production operations were performed.
- [x] **M0.4** Run backend/frontend/type/contract/migration suites; diagnose full-repo mypy and inventory failures rather than blanket disabling. Record genuine pre-existing failures with baseline evidence.
  - Evidence (2026-11-01): `npm run check` passed lint, format, Next typecheck, strict mypy (`172` files), web unit tests (`166`), API unit tests (`593 passed, 2 skipped, 193 deselected`), repository source-data policy (`3 passed`), contracts, and optimized Next.js build. `npm run test:integration` passed against the preflight-verified local `127.0.0.1/portfolio_app_test` target (`133 passed, 4 skipped, 651 deselected`); migration roundtrip and incremental upgrade from `6c2eaf0b8147` were exercised in disposable schemas. Focused N1 suite was also green (`71 passed, 2 skipped`). `alembic heads` reports only `9f2a6d4c81b7`; no generated files or test changes remain in the working tree. Skips are retained as reported by pytest, not converted to passes. No production operation was run.
- [x] **M0.5** Verify model workspace in browser desktop/mobile (including proposal preview and explicit reviewer confirmation); distinguish fixture browser evidence from live database verification.
  - Evidence (2026-11-01): `npm run test:e2e -- --project=desktop --project=mobile` completed with 55 passed, 11 conditionally skipped and 0 failed. The model workspace preview/accept flow verifies proposed-vs-current input/output differences, disabled acceptance before review, required decision note, explicit confirmation, one acceptance request and immutable revision ID. The broader run covers Company Explorer, Portfolio, Decisions, Universe, Research review, Operations states, navigation and responsive behavior in Chromium desktop/iPhone-sized mobile contexts. Initial failures were stale E2E assertions for content behind existing disclosures and an updated missing-estimate message; tests were aligned with current accessible UI semantics. No product behavior was changed. `npx prettier --check apps/web/e2e/research.spec.ts` and `git diff --check` pass. Eleven live-database or project-conditional checks remain skipped; this is fixture-based UI evidence, not live Neon/deployed verification.
- [ ] **M0.6** Milestone quality review; open PR, capture check results and owner decision; reassess M1–M9 against Product Vision.
  - Review evidence (2026-11-01): owner confirmed the two XLSX files already tracked on public `origin/main` are safe to publish; they remain unchanged. The PR adds no workbook snapshots and the credential-pattern scan found no token, service-account credential or database URL patterns. Private source identifiers remain omitted. CI confirmed the `ubuntu-24.04` pin restores Python 3.12.3 setup, then exposed two tests coupled to the excluded workbook, six unclassified application tables, and stale backup/restore assertions for Alembic `6c2eaf0b8147` even though the fixture upgrades to the repository head. Commit `99a8bdf` marks the workbook-dependent tests as `source_data`, classifies the six tables and adds a registry-coverage regression; commit `3533b83` derives both backup/restore assertions from the checked-in Alembic heads. Local `npm run check` passes (592 API passed, 2 skipped; web 166 passed); both source-data DCF tests pass locally. The corrected PostgreSQL Actions rerun is pending. No merge, production write/migration, manual deployment, Sheets edit or model acceptance occurred.
  - Product alignment is recorded below; the dependency ordering remains consistent with the approved vision and architecture.

### M0.6 Product-vision reassessment

The M1→M2→M3 order matches the product vision and Portfolio architecture: verify target, recovery and private access first; prove one reviewed real-model lifecycle; then establish useful canonical holdings, cash and targets without requiring a whole-workbook import. M4/M5 complete company research and human-reviewed proposals; M6 broadens only proven paths; M7 provides operational reliability; M8/M9 remain deferred until Portfolio is secure and stable. Add an explicit dependency: complete the private hosted identity/session boundary (M1.4/M7.1) before hosted access or any production model/portfolio write in M2.5/M3.4. No investment-policy or methodology changes are proposed.

**Done when:** critical work is version-controlled and integrated for review, local test baseline is honest, no sensitive artifacts tracked, migration head unique; PR URL captured. An unresolved browser gate remains explicitly blocked if not executed.

## Milestone M1 — Verify cloud target and safe delivery controls

**Objective:** Live read-only verification and rehearsed release path; no import yet.  
**Dependencies:** M0 integration baseline. **Exit:** verified target, schema drift plan and recovery procedure.

- [ ] **M1.1** Use authorized read-only Neon control-plane/SQL access; identify exact project/branch/database, current production Alembic head and counts. Do not bypass target guard.
- [ ] **M1.2** Map migration chain from last reported prod `6c2eaf0b8147` through relevant local heads (`b16d4f8a2c91`, `c17a0b9d4e62`, `3e5c8a1d7b42`, `9f2a6d4c81b7` as actually present); verify order from repository, not from this historical list.
- [ ] **M1.3** Rehearse migrations in disposable PostgreSQL with backup/restore, backward-compatible API checks, data guard and idempotence tests. Prepare scoped production approval package; **do not apply**.
- [ ] **M1.4** Verify deployed Vercel/Render topology, API auth and read-only endpoints; document release/rollback procedure and shared-runtime risks.
- [ ] **M1.5** Milestone review, PR and vision alignment; keep approval-needed changes as separate planned operations.

## Milestone M2 — First real reviewed company/model in cloud

**Objective:** Deployed user can see a legitimately accepted P-GOOGL native valuation with revision provenance.  
**Dependencies:** M0/M1; exact reviewed source acceptance, schema and recovery approvals. **Exit:** production readback and app/browser evidence.

- [ ] **M2.1** Revalidate the immutable P-GOOGL source package from the local private snapshot store and confirm its payload hash and current mapping. The last evidence was 30/30 projection and 22/22 output parity; input drift is `PROPOSED_SOURCE_REVISION`, not accepted.
- [ ] **M2.2** Independently review probability drift, financial methodology, source age and identity mapping; explicitly approve/reject the exact source proposal. No automatic fixture replacement.
- [ ] **M2.3** Perform guarded **read-only** identity and model preview against verified live Neon; capture exact proposed records, existing/base revision state, compatibility errors and before/after counts.
- [ ] **M2.4** **OWNER GATE:** Review exact migration, fresh recovery point, identity bootstrap and model acceptance/apply plan. Without explicit approval, mark blocked and work on unrelated ready tasks.
- [ ] **M2.5** After explicit scoped approval only, apply migration/identity/model transactions; verify receipts, idempotency, immutable revision history and expected counts.
- [ ] **M2.6** Verify Render/API and browser (desktop/mobile) reads the accepted valuation; confirm enterprise IRR label vs shareholder IRR and unavailable data behavior. Review and open milestone PR for code/docs; production action recorded separately.

## Milestone M3 — Useful canonical portfolio baseline

**Objective:** Verified real holdings, cash, companies/listings and strategic targets on the cloud dashboard.  
**Dependencies:** M1, app contracts; source ownership review. **Exit:** Portfolio and Universe useful without whole-workbook import.

- [ ] **M3.1** Define and approve minimal typed source contracts for company/listing identity, holdings/cash and targets; reconcile held listings, including AUX cases, without inferred identity.
- [ ] **M3.2** Implement/test small source extraction and immutable package replay; handle sparse Sheets responses correctly and explicitly. No XLSX formula-cache dependency.
- [ ] **M3.3** Show private, read-only canonical diff with gaps, source freshness, totals and exclusions; separate optional candidates/scores from held-position blockers.
- [ ] **M3.4** **OWNER GATE:** Approve specific input hashes, target, recovery and guarded import. Then verify transactional apply/readback if authorized.
- [ ] **M3.5** Deliver Portfolio and Universe UI data reconciliation, target gaps, missing-data and stale-source indicators; browser-verify desktop/mobile.
- [ ] **M3.6** Milestone PR, review product usefulness and revise future sequence.

## Milestone M4 — Decision-ready Company Explorer and research queue

**Objective:** User can investigate and prioritize companies, not merely browse imported tables.  
**Dependencies:** canonical identities and at least representative real data. **Exit:** end-to-end research workflows.

- [ ] **M4.1** Audit existing Company Explorer/Rankings/Assessments; retain working features and address only demonstrated gaps.
- [ ] **M4.2** Integrate source-backed fundamentals, estimates/market observations and clear freshness/provenance. Preserve provider conflicts and point-in-time semantics.
- [ ] **M4.3** Show independent Durability, Quality, Execution and Risk, approved lifecycle and Portfolio/Watchlist/Research ranking logic with explanatory gaps.
- [ ] **M4.4** Add actionable attention/research queue, thesis evidence and material change history; no automatic lifecycle decisions.
- [ ] **M4.5** Review desktop/mobile UX, integration, numerical semantics, cross-company comparisons; PR and roadmap reassessment.

## Milestone M5 — End-to-end human-reviewed agent workflow

**Objective:** Research agent can propose a change; reviewer can safely decide; accepted state propagates.  
**Dependencies:** deployed auth/role separation, model/assessment contracts, M2 first accepted revision. **Exit:** real authorized proposal loop.

- [ ] **M5.1** Verify M7 proposal API code and migrations actually integrated; validate agent/reviewer token separation, authorization negative tests and base revision conflicts.
- [ ] **M5.2** Confirm agent-authored proposals have method-specific inputs, evidence, rationale, provenance and no implicit acceptance.
- [ ] **M5.3** Deploy authenticated proposal/read/review APIs only with approved security changes and release gate.
- [ ] **M5.4** End-to-end reviewer UI: diff, calculation parity, stale/conflict states, explicit accept/reject, immutable history and audit.
- [ ] **M5.5** Test one realistic proposed model update without uncontrolled mutation; review and PR.

## Milestone M6 — Broaden model and data coverage incrementally

**Objective:** Multiple companies/methods can be used through the same trusted lifecycle.  
**Dependencies:** proven M2/M5 flows. **Exit:** repeatable documented onboarding, not universal parser.

- [ ] **M6.1** Live-validate scoped UFCF exporters P-CPRT and P-AMZN with distinct methods; correct template assumptions and report drift separately.
- [ ] **M6.2** Validate owner-cash-flow and residual-income representative models; preserve missing eligible quotes and HDFC legacy/drop status.
- [ ] **M6.3** Document versioned package schema evolution, compatibility and method onboarding; reject unknown layouts/methods safely.
- [ ] **M6.4** Expand source/market/FX ingestion under review and operational bounds; measure coverage and quality rather than add providers indiscriminately.
- [ ] **M6.5** PR, product/ROI review; stop adding methods without clear user demand.

## Milestone M7 — Reliable private cloud operations

**Objective:** Safe daily use, current data and recoverable failure.  
**Dependencies:** M3–M6 as relevant. **Exit:** monitored, secure and economically reasonable runtime.

- [ ] **M7.1** Select and verify a real supported identity/session provider; enforce backend app/role permissions, trusted proxy, CSRF/session and secret handling.
- [ ] **M7.2** Establish reviewable scheduled acquisition jobs with timeouts, quotas, refresh metrics and recovery; **OWNER GATE** before activation.
- [ ] **M7.3** Build Data Health UX for stale provider data, failed packages, pending approvals and source quality.
- [ ] **M7.4** Test backup/recovery, API/web deploy rollback, auth-negative tests, observability and cost dashboards.
- [ ] **M7.5** Prove ordinary usage is available in cloud without local computer; PR and release acceptance.

## Milestone M8 — Personal Universe shared platform

**Objective:** Preserve stable Portfolio while introducing reusable foundations.  
**Dependencies:** Portfolio reliable in cloud. **Exit:** shared boundaries enforced without big-bang migration.

- [ ] **M8.1** Inventory true second-consumer candidates; define module owner/registry and platform boundaries.
- [ ] **M8.2** Establish shell, shared design tokens/components and API conventions incrementally; cross-app smoke tests.
- [ ] **M8.3** Introduce private App Hub and route migration with redirects; retain Portfolio deep links.
- [ ] **M8.4** Implement reviewed app module template/generator and scoped database ownership; avoid moving Portfolio `public.*` just for symmetry.
- [ ] **M8.5** PR and architecture review against `personal-universe.md`.

## Milestone M9 — Prove second app and finish v1 product acceptance

**Objective:** A second useful private app runs under the same default Neon/Render/Vercel topology while Portfolio remains fully functional.  
**Dependencies:** M8 and production security. **Exit:** architecture claim demonstrated by actual product.

- [ ] **M9.1** Select a small genuine second app, not a placeholder; document its data owner and minimal CRUD job.
- [ ] **M9.2** Generate and deliver authenticated web/API/schema/transaction workflow; add cross-app and responsive E2E tests.
- [ ] **M9.3** Verify shared deployment, isolated domain permissions, migration rollback, cost/operational tradeoffs and app-hub navigation.
- [ ] **M9.4** Complete Portfolio product-vision acceptance review; document supported functionality, remaining gaps and roadmap v2.
- [ ] **M9.5** Final milestone PR/release handoff with rollback and production approvals kept distinct.

## Historical evidence — VERIFY, NOT AUTO-ACCEPT

- P-GOOGL v1 real capture: exact run ID and payload hash remain in the local private store and are intentionally omitted from this public repository; 186 cells/17 ranges, computational parity pass (30 projections, 22 outputs), and input drift remains a proposal. Evidence stored privately, not in Git.
- Identity bootstrap and proposal API were reported locally implemented with migrations `3e5c8a1d7b42` and `9f2a6d4c81b7`; actual integration and prod schema **not verified** here.
- Exporter v2 supported P-GOOGL/P-CPRT/P-AMZN in tests; package v3 provided UFCF/owner-cash-flow/residual-income transport. Other live captures **not verified**.
- Model workspace passed unit/build checks; browser E2E was blocked by `spawn EPERM`; do not claim desktop/mobile verification.
- Neon last reported prod head `6c2eaf0b8147`, initially schema-only, with write controls off. Reverify rather than rely on historical state.

## Decision and blocker log

| ID    | Status                   | Item                                                             | Resolution/owner                                                                             |
| ----- | ------------------------ | ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| D-001 | AGREED_DIRECTION         | Small reviewed per-model packages, not full workbook import      | Product architecture; method-specific contracts                                              |
| D-002 | AGREED_DIRECTION         | Shared Personal Universe modular monolith; Portfolio first       | Existing platform architecture; phase after stable Portfolio                                 |
| D-003 | OPEN                     | Accept or reject current P-GOOGL source-input drift              | Owner; needs exact proposal evidence                                                         |
| D-004 | OPEN                     | Production schema/identity preview, migration and recovery point | Read-only operator verification then approval                                                |
| D-005 | OPEN                     | Auth provider and trusted Vercel–Render session boundary         | Security review                                                                              |
| D-006 | RESOLVED_OWNER_CONFIRMED | Public-repository privacy review                                 | Owner confirmed reference workbooks are safe for publishing; no workbook content was changed |
| B-001 | RESOLVED_LOCAL           | Uncommitted/inconsistent M2, M5–M8 implementation state          | M0.3 confirmed integrated local code, tests, contracts and migration graph                   |
| B-002 | RESOLVED_LOCAL           | Browser E2E was not verified in the earlier sandbox              | M0.5 Playwright desktop/mobile fixture run passed; live DB scenarios remain separate         |
| B-003 | RESOLVED_OWNER_CONFIRMED | Existing workbook XLSX files on public `origin/main`             | Owner confirmed both are safe for publishing; no content was opened or changed here          |

## Milestone PR template (copy into each PR)

**Outcome:** User-visible result and domain scope.  
**Implementation:** Commits, migrations and contracts changed.  
**Evidence:** Tests/checks/browser screenshots or recorded blocker, actual source/target verification, numerical parity.  
**Safety:** Data ownership, permissions, source provenance, secret scanning, rollback, protected operations not executed.  
**Known gaps:** Clearly labeled.  
**Roadmap impact:** Completed IDs, changed priorities, next cursor.  
**Production authorization:** `NOT REQUESTED` / `PENDING` / `SEPARATELY APPROVED` with reference, never inferred from PR.

## Completed task log

_Add one short row per completed subtask: date | task ID | commit | tests/evidence | decision/blocker | next cursor. Do not paste secrets, source values or huge logs here._

| 2026-11-01 | M0.1 | `f0405f5` (consolidated)| Git inventory; one Alembic head; CI source-data policy PASS | Protected docs, branches and stash preserved; production migrations pending | M0.2 |
| 2026-11-01 | M0.2 | `f0405f5` (consolidated)| Formatting, diff whitespace and doc targets PASS | Historical architecture scope clarified; no semantic or financial changes | M0.3 |
| 2026-11-01 | M0.3 | `f0405f5` (consolidated)| Package parity validation; contracts current; focused 71-pass suite; single migration head | Source inputs remain proposed; production schema is behind local head | M0.4 |
| 2026-11-01 | M0.4 | `f0405f5` (consolidated)| Full local quality checks PASS; PostgreSQL integration 133 passed, 4 skipped | Browser workflow is the remaining local M0 gate; production schema remains behind local head | M0.5 |
| 2026-11-01 | M0.5 | `f0405f5` (consolidated)| Desktop/mobile Playwright: 55 passed, 11 skipped, 0 failed; focused browser regression corrected; formatting and diff checks pass | Live database/deployed checks remain unverified; no application behavior changed | M0.6 |
| 2026-11-01 | M0.6 (IN_PROGRESS) | `3533b83` | Corrected Ubuntu pin, CI source-data test classification, migration table-group coverage and stale Alembic-head assertions; `npm run check` passes | Corrected GitHub Actions rerun pending; no merge or production action | Verify checks on PR #13 |
