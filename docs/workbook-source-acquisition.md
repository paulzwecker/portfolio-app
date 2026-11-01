# Private workbook source acquisition

This component acquires one explicitly selected workbook snapshot. It validates the XLSX
package and known sheet contract, writes the unchanged file to a private content-addressed
store, and records an immutable run manifest. It does not connect to PostgreSQL, call an
importer, or change application state. Acquisition requires the explicit
`--confirm-source-acquisition` flag.

No live Google workbook was accessed while implementing or testing this component. Tests
generate synthetic XLSX files and mock all Google Drive responses.

## Source decision

The current importers consume complete OOXML workbook files. They resolve tabs by name,
read fixed cell coordinates, preserve cached cell values as exact decimals, and retain
source-cell references. They do not evaluate formulas or use named ranges. The Google
Sheets API reader in the application reads only the separate versioned review inboxes;
it does not read the legacy portfolio workbook.

For an XLSX file stored in Drive, the preferred cloud transport is Drive API `files.get`
with `alt=media`; this downloads that file's bytes without converting it. For a native
Google spreadsheet, Drive API `files.export` produces XLSX, which preserves the workbook
tab and cell structure but is a Google conversion. The export may differ from the values
or formula caches of a previously saved Excel file. Use the recorded Drive revision and
content hash, then review representative formula, numeric, currency and date cells before
using that snapshot in an importer. If exact original XLSX bytes are required, use
`--from-file` with the operator-supplied authoritative XLSX export.

The Sheets API is not used to acquire the source artifact: its per-cell value/formula
representation is diagnostic only and is not the OOXML artifact consumed by existing
importers. The service queries one explicitly configured file ID only; it does not search
or list Drive contents. For the `portfolio` profile, when
`GOOGLE_DRIVE_PORTFOLIO_WORKBOOK_FILE_ID` is absent, the existing
`GOOGLE_SHEETS_SPREADSHEET_ID` is an approved fallback identity. The acquisition still
checks Drive's exact returned file ID and MIME type, requires stable source metadata,
downloads/exports the file, rechecks its revision metadata after transfer, and validates
the complete portfolio workbook contract. `market_data` never falls back to the portfolio
spreadsheet ID and requires its own explicit source ID or an operator-supplied XLSX.

For an uploaded XLSX, direct `alt=media` download preserves exact file bytes. For a native
Google spreadsheet, Drive XLSX export is a conversion; it must be accepted only after a
reviewer checks representative formula caches, numbers, currencies, dates, and exact
decimal behavior against the approved source contract. A permission error stops before
any workbook bytes are acquired. Share only the exact approved source with the configured
service account as Viewer and enable Drive API access; do not broaden its Drive access.

## Current importer contract inventory

| Workbook                   | Sheets required by the acquisition profile                                                                                                                                                                                                               | Existing consumer and mapped data                                                                                                                                                                                                                                             |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Portfolio_Watchlist.xlsx` | `Universe Registry`, `Current Holdings`, `Target Architecture`, `10Y Durability`, `Compounder Quality`, `Price Feed`, `Model Contract`, `Model Revision History`, `Estimate History`, `Candidate Ranking`, plus at least one `P-` and one `W-` model tab | Company identity/lifecycle, holdings and native-currency cash, exact fractional targets including zero, current scores, cached ranking positions, legacy estimates, research priority inputs, published model outputs/revision snapshots, and selected reviewed model inputs. |
| `Market Data.xlsx`         | `Listings`, `Daily Prices`, `Corporate Actions`, `Price Regime`, `Data QA`                                                                                                                                                                               | Exact venue/ticker/currency listing mappings, dated prices, action metadata, source quality and cached price-regime observations.                                                                                                                                             |

The acquisition profile fingerprints the tab order, defined-name names/scopes, workbook
date system, and importer header/contract cells. It records each tab's used range and
formula-cell count without putting cell values or formulas into the manifest. The full
file SHA-256 detects every content change, including changes to formulas and cached
values. Existing importer documentation describes the finer domain contracts and source
cell mappings in [workbook-import.md](workbook-import.md), [workbook-map.md](workbook-map.md),
[model-output-ingestion.md](model-output-ingestion.md), and [market-data.md](market-data.md).

No required named ranges are currently documented or read by these importers. Any named
ranges present in the source are inventoried; additions, removals or scope changes alter
the schema fingerprint and require review.

## Import-value fidelity and semantic fingerprints

For portfolio snapshots, acquisition records two independent identities:

- `artifact_sha256` is the SHA-256 of the exact XLSX bytes and remains the integrity,
  storage, and provenance key.
- `semantic_fingerprint_version` and `semantic_sha256` identify the normalized values
  consumed by the current portfolio import adapters. Version `portfolio-import-values-v2`
  serializes allowlisted importer cells, their canonical target-field mapping, source role,
  formula-presence state, and normalized value as canonical JSON, then hashes it with
  SHA-256. It is independent of XLSX ZIP timestamps, member order, and other packaging
  differences.

The semantic projection includes source type and an explicit state for missing, blank,
zero, invalid, formula-cache-empty, and formula-error cells. Numeric values are parsed as
`Decimal`; no binary floating-point conversion is used. Numeric meaning is canonicalized
without losing significant digits. A numeric cell and a text cell containing the same
digits remain distinct. Currency codes remain identifiers; no currency conversion is
performed. Estimate History date serials are normalized using the XLSX 1900/1904 date
system, while model-history timestamps still require the timezone-aware representation
accepted by the existing model importer. The workbook date system remains part of the
structural schema fingerprint.

The semantic hash covers only importer-owned values, not every workbook formula. It does
not replace the raw hash or source version. The manifest records Drive revision,
modification metadata, acquisition time, artifact hash, and semantic hash separately.
Thus two byte-different exports may have the same `semantic_sha256` and
`semantic_state: UNCHANGED`; their distinct `artifact_sha256` values remain auditable.
Formula text and workbook revision are protected by the frozen artifact and source
revision. A new source revision is never collapsed into an older snapshot merely because
its values happen to match. A changed XLSX cache under an unchanged Drive revision remains
a separately recorded artifact and changes the semantic hash when an imported value or
formula-presence state changes.

Each projection entry names the importer target and transformation rather than relying on
sheet geometry as architecture. `source_role` distinguishes spreadsheet-derived cached
values, literal inputs, legacy rank snapshots, listing crosswalk rows, score assessments,
research-priority inputs, historical estimate observations, and published model outputs.
Published Bear/Base/Bull and normalized return fields are copied as source-published values;
they are never silently recalculated or replaced with a live Sheets value. Workbook
current/target membership weights are recorded as legacy membership inputs and are not
treated as canonical current weights. Listing and cash currencies remain identifiers; the
importer performs no implicit currency conversion.

`semantic_summary.by_domain` counts formula cells, empty formula caches, formula errors,
and invalid importer values only for these bounded source areas:

| Import domain                        | Importer-consumed source cells                                                                                                                                                                    |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity, lifecycle and cached ranks | `Universe Registry` A/B/C/D/F/J/L/M, data rows from 5                                                                                                                                             |
| Holdings and cash                    | `Current Holdings` A/B/D/E/G, data rows from 5, plus base-currency label L4                                                                                                                       |
| Strategic targets                    | `Target Architecture` A/D, data rows from 5, plus control total P3                                                                                                                                |
| Quality assessments                  | `10Y Durability` and `Compounder Quality` A:G/K:M, data rows from 5                                                                                                                               |
| Listing identity crosswalk           | `Price Feed` A/B/C/D/H, data rows from 5                                                                                                                                                          |
| Research-priority inputs             | `Candidate Ranking` A/B from row 2 and `Universe Registry` A/C                                                                                                                                    |
| Published model outputs and scores   | `P-`, `W-`, and `C-` tabs: A7:B8; `P-`/`W-` output contract `AZ3:AZ20`, `BA3:BA15`, and `BA19:BA20`; recognized currency labels plus the next one to three cells scanned for an ISO currency code |
| Published model-output history       | `Model Revision History` A:Z for rows with a revision identity in A                                                                                                                               |
| Legacy estimate history              | `Estimate History` A/B/D:G for data rows from 2                                                                                                                                                   |

Unrelated research/dashboard formulas are excluded and do not block structural schema
approval. This does not make an affected imported field valid: an empty or erroneous
importer formula remains unavailable and is handled by its domain importer:

- Blank cached current/target weights do not classify lifecycle. Cached rank values remain
  unavailable when membership cannot be established.
- Missing/invalid `Target Architecture!P3` blocks target import because the target control
  total cannot be reconciled. Target rows are never normalized to fit it.
- An empty score formula cache creates an INVALID/null score assessment with an explicit
  issue. It is not neutral, zero, or passing.
- An empty published model-output formula cache remains null and marks that output snapshot
  `DATA_CHECK`; an empty formula result in historical output cells is likewise preserved
  as null with an issue. No live value is substituted into the frozen snapshot.
- Formula errors on unrelated tabs/cells are reported only if the existing importer reads
  those cells. Invalid accepted outputs are not converted to zero.

### Read-only live Sheets comparison

Use this only to diagnose an exact frozen native-Google-Sheets XLSX export. The command
uses the configured portfolio spreadsheet identity and service account with read-only
Drive and Sheets scopes. It verifies the source identity, Drive revision and modification
time before reading, fetches only allowlisted importer ranges in bounded requests, repeats
the complete effective-value read, and checks Drive metadata again. One consistency fence
covers both complete sweeps; chunks are not validated against independent metadata
snapshots. Each HTTP attempt, including metadata requests and retries, is paced by the same
limiter. It requires identical normalized live value and formula-definition fingerprints
across both sweeps and stable Drive metadata. If the revision has advanced, it reports
`SOURCE_ADVANCED_REACQUIRE_REQUIRED`; if the workbook or effective values change during
comparison, it reports a non-accepted diagnostic status. Sheets does not provide a
transaction/snapshot token for formula recalculation, so repeated equal projections are a
bounded stability check, not a claim that volatile formulas are transactionally frozen. It
does not edit Sheets, acquire another XLSX, connect to Neon, or write application/domain
data.

The comparator has explicit scopes. `canonical-bootstrap` (the default) compares every
importer-consumed value needed by the initial canonical portfolio import: identity and
lifecycle, holdings and cash, strategic targets, quality assessments, listing crosswalk,
research-priority inputs, and investment scores. Published model-output snapshots, output
history, model currency metadata, and legacy estimate history are a separate
`optional-model-research` scope, consumed by the distinct model/analytics bootstrap. Use
`all-importers` when a complete source review is intended. Unknown importer domains block
planning rather than being silently omitted.

Before making any Google API request, the command builds and reports the complete selected
work plan. Work is blocked with `BLOCKED_VALIDATION_BUDGET_EXCEEDED` and a private report
containing counts/limits rather than sampled if any ceiling is exceeded. Current explicit
per-run ceilings are 30,000 selected contract cells, 60,000 requested range cells per sweep,
4,000 ranges and 70 API chunks per sweep. Each Sheets request is limited to 60 ranges and
8,000 requested cells. Ranges are exact, deduplicated, deterministically ordered and
compactly merged only when every cell in the resulting rectangle is selected. A repeated
two-sweep comparison therefore remains bounded to at most 426 HTTP attempts including
retries; actual request attempts are recorded. If a future importer population exceeds the
work budget, the report is a blocker, not an invitation to raise a ceiling or sample cells
without review.

For a fresh importer-scoped projection, acquire a new frozen snapshot first. This does not
approve a schema, import data, or connect to PostgreSQL. The acquisition may exit with code
2 when the snapshot needs structural review; retain the emitted run ID for the comparison.

```powershell
$snapshotStore = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run source:workbook -- acquire portfolio --store $snapshotStore `
  --confirm-source-acquisition
```

Then compare that exact frozen snapshot. The PowerShell command is:

```powershell
$snapshotStore = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run source:workbook:compare-values -- '<frozen-portfolio-run-id>' `
  --store $snapshotStore `
  --scope canonical-bootstrap `
  --confirm-read-only-live-comparison
```

Use `--scope optional-model-research` for the separate model/research import scope or
`--scope all-importers` to validate both. Sanitized command output includes selected
cell/range/chunk counts, compared cells, request progress, mismatch classes and consistency
result. Detailed cell coordinates and hashed comparison evidence remain in the private
value-comparison report. A `COMPARED` result with any mismatch class is still a CLI failure
and does not establish value-fidelity GO.

The service account needs Viewer access to that exact spreadsheet. The local network
proxy must be reachable; the command honors normal requests proxy settings and must not be
used to bypass a network restriction. A separate `spreadsheets.readonly` authorization
scope is used for the cell comparison. Console output contains counts and classifications
only. The acquisition manifest privately records formula-cache/error coordinates together
with their importer target and transformation. Comparison contract v3 and later write a versioned
exception ledger in the private store's `value-comparisons` directory. For mismatches it
retains exact XLSX cached values/formulas/types and live Sheets entered formulas/effective
values/types, normalized hashes, importer semantics and source-version evidence. Protect
that private ledger with user-only filesystem permissions; never copy it into Git, CI,
tickets or public reports. Raw values, formulas, file IDs and credentials are not printed
by the CLI.

Current comparison contract v5 also records the UTC start and completion times of the
entire metadata/value consistency fence. Earlier comparison reports without those timestamps
remain useful for diagnosis, but cannot authorize a live-value overlay.
Each v5 comparison also writes a private attempt-start record before reading the snapshot or
contacting Google, then links its terminal report by an attempt ID. An interrupted attempt,
newer failed comparison, unreadable report, or unsupported newer contract blocks overlay
generation and approval; the tool never falls back to an older successful comparison. A new
successful comparison is required to close an interrupted attempt.

Native Google Sheets files may not expose a Drive `headRevisionId`. Missing revision
metadata does not by itself block comparison, but it also does not make a matching
`modifiedTime` sufficient evidence. The command then requires all of the following:

1. The manifest's hashed source identity matches the one configured file, and the live
   Drive metadata returns that exact file ID and native spreadsheet MIME type.
2. The snapshot and live `modifiedTime` are both present and exactly equal. Any source
   checksum captured in the manifest must also match.
3. Two complete, bounded reads of the importer-allowlisted ranges produce identical
   normalized value fingerprints **and** identical formula-definition fingerprints.
4. A final Drive metadata read exactly matches the first read for file ID, MIME type,
   modification time, revision metadata and checksum.
5. The frozen XLSX passes its raw SHA-256 check, its importer semantic fingerprint
   recomputes, and live importer values are compared against that frozen projection.

When `headRevisionId` is absent in both the frozen manifest and live metadata, the report
sets `consistency_protocol` to `NO_DRIVE_REVISION_SEMANTIC_FENCE` and leaves
`source_revision_matches_snapshot` null. A revision appearing or disappearing between
acquisition and validation fails closed and requires a fresh acquisition. Changes to live
values, formula definitions, or metadata between the two reads produce a non-accepted
status. A stable pair of reads is a bounded semantic consistency fence, not a Google
transaction/snapshot token; it cannot prove atomicity for unrelated cells or volatile
calculations outside the importer scope. If the source advances, reacquire and validate
that exact new frozen artifact rather than accepting an older run.

### Review-gated stale-cache overlay

For new canonical imports from native Google Sheets, the versioned source-value bundle in
[`native-google-sheets-source-value-bundle.md`](native-google-sheets-source-value-bundle.md)
supersedes this overlay path. The bundle is required to make the native Sheets effective
values authoritative for the declared importer fields. This older overlay is retained for
historical review/replay only; it cannot be combined with a native Google Sheets bootstrap
and its approval is not transferable to a source-value bundle. Do not use it to waive the
native source-value review gates.

The comparator never changes the XLSX artifact. If a complete v5 comparison proves a
numeric importer field has a stale XLSX formula cache while the source and live formulas
match exactly, the local operator may create a private candidate with:

```powershell
npm run source:workbook:value-overlay -- candidate `
  --store $snapshotStore `
  --portfolio-run '<exact-portfolio-acquisition-run-id>'
```

The candidate is limited to explicitly allowlisted score fields and legacy lifecycle
membership inputs. It binds the exact acquisition run, raw artifact hash, semantic
fingerprint, hashed source identity, Drive modification/revision metadata, comparison
report hash, comparison time window, source cell, exact cached/live decimal text and
expanded formula identity. Shared formula followers are expanded using OOXML anchor
references with ordinary A1 relative/absolute reference rules; unsupported reference
shapes fail closed. A candidate is always `REVIEW_REQUIRED` and stored in the private
`value-overlays` directory. The generation command is repeatable and does not contact
Google, connect to PostgreSQL, or alter the workbook.

Only after reviewing the private candidate may an operator create an immutable local
approval receipt. The explicit confirmation flag is required:

```powershell
npm run source:workbook:value-overlay -- approve `
  --store $snapshotStore `
  --portfolio-run '<exact-portfolio-acquisition-run-id>' `
  --candidate-sha256 '<reviewed-candidate-sha256>' `
  --reviewed-by '<reviewer>' `
  --review-note '<review summary>' `
  --confirm-overlay-values
```

Approval is not schema acceptance or production authorization. A canonical bootstrap
preview/apply/reconcile must be given both `--portfolio-value-overlay` and its exact
`--portfolio-value-overlay-sha256`; the bootstrap verifies the overlay receipt, its
candidate and report against the same frozen artifact before resolving values. Omitting
the overlay preserves cached XLSX behavior. When applied, the overlay SHA is included in
the import source digest and source references, so replay is idempotent for the same
approved resolution and distinct from a cached-only import. The original XLSX SHA and
semantic fingerprint are never changed. Apply remains subject to all ordinary schema,
source, identity, database-target and write-authorization gates.

An overlay is unavailable when the comparison is unstable, any importer-consumed formula
difference remains unresolved (including a current-value match), a source formula is unresolved,
the field is not allowlisted, the value is blank/error/non-numeric, or exact decimal and
source-cell checks fail. It must not resolve listing identity, missing inputs, unsupported
methodologies, invalid source rows, or any human investment decision.

The comparison contract reports formula-definition, typed-value, number-format and current
importer-semantic relations independently. Formula text normalization is limited to trimming
whitespace around the formula and one optional leading `=`; no formula parser or algebraic
rewrite is used. Numeric comparison uses exact `Decimal`, currency identity remains explicit,
and display formatting never rescales a stored currency or percent value. Blank/missing
absence remains distinct from zero; formula-cache-empty and formula-error states remain
unavailable. Narrow importer equivalences (for example, presence-only evidence counts or an
unused fallback name) are recorded explicitly without erasing the underlying mismatch.
Mismatch classes distinguish formula errors, empty XLSX formula caches with live values,
same-source-metadata formula-cache/live differences, changed dynamic/external formula results,
value-type differences, date interpretation/format differences, currency identity and
format differences, percent and numeric-format differences, and other value differences.
`STALE_XLSX_CACHE_CANDIDATE` and
`LIVE_CALCULATION_CHANGED_AFTER_EXPORT_CANDIDATE` are diagnostic classifications, not
proof of root cause: a formula may depend indirectly on dynamic data. Formula errors are
classified as such only for importer-allowlisted cells; errors elsewhere in research or
dashboard tabs do not block value-fidelity review. A changed Drive revision is reported
separately and must be reacquired before values are compared. The comparison never writes a
live effective value back into the snapshot or bootstrap plan.

An older private comparison report may predate comparison-contract versioning and may not
retain exact live values or formulas. Its class counts can support triage only; formula
syntax and exact value deltas require a new read-only comparison under the current contract.
Do not infer syntax translation, locale conversion, array expansion or formula equivalence
from hashes alone.

Importer-value GO is assessed per source domain: the frozen raw artifact must pass
SHA-256 verification, the v2 semantic projection must recompute exactly, source identity
and revision must match, and relied-upon values must have acceptable type, precision, and
status. Required formula-derived fields with empty caches, formula errors, invalid dates,
unresolved identities, or unexplained live mismatches keep the affected domain unavailable
or NO-GO. Unrelated formulas do not block other domains or structural schema acceptance.
A live-vs-cache mismatch remains a review blocker for a field whose imported value depends
on that cell until an authorized reviewer resolves it with source evidence; this tool never
chooses a winner.

## Storage and manifests

Use a private store outside the repository checkout. The tool rejects store, credential
and operator-file paths inside the checkout. On POSIX systems it creates directories with
owner-only access and files with owner-only read/write access; the service-account file
must also be owner-only. On Windows, place the store and credential under a user-private
directory with restrictive NTFS ACLs. In a cloud execution environment, use private
ephemeral storage outside the checkout; use encrypted storage if the snapshot must persist.
Do not upload the store or its contents to GitHub, CI artifacts, PR attachments or public
storage.

The store layout is:

```text
<private-store>/
  blobs/sha256/<content-sha256>/workbook.xlsx
  runs/<run-id>.json
```

The workbook blob is content-addressed and never overwritten. Identical acquisitions
reuse that blob and create a new manifest. Each manifest records the source profile and
contract version, acquisition method and time, Drive revision metadata when available,
content hash/size, schema fingerprint, tab inventory, formula counts, date system, prior
accepted run, review state and `import_triggered: false`. Drive file IDs are represented
only by a SHA-256 source identity; credentials, file names returned by Drive, response
bodies and workbook cell values are not logged or copied into manifests.

Manifest creation is append-only at the application level; the store is not a signed or
tamper-proof archive. Protect the containing filesystem and retain any separate backups
under the operator's security policy.

## Google access configuration

1. In the Google Cloud project, enable the Google Drive API.
2. Create a dedicated service account for this acquisition. Do not grant it project-wide
   Editor/Owner roles or membership in a shared drive.
3. Share only the authoritative portfolio workbook and Market Data workbook with that
   service account as **Viewer**. Drive grants file access, so keep the account dedicated
   and share no unrelated files.
4. Place its JSON key in a private secret file outside the checkout. On Linux, set mode
   `0600`; on Windows, restrict the file's ACL to the operator/runtime identity. The
   current implementation loads this service-account file with the Drive read-only
   `drive.readonly` scope. It does not support an interactive OAuth flow.
5. Obtain each Drive file ID from its approved source record. Set the file IDs and key
   path only in the explicitly authorized acquisition environment. Do not put them in
   GitHub Actions, `.env.example`, source code, shell transcripts or the workbook run
   manifest.
6. Set an absolute private store path outside the repository. Acquire one source at a
   time and keep the resulting run ID and private manifest available for review.

For Windows PowerShell 5.1 or 7, place the key file first, then create private
directories and remove inherited ACLs before granting access to the identity that will
run acquisition:

```powershell
$secretFile = 'C:\private-secrets\drive-workbook-reader.json'
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
New-Item -ItemType Directory -Force -Path (Split-Path $secretFile) | Out-Null
New-Item -ItemType Directory -Force -Path $store | Out-Null
$operatorIdentity = "$($env:USERDOMAIN)\$($env:USERNAME)"
icacls $secretFile /inheritance:r
icacls $secretFile /grant:r "${operatorIdentity}:(R)"
icacls $store /inheritance:r
icacls $store /grant:r "${operatorIdentity}:(OI)(CI)F"
```

For a hosted runtime, use its execution identity and follow its secret-mount and storage
policy. Keep the printed ACL output private if it reveals user names.

No Render, Vercel, Neon or GitHub settings are changed by this component. Do not add these
secrets to a persistent production service environment without separate authorization.

### Windows PowerShell 5.1 or 7 — Drive acquisition

Run from the repository root. Replace placeholders locally; do not paste real file IDs or
credential contents into a PR or support log.

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
$env:GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = 'C:\private-secrets\drive-workbook-reader.json'
$env:GOOGLE_DRIVE_PORTFOLIO_WORKBOOK_FILE_ID = '<approved-portfolio-drive-file-id>'

npm run source:workbook -- acquire portfolio --store $store --confirm-source-acquisition
```

For Market Data, set `GOOGLE_DRIVE_MARKET_DATA_WORKBOOK_FILE_ID` to its approved file ID
and run:

```powershell
npm run source:workbook -- acquire market_data --store $store --confirm-source-acquisition
```

### Windows PowerShell — operator-supplied snapshot

Place the exact XLSX in a private directory outside the repository, then run:

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run source:workbook -- acquire portfolio --store $store `
  --from-file 'C:\private-source\Portfolio_Watchlist.xlsx' `
  --confirm-source-acquisition
```

This path does not use Google credentials. Repeat with `market_data` and the approved
`Market Data.xlsx` file for that source.

### Linux or a one-shot cloud execution environment

Mount the service-account JSON as a protected secret file and supply file IDs through the
execution environment, not through source control. For example:

```sh
export GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=/run/secrets/drive-workbook-reader.json
export GOOGLE_DRIVE_PORTFOLIO_WORKBOOK_FILE_ID='<approved-portfolio-drive-file-id>'
snapshot_store=/var/tmp/portfolio-private/workbook-snapshots
npm run source:workbook -- acquire portfolio --store "$snapshot_store" --confirm-source-acquisition
```

The store should be ephemeral and private for a one-shot run. If a later execution needs
the same version, acquire from the same Drive revision and compare hashes, or transfer the
operator-approved snapshot through an approved private channel. Do not create a CI cache
or artifact containing the workbook.

## Review and schema baseline

The first valid acquisition has `schema_state: UNBASELINED` and
`status: ACQUIRED_REVIEW_REQUIRED`. A missing/empty required tab, invalid XLSX part,
checksum mismatch, size violation or invalid target writes a failed manifest but no
workbook blob. Review-required and failed commands return exit code `2`; a stable,
previously reviewed schema returns `0`. A changed tab list, defined-name inventory,
header contract or date system
has `schema_state: DRIFTED` and remains review-required. The acquisition records the full
content hash for ordinary source changes even when the schema stays the same.

Review the private manifest and its inventory before accepting a first baseline or schema
change:

```powershell
npm run source:workbook -- show '<run-id>' --store $store
```

Compare the recorded source revision, tab inventory, unclassified tabs, defined names,
date system and relevant source-cell contract to the approved source. Confirm that the
XLSX export has the expected cached numeric/formula behavior. After that exact snapshot
has been reviewed, append a separate immutable schema-baseline acceptance record pinned
to the SHA-256 from its manifest:

```powershell
npm run source:workbook -- accept-schema '<run-id>' --store $store `
  --expected-sha256 '<reviewed-64-character-sha256>'
```

The acceptance record points to the original content-addressed blob and parent run; it
does not edit the original manifest or fetch the workbook again. It cannot accept a stale
run if a newer acquisition for that source exists. A repeated acquisition with the same
schema then reports `schema_state: UNCHANGED`; a new workbook hash is recorded as a new
content version. A later schema change must be reviewed and accepted again.

The acquisition and schema acceptance commands never call an import. Import remains a
separate operator action using its existing dry-run/reconciliation workflow, for example
`db:import-workbook` or `db:import-market-data`. Review the source manifest, importer
preview and target write authorization independently before any import. The workbook
content is not automatically copied into a report or database by this component.

For ongoing portfolio-source snapshots, rerun the same `source:workbook acquire portfolio`
command after the source publishes a new revision. The command appends a new immutable
manifest and content-addressed blob, deduplicates identical bytes, and never approves a
changed schema. Repeated acquisition is a transport/update history only; it does not
synchronize canonical database state. Field ownership and the future synchronization
protocol are documented in [workbook-sync-ownership.md](workbook-sync-ownership.md).

## Limits and CI boundary

- Maximum compressed workbook size is 32 MiB; maximum uncompressed XLSX package size is
  256 MiB and the archive may contain at most 10,000 parts.
- Google Drive requests use bounded 30-second reads and at most three attempts for
  transient network/429/5xx failures. Permission, identity, format and validation errors
  do not retry.
- Google Drive uploaded XLSX files are checked against Drive's MD5 when supplied; all
  accepted artifacts receive a local SHA-256. Drive file identity, MIME type, modification
  time, revision ID and MD5 are checked again after transfer; concurrent source edits fail
  closed. Native Google Sheet exports have no Drive file MD5 and are identified by the
  acquired XLSX SHA-256 plus Drive modification metadata. Google limits native document
  exports to 10 MB; larger exports need an operator-supplied XLSX or another approved
  transfer.
- The private cache deduplicates by content hash. It does not run a background refresh,
  schedule ingestion or require a database connection.
- CI has no Google source IDs or credentials, does not run acquisition, and excludes
  source workbook files and source-bound tests. Workbook acquisition tests use generated
  synthetic XLSX files and mocked responses only.

The implementation is ready for operator review, but no real source acquisition or
snapshot has been staged or executed.
