# Cloud-native canonical baseline runbook

## Scope and status

This runbook prepares a **new canonical cloud baseline** from versioned,
authoritative inputs. The historical local PostgreSQL database is out of scope and
must not be queried, exported, or migrated for this workflow. No Neon, Render, or
Vercel changes are part of this preparation.

The manifest `validate` command checks metadata. This PR adds `verify-inputs`,
which compares frozen source and mapping files with their manifest SHA-256 values.
Both commands are read-only and do not connect to PostgreSQL or providers or write
canonical state. A target-verified bootstrap orchestrator and full domain
reconciliation remain future work. Keep importer `--apply` disabled for this
baseline until the shared write guard and a disposable PostgreSQL 18 rehearsal are
in the reviewed execution path.

| State       | Current implementation status                                                                                                                                                                              |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Implemented | Closed metadata manifest contract and private input hash verification; dependency, identity-map, timestamp, history, exact-decimal, and missing-versus-zero checks; CI checkout excludes source artifacts. |
| Tested      | Synthetic manifest and artifact verification plus synthetic financial model fixtures; database integration tests use disposable PostgreSQL only.                                                           |
| Staged      | Operator-populated source manifest and artifacts, exact identity mapping, recovery decisions, target authorization, domain import phases, and full orchestration.                                          |
| Executed    | Manifest and artifact checks against synthetic temporary files only. No portfolio source data, canonical database, or cloud resource was accessed or changed.                                              |

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

No rehearsal or production action is authorized by this PR. A later reviewed PR
must first add a bounded orchestrator that verifies the Neon control-plane project,
branch, endpoint, and primary-production identity against the exact resolved
database connection; verifies PostgreSQL 18, expected Alembic head, allowed
extensions, and target emptiness; and checks the manifest plus source hashes before
any writes. It must use one-domain transactions and persistent idempotency records,
resume by completed source entry, and emit sanitized reconciliation and gap reports.
Test it twice and across an interrupted run on disposable PostgreSQL 18 before any
operator rehearsal.

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
