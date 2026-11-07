# Canonical production portfolio baseline

**Verification date:** 2026-11-07

**State:** `PRODUCTION_VERIFIED` for the reviewed minimal Portfolio import only.

This record documents the first canonical portfolio restoration on the existing
production database. It does not establish full Google Sheets migration,
market-data readiness, model acceptance, or unattended operating readiness.
The exact source run IDs, raw hashes, position-level reconciliation, receipt
identifiers, and full reports remain in the operator's private
`%LOCALAPPDATA%\PortfolioResearch\workbook-snapshots` store and database
receipts. They are intentionally not copied into this public repository.

## Verified target and result

- Neon project `blue-pond-96398788`, primary branch
  `br-square-butterfly-bacw0rn5`, endpoint `ep-floral-cake-bae16liy`, database
  `neondb`, schema `public`.
- Alembic revision `9f2a6d4c81b7`.
- Render API and Vercel production ran merged commit
  `21e4d969d65af3ad5e0036a4a613c467e2e847a9` during the final import
  verification.
- One owner-authorized guarded apply completed as `APPLIED_WITH_GAPS` using the
  reviewed Portfolio and Market Data snapshots and the approved target-bound
  preview input. The receipt retains the exact input digest and source
  provenance.
- One canonical bootstrap receipt and one legacy import batch were recorded.
- Persisted scope: 209 companies, 23 securities, 23 listings, 1 portfolio, 1
  holdings snapshot, 22 holding positions, 2 native-currency cash positions,
  1 target revision, and 16 company target allocations totaling 100%.
- No models, lifecycle events, score assessments, ranking entries, prices,
  FX observations, fundamentals, consensus, theses, or research history were
  imported by this operation.
- A subsequent existing-command read-only preview returned `ALREADY_APPLIED`;
  its canonical receipt and receipt projection matched. The private report
  recorded zero reconciliation differences for identity, holdings, cash, and
  targets. Reconciliation uses the existing exact identity and decimal
  comparisons.
- Render `/health/ready` returned 200 and authenticated Portfolio/Universe API
  reads succeeded. The owner confirmed that companies and positions are visible
  in the production UI.

`APPLIED_WITH_GAPS` is intentional. It records the approved minimal scope and
does not mean every source workbook row was migrated.

## Reviewed exclusions and remaining coverage

The import retained the reviewed exclusions: 10 universe rows lacked company
names; 111 companies lacked optional listing mappings; 11 Market Data listing
rows were invalid and 3 were not ready. The formula-derived aggregate cash
summary was excluded; two native-currency cash positions were imported. The
zero reserve target was not modeled. Lifecycle, scores, rankings, model inputs
and outputs, and all market/fundamental/research observations were outside the
approved import contract. The held Novo Nordisk identity is Copenhagen-listed
`NOVO-B` in DKK; the SPYY ETF uses its reviewed standalone security/listing
identity without a fabricated company.

These are source and scope limitations, not zero-valued canonical records.
Resolve them only through their owning reviewed source contracts. Do not infer
company identities, listings, lifecycle, scores, model assumptions, or
investment decisions from the imported holdings or targets.

## Recovery retention

The pre-import recovery branch `br-sparkling-rice-baipcnmc` was verified as a
ready child of production with the expected parent LSN and pre-import schema
and data state. Its recorded expiration is **2026-11-14 09:54 CET**. It was
still present and unchanged after the import. Preserve it through owner review
and acceptance of this initial production baseline. It is a short-lived Neon
branch, not a durable backup; no restore was performed or rehearsed. Before it
expires, the owner must decide whether to preserve a separately verified
logical backup or establish another approved recovery point. Do not reset,
restore, extend, or replace it as part of routine application work.

Production write authorization was temporary to the single approved process
and is false in persistent local configuration. Hosted production-write,
manual-operation, workbook-sync, provider-ingestion, recurring-operation, and
Sheets-polling controls remain disabled. The import did not run migrations,
modify Sheets, accept a model, or trigger provider ingestion.

## M2 handoff: first model lifecycle

The P-GOOGL package and source-difference review remain private. Existing
validation evidence records native computational parity of 30/30 projections
and 22/22 published outputs, alongside five changed source inputs and 26
changed published-output fields relative to the prior package. This is source
revision drift, not a failed calculation-parity check. The current source
revision is still unapproved, and no canonical financial model was created by
the minimal portfolio import.

Next step is a **read-only** production preview using the existing
`db:financial-model-package preview` command and the exact privately stored
package run ID and payload hash. The imported canonical company/security/listing
identity removes the former `BLOCKED_IDENTITY` dependency, but the preview must
revalidate the exact identity, current schema, model method, package provenance,
existing model/base-revision state, and native calculation before reporting any
proposal as ready. Use `docs/financial-model-package-v1.md` for the command and
`docs/model-identity-bootstrap.md` for identity semantics. Do not run the
identity bootstrap again unless the read-only check proves the identity is
absent or inconsistent.

After independently verifying the private package manifest/hash and the live
production target, the documented preview shape is:

```powershell
$snapshotStore = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
$modelRun = '<exact privately stored P-GOOGL package run ID>'
$modelSha256 = '<matching package payload SHA-256>'

npm run db:financial-model-package -- preview `
  --store $snapshotStore `
  --run-id $modelRun `
  --payload-sha256 $modelSha256 `
  --target-environment production
```

This preview does not authorize or perform acceptance. Do not set production
write authorization and do not substitute a newly captured package or hash.

Before any model acceptance, the owner must review the private diff for the
exact package hash, all changed assumptions and outputs, probability
normalization evidence, source dates (which may be unknown), USD/NASDAQ:GOOGL
basis, enterprise-return semantics, and the precise new-revision effect. Model
acceptance is a separate guarded operation requiring its own explicit,
package-specific approval and fresh recovery review. Portfolio-import approval
does not authorize model acceptance.
