# Workbook source ownership and future synchronization contract

## Status

The approved portfolio/watchlist workbook remains authoritative for the workbook-
owned investment inputs listed below. The application now has a bounded, versioned,
manual synchronization path. See [Workbook Sync Operations](workbook-sync-operations.md)
for its review and apply workflow. Implementing this path does not activate recurring
polling, schedule cloud jobs, or authorize a production import; activation flags remain
disabled by default.

## Field ownership

| Ownership              | Fields and records                                                                                                                                                                                                                                                                                                                     | Synchronization behavior                                                                                                                                                                                                                                                                                     |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Sheets-authoritative   | Source company identities and lifecycle inputs; workbook listing crosswalks when explicitly mapped; holdings and cash snapshots; strategic target inputs; workbook quality scores and research-priority inputs; workbook-produced model-output snapshots; cached legacy rank positions when imported as historical source observations | Import only from a validated, versioned workbook snapshot using the explicit mappings in [Canonical Portfolio Bootstrap](canonical-portfolio-bootstrap.md). Preserve source dates, exact listing/currency identity, nulls, zeroes, and source references. A repeated snapshot digest is an idempotent no-op. |
| Provider-authoritative | Canonical prices, FX, corporate actions, reported fundamentals, filings, and third-party analyst consensus                                                                                                                                                                                                                             | Continue through the relevant provider adapters and precedence rules. Workbook values do not silently replace provider observations. Workbook crosswalks may identify a mapping only after exact review.                                                                                                     |
| Application-owned      | Accepted native financial-model revisions and revision history; accepted research forecasts, thesis/evidence revisions, and risk assessments; application review decisions; canonical ranking and Execution Pace runs; holdings-confirmation history; import receipts and operational records                                          | Never overwrite from a workbook snapshot. External proposals enter the existing preview/review/acceptance workflows. Historical application runs and accepted revisions remain immutable.                                                                                                                    |
| Derived/recomputable   | Current mark-to-market value and weights; allocation gaps; current Expected IRR derived under its documented methodology; canonical rankings, Execution Pace, Attention Center events, and market analytics                                                                                                                            | Recompute from eligible canonical inputs. Do not write derived results back as accepted assumptions, targets, provider facts, or historical decision runs. Historical outputs/runs remain tied to their original inputs.                                                                                     |

Workbook model outputs are not accepted native model state. Preserve them as
source-linked imported snapshots where the corresponding import workflow supports
them; they must not overwrite an accepted native revision. Likewise, cached workbook
rank positions are imported legacy observations, not replacements for application
ranking runs.

## Snapshot and synchronization identity

Every source observation starts with an immutable acquisition manifest containing a
random run identity, exact source identity hash, source revision/checksum where Drive
provides them, acquisition timestamp, artifact SHA-256, contract version, schema and
header fingerprints, and review state. The raw XLSX blob is content-addressed in the
private snapshot store. The source identity itself and workbook contents stay out of
Git, CI artifacts, and task output. An unchanged artifact may reuse the content blob,
but each acquisition attempt retains its own manifest and source revision context.

The implemented portfolio synchronization is incremental by source snapshot plus
exact domain projection digest. It follows these rules:

1. Validate the complete workbook contract and the approved schema fingerprint before
   producing a domain projection.
2. Resolve rows only through explicit canonical company, security, listing, currency,
   and fiscal/period mappings; unresolved or conflicting mappings block the affected
   projection rather than guessing.
3. Compare the selected snapshot with the last successfully reconciled snapshot for
   the same source and domain. An identical projection digest is an idempotent no-op.
4. Persist a redacted, durable receipt that links the acquired snapshot, importer
   version, domain digest, validation/reconciliation result, and target identity.
5. Write only fields owned by the source domain. App-owned history, decisions,
   accepted model revisions, provider observations, and prior import receipts are
   never updated or deleted by a newer workbook revision.
6. Report conflicts and partial rows explicitly. Preserve missing versus zero and
   avoid silently normalizing inconsistent holdings, cash, lifecycle, targets,
   currencies, or listing identities.

## Deletions, corrections, and rollback

A row absent from a later workbook is not by itself a deletion instruction. It may
reflect a partial export, changed filter, renamed row, or incomplete source. Require
an explicit source tombstone or a reviewed deactivation decision with a reason and
source evidence before changing current source-owned state. Never infer company
lifecycle from holdings or ranks.

Corrections create a new source snapshot and a new import receipt. They do not rewrite
the acquisition manifest or historical imported observation. A conflict with an
application-owned record goes to review; it is not resolved by last-write-wins.

Rollback is compensating, not destructive: reconcile against the previously approved
snapshot, then create a new reviewed import/correction receipt that restores only the
source-owned current projection. Keep the mistaken import receipt and all historical
observations for audit. Before any production synchronization, create and verify the
database restore point required by the bootstrap runbook and review a read-only
preview against the exact production identity.

## Current operational state

`source:workbook acquire portfolio` can use the configured
`GOOGLE_SHEETS_SPREADSHEET_ID` as its explicit portfolio source when the dedicated
`GOOGLE_DRIVE_PORTFOLIO_WORKBOOK_FILE_ID` is unset. It still performs exact Drive
metadata, stable-revision, download/export and complete XLSX contract checks. The
Market Data source never inherits the portfolio ID and still requires its own approved
ID or a separately authorized operator-provided XLSX. Schema changes continue to
require explicit hash-based review.

The live configured source could not be acquired in this task because Google Drive
denied the exact metadata request. Therefore no real workbook contract, revision,
formula cache, snapshot hash, or schema fingerprint has been verified. See
[Workbook Source Acquisition](workbook-source-acquisition.md) for the operator access
recovery steps. Database synchronization and recurring polling remain disabled unless
an operator explicitly enables the relevant flags and authorizes the target. The
portfolio workbook is not included in automatic Sheets inbox polling.
