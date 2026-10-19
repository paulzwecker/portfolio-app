# Cloud-native canonical baseline runbook

## Scope and status

This runbook prepares a **new canonical cloud baseline** from versioned,
authoritative inputs. The historical local PostgreSQL database is out of scope and
must not be queried, exported, or migrated for this workflow. No Neon, Render, or
Vercel changes are part of this preparation.

The manifest `validate` and `verify-inputs` commands check metadata and frozen
source bytes without connecting to PostgreSQL or providers. The `preflight`
command also verifies the explicitly selected target through the shared database
write guard and checks that the database is at the exact Alembic head. It is
read-only; it does not import data or call providers. Task 4 adds a first-stage
canonical workbook import command with `preview`, `apply`, `resume`, and
`reconcile` operations. That command consumes only approved Task 3 workbook
snapshots and reviewed SEC CIK mappings. The guard verifies Neon project, branch,
and endpoint metadata through the control plane. Writes require an explicit
target environment and authorization; production bootstrap additionally requires
interactive confirmation of the verified target. See
[`database-write-targets.md`](database-write-targets.md) for the policy.

The Task 4 command is a bounded first stage, not a complete cloud-baseline
orchestrator. Later market, fundamentals, model/analytics, and end-to-end
rehearsal stages remain future work. Do not run this first-stage apply against a
real source snapshot or cloud target until that exact rehearsal has been
separately authorized and its preview reviewed.

| State       | Current implementation status                                                                                                                                                                                  |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Implemented | Closed metadata manifest contract; frozen-input SHA-256 verification; target-authorized, Alembic-aware preflight; Task 4 first-stage canonical workbook bootstrap; private run reports and immutable receipts. |
| Tested      | Synthetic manifest/artifact/preflight checks; generated Task 4 workbook fixtures; PostgreSQL 18 guard, interruption, exact reconciliation, and rerun idempotency tests on disposable local databases.          |
| Staged      | Operator-populated Task 3 snapshots and reviewed SEC mappings, followed by preview on a separately verified isolated development or rehearsal target. Later bootstrap stages remain unimplemented.             |
| Executed    | Synthetic artifact checks, target/write-guard checks, and synthetic Task 4 import only. No real portfolio source data, Neon branch, or cloud resource was accessed or changed.                                 |

The source-data suites (`test_legacy_import.py`, `test_consensus_source_data.py`,
`test_model_input_migration.py`, `test_model_input_parity.py`,
`test_model_migration_inventory.py`, `test_research_rank_source_data.py`, and
`test_yahoo_finance_source_data.py`) remain available for a trusted operator
checkout but are excluded from CI because they read personal workbook inputs,
source-specific model values, or reviewed portfolio listing mappings. CI instead
runs synthetic calculation and API/domain PostgreSQL integration coverage. This
leaves direct source-workbook and crosswalk parity unverified by CI until
equivalent synthetic contracts replace those source-bound cases.

## Prepare the manifest on the trusted operator workstation

Use Windows PowerShell 5.1 or PowerShell 7. Keep the authoritative input files,
the completed manifest, and detailed import reports in a private local directory
outside the repository, OneDrive/Dropbox, CI artifacts, and PR attachments. Do not
paste their contents, paths, hashes, credentials, or reports into Codex or GitHub.

Copy the metadata-only template to that private directory:

```powershell
$manifest = Join-Path $env:USERPROFILE 'Documents\portfolio-baseline-manifest.json'
Copy-Item 'docs/cloud-native-bootstrap-manifest.template.json' $manifest
```

For every input entry, record its exact source authority and version, source
recorded time, effective time when known, SHA-256 of the frozen source artifact,
SHA-256 of the identity mapping, and expected record count (`null` means unknown;
zero means a verified empty source). Record a separate entry for each domain and
list source dependencies. The hashes are metadata, not substitutes for reviewing
the artifact or reconciling imported values.

In the private input directory, keep the frozen bytes under the manifest's stable
`source_id` as `<source_id>.artifact`, and its mapping as
`<source_id>.identity-map.artifact`. Keep original exports unchanged; do not
normalize or rewrite them after hashing. The eventual orchestrator can resolve
these names under an operator-selected private input root without putting personal
file paths in the manifest. The `verify-inputs` command uses the same fixed naming
contract before any future import phase.

For financial domains, use decimal strings and set
`decimal_semantics` to `exact_decimal_strings` and
`missing_value_semantics` to `null_absent_distinct_from_zero`. Never encode missing
values as zero. Set `effective_at` to `null` when the source does not supply a
reliable effective time; do not substitute the import time. Pin deterministic
calculation code with its source/methodology SHA-256. Distinguish stored model
outputs from outputs recalculated by the new baseline. An approved history omission
needs a real local approval reference. Do not include file paths, URLs, database
URLs, API keys, passwords, service-account JSON, row values, or private notes in the
manifest.

Generate local hashes for the frozen source files and identity-map files with
PowerShell; keep the output local:

```powershell
Get-FileHash -LiteralPath 'D:\private-inputs\authoritative-source.xlsx' -Algorithm SHA256
Get-FileHash -LiteralPath 'D:\private-inputs\identity-map.csv' -Algorithm SHA256
```

The template contains placeholders and is intentionally rejected until its hashes,
times, expected counts, versions, and approval references are replaced. Never
commit the populated file.

## Validate metadata without a database

After `npm run setup` has completed in the repository checkout, invoke the same
command in PowerShell 5.1 or PowerShell 7:

```powershell
npm run db:bootstrap-manifest-check -- validate --manifest $manifest
```

Expected success output:

```text
Bootstrap input manifest valid: sources=N; no database accessed.
Dependency order: <source-id> -> <source-id> -> ...
```

Expected failures return exit code 2 and identify the invalid manifest field. The
command rejects unknown keys (including paths and credentials), non-unique source
IDs, missing dependencies, dependency cycles, invalid hashes/timestamps, missing
identity-map hashes, unpinned recalculations, unapproved historical omissions,
financial domains that do not preserve exact decimal strings, and missing-versus-
zero ambiguity. It never prints manifest values other than the validated source
IDs in the dependency order. Save no output as a repository artifact.

This is a metadata check, not a readiness approval or an import. A successful
result means only that the input inventory is structurally reviewable. It does not
prove that a workbook/API response is authoritative, that a hash matches a file,
that source identities reconcile, or that a cloud database is isolated.

## Verify frozen input bytes

After the metadata check, compare the private files against the manifest hashes.
Keep the input directory outside the repository and do not pass it to CI:

```powershell
$inputRoot = Join-Path $env:USERPROFILE 'Documents\portfolio-baseline-inputs'
npm run db:bootstrap-inputs-check -- verify-inputs --manifest $manifest --input-root $inputRoot
```

Expected success output is limited to counts and the safe dependency order:

```text
Bootstrap input artifacts verified: verified=N; not_required=M; sources=K; no database or provider accessed.
Dependency order: <source-id> -> <source-id> -> ...
```

The verifier streams each source artifact and identity map and compares its SHA-256
to the manifest. Missing, unreadable, non-regular, symlinked, or changed files fail
with exit code 2 and identify only the source ID and artifact kind. Approved
operator-decision entries with null artifact hashes are reported as
`not_required`. The verifier never prints a private path, hash, file content, or
row value. A successful result proves byte integrity only; it does not approve the
source, validate mappings or imported records, or authorize a database write.

## Verify the selected target and schema

Run this after the source artifacts pass verification. It compares the explicit
CLI environment to `DATABASE_TARGET_ENVIRONMENT`, then invokes the shared database
write-target guard on the configured connection. Neon targets must resolve to the
configured project, branch, and direct endpoint through the control plane. The
command also requires the application schema and table privileges and checks the
exact Alembic head used by this checkout.

Use the same private input directory and manifest. Configure `DATABASE_URL`,
`DATABASE_TARGET_ENVIRONMENT`, `DATABASE_TARGET_DATABASE`, and the appropriate
target authorization in the local operator environment. Never paste these values
into chat, a PR, or the manifest.

```powershell
npm run db:bootstrap-preflight -- --manifest $manifest --input-root $inputRoot --target-environment rehearsal
```

Choose `development`, `rehearsal`, or `production` to match the intended target.
For production, the write guard additionally requires the production authorization
setting and interactive confirmation of the verified project/branch/endpoint/
database identity. Do not run that path without the separately approved production
activation procedure.

Expected success output contains only the target environment, migration status,
source and artifact counts, and safe dependency order:

```text
Bootstrap preflight passed: target=rehearsal; alembic=current; sources=N; artifacts_verified=M; artifacts_not_required=K; no writes or provider calls.
Dependency order: <source-id> -> <source-id> -> ...
```

The guard emits a redacted target-authorization audit record. A failed target,
authorization, privilege, or migration check exits nonzero and reports a safe
reason. No import starts. A passing preflight proves target and schema readiness
at that moment only; every later writer is checked again by the shared guard.
This preflight does not establish that the database is empty or reconcile domain
data. The Task 4 canonical command performs its own empty-target/resume checks and
writes its run receipt in the same transaction as its domain imports.

## Dependencies and pipeline readiness

The audited sequence is: company identities; securities and exact listings;
portfolio holdings, cash and targets; current investment assessments; saved model
outputs; parity-approved native model inputs; source documents and reported
fundamentals; reviewed price and FX observations; licensed consensus only where
storage rights permit; and selected derived analytics. Rankings must be labeled as
preserved snapshots or new calculations. Never silently convert a cached model
output into a newly calculated value, relabel expected-return methodology, or
accept a proposed research revision.

Google Sheets imports require an authorized workbook share and service-account
access; provider ingestion requires each provider's credentials, rate limits, and
storage/display rights to be reviewed. Do not place credentials in GitHub Actions.
Do not enable recurring jobs or paid services. The existing Render Free web process
is not an approved bootstrap worker, and no scheduled execution is configured by
this runbook. Neon storage and compute cost cannot be estimated accurately until
the reviewed input scope and a rehearsal size report exist. This PR adds no cloud
resources and has $0 incremental infrastructure cost.

## History loss and recovery limits

The new baseline excludes local-database-only history. Unless an authoritative
portable archive is separately identified and approved, it cannot recover prior
accepted model revisions, reviewer/authorship trails, historical holdings and
targets, lifecycle/ranking/execution transitions, original `known_at`/`recorded_at`
times, prior provider payload bytes, ingestion retries, or accepted thesis and
evidence revisions. A current workbook snapshot or new provider response does not
recreate those histories. Record each included source, each recomputed output, and
each approved omission separately in the eventual recovery-gap report.

## Rehearsal, cutover, and rollback

No real-source rehearsal or production action is authorized by this PR. Task 4's
synthetic PostgreSQL 18 rehearsal covers only the current workbook-backed stage.
Later reviewed changes must add the market, fundamentals, and model/analytics
stages, then exercise a complete clean rebuild with frozen inputs and full domain
reconciliation before any real-source rehearsal. Production activation remains a
separate, explicitly authorized operation.

For a future rehearsal, use a separately verified disposable Neon branch, keep
workers and ingestion disabled, and save detailed reports locally. A rehearsal
branch is not the eventual canonical production database. Production activation
requires separate explicit authorization to change the application database
connection and any provider or scheduler settings. Before activation, capture a
recoverable backup of the then-current cloud database and agree on how post-cutover
writes are handled. Rollback before writes means restoring the prior application
connection; after writes, preserve and reconcile those writes before switching back.
Never use a branch label or hostname alone as proof of isolation, and never reset
production as a rollback method.
