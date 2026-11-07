# Portfolio execution roadmap

Updated 2026-11-07. [Product vision](docs/PRODUCT_VISION.md) owns outcomes.
The [documentation index](docs/README.md) routes detailed contracts and runbooks.

## Execution cursor

| Field         | Current value                                                                                             |
| ------------- | --------------------------------------------------------------------------------------------------------- |
| Active work   | MP1 publication-review completion on existing PR #23                                                      |
| Branch        | `codex/model-publication-vertical-slice`                                                                  |
| Status        | IMPLEMENTATION_COMPLETE / LOCAL_VERIFIED. Updated PR awaits owner review                                  |
| Next task     | Review/merge PR #23, then resume MP2 from updated main with a reviewed real template and canonical base   |
| PR            | [#23](https://github.com/paulzwecker/portfolio-app/pull/23), open and unmerged at inspection              |
| Approval gate | Owner review/merge, followed by separately authorized source installation and production/model operations |

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
