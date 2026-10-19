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

The Sheets API is not used for acquisition: its per-cell value/formula representation
would require a new normalization layer and would not be the OOXML artifact the existing
importers consume. The service queries one configured file ID only; it does not search or
list Drive contents.

Because the live source's Drive MIME type has not been authorized for inspection, the
conservative first acquisition is an operator-supplied `.xlsx` snapshot from the approved
source. Once the source is confirmed to be an XLSX file in Drive, direct `alt=media`
download is the most portable unattended path and preserves those exact file bytes. If it
is a native Google spreadsheet, use Drive export only after comparing a reviewed sample
against the approved XLSX values/formula caches. This keeps the first migration snapshot
from silently depending on unverified export semantics.

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
