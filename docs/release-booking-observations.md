# Booking observations PR #42 — controlled production release

**Status: preparation only, NOT authorized for deployment or migration.**
Prepared November 20, 2026. Use this card with
[deployment and migration safeguards](deployment-and-migrations.md) and
[encrypted recovery](encrypted-production-recovery.md). This is an
operator-controlled procedure, not a new scheduler or deploy workflow.

## Verified targets and release boundary

- Draft PR: [#42](https://github.com/paulzwecker/portfolio-app/pull/42),
  branch `feat/api-first-company-observations`. Re-read its **exact head**
  and all three required CI checks immediately before a merge decision;
  an older green run is not enough.
- Canonical Neon: project `blue-pond-96398788`, primary
  `br-square-butterfly-bacw0rn5`, direct endpoint
  `ep-floral-cake-bae16liy`, database `neondb.public`. Live Alembic
  version is `b59f16c8a203`.
- Reviewed Booking Holdings / BKNG → SEC CIK `0001075531` exists;
  do not import it again. No company-metric or observation-review tables
  exist yet. No operating actuals have been accepted.
- Existing Render `portfolio-api`, service `srv-dba8q3rncjis73cl7to0`,
  remains on production main commit `41baea8a`; auto-deploy after
  checks **is enabled**. Check Blueprint Auto Sync separately. Vercel
  production freeze and deployment-check enforcement were not verified.
- Neon lists only the production branch, with **24-hour history
  retention**. There is no currently verified fresh recovery branch
  or confirmed off-device encrypted, restorable production backup.

The feature adds exactly two Alembic revisions:
`b59f16c8a203 -> c6d8e4f1a290 -> d7b4a6c8e2f0`.
Migration 1 creates metric definitions, KPI observations, guidance and
accepted revision-scoped model-driver projections. Migration 2 creates
the agent proposal-review inbox. Both are additive DDL, not authority
to create observations. Their application is **not** part of this card.

## Gates before merge

1. **Production deployment freeze — separately approve and verify.**
   Disable Render automatic deployment and Blueprint sync on the
   existing API. In Vercel, allow previews but freeze the production
   branch with the provider's Ignored Build Step. Read back the exact
   controls. Confirm no pending `main` deployment is about to start.
   Do not rely on `render.yaml` alone to freeze production.
2. **Fresh recovery — separately approve and verify.** Establish
   a fresh restore-capable Neon recovery branch, required by the
   existing migration preflight. Validate its identity, parent LSN,
   creation/expiry, Alembic head and canonical inventory against
   primary. A Neon branch alone is temporary, not a durable off-device
   backup; also establish a separately retained encrypted full-database
   backup and rehearse restoration under the existing recovery
   procedure before a data-bearing production migration.
3. **Exact-head CI and review.** Resolve any GitHub Actions
   `action_required` state and run all three named jobs on the
   exact intended commit: `Quality, contracts and build`,
   `PostgreSQL integration tests` and
   `Windows migration command compatibility`. Inspect Vercel
   Preview, the additive migration diff and open review discussions.
   The fixed schema `review` gate may report two pending revisions;
   the `deploy` gate must remain blocked before migration.
4. **Explicit merge approval.** Merging is a separate owner action
   **only after both production deployment freezes and recovery
   controls are verified**. Protected `main` and its deployed
   revision are not changed during this preparation.

## After an authorized merge, before any migration

From the reviewed **clean `main` checkout** at the exact merged SHA,
load the existing production database secrets privately (direct
TLS `verify-full`, expected Neon project/branch/endpoint/database)
with all write/ingestion/acceptance flags disabled. Configure the
fresh recovery branch's private direct credentials as documented in
`production_migration_preflight.py` and the main deployment runbook.
Never put credentials in GitHub, logs or this document.

These **read-only** commands must pass, with a recovery point created
within four hours and expiring no sooner than 24 hours from the check:

```sh
npm run db:production-preflight -- readonly
# After reviewing the exact migration confirmation, still read-only:
npm run db:production-preflight -- migration-preflight
```

The checked-in migration preflight now allows only the verified
production base `b59f16c8a203` and repository head
`d7b4a6c8e2f0`. The second command requires a privately supplied
exact `MIGRATION_CONFIRMATION` for that project/branch/endpoint/
database and revision range. Old release confirmations fail closed.
The command never migrates a database.

## Separately authorized cutover

1. With freezes maintained, recovery verified, an owner-approved
   migration window and the existing production-write guard enabled
   _only within its isolated operator process_, run the established
   `npm run db:migrate` procedure once from clean, pinned `main`.
   Do not run Alembic from CI or Render startup. Plan for the old
   Render API to become unready as soon as Alembic advances.
2. Run `npm run db:production-preflight -- schema-check` in its
   read-only mode on the migrated primary. Independently verify
   Alembic `d7b4a6c8e2f0`, no metadata drift, the five newly
   created tables, and zero accepted operating observations,
   proposals or model drivers. Reconcile existing canonical
   holdings/cash/targets, model lineage and Booking CIK mapping to
   the pre-migration recovery inventory; abort on unexpected changes.
3. **Only after exact live schema evidence**, create a separate
   reviewed update to `scripts/deployment/production-schema.json`:
   new revision `d7b4a6c8e2f0`, current verification timestamp
   and verified repository migration-history fingerprint. Do not
   edit the attestation ahead of production. Its checked-in
   `b59f16c8a203` value is deliberately still correct today.
   Let GitHub's `schema-gate deploy` become green on the attested
   main commit while production deployments stay frozen.
4. With separate deployment approval, release the verified main
   API through Render **before** the frontend. Verify exact
   commit, `/health/ready` and authenticated Portfolio, Universe
   and BKNG company reads. Keep manual operations, provider
   ingestion, recurring jobs, Sheet sync, observation proposals
   and acceptance **off**.
5. Only after API health and matched production schema, approve
   the Vercel production build/promotion, verify deployment checks,
   exact frontend/API versions and desktop/mobile read-only company
   journey. Do not use a force-promote bypass.

## First Booking read-only agent pilot (separate activation)

After the deployed API includes `CompanyAgentContextV1.sec_identity`,
privately configure an **independent 32+ character**
`DATA_UNIVERSE_READ_TOKEN`, `DATA_UNIVERSE_READ_ENABLED=true`
and `DATA_UNIVERSE_READ_COMPANY_IDS` containing only the
existing Booking UUID. This is a separately authorized credential
change. Configure a proper SEC fair-access `SEC_USER_AGENT`
outside Git and verify the live source. The dry-run handoff must
report the exact SEC CIK `0001075531`, source match and candidate
definitions, but **no POST, accepted observation or model revision**.
Human proposal review and acceptance are later, separate decisions.

## Stop and recovery rules

Stop if target IDs, migration base, recovery evidence, schema
inventory, CI checks, data reconciliation or deployed SHA differ
from this reviewed plan. Keep both providers frozen and preserve
the pre-migration recovery state. An application rollback to
`41baea8a` **without restoring its compatible database schema**
will not restore readiness. Do not silently downgrade, reset Neon
or delete recorded canonical data. Use the separately approved
restore procedure, restore rehearsal evidence and owner decision
before any data-bearing rollback. Record before/after receipts
privately; never publish connection strings or portfolio contents.
