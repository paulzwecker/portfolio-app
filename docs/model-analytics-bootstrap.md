# Model and analytics bootstrap

## Purpose and boundaries

`db:bootstrap-model-analytics` composes the existing published-output importer and native
model-input importer over one frozen, explicitly approved Portfolio workbook snapshot. It does
not evaluate workbook formulas, turn output-only contracts into native models, relax a parity
mapping, or create ranking or Execution Pace history.

Published `Model Output Contract` rows remain immutable imported output snapshots with their
source status, currency, provenance, and effective-time policy. They are not described as new
native engine calculations. Native revisions are accepted only through the existing
method-specific importer when the exact workbook hash is pinned in the reviewed model migration
inventory, the supported assumptions are complete, identity and listing/currency are exact, and
all applicable deterministic projection/output parity checks pass. A hash mismatch blocks native
input acceptance while still allowing eligible published-output snapshots to be previewed.

No generic financial engine is introduced. UFCF DCF, owner-cash-flow, and residual-income behavior
continues to be owned by their existing deterministic methodology implementations and parity
fixtures. Decimal precision and Bear/Base/Bull scenarios remain as represented by those contracts.
Enterprise UFCF return definitions remain distinct from shareholder cash-flow IRR.

## Source and time handling

The command accepts only the latest schema-approved snapshot for the selected source identity,
rechecks the workbook schema fingerprint and content SHA-256, and requires the operator-supplied
digest to match. It does not contact Google Drive or modify the source workbook.

The workbook generally has no trustworthy global effective date. Historical output rows retain
only valid dates explicitly present in the model revision history. Current output-contract values
use an observation/recording time, never a fabricated effective date. Native model acceptance
uses application acceptance time when no reviewed source effective time exists. Native model
current outputs are recalculated by the existing engine; any missing/stale exact-listing quote or
other required input remains explicitly unavailable.

## Commands

First identify an exact approved Portfolio snapshot run and SHA-256 in the private snapshot store.
An `ACQUIRED_REVIEW_REQUIRED` or unbaselined snapshot is not eligible. Never copy the workbook or
the generated report into the repository.

Read-only preview:

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run db:bootstrap-model-analytics -- preview `
  --store $store `
  --portfolio-run <approved-32-character-run-id> `
  --portfolio-sha256 <approved-lowercase-sha256> `
  --target-environment production
```

The preview uses a read-only PostgreSQL connection, verifies the configured target and Alembic
head, and fails closed if the Neon control plane cannot verify the exact configured project,
branch, and endpoint. Its detailed report is written under
`model-analytics-bootstrap-runs` inside the private snapshot store; console output contains only
status and counts.

Apply is a separate operation and requires all of the following: reviewed preview, approved
snapshot, exact parity inventory hash for native inputs, explicit `--confirm-apply`, matching
`DATABASE_TARGET_ENVIRONMENT`, the existing database write-target guard, and its required
production authorization/confirmation. This documentation is not authorization to apply:

```powershell
npm run db:bootstrap-model-analytics -- apply `
  --store $store `
  --portfolio-run <approved-32-character-run-id> `
  --portfolio-sha256 <approved-lowercase-sha256> `
  --target-environment production `
  --confirm-apply
```

An apply runs published-output import and any eligible native-input acceptance in one database
transaction. Existing importer receipts make exact replay idempotent. If output reconciliation
fails, the transaction stops before native-input import. Individual unsupported, incomplete,
unmapped, or non-parity models remain blocked by the existing native importer and are not forced
into accepted state. The command never creates a rank or execution run; run those existing
read-only previews separately only after their prerequisites are satisfied.

## Historical readiness at implementation

The implementation-time private store contained portfolio acquisitions marked
`ACQUIRED_REVIEW_REQUIRED`; no schema-approved snapshot is available. The current local settings
also have production writes, recurring operations, Sheets polling, and cloud ingestion disabled.
That record describes the full-workbook model bootstrap. The later minimal
portfolio restoration is recorded in [the canonical baseline](production-canonical-baseline.md). A target-verified preview
requires working Neon control-plane access as well as an approved frozen snapshot.

The native model migration inventory is hash-pinned to its reviewed source workbook. Do not update
that hash just to make a newer workbook importable. A changed workbook requires a reviewed mapping
and parity update first.
