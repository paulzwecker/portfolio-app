# Recovery Milestone A — Repository Consolidation and Bootstrap Baseline

- **Assessment date:** 2026-10-31
- **Integration branch:** `codex/recovery-a-bootstrap-freeze-2026-10-31`
- **Bootstrap compatibility:** YES, using the separate reviewed `b02f6c3` checkout at Alembic 6c
- **Production execution:** NOT performed

## Integrated local state

The new integration branch is rooted at the reviewed R3 baseline and merges the
preserved local R8/Task 9 work. No remote branch was fetched or changed, no branch or
stash was deleted, and nothing was pushed.

| Purpose                                 | Reference                                  | Notes                                                                                                                                                                 |
| --------------------------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reviewed integration baseline           | `b02f6c3b1aa9693bfc12d4be2f5750d1f5c8cdcc` | R3 integration baseline; ancestor includes source acquisition, model analytics bootstrap and importer-scoped value-fidelity work.                                     |
| Task 7 model analytics bootstrap        | `d6fd1b57d560306684c4d48ae573f446886654bc` | Already in the baseline ancestry; no duplicate cherry-pick.                                                                                                           |
| Step 5A.1 acquisition/read-only preview | `6a671e07b35e7b76c07672101578b6371ff92e1a` | Already in the baseline ancestry.                                                                                                                                     |
| Task 8/value-fidelity branch            | `4931b185e091c519ded3555bc99ac2f081e50a92` | Already in the baseline ancestry; includes importer-scoped semantic validation.                                                                                       |
| R3 integration commit                   | `b02f6c3b1aa9693bfc12d4be2f5750d1f5c8cdcc` | Root of the recovery integration branch.                                                                                                                              |
| Preserved worktree snapshot             | `9529d40158f507bed6ddd958b7af624dc24f21dc` | Local preservation commit for recovered R8/Task 9 changes; also retained on `codex/recovery-a-preserved-work-2026-10-31`.                                             |
| Integration merge                       | `b71ddf00a0fd907f595a3977ee88bdec384b7ab3` | Merges preserved changes onto the R3 baseline without conflicts.                                                                                                      |
| Original preservation stash             | `9bdd3ea6c97fa80950df070fc06443891bb10307` | Retained unchanged. Its workbook-sync module and `b16` migration are duplicates of files included in the preserved worktree commit; it was not applied a second time. |

R1/R2/R4/R5/R6/R7/R8/R9/R10 are not represented by one clean series of
milestone-labelled commits in the available repository. We found no standalone Task 8
or Task 9 completion report. The available implementation evidence is the commit and
stash inventory above, the current R10 report, and the synthetic tests described below.
This does not establish live Google Drive, Neon, or production import completion.

The merge retained the manual-operations request isolation change: requests run by
exact ID do not claim another queued request, and the API contract test explicitly sets
its enabled state instead of inheriting the operator's disabled `.env` setting.

## Migration dependency map

The graph has exactly one current head. Its tail is:

```text
12a6f0d9c3e1
  └─ 14b4c1a0a001  canonical bootstrap receipts
      └─ 3f7c9d12b6a4  historical market bootstrap runs
          └─ 6c2eaf0b8147  fundamentals bootstrap runs  [last verified production head]
              └─ b16d4f8a2c91  workbook sync artifacts, approvals, runs, previews
                  └─ c17a0b9d4e62  permit production target label in market/fundamental run ledgers [local head]
```

- `b16d4f8a2c91` is the Task 9 schema dependency. It creates the workbook-sync ledger
  tables and extends the operational job-name constraint. It does not transform
  canonical portfolio data.
- `c17a0b9d4e62` depends on `b16d4f8a2c91` and changes the two bootstrap-ledger target
  constraints to admit `production`. It does not import observations. Neither
  migration was run against production.
- The current integration branch is at local Alembic head `c17a0b9d4e62`; `alembic
heads` reports one head. The reviewed `b02f6c3` tree contains neither newer migration,
  and an isolated `git archive` check reports its head as `6c2eaf0b8147`.

## R7 bootstrap compatibility decision

**The initial canonical portfolio bootstrap is schema-compatible with production at
`6c2eaf0b8147`, provided it uses the reviewed `b02f6c3` checkout.** The canonical
receipt table is created by `14b4c1a0a001`, already included in 6c. The R7 importer
does not need the later workbook-sync tables or the production-label constraint added
for R8. A new synthetic PostgreSQL integration test downgraded only its unique,
disposable test schema to 6c and successfully applied/reconciled the canonical sample
bootstrap.

The bootstrap CLI deliberately requires the target's Alembic heads to equal the
checked-out code's expected heads. Therefore running the current integration branch at
production 6c would fail closed: its expected head is `c17a0b9d4e62`. Use the b02
bootstrap-compatible checkout for R7; do not relax the exact-head check. This is a
code/schema compatibility conclusion, not authorization to run R7. The source snapshot
acceptance, exact current preview, target identity, recovery point, and separate
operator approval remain mandatory.

### Bootstrap-critical and post-bootstrap checkouts

- **R7:** `codex/r3-integration-baseline` at `b02f6c3b1aa9693bfc12d4be2f5750d1f5c8cdcc`.
  This preserves the reviewed acquisition, semantic fingerprint, target guard,
  preflight, and canonical importer while matching the production 6c head. The Task 7
  model-analytics code is present in its ancestry but is not invoked by the canonical
  portfolio import.
- **After R7 and a separately reviewed schema upgrade:**
  `codex/recovery-a-bootstrap-freeze-2026-10-31` at the integration commit. It contains
  Task 9 sync and R8 production-ingestion support and expects b16/c17. Do not use it for
  a production operation until those migrations are separately reviewed, backed up and
  applied under authorization.

## Verification

- `npm run check`: lint, format, web/API typechecks and unit suites passed; it stopped
  when Node's test runner tried to spawn a worker and Windows returned `spawn EPERM`.
- Unit results on the integrated branch: 163 web tests passed; 470 API tests passed,
  2 skipped, 147 deselected by markers.
- The source-data policy assertions pass 3/3 when invoking
  `node scripts/tests/ci-source-data-policy.test.mjs` directly. The npm test-runner
  wrapper is blocked by the process-spawn restriction, not by a failed policy
  assertion.
- `npm run contracts:check`: passed.
- `npm run build`: passed; production Next.js build and static page generation completed.
- Focused PostgreSQL integration on the loopback `portfolio_app_test` database: 11
  passed, including workbook-sync preview/apply/replay and R7 import compatibility at
  schema 6c. Each test used an isolated schema; no production database was contacted.
- A broader integration run produced 120 passes. Two role-boundary cases require
  `CREATEROLE`; two migration backup/restore cases require PostgreSQL client utilities
  (`pg_dump`/`pg_restore`) or the configured tools container. Three workbook-sync
  failures from incomplete synthetic manifests were fixed by completing the test
  manifest (not weakening validation); all five workbook-sync integration cases passed
  in the focused run.
- Current Alembic graph: one head, `c17a0b9d4e62`. Baseline b02 graph: one head,
  `6c2eaf0b8147`.

## Data-in-Git blocker

No new workbook snapshot, credential, source manifest or private valuation payload was
added by Recovery A. However, the repository already tracks the real-looking
`reference/workbook/Portfolio_Watchlist.xlsx` and `reference/workbook/Market Data.xlsx`
files from the initial commit, and numerous historical reconciliation JSON reports
contain imported financial/model details. They are not ignored; the checked-in
`origin/main` reference also contains the workbook files. The source workbooks' private
contents were not opened or reproduced here.

This means the requirement that real/private workbook data remain out of Git is **not
met by the existing repository history or current tree**. Removing files in a new
commit would only remove them from the tip; it would not erase their earlier Git
objects. Complete purging requires a separately planned history rewrite and remote
coordination, which this task forbids. Do not publish or push this branch under an
assumption that the privacy condition has been satisfied. Keep the actual approved
source snapshots in the external private store and decide separately whether/how to
sanitize historical Git content and dependent defaults/reports.

## Next steps

1. Confirm the exact accepted portfolio/market snapshot pair and R5 preview privately;
   this report intentionally does not inspect or restate those IDs or hashes.
2. If still valid, prepare R7 from the b02 bootstrap-compatible checkout and repeat
   the guarded target/source/recovery-point checks immediately before any apply. R7
   remains separately gated and was not executed.
3. Only after R7 reconciliation, review and authorize migration `b16`, then `c17`,
   before running Task 9 synchronization or R8 production ingestion.
4. Install PostgreSQL 18 client utilities or configure the supported test-tools
   container; use a disposable test role with test-only `CREATEROLE` for the remaining
   integration cases. Never grant these privileges to the production app role.
5. Resolve the pre-existing data-in-Git issue before any push/PR that would distribute
   additional copies or history references.
