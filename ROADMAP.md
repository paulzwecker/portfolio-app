# Portfolio execution roadmap

Updated 2026-11-07. [Product vision](docs/PRODUCT_VISION.md) owns outcomes.
The [documentation index](docs/README.md) routes detailed contracts and runbooks.

## Execution cursor

| Field         | Current value                                                                                                                                                         |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Active work   | C2.1 held-listing/FX coverage, canonical ingestion compatibility and recovery assessment                                                                              |
| Branch        | `codex/c2-canonical-ingestion-readiness`, independently based on merged PR #23                                                                                        |
| Status        | IMPLEMENTATION_COMPLETE / LOCAL_VERIFIED / PRODUCTION_PREVIEW_VERIFIED for the market planning scope                                                                  |
| Next task     | Owner review; current-state recovery and bounded market authorization, plus reviewed SEC issuer mappings                                                              |
| PR            | [#25](https://github.com/paulzwecker/portfolio-app/pull/25), owner review/CI gate; completed [#24](https://github.com/paulzwecker/portfolio-app/pull/24) stays stable |
| Approval gate | Owner merge, current-state recovery and separately authorized ingestion. P-GOOGL acceptance remains DEFER                                                             |

## Baseline and outstanding gates

- M0 merged as PR #13. M1 is `PRODUCTION_VERIFIED` for the minimal portfolio scope.
  The [canonical baseline](docs/production-canonical-baseline.md) records 209
  companies, 23 securities/listings, 22 holdings, two cash rows and 16 targets.
- M2 P-GOOGL is `PRODUCTION_PREVIEW_VERIFIED` and unaccepted. Native parity passes.
  The private investment review recommends DEFER pending dated assumptions, fiscal
  alignment and methodology evidence. PR #22 merged.
- Last recorded production schema is `9f2a6d4c81b7`. Reverify live target/schema
  before operations. The portfolio recovery branch expires 2026-11-14 at 09:54 CET.
- Earlier MP1 local verification passed full quality/build checks (166 web and
  659 API tests, two skips), PostgreSQL (137 passed, four skips), focused sync
  tests (19 passed), and desktop/mobile model review (two passed).
- Production synchronization and automatic promotion await authorization. M7
  retains backup/restore privilege/tool skips and hosted role-separation work.
- PR #23 merged as `0717498`; PR #24 contains the completed publication preflight
  and capability-roadmap work awaiting owner review. C2.1 advances the independent
  missing market-data foundation without expanding that completed PR.

## Current integration milestone

| Task                                     | Status         | Acceptance                                                                                        |
| ---------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------- |
| MP1.1 Publication contract               | LOCAL_VERIFIED | Frozen typed publication, native parity, bounded capture and durable proposals                    |
| MP1.2 Reliability                        | LOCAL_VERIFIED | Source lock, replay and immutable conflicts retained through acceptance                           |
| MP1.F1 Documentation hierarchy           | LOCAL_VERIFIED | Selective entrypoints, index, original history preserved, stale claims scoped and link validation |
| MP1.F2 Independent model synchronization | LOCAL_VERIFIED | Same-company methods may share revision labels; conflicts remain scoped to their model            |
| MP1.F3 Exact model selection             | LOCAL_VERIFIED | Summary, history and editor preserve the selected model/listing                                   |
| MP1.F4 Cross-method proof                | LOCAL_VERIFIED | DCF/owner-cash-flow/residual-income retain independent evidence, revisions and return definitions |
| MP1.F5 Integration gate                  | LOCAL_VERIFIED | Focused/DB/UI checks, independent review, quality checks and one updated PR                       |
| MP1.R1 Publication review safeguards     | LOCAL_VERIFIED | Typed source/native values and caller-bound preview hash; stale reviewer tabs remain blocked      |
| MP1.R2 Reviewer workflow                 | LOCAL_VERIFIED | Actual acceptance outcome, preserved unresolved rationale, explicit parity and immutable identity |

## Next milestones

- **MP2** follows MP1 merge. Onboard a reviewed real template and canonical base.
  First-model seeding uses the existing guarded path. Real source publication and
  any model acceptance need their specific owner approval and current recovery.
- **MP3** follows a proven reviewed lifecycle. Design and test promotion policy,
  exceptional-change routing, freshness limits and recovery. Policy approval and
  activation remain separate gates.
- **M3** remaining work is portfolio/Universe data-quality and browser acceptance.
  The minimal import tasks were completed by M1.
- **M4** advances source-backed company research. **M5** proves the hosted agent /
  reviewer loop after role separation and one accepted model. **M6** expands
  reviewed model coverage afterward.
- **M7** covers security, recovery, monitoring and bounded operations. **M8/M9**
  platform extraction and another application follow a useful, stable Portfolio.

Original task definitions, decisions and evidence remain in the
[roadmap through MP1](docs/history/roadmap-through-mp1.md).

## Execution evidence

### C2.1 — canonical ingestion readiness

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
- Recovery remains ready and expires 2026-11-14 09:54 CET, but contains the empty
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

| Date       | Task                    | Evidence                                                                                                                                                                                                                                                                                                                                                                  | Next action                                             |
| ---------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 2026-11-07 | MP1.F1                  | Audited 125 Markdown files; preserved safety/provenance, consolidated entrypoints and archived the original ledger                                                                                                                                                                                                                                                        | Check links; complete model-scoped sync                 |
| 2026-11-07 | MP1.F2/F4               | Three methods on one synthetic company publish the same revision label; native parity, independent advancement, model-scoped conflicts and corrected source metadata pass PostgreSQL verification. Three Apps Script tests pass                                                                                                                                           | Complete UI verification and final review               |
| 2026-11-07 | MP1.F3/F5               | Full check passes (166 web / 659 API unit, two skips); isolated PostgreSQL 139 passed / four skips; focused suite 31; browser six plus two screenshot checks; 133 Markdown files link-clean; independent reviews pass                                                                                                                                                     | Owner review of PR #23, then MP2 from merged main       |
| 2026-11-07 | Remote integration gate | [GitHub Actions](https://github.com/paulzwecker/portfolio-app/actions/runs/42388954068) passed all three jobs on code commit `c770e0f`; Vercel Preview passed                                                                                                                                                                                                             | Owner review of the current PR head                     |
| 2026-11-07 | MP1.R1/R2 inspection    | PR #23 remains open. Clean branch/worktree and preserved stash. Independent review found false acceptance feedback and server-only preview approval. Baseline desktop/mobile review tests pass                                                                                                                                                                            | Verify caller-bound acceptance and reviewer evidence    |
| 2026-11-07 | MP1.R1                  | Typed parity evidence, 14 unit cases, six isolated PostgreSQL checks plus three API/replay checks, strict backend types and lint pass. Production controls remain disabled                                                                                                                                                                                                | Verify reviewer feedback and desktop/mobile interaction |
| 2026-11-07 | MP1.R2 / review         | Exact source/native values, signed deltas, hashes and timestamps are visible through shared responsive tables. Six affected desktop/mobile checks pass, including refreshed/conflicted acceptance feedback, keyboard disclosure, preserved rationale and explicit reconfirmation. Independent review correction passes 16 API unit cases and 14 isolated PostgreSQL tests | Complete integration checks and update PR #23           |
| 2026-11-07 | MP1.R integration       | Code `1c5e712` passes full check (169 web, 666 API, two environment-specific skips), strict types, contracts and build. Focused PostgreSQL 14 passed. Six affected browser checks and final review reruns pass. Independent review and 133 Markdown links pass                                                                                                            | Owner review/merge of updated PR #23, then MP2          |

Browser evidence uses synthetic API responses on the local application. Desktop/mobile
screenshots remain in ignored `apps/web/test-results/**/publication-review*.png`.
The two unit skips cover Windows symlink privileges and POSIX-only credential mode
bits. Real source onboarding and production review remain owner-gated. Legacy bare
portable contracts retain their compatibility path, while publication acceptance
requires the caller-reviewed preview hash.

## Upkeep

Update cursor, status, short evidence and next action after each subtask. Put
stable behavior in canonical references, commands in runbooks and long results in
dated history. At integration, record tests/skips and review, update the existing
PR and wait for owner merge. Resume subsequent work from updated main. Report
implementation, local/source verification, production preview/readiness and
production application only with the corresponding evidence.
