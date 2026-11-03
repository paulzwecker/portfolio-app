# Coordinated Production Release Pipeline

**Status:** Implemented in the M1 feature branch; not activated or live-tested. The workflow is manual and must be configured and reviewed before use. No production migration, deployment or database change was performed while preparing this document.

## Release contract

`.github/workflows/production-release.yml` is the only proposed production release path. It is manually dispatched from `main`, requires the exact current main SHA and green CI for that SHA, serializes releases, and deploys API and web artifacts from that same checkout. Before creating a deployment, it checks provider deployment history for the exact release SHA. A verified existing live/ready deployment is reused; an in-progress deployment is followed; failed, terminal, ambiguous or incompletely scanned history stops the release instead of creating a second deployment. The workflow does not import workbook data, run provider ingestion, accept financial-model or research proposals, recompute investment decisions, or activate recurring jobs.

The release sequence is:

1. Validate the selected SHA, current `main` tip, CI checks and GitHub environment protection rules.
2. Obtain read-only approval and verify Neon, a current recovery point, Render, Vercel and disabled background-operation flags.
3. If and only if the database is exactly at the reviewed base `6c2eaf0b8147` and the release repository head is `9f2a6d4c81b7`, require the migration checkbox, exact migration confirmation, and approval for the separate `production-migration` environment. If the database is already at `9f2a6d4c81b7`, skip migrations. Any other head stops the release for review.
4. Reverify the migration target, base head, recovery point and exact confirmation with the read-only URL and write authorization disabled. Then run only `npm run db:migrate` with the guarded production writer URL and authorization enabled. The writer URL and flag exist only for this command. Afterward, run `production_release schema-check` with the separate read-only URL, disabled write authorization, a verified Neon target and a PostgreSQL session forced into read-only mode. The schema check invokes Alembic metadata comparison on that read-only connection and returns sanitized drift errors; it does not reuse the migration engine or writer credentials. Finally, recheck the exact head with the read-only preflight.
5. Deploy the exact SHA to Render, require its deploy record to report that commit as live, and wait for `/health/ready` to return `database=connected` and `schema=current`.
6. Install the pinned Vercel CLI before exposing credentials, link the project and pull production build settings in a step-scoped token operation, remove the pulled `.vercel/.env.production.local` cache, and build the checked-out SHA with an allowlisted environment that excludes deployment/GitHub tokens. Then deploy the prebuilt artifact tagged with the release SHA and verify its project, status, commit metadata and production alias. Runtime environment values remain configured on the Vercel project; they are not copied into the local build process or artifact by this workflow.
7. Run direct API and authenticated web-to-API read-only smoke checks.
8. Publish a sanitized workflow summary and a 90-day release evidence artifact. These records are useful audit evidence, not tamper-proof storage; repository administrators can delete workflow records and artifacts.

`cancel-in-progress: false` prevents a second production workflow from interrupting an active release. The workflow rechecks that the approved SHA remains the `main` tip before migration and deployment; a newer main commit stops the old release. Render history is scanned in bounded 100-deploy cursor pages; Vercel history is scanned in bounded 100-deployment production pages scoped to the exact project/team. If the five-page limit is reached before the provider reports the end of history, the release fails closed. GitHub concurrency and provider history checks prevent duplicate releases through this workflow and make retries idempotent when the provider recorded the prior request. They cannot serialize an independently initiated provider-dashboard/API deployment that races with the final check; keep provider deploy credentials restricted and use the coordinated workflow as the sole production path.

## Required GitHub setup

Before a release can run, create these GitHub environments, restrict each to the `main` branch only, and add at least one required reviewer whose numeric GitHub user or team ID is in repository variable `RELEASE_REVIEWER_IDS` (comma-separated IDs):

- `production-readonly`
- `production-migration`
- `production-api`
- `production-web`
- `production-smoke`

The workflow checks the environment reviewers and exact branch policy through the GitHub API and fails closed if those rules cannot be read or do not match. Do not rely on the job's `environment:` label alone: GitHub does not create reviewer protection merely because a workflow names an environment.
Enable GitHub's **Prevent self-review** setting for each environment, and disable administrator bypass of protection rules in the repository deployment protection settings. The API preflight verifies `prevent_self_review` and reviewers; GitHub's environment read API does not expose the administrator-bypass toggle, so that setting needs a dashboard check during activation.

The release workflow requires `GITHUB_TOKEN` permissions only for repository contents, checks, environment metadata and deployment records. It does not need a personal access token. The selected SHA must have successful CI check runs named `Quality, contracts and build`, `PostgreSQL integration tests`, and `Windows migration command compatibility`.

### Repository variables

| Variable                   | Value                                                                           |
| -------------------------- | ------------------------------------------------------------------------------- |
| `RELEASE_REVIEWER_IDS`     | Numeric GitHub user/team IDs authorized to review all five release environments |
| `VERCEL_PROJECT_ID`        | Exact Vercel project ID for `portfolio-research`                                |
| `VERCEL_ORG_ID`            | Vercel team/org ID owning the project                                           |
| `VERCEL_PRODUCTION_DOMAIN` | Exact production domain `portfolio-research-omega.vercel.app`                   |
| `RECOVERY_BRANCH_ID`       | ID of a newly created, current Neon child recovery branch                       |
| `RECOVERY_ENDPOINT_ID`     | Direct endpoint ID attached to that recovery branch                             |

Project, service, Neon primary project/branch/endpoint, database name and production base/head are pinned in the workflow or preflight module. Do not replace them with user-editable dispatch inputs.

### Environment secrets

| Environment            | Secret                                       | Required scope                                                                              |
| ---------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `production-readonly`  | `PRODUCTION_READONLY_DATABASE_URL`           | Read-only PostgreSQL role; direct Neon primary; `sslmode=verify-full`                       |
| `production-readonly`  | `RECOVERY_READONLY_DATABASE_URL`             | Read-only role; direct endpoint on the recovery child; `sslmode=verify-full`                |
| `production-readonly`  | `NEON_API_KEY`                               | Read-only Neon project/branch/endpoint metadata lookup                                      |
| `production-readonly`  | `RENDER_READ_TOKEN`                          | Read the exact Render service and its environment configuration                             |
| `production-readonly`  | `VERCEL_READ_TOKEN`                          | Read only the exact project, domain and environment-variable names                          |
| `production-migration` | `NEON_PRODUCTION_MIGRATION_DATABASE_URL`     | Non-superuser migration role with the reviewed schema ownership/CREATE privileges           |
| `production-migration` | `PRODUCTION_READONLY_DATABASE_URL`           | The same direct-primary read-only role/URL as above, for post-migration verification        |
| `production-migration` | `NEON_API_KEY`                               | Read-only Neon identity lookup, also required by the existing database write guard          |
| `production-migration` | `RECOVERY_READONLY_DATABASE_URL`             | Read-only verification of the fresh recovery child                                          |
| `production-api`       | `RENDER_DEPLOY_TOKEN`                        | Deploy the configured Render API service; no service or setting changes                     |
| `production-web`       | `VERCEL_DEPLOY_TOKEN`                        | Link/pull and deploy only the configured Vercel project; never present during the app build |
| `production-smoke`     | `WEB_ACCESS_USERNAME`, `WEB_ACCESS_PASSWORD` | Existing shared web login used for read-only smoke requests                                 |

Use distinct read and deploy credentials. The migration environment needs its own copy of `PRODUCTION_READONLY_DATABASE_URL` because GitHub environment secrets are scoped to one environment. The workflow places read-only database URLs, Neon keys and recovery URLs on only the specific preflight or verification step that needs them; checkout, dependency installation, and GitHub API checks do not receive database credentials. The pre-migration check verifies the exact target, reviewed head, recovery point and confirmation through the read-only guard. Only the `npm run db:migrate` step receives the production writer URL and `DATABASE_PRODUCTION_WRITES_AUTHORIZED=true`; the migration command itself revalidates its target with the existing write guard. Post-migration schema-drift and head checks use the read-only URL with authorization false. Secret-bearing Python commands set `UV_NO_SYNC=1`; locked dependencies are installed in the earlier credential-free setup step so `uv run` cannot synchronize packages while production credentials are present. The pinned Vercel CLI is installed before its token is introduced. The web build runs separately with a narrow environment allowlist and no Vercel/GitHub deployment tokens. The production env cache written by `vercel pull` is deleted and verified absent before the build, while runtime values remain managed in Vercel project settings. Only project link/pull and the final prebuilt deployment steps receive the Vercel token. Do not copy the web/API runtime token into the workflow unless a future, documented smoke endpoint requires it. Never print provider responses containing env values or post credentials in CLI arguments in local terminals.

The one-shot migration job sets `DATABASE_PRODUCTION_WRITES_AUTHORIZED=true` only inside its reviewer-gated process and only after the exact target guard, current base revision, fresh recovery point and typed confirmation pass. It uses the existing `create_database_engine`/`verify_database_write_target` path; it does not use offline SQL output or a raw database driver. All data/provider operations stay disabled.

## Provider setting handoff

The checked-in deployment files now propose:

- Render `autoDeployTrigger: off`; production API deployment will be requested for an exact SHA through Render's deploy endpoint.
- Vercel `git.deploymentEnabled.main: false`; other branches remain enabled by default, preserving PR previews.

These are repository configuration proposals. They do not change the current provider dashboards by themselves. Before merging or activating this pipeline, the operator must separately disable Render main autodeploy and Vercel main-branch autodeploy in provider settings, verify both by read-only API/dashboard inspection, and synchronize the Render Blueprint only after review. The Vercel project must remain connected to `paulzwecker/portfolio-app`, production branch `main`, root `apps/web`, and the expected production domain. The workflow verifies live Render autodeploy state and checks the checked-out Vercel per-branch configuration. It also verifies the Vercel project/domain and production/preview environment-variable scopes.

Render's deploy API can request a specific commit, but that request does **not** disable autodeploy. Disable it first. Vercel's versioned-deployment guidance uses `git.deploymentEnabled` and CLI-based production deploys; unspecified branches remain enabled, so the `main: false` rule keeps branch/PR preview deployment available. See [Render deploy API](https://api-docs.render.com/reference/create-deploy), [Render service settings](https://api-docs.render.com/reference/create-service), [Vercel Git configuration](https://vercel.com/docs/project-configuration/git-configuration), and [Vercel versioned deployment guidance](https://vercel.com/kb/guide/can-you-deploy-based-on-tags-releases-on-vercel).

The remote API must use direct Neon TLS with `sslmode=verify-full`. The settings validator now rejects `require` and `verify-ca` for hosted `preview` and `production` apps; the existing write guard already required `verify-full` for remote writes. Do not put database URLs in GitHub variables; store them only as protected environment secrets.
Render's runtime preflight also requires the exact Neon project/primary branch/endpoint/database identity, a configured Neon control-plane key, `DATABASE_PRODUCTION_WRITES_AUTHORIZED=false`, and all provider ingestion, recurring, manual-operation, workbook-sync, FMP and Sheets polling flags explicitly disabled. The checked-in Blueprint declares these values; its `sync: false` placeholders require operator-managed secrets and do not reveal or set live values by themselves.

## Initial release migration review

The live production branch was last independently verified on 2026-11-03 at PostgreSQL 18.6, database `neondb`, Alembic `6c2eaf0b8147`. It had 89 public tables and 20 rows total in four populated tables: one Alembic version row, 11 ranking definition rows, four return methodology definitions and four score definitions. No canonical company, holding, target or accepted-model rows were present. Rerun preflight before any release; these are dated observations, not current guarantees.

The single local Alembic head is `9f2a6d4c81b7`, with this linear upgrade:

```text
6c2eaf0b8147
  -> b16d4f8a2c91  workbook sync artifacts, schema approvals, runs/previews; job-name check extension
  -> c17a0b9d4e62  permit production in two bootstrap-run target checks
  -> 3e5c8a1d7b42  model-only identity bootstrap receipt table
  -> 9f2a6d4c81b7  agent model revision proposal table and indexes
```

Review of the checked-in migration files found no data backfill. The first, third and fourth revisions add tables/indexes. `c17a0b9d4e62` replaces two check constraints to include `production`. Downgrades drop newly created tables and their stored state; the constraint downgrade narrows allowed values and could fail if production-target rows exist. **Do not automate Alembic downgrade as rollback.** If a migration fails or a later deploy fails, stop the release, preserve the new schema, keep the existing API running where compatible, verify exact state read-only, and obtain an owner decision for a forward fix or a separately rehearsed Neon restore. A Neon child branch is a restore point, not an automatic rollback of the primary.

For the migration path, preflight requires a recovery branch that is a direct child of the verified primary, ready, same database/PostgreSQL version/current schema and table-count inventory, created in the last four hours, and not expiring within the next day. The workflow never creates, deletes, promotes or extends a Neon branch. A currently known recovery child at Alembic `12a6f0d9c3e1` is stale for this path and must not be reused.

## Current external blockers (2026-11-03)

These do not prevent local implementation/testing, but they deliberately prevent a live release:

- Render control-plane access is now read-only verified. The service still has `autoDeployTrigger=commit`; its production database URL uses `sslmode=require` rather than `verify-full`. The new preflight will block until the owner applies and verifies both settings.
- A fresh Neon recovery branch is not configured. The previously verified branch is behind production at `12a6f0d9c3e1`. The owner must create a new child restore point and enter its ID, endpoint ID and read-only URL into the protected workflow configuration.
- Vercel read/deploy credentials and project/org IDs are not available in the local environment. Its public domain returns the existing Basic Auth challenge; authenticated API reads and provider settings are not independently verified yet.
- GitHub currently has no configured release environment reviewer policy. The owner must create all five protected environments and exact `main` branch policies before the workflow will proceed.
- PostgreSQL 18.3 client tools are installed locally. The isolated test role can connect to `127.0.0.1/portfolio_app_test`, but lacks `CREATEDB` and `CREATEROLE`; backup/restore integration cases remain environment-blocked. Do not grant those privileges on Neon.

## Operator activation procedure

Do not use this procedure until the M1 PR is reviewed/merged, CI passes, the exact cloud settings and GitHub environments are verified, a fresh recovery point is available, and the owner approves a specific release. This document does not itself authorize any production action.

1. Configure the five GitHub environments and `RELEASE_REVIEWER_IDS`. Every environment must require an allowlisted reviewer, prevent self-review, disallow administrator bypass, and permit deployments from `main` only. Add only the scoped secrets/variables above. Configure Vercel preview values for a separate HTTPS nonproduction API plus separate preview credentials; never point the preview API at the Render production service.
2. In Render dashboard, disable main-branch autodeploy, set production `DATABASE_URL` to direct `sslmode=verify-full`, preserve the API runtime token, and confirm all ingestion, recurring, Sheets-poll and FMP flags remain disabled. In Vercel, disable only main Git-triggered production deployments, preserve branch/PR previews, and verify project/branch/root/domain and environment scopes.
3. Create a fresh Neon branch from the verified primary (manual Neon action) only as part of an approved release plan. Verify parent, branch/endpoint/database, creation time, expiry, Alembic head, PostgreSQL version and data inventory; configure its read-only URL and IDs as protected secrets/variables.
4. Verify the intended exact release commit is the `main` tip and has all three required successful CI checks. Open **Actions → Coordinated production release → Run workflow**, select `main`, paste that 40-character commit SHA and leave `run_migrations=false` unless the reviewed live preflight requires the known `6c2eaf0b8147 → 9f2a6d4c81b7` chain.
5. For that exact initial migration only, an explicitly approved operator enters:

   ```text
   MIGRATE delicate-heart-04560404/br-morning-truth-b96361yh/ep-snowy-term-b9gr75j6/neondb/6c2eaf0b8147->9f2a6d4c81b7
   ```

   The migration input also requires the separately protected `production-migration` environment reviewer. Any different source head, repository head, target identity, recovery inventory or confirmation stops the release.

6. Review the release artifact and job summary. On failure after migration, do not downgrade automatically and do not rerun with broader credentials; keep writes/jobs disabled, verify database and deployments read-only, then decide whether a forward fix or separately authorized restore is appropriate.

## Verification performed for this implementation

Unit tests exercise release SHA checks, required CI outcomes, exact GitHub environment reviewer and branch rules, Render/Vercel target/TLS/autodeploy validation, exact commit deployment responses, bounded exact-SHA deployment-history scans and replay behavior, readiness status, mocked Render/Vercel API requests, migration head gates, exact migration confirmation, recovery freshness and workflow credential scoping. They assert that `uv` synchronization is disabled while database credentials are present, Alembic metadata checks use the read-only engine, the Vercel CLI install precedes credentials, the Vercel build has no deployment tokens, and the pulled production env cache is removed and checked before build. They do not call production APIs. The provider list calls follow Render's [List deploys API](https://api-docs.render.com/reference/list-deploys) and Vercel's [List deployments API](https://vercel.com/docs/rest-api/deployments/list-deployments). The Vercel build behavior follows the official [`vercel pull` cache contract](https://vercel.com/docs/cli/pull) and [`vercel build` guidance](https://vercel.com/docs/cli/build). No GitHub Actions release workflow was dispatched; no migration, provider setting change, deployment, Neon branch creation, import or application-state write occurred.
