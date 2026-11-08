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
on database readiness. Vercel keeps its native pull-request previews. Production
builds additionally require the reviewed schema attestation described below. No
GitHub deployment environments, production secrets in CI or release orchestrator
are required.

```text
Pull request ── GitHub CI + owner review ── merge to main
     └──────── Vercel Preview                 ├── Render: schema gate + CI → readiness → traffic
                                               └── Vercel: schema gate → native production build

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
production deployment for the configured production branch. The operator-installed
Ignored Build Step below checks schema compatibility before production builds.
GitHub protects code integration; this small offline check protects release ordering.
See [Vercel Git deployments](https://vercel.com/docs/git).

## `main` protection and owner review

The November 8 read-only effective-rules inspection confirms PR-based integration,
conversation resolution, the three required strict CI checks, and protection from
deletion/force pushes. This supersedes the November 4 observation of missing
protection. Reverify the effective rules at a release boundary. This task changes
no GitHub settings.

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

## November 8 incident and immediate recovery gate

**Resolution.** On November 8 the owner authorized one migration and one Render
deployment. Production reached `b59f16c8a203`, all accepted portfolio fingerprints
reconciled, and Render deployment `dep-dbo84g5g1s2s73ef7kcg` became live at
`deda2ce`. Authenticated frontend and API reads passed. Render Auto-Deploy and
Blueprint Auto Sync remain off, and Vercel production builds remain frozen.
The observations below describe the earlier incident and its historical procedure.

Read-only checks at 12:23–12:45 UTC found release skew after
[PR #26](https://github.com/paulzwecker/portfolio-app/pull/26) merged as
`deda2ced13df8ef0874df2727cca0d050ab6c164`.

- Render `portfolio-api` (`srv-dba8q3rncjis73cl7to0`) rejected that candidate
  with `update_failed`. Prior commit `395f842` remains live. Its live/ready endpoints
  and authenticated portfolio read return 200; its ledger-anchor endpoint returns 404.
- Vercel production alias `portfolio-research-omega.vercel.app` serves `deda2ce`.
  The owner verified authenticated health as connected/current at 12:37:09 UTC,
  while the ledger page displays “This record was not found”. Automated authenticated
  browser inspection was blocked by browser URL policy. Old API health establishes
  compatibility with its own migration head.
- Independently verified Neon primary is `blue-pond-96398788` /
  `br-square-butterfly-bacw0rn5` / `ep-floral-cake-bae16liy`, `neondb.public`,
  PostgreSQL 18.6, Alembic `9f2a6d4c81b7`, 95 public tables. The accepted baseline
  remains intact with 22 positions, two cash rows and 16 targets totaling 1.
  Model revisions remain empty; the three ledger tables are absent. Full identity,
  inventory and reconciliation evidence remain in the private incident store.
- Both pending upgrades are additive. `a832e94d6f10` creates candidate/review
  tables and indexes; `b59f16c8a203` creates publication lineage. No upgrade DML,
  existing-table alteration or ownership activation occurs. Expected result is
  98 public tables, three empty ledger tables and unchanged accepted state.
- Recovery `br-sparkling-rice-baipcnmc` is ready, parented to production at LSN
  `0/22A4B20`, created November 7 at 08:54:30 UTC and expiring November 14 at
  08:54:33 UTC (09:54:33 CET). Read-only SQL confirms the old schema and **zero**
  canonical records. A fresh populated-state clone is mandatory.

All three required checks passed for the merge SHA. Render's `checksPass` setting
worked, starting the candidate after the last check at 11:01:30 UTC. CI tested
disposable schemas at repository head; it had no production-schema gate. Vercel
built independently from main, and production freezes were absent. Readiness
protected the old API instance but could not prevent frontend/API version skew.
Render logs independently confirm 85 `readiness_schema_mismatch` events between
11:03 and deployment failure, containing expected `b59f16c8a203` and observed
`9f2a6d4c81b7`.

The immediate freeze requires owner authorization. Set Render service Auto-Deploy
**Off**, and Blueprint Auto Sync **No** if Blueprint-managed. In Vercel use Ignored
Build Step **Only build pre-production** (older UI wording **Only build preview**).
Preserve the healthy old instance. If temporary user impact requires rolling back
the frontend to `395f842`, obtain separate deployment approval first. No provider
setting or deployment was changed during this investigation.

Follow the data-bearing procedure below from a separate clean `main` checkout
pinned to `deda2ced13df8ef0874df2727cca0d050ab6c164`; preserve the ledger feature
branch. After separate approval create a fresh recovery branch and verify its
parent/LSN, endpoint, creation/expiry, schema/counts and private canonical content.
Verify documented Neon restore/reset permissions and recovery access; metadata GET
success does not establish restore authorization. A disposable restore rehearsal
or reviewed provider recovery procedure is an acceptance gate.

Local TLS inspection required the trusted certifi bundle in the operator child
process. Retain `sslmode=verify-full`. Load exact production and **new** recovery
credentials/IDs securely into that process as described below, with writes false.

```powershell
$env:PGSSLROOTCERT = (node scripts/uv.mjs run --locked --project apps/api python -c "import certifi; print(certifi.where())").Trim()
$env:EXPECTED_CHECKOUT_SHA = 'deda2ced13df8ef0874df2727cca0d050ab6c164'
npm run db:production-preflight -- readonly
$env:MIGRATION_CONFIRMATION = 'MIGRATE blue-pond-96398788/br-square-butterfly-bacw0rn5/ep-floral-cake-bae16liy/neondb/9f2a6d4c81b7->b59f16c8a203'
npm run db:production-preflight -- migration-preflight
```

Both commands are read-only; the older empty pre-import branch fails the existing
guard. Use the freshly verified populated-state recovery point.
Only a separately authorized migration may run `npm run db:migrate` using the
temporary authorization/finally block below. Post-check existing application
rows/content, three new empty tables and the expected Alembic version-row update
before a separately authorized native
Render deployment of the reviewed commit. The old API can become unready once
schema advances, so reserve a coordinated operator window. Verify authenticated
health, Portfolio/Universe and ledger anchor before removing freezes.

## Schema-aware release check

[`schema-gate.mjs`](../scripts/deployment/schema-gate.mjs) reads literal Alembic
metadata without importing migrations or contacting databases. It validates the
single-head graph, including historical merges. The owner-reviewed
[production schema attestation](../scripts/deployment/production-schema.json)
records exact target, verified revision/time and SHA-256 of applied migration files,
normalized to LF. Changes to applied history fail closed. The checked-in attestation
records `b59f16c8a203`, verified on November 8 against the production target and
the exact migrated main checkout. Reverify production after a restore or unexpected
drift; the file does not query Neon.

```sh
node scripts/deployment/schema-gate.mjs review
node scripts/deployment/schema-gate.mjs deploy
```

PR `review` validates history and reports the complete pending range while allowing
synthetic checks. Main `deploy` fails the existing Quality check until repository
head matches the attestation. Render must retain **After CI Checks Pass**. No
production credential, migration or cloud request enters CI. The attestation is
reviewed evidence, not a live monitor; cloud drift or restore requires new
target-bound verification and a production freeze.

The gate rejects `apps/web/vercel.json` overrides of `ignoreCommand` and
`git.deploymentEnabled`. Vercel gives a repository `ignoreCommand` precedence over
the project setting, so review those files and the gate itself in every release PR.
CI cannot stop a bypassed Vercel build by itself. Require Vercel GitHub Deployment
Checks on the exact main commit before production aliasing, as described below.

| Decision              | Required evidence                                                                                                                                                 |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PR CI green           | Synthetic checks and Preview passed. A pending migration can still be reported.                                                                                   |
| Safe to merge         | Owner reviewed code, gate/config changes and migration order. A schema-dependent PR requires verified production freezes.                                         |
| Safe to deploy        | The exact main SHA passed all three CI jobs, the schema attestation matches the verified target, and Vercel's required checks and hook are active.                |
| Coordinated migration | Fresh populated recovery, read-only target preflight and separate owner migration and deployment authorizations. Keep both providers frozen through verification. |

### Owner activation sequence

1. Keep the current freezes. Review the combined milestone PR, including the gate,
   attestation and any `vercel.json` changes. Merge requires separate owner action.
2. Verify the exact merged main SHA passed all three named GitHub CI checks. Confirm
   Render remains off and Vercel skipped production while PR Preview remains enabled.
3. In the existing Vercel project's Production Deployment Checks, select GitHub
   checks `Quality, contracts and build`, `PostgreSQL integration tests`, and
   `Windows migration command compatibility`. Verify the current account/plan can
   enforce each check on the same production commit. Pending, missing and failed
   checks must hold promotion. Vercel can treat neutral or skipped checks as
   non-blocking, so all three required jobs must run unconditionally. Keep the
   freeze if settings or enforcement cannot be verified. Avoid duplicate workflow/
   job names, skipped checks and force-promote.
4. After the gate is on main, verify the configured checks while the Vercel freeze
   remains in place. The Custom Ignored Build Step below is a **controlled Vercel
   unfreeze**. Change it only for a separately authorized test window, with Render
   still frozen and no unrelated pushes. Confirm the exact value, exposed system
   variables and absence of repository overrides before any test. This setting is
   currently **not installed**.
5. With explicit deployment authorization, verify the provider checks and hook in
   a controlled release, including missing/failed check behavior and the exact SHA.
   No such live experiment has been run in this task. If evidence is inconclusive,
   restore the Vercel production freeze under the owner's configuration authority.
6. After that evidence and explicit authorization, restore Render Auto-Deploy to
   **After CI Checks Pass**, then Blueprint Auto Sync if applicable. Verify the
   actual settings, exact code revisions and authenticated readback. Never force a
   Vercel promotion or bypass a failed check to complete activation.

Vercel can deploy independently of Render's CI gate. Its Deployment Checks and
ignore hook cover different failure modes. The hook uses reviewed source files and
cannot prove live schema state or protect against privileged manual deployment or
force promotion. Owner review and the migration runbook remain necessary. See
[Vercel Deployment Checks](https://vercel.com/docs/deployment-checks) and
[Vercel project configuration](https://vercel.com/docs/project-configuration/vercel-json).

For Vercel, after owner approval and once the script is available on main, replace
the temporary freeze with this Custom Ignored Build Step, root `apps/web`.
This provider setting has **not** been installed by this task.

```sh
if [ "$VERCEL_ENV" = "preview" ]; then exit 1; fi; if [ "$VERCEL_ENV" = "production" ] && node ../../scripts/deployment/schema-gate.mjs deploy; then exit 1; else exit 0; fi
```

The shell translates successful verification to exit 1 (build), and any Node error,
missing script, invalid/behind attestation or unknown environment to exit 0 (skip).
Preview builds exit 1 independently. A direct Node command would be unsafe here
because Vercel interprets failure as permission to build. Keep the temporary freeze
until the command is available and tested. Repository CI alone cannot hold Vercel
production before this operator setup.

At major integration boundaries review pending migrations, freezes and recovery
before merge. Keep schema-dependent releases frozen, complete the separately
authorized guarded migration and read-only schema/content checks, then promote
the attestation through an owner-reviewed commit. Update its revision, timestamp
and `migration_history_sha256` with the exact `repository_history_sha256` from
`review` on the verified checkout. Never advance the marker to clear CI before
verifying the database at that head. Require all three checks on the promoted main
SHA before native deployments and authenticated readback. Manual deployments keep
the same gates. Ordinary same-schema changes retain the fast native workflow.
Database guards, readiness and investment acceptance remain independent.

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
   metadata read-only. Both must pass before connecting the web service. Follow
   the schema-attestation promotion procedure above before automatic deployments;
   a changed production target also requires review of the checked-in target pins.

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
   `API_ACCESS_TOKEN`, and existing web login settings. Install the schema-aware
   Ignored Build Step above, keep Preview enabled, and keep Preview isolated from
   production data. No new
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
   Settings, set **Auto Sync = No** if Blueprint-managed. In the existing `portfolio-api` service Settings,
   set **Auto-Deploy = Off**. In the existing Vercel project Settings → Build and
   Deployment → Ignored Build Step, select **Only build pre-production** (formerly
   **Only build preview**). This lets previews continue while production builds are
   skipped. Confirm each applicable freeze before continuing. Render Blueprints can redeploy affected
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
5. **Verify the exact merged commit.** Record the `main` SHA and passing PR quality,
   integration and Windows evidence for its reviewed content. Confirm Vercel skipped
   production. With the schema gate installed, the main Quality job intentionally
   fails at `MIGRATION_REQUIRED` until the actual migration and attestation promotion.
   That expected release hold grants no migration authority. Other failures or
   unreviewed merge content are stop conditions. All main checks must pass before
   deployment at step 11.
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
    holdings/targets. The one existing `alembic_version` row must change from the
    reviewed base to the release head. Compare the other 94 pre-existing public
    tables for exact content preservation and require all three new tables empty.
    The older API can report schema outdated until the matching
    code is deployed, so plan a coordinated operator window. Database verification
    precedes the native deployments in the next step. If it fails, leave freezes on
    and fix forward under review or follow a separately authorized recovery plan.
11. **Promote the attestation, then remove freezes.** Follow the reviewed promotion
    procedure above after live schema/content verification. In Render, sync the
    Blueprint only if managed by one, after the exact promoted main SHA passes all
    CI checks. Verify the service has
    Auto-Deploy **After CI Checks Pass**, `/health/ready`, and the existing disabled
    background flags. Restore Blueprint **Auto Sync = Yes** only if applicable. Wait for the checked-in
    main commit to deploy and verify its live SHA and `/health/ready`. If the sync did
    not start a deploy, use Render's native dashboard **Deploy a specific commit**
    with that exact CI-passing main SHA. In Vercel, replace the temporary freeze with
    the tested schema-aware Custom Ignored Build Step above. Verify production uses
    the promoted main SHA;
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
let Vercel deploy natively through its schema check while Render waits for CI. Any schema change follows
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

### Durable recovery of populated production

The November 8 populated recovery branch is a **pre-migration** state and expires
November 15 at 14:18 CET. It protects the accepted portfolio at capture time, not
subsequent writes or the current schema. Its existence does not prove a restore.
The observed 24-hour Neon history window is a dated project observation, not a
durable off-provider backup or a promise of future retention. Check the active plan,
history, branch expiry and restore permissions before relying on them.

The existing [PostgreSQL migration toolkit](postgresql-migration.md) explicitly
accepts only a loopback source. It must not be pointed at production through a
tunnel to evade that guard. No production archive or complete restore rehearsal
has been verified by this procedure. As a local, non-database prerequisite check:

```powershell
node scripts/deployment/recovery-tools.mjs --pg-bin "$env:ProgramFiles\PostgreSQL\18\bin"
```

`TOOLS_AVAILABLE` establishes only that the matching client executables can report
their PostgreSQL 18 versions; it does not prove encryption, permissions, connectivity,
archive integrity, backup coverage or restore success.

Before expiration the owner should choose a recovery point objective and retention
period, confirm Neon plan capabilities/costs, and separately authorize a current
populated-state recovery point and an independent encrypted off-provider backup.
Use least-privilege read access, `verify-full`, private storage outside Git/cloud-sync,
and a reviewed snapshot-consistent PostgreSQL 18 export. Preserve a versioned
manifest with schema, source identity, timestamps, file hashes and coverage; verify
archive integrity without publishing portfolio data. Establish retention and secure
off-device copy with tested access and key recovery. These are requirements for a
separately reviewed production backup procedure, not claims that one exists here.
That review must account for every database and required role/grant, extension,
large object, table and sequence; a single database dump does not itself preserve
cluster-wide roles. Verify the backup role can read every intended row, including
row-level security behavior, rather than accepting a partial archive. Preserve the
exact archive and manifest together and test decryption before relying on a copy.

Separately authorize an isolated restore rehearsal with an exact nonproduction target;
verify schema and complete table/sequence fingerprints, accepted portfolio counts,
receipts and application readback. Record restore duration, residual gaps and the
recovery point's timestamp privately. Repeat on an owner-defined schedule and after
material schema changes. A real production restore or any rerouting remains a distinct
authorization, with writes frozen and post-backup changes reconciled. Keep the expiring
branch until a replacement is verified; do not assume PITR, branch snapshots or a
successful hash check alone prove recoverability.
