# Native deployment and separately reviewed migrations

**Scope:** one developer, the existing GitHub repository, Render API, Vercel web
project, and Neon PostgreSQL database. This runbook describes the proposed
configuration in this branch; it does not confirm or change live provider
settings. Keep production writes, migrations, provider ingestion, recurring jobs
and Sheets polling separately authorized and disabled by default.

## Operating principle

Prefer provider-native behavior over a bespoke release orchestrator. GitHub Actions
checks pull requests. Protected `main` is the only production source branch. Render
deploys its existing API service only after GitHub CI checks pass, then gates traffic
on database readiness. Vercel keeps its native pull-request previews and deploys
`main` to production after merge. No GitHub deployment environments, provider API
tokens, custom deployment scripts, or deploy workflow are required.

```text
Pull request ── GitHub CI + owner review ── merge to main
     └──────── Vercel Preview                 ├── Render: CI checks pass → /health/ready → traffic
                                               └── Vercel: native production deployment

Production schema migration: separate operator review + recovery point + guarded CLI
```

The existing GitHub Environments, if present, are unused by this workflow. Leave
them untouched; no release secrets are needed in GitHub Actions. Do not add a Render
`preDeployCommand` for Alembic. Application startup and provider deployment never
apply migrations.

## Checked-in configuration

- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on pull requests to
  `main` and pushes to `main`. Require these exact job checks before merging:
  `Quality, contracts and build`, `PostgreSQL integration tests`, and
  `Windows migration command compatibility`. CI migrations and integration tests
  use only disposable local PostgreSQL; the workflow has no production credentials.
- [`render.yaml`](../render.yaml) keeps the existing `portfolio-api` service on
  `main`, sets `autoDeployTrigger: checksPass`, and uses `/health/ready`. The
  manifest retains production target verification and leaves ingestion, recurring
  operations, manual operations, workbook sync, Sheets polling and FMP disabled.
- [`apps/web/vercel.json`](../apps/web/vercel.json) keeps the existing Next.js
  monorepo install/build commands and does not suppress `main`. The Vercel project
  must be connected to this repository with root directory `apps/web` and
  production branch `main`; non-production branches remain Vercel Preview deploys.
- [`production_migration_preflight.py`](../apps/api/src/portfolio_api/production_migration_preflight.py)
  performs read-only Neon target, schema and recovery checks for a human-run
  migration. It never applies DDL. Only the existing guarded `npm run db:migrate`
  command can apply migrations.

Never run `npm run db:migrate` from CI.

Render documents that `checksPass` waits for the linked branch's CI checks, does not
deploy if checks are absent or any check fails, and treats GitHub check conclusions
`success`, `neutral` or `skipped` as passing. The three required CI jobs above must
therefore stay enabled and non-conditional. Render health checks reject an unhealthy
new instance before it receives traffic; its zero-downtime deploy keeps the prior
instance running when the new instance fails health checks. See [Render deploys](https://render.com/docs/deploys)
and [Render health checks](https://render.com/docs/health-checks).

Vercel's Git integration creates Preview deployments for pull requests and a
production deployment for the configured production branch. CI is enforced before
merge by GitHub branch protection; no separate Vercel Deployment Checks are needed
for this solo workflow. This avoids adding a second gate and avoids check-name
collisions. See [Vercel Git deployments](https://vercel.com/docs/git).

## `main` protection and owner review

The last read-only GitHub settings inspection recorded in the M1 evidence (2026-11-04)
found no `main` protection rule. Configure this manually before merging; this task
does not change GitHub settings.

In repository **Settings → Branches → Add branch protection rule**, target `main`
and enable:

1. **Require a pull request before merging**.
2. **Require status checks to pass before merging**, selecting the three exact job
   checks listed above after they have appeared on a pull request.
3. **Require conversation resolution before merging**.
4. Apply rules to administrators / disallow bypass, block force pushes and deletion,
   and do not allow direct pushes to `main`.

Use the owner checklist in the pull request template to record review of the diff,
financial/data invariants, migration effects, recovery plan, and CI/Preview evidence.
GitHub does not allow a pull request author to approve their own pull request. For
this one-person repository, the owner review is a recorded manual review before
merge; do not configure a required approving-review count that would deadlock the
owner. A formally enforced independent approving review requires a second GitHub
reviewer. See [GitHub's required-review behavior](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews).

## Historical initial schema mismatch and safety behavior

The last recorded live read-only observation of the previous Neon target
(2026-11-03) found Alembic `6c2eaf0b8147`, while the repository expected
`9f2a6d4c81b7`; the API reported `/health/live = 200` and `/health/ready = 503`
(`schema=outdated`). That target was not the new production database. The current
minimal canonical portfolio baseline and its production target are documented in
the [canonical production baseline](production-canonical-baseline.md). These
historical observations must not be used as current target evidence; reverify the
live identity/schema before any future release or migration.

Do **not** point the application at this older database with code that requires the
newer schema. For a first activation on a separate, verified-empty Neon database,
use the short path below; it does not migrate or retire this older database. For a
schema change to an existing data-bearing database, use the coordinated migration
procedure in the following section. The checked-in Render readiness path keeps an
incompatible new instance out of traffic; it is a deployment backstop, not a
replacement for migration sequencing.

The reviewed migration chain is linear:

```text
6c2eaf0b8147 → b16d4f8a2c91 → c17a0b9d4e62 → 3e5c8a1d7b42 → 9f2a6d4c81b7
→ a832e94d6f10 → b59f16c8a203
```

The historical revisions add workbook-sync tables, expand two check constraints,
and add model identity/proposal tables. The two ledger revisions append candidate,
review and publication tables without changing accepted holdings or targets. All
three ledger tables belong to the existing portfolio recovery inventory. No source
ownership transfers during migration. Publication is a separately authorized data
operation. Once publication history exists, its downgrade fails closed. Code that
predates the ownership guard cannot safely become a writer after ledger cutover.

The current read-only release preflight is pinned to the existing production
project `blue-pond-96398788`, primary `br-square-butterfly-bacw0rn5`, direct endpoint
`ep-floral-cake-bae16liy`, database `neondb`, and migration range
`9f2a6d4c81b7` → `b59f16c8a203`. These pins are a reviewable release plan. Fresh
live identity, inventory and recovery verification remain mandatory before owner
authorization. Earlier target/revision approvals grant no authority for this range.

## Initial activation on a new, empty Neon database

This path applies only when the exact configured Neon primary database has no
user relations, no rows, and no Alembic revision. It upgrades that new target from
`base` through the complete checked-in migration chain. It does not require a
historical-schema reconciliation or recovery branch because there is no existing
application state to preserve. If any user relation or Alembic state exists, stop
and use the data-bearing migration procedure below; do not call the target empty.

Keep the existing Render and Vercel projects. Do not point either service at the
new database until the migration and read-only schema check succeed. Keep the
previous Neon database intact until the new service is healthy and its read-only
identity/data inventory has been reviewed. Retiring the previous target is a
separate owner decision.

1. In Neon, create a new database on a primary branch (or a new Neon project if
   that is the chosen isolation boundary). Use the direct endpoint and a
   non-superuser migration-capable role. Record its exact project, primary branch,
   endpoint and database identifiers. Do not use a child/recovery branch as the
   production target.
2. In a secure local PowerShell session, configure `DATABASE_URL` with the direct
   endpoint and `sslmode=verify-full`; set `APP_ENV=development`,
   `DATABASE_TARGET_ENVIRONMENT=production`, `DATABASE_TARGET_DATABASE` to the
   exact new database name, and the matching `NEON_PROJECT_ID`, `NEON_BRANCH_ID`,
   `NEON_ENDPOINT_ID` and existing `NEON_API_KEY`. Keep all database write
   authorizations false, `CLOUD_INGESTION_ENABLED=false`,
   `RECURRING_OPERATIONS_ENABLED=false`, `MANUAL_OPERATIONS_ENABLED=false`,
   workbook sync disabled, and `GOOGLE_SHEETS_POLL_SECONDS=0`. The preflight reads
   process settings only; it does not load `.env` itself. Do not persist write
   authorization in `.env`.
3. Check out the clean, reviewed PR #14 commit that contains the migration graph.
   Copy that exact 40-character SHA from the reviewed GitHub PR into
   `EXPECTED_CHECKOUT_SHA`. Set `INITIAL_BOOTSTRAP_CONFIRMATION` to the exact
   `INITIALIZE <project>/<primary-branch>/<endpoint>/<database>/base-><head>`
   string shown below, using the identifiers and repository head returned by the
   independent Neon/GitHub checks. Run the read-only preflight:

   ```powershell
   $env:EXPECTED_CHECKOUT_SHA = '<reviewed 40-character PR commit SHA>'
   $env:INITIAL_BOOTSTRAP_CONFIRMATION = 'INITIALIZE <project>/<primary-branch>/<endpoint>/<database>/base->b59f16c8a203'
   npm run db:production-preflight -- fresh-bootstrap-preflight
   ```

   The command verifies the clean pinned `main` or `codex/*` checkout, exact Neon
   primary through the control-plane API and live PostgreSQL connection, TLS,
   database name, empty public/default schema, absence of user relations, absence
   of Alembic state, and disabled write/background authorization. It reports an
   empty-state fingerprint and `recovery_required=false`; it is read-only. A
   mismatch, unknown relation, or changed target is a stop condition.

4. Review the exact target, migration head, empty-state result and PR checks. Only
   after separate explicit owner authorization, recheck `git rev-parse HEAD` and
   run the existing full-chain migration with temporary process-only authorization.
   This is `alembic upgrade head` through the guarded `db:migrate` command; never
   use `alembic stamp`:

   ```powershell
   $previousAuthorization = [Environment]::GetEnvironmentVariable('DATABASE_PRODUCTION_WRITES_AUTHORIZED', 'Process')
   if ($previousAuthorization -eq 'true') { throw 'Start without production write authorization.' }
   try {
       $env:DATABASE_PRODUCTION_WRITES_AUTHORIZED = 'true'
       npm run db:migrate
       if ($LASTEXITCODE -ne 0) { throw 'Migration failed; stop and inspect the target read-only.' }
   }
   finally {
       if ($null -eq $previousAuthorization) { Remove-Item Env:DATABASE_PRODUCTION_WRITES_AUTHORIZED -ErrorAction SilentlyContinue }
       else { $env:DATABASE_PRODUCTION_WRITES_AUTHORIZED = $previousAuthorization }
   }
   ```

   The database write-target guard still verifies production primary identity,
   TLS, role privileges and explicit production authorization on the migration
   connection. The empty-database preflight does not authorize or execute DDL. If
   migration stops partway through, do not rerun the empty preflight, stamp, reset
   or downgrade; inspect the exact Alembic state and seek owner review.

5. With production write authorization false again, verify the same pinned target:

   ```powershell
   npm run db:production-preflight -- fresh-bootstrap-schema-check
   npm run db:check
   ```

   The first command verifies the exact Neon primary, release head and mapped
   metadata read-only. Both must pass before connecting the web service.

6. In the existing Render service, configure `APP_ENV=production`, the new direct
   `DATABASE_URL`, `DATABASE_TARGET_ENVIRONMENT=production`, the exact
   `DATABASE_TARGET_DATABASE`, `NEON_PROJECT_ID`, `NEON_BRANCH_ID`,
   `NEON_ENDPOINT_ID`, and the already used `NEON_API_KEY`. Keep
   `DATABASE_PRODUCTION_WRITES_AUTHORIZED=false` and
   `DATABASE_REHEARSAL_WRITES_AUTHORIZED=false`; retain the existing
   `API_ACCESS_TOKEN`. Keep cloud ingestion, recurring/manual operations, workbook
   sync, FMP and Sheets polling disabled. Keep `/health/ready` and native
   **Auto-Deploy After CI Checks Pass** enabled. Do not add a migration pre-deploy
   command. The migrated schema is ready before Render connects; its native health
   check gates traffic.
7. In the existing Vercel project, retain root `apps/web`, production branch
   `main`, the production Render `API_BASE_URL`, the existing matching server-side
   `API_ACCESS_TOKEN`, and existing web login settings. Keep pull-request Preview
   deployments enabled, and do not point Preview at production data. No new
   deployment service, environment, API token or orchestrator is needed.
8. After the owner reviews the exact PR head and required checks, merge through the
   protected GitHub PR path. Render deploys natively after CI checks pass and
   `/health/ready`; Vercel creates its native production deployment from `main`.
   Verify deployed commit and authenticated health before any separate decision to
   retire the previous Neon database. This procedure changes no settings or target
   automatically.

For future migrations on a database with accepted application data, use the
recovery-first procedure below. The first-activation exception is not reusable for
an existing database, even if its application tables currently contain zero rows.

## Existing data-bearing database: coordinated schema migration

Perform these steps in order when the owner is ready to merge this deployment
change. They are instructions only; no live setting has been changed here.

1. **Protect `main`.** Configure the branch rule above and verify the PR requires all
   three CI checks. Record the owner's manual review in the PR.
2. **Freeze production deployments before merge.** In the existing Render Blueprint
   Settings, set **Auto Sync = No**. In the existing `portfolio-api` service Settings,
   set **Auto-Deploy = Off**. In the existing Vercel project Settings → Build and
   Deployment → Ignored Build Step, select **Only build preview**. This lets PR
   previews continue while main-branch production builds are skipped. Confirm all
   three freeze settings before continuing. Render Blueprints can redeploy affected
   resources on sync; disabling Auto Sync prevents a repository push from applying
   the new Blueprint configuration. See [Render Blueprints](https://render.com/docs/infrastructure-as-code)
   and [Vercel ignored build steps](https://vercel.com/docs/project-configuration/project-settings).
3. **Verify existing provider links while frozen.** Confirm Render still uses the
   existing `portfolio-api`, this repo, branch `main`, root `apps/api`, and the
   intended production environment. Confirm Vercel still uses the existing project,
   this repo, root `apps/web`, production branch `main`, the current production
   domain, and the intended production API/auth environment variables. Do not create
   duplicate services/projects or change credentials as part of this procedure.
   Verify a PR Preview still builds and does not point at production Neon.
4. **Review and merge the PR.** Wait for the three required GitHub CI checks and the
   Vercel Preview to finish. Complete the owner checklist. Merge only through the
   protected PR path. This push may run CI on the resulting `main` commit; keep both
   production freezes in place.
5. **Verify the exact merged commit.** Record the `main` SHA, confirm all three CI
   jobs succeeded for that commit, and confirm Vercel skipped only the production
   build. If CI failed or the merge SHA is not the reviewed content, stop.
6. **Reverify Neon read-only.** From the exact clean merged checkout, verify the live
   project, primary branch, direct endpoint, `neondb`, TLS `verify-full`, Alembic
   head and complete table/data inventory. Require current head exactly
   `9f2a6d4c81b7` and the reviewed repository head exactly `b59f16c8a203`; any
   unexpected head, data, identity or migration graph is a stop condition.
7. **Create a fresh recovery point.** Create a new Neon branch from the just-verified
   production primary. Earlier pre-import branches do not protect the accepted
   M1 holdings. Confirm same project/parent, ready endpoint, database/PostgreSQL
   version, schema head and complete table counts; record creation time and expiry.
   The migration preflight requires the branch to be no more than four hours old and
   to have more than 24 hours before expiry. Keep it through successful application
   readiness verification. Once accepted portfolio/model data exists, retain the
   required recoverable pre-migration state for every schema migration.
8. **Run the read-only preflight.** Load credentials from the operator's secure local
   environment without echoing them. The preflight needs `DATABASE_URL` for the
   verified direct Neon target, `NEON_API_KEY`, `NEON_PROJECT_ID`, `NEON_BRANCH_ID`,
   `NEON_ENDPOINT_ID`, the recovery branch values `RECOVERY_DATABASE_URL`,
   `RECOVERY_BRANCH_ID`, `RECOVERY_ENDPOINT_ID`, and the exact confirmation below.
   Set `APP_ENV=development`, `DATABASE_TARGET_ENVIRONMENT=production`,
   `DATABASE_TARGET_DATABASE=neondb`, `DATABASE_PRODUCTION_WRITES_AUTHORIZED=false`,
   and keep all ingestion/worker/Sheets flags disabled. The preflight settings loader
   reads process environment only; it does not load `.env`.

   ```powershell
   $env:EXPECTED_CHECKOUT_SHA = (git rev-parse HEAD).Trim()
   npm run db:production-preflight -- readonly
   $env:MIGRATION_CONFIRMATION = "MIGRATE blue-pond-96398788/br-square-butterfly-bacw0rn5/ep-floral-cake-bae16liy/neondb/9f2a6d4c81b7->b59f16c8a203"
   npm run db:production-preflight -- migration-preflight
   ```

   The second command independently verifies the recovery branch against the
   current primary and requires that exact migration confirmation. It remains
   read-only.

   Both modes are read-only and fail closed. The first reports the current target,
   migration requirement and inventory fingerprint. The second is valid only when
   the schema is at the reviewed base, write authorization is false, and the fresh
   recovery point matches.

9. **Separate approval and migration.** Review the exact preflight output, recovery
   point, diff and scope, then obtain explicit owner authorization for this specific
   schema change. Run `npm run db:migrate` from the exact merged checkout with the
   verified migration-capable direct URL. Set
   `DATABASE_PRODUCTION_WRITES_AUTHORIZED=true` only for that process:

   ```powershell
   $previousAuthorization = [Environment]::GetEnvironmentVariable("DATABASE_PRODUCTION_WRITES_AUTHORIZED", "Process")
   if ($previousAuthorization -eq "true") { throw "Start from a process without production write authorization." }
   try {
       $env:DATABASE_PRODUCTION_WRITES_AUTHORIZED = "true"
       npm run db:migrate
       if ($LASTEXITCODE -ne 0) { throw "Guarded migration failed; leave deployment freezes on and stop." }
   }
   finally {
       if ($null -eq $previousAuthorization) {
           Remove-Item Env:DATABASE_PRODUCTION_WRITES_AUTHORIZED -ErrorAction SilentlyContinue
       } else {
           $env:DATABASE_PRODUCTION_WRITES_AUTHORIZED = $previousAuthorization
       }
   }
   ```

   The existing database write-target guard verifies Neon identity, TLS, privileges
   and authorization on the active database connection. Do not put the write
   authorization in `.env`, GitHub, Render, Vercel or a persistent shell profile. Do
   not combine this command with imports, ingestion, model acceptance or portfolio
   writes. If the command fails or observes another head, stop; do not downgrade or
   reset.

10. **Verify before unfreezing.** Remove temporary write authorization immediately.
    With a read-only URL, run `npm run db:production-preflight -- schema-check` and
    confirm Alembic `b59f16c8a203` plus no metadata drift and unchanged accepted
    holdings/targets. The older API can report schema outdated until the matching
    code is deployed, so plan a coordinated operator window. Database verification
    precedes the native deployments in the next step. If it fails, leave freezes on
    and fix forward under review or follow a separately authorized recovery plan.
11. **Remove the freezes.** In Render, manually sync the Blueprint from `main` after
    confirming the exact merged SHA passed all CI checks. Verify the service now has
    Auto-Deploy **After CI Checks Pass**, `/health/ready`, and the existing disabled
    background flags. Then set Blueprint **Auto Sync = Yes**. Wait for the checked-in
    main commit to deploy and verify its live SHA and `/health/ready`. If the sync did
    not start a deploy, use Render's native dashboard **Deploy a specific commit**
    with that exact CI-passing main SHA. In Vercel, restore Ignored Build Step to
    **Automatic**. Verify the native production deployment uses the merged main SHA;
    if Vercel skipped it while frozen, create a deployment from that exact SHA using
    the Vercel dashboard. Keep Preview deployments enabled. Verify the new Render
    `/health/ready` and authenticated Vercel `/api/health`, matching code revisions
    and read-only Portfolio/Universe/ledger-anchor readback. A failing readiness
    check remains a stop condition; keep the prior instance and investigate safely.
12. **Close out.** Verify both production URLs, source commit, API readiness and
    that write authorization, ingestion, recurring jobs, manual operations, workbook
    sync and Sheets polling remain disabled. Retain the migration/recovery evidence
    according to the operator's private retention policy. Never store URLs, tokens,
    workbook data or private inventory reports in Git or CI artifacts.

For subsequent changes after this first transition, normal operation is simple:
open a PR, review it, wait for the required checks, merge to protected `main`, and
let Vercel deploy natively while Render waits for CI. Any schema change still follows
steps 6–10 separately before deploying code that needs the new schema. Apply the
temporary provider freezes again whenever code and schema must be released in this
ordered way.

## Failure and rollback

- **CI fails:** do not merge; provider deploys remain gated by CI and branch policy.
- **Neon target, recovery or schema verification differs:** stop before migration;
  do not reuse an older branch or weaken the guard.
- **Migration fails or readiness remains red:** keep production freezes enabled,
  preserve the database and pre-migration branch, inspect read-only, and prepare a
  reviewed forward repair or separately authorized restore. Never automatically run
  Alembic downgrade/reset.
- **Render deploy fails health checks:** Render should keep traffic on the prior
  instance; leave the API deployment frozen, fix the cause and retry only after CI
  and schema checks pass.
- **Vercel deployment fails:** use Vercel's native deployment rollback or restore a
  known-good main commit through a reviewed PR. A code rollback does not reverse a
  database migration.

The pre-migration Neon branch is time-limited recovery protection, not a perpetual
backup or automated rollback. After accepted application data exists, verify the
restore procedure on isolated infrastructure and make an appropriately retained
recovery point before every production schema change.
