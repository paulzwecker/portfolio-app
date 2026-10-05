# Canonical model-output ingestion

Milestone 2B ingests the published normalized outputs and recorded revision rows
from `reference/workbook/Portfolio_Watchlist.xlsx`. It does not migrate model
assumptions, projections, formulas, or the Google Sheets authoring workflow. The
workbook remains the authoring environment for those parts of the model.

## Source and mapping

The fixed `Model Output Contract` block uses labels in `AZ3:AZ20` and published
values in `BA3:BA20`. Import validates those labels against the versioned v1
contract before accepting numeric values. A contract is published only where the
source explicitly marks `BA20` as `PASS`; `NOT MAPPED`, blank status and any other
status remain separate unavailable/data-check states. Numeric values from
non-published contracts are withheld.

The importer takes only these numeric output fields:

- Bear, Base and Bull fair values and scenario probabilities
- Weighted Fair Value and Weighted Upside
- Expected Cash-Flow IRR, Hurdle and Expected Excess
- Forward Fundamental CAGR

It records model status, the exact model-tab key, explicit model currency where a
currency label and ISO code are present, workbook hash and source cells. It does
not import the contract's lifecycle or central score values. It does not infer
model currency from listing currency, company reporting currency, or the
`Model Revision History` current-price currency.

For identity mapping, the importer matches the source `Universe Registry` ticker
and company name to one non-demo application company. Exact listing ticker may
disambiguate duplicate company names. Ambiguous or absent identities are reported
and withheld; the importer does not create companies or listings.

The `Model Revision History` ledger supplies append-only historical output
snapshots. Mapped fields are Forward Fundamental CAGR, Bear/Base/Bull fair values,
Weighted Fair Value, Expected Cash-Flow IRR, Hurdle and Expected Excess, together
with revision ID, effective timestamp when valid, source/type, author lane,
rationale, evidence and notes. Other history columns that belong to price,
lifecycle or score domains are excluded. A missing or invalid timestamp stays
unknown. Invalid nonblank numeric cells remain null and are identified by an exact
source-cell issue.

Workbook cached values are read as exact decimals. The importer never evaluates
formulas and never derives Weighted Fair Value, Upside, Excess, IRR or CAGR. The
definitions in `docs/domain-model.md` specify their investment semantics; this
slice copies published results without claiming formula parity.

## Running and repeat behavior

Preview first; it performs no database writes and emits reconciliation and
unresolved mapping details:

```powershell
npm run db:import-model-outputs -- --report docs/reconciliation/model-output-dry-run.json
```

After reviewing the report, persist the additive snapshot import in a single
transaction:

```powershell
npm run db:import-model-outputs -- --apply --report docs/reconciliation/model-output-import.json
```

The default source is the committed `Portfolio_Watchlist.xlsx`; `--workbook` can
select another snapshot. `--observed-at` accepts an ISO timestamp with an explicit
offset and is useful for deterministic development runs. It is an import
observation/recorded time, never a substitute for the contract's unknown effective
time. The source workbook hash determines a stable batch identity, so repeating
the same import returns the stored receipt. Current contract snapshots are
fingerprinted and reused when identical. Legacy revisions are keyed by their
source revision ID; a changed payload under an already accepted revision ID
aborts instead of overwriting history.

Each batch receipt stores the workbook/source digests, observed time, mapped and
unresolved counts, issue detail, source-to-contract comparison and exact
persisted-value reconciliation. The ORM rejects later mutation/deletion of
accepted batches and snapshots.

## Reconciliation

The importer checks the cached Bear/Base/Bull outputs for three representative
model archetypes against their native model cells:

| Model     | Archetype       | Native fair-value cells | Contract cells |
| --------- | --------------- | ----------------------- | -------------- |
| `P-GOOGL` | DCF             | `E4:G4`                 | `BA4:BA6`      |
| `W-HDFC`  | Residual income | `B77:D77`               | `BA4:BA6`      |
| `W-TOST`  | Owner cash flow | `M46:M48`               | `BA4:BA6`      |

The comparison is exact Decimal equality over nine cached values. Any mismatch
prevents apply. The import then compares every non-null normalized numeric field
against persisted PostgreSQL values. This validates the published output mapping
and storage, not the formulas that produced it.

The checked-in workbook has 116 model tabs: 97 labelled `PASS`, 11 explicitly
marked `NOT MAPPED`, and 8 with no contract status. Of the 97 nominal `PASS`
blocks, 96 are accepted and one is withheld: `W-PLEJD` has a ticker/layout defect
and remains `DATA_CHECK`. Two model tabs (`P-MELI-SOTP` and `P-SPGI-CIQ`) do not
map to exact application company identities and are withheld. The history ledger
has 231 revision rows; 230 become snapshots and one `TKO` row is withheld because
its company identity is unresolved. Forty malformed numeric history cells and
one invalid effective timestamp remain null with field-level issues. Currency is
explicitly documented for 54 model tabs and unknown for 62; no currency is
inferred.

The nine representative cached values reconcile exactly with zero mismatches.
Apply stored 344 snapshots: 114 current-contract rows and 230 legacy history
revisions. The importer compared 2,367 populated decimal fields against
PostgreSQL, with zero differences. The machine-readable receipt linked below
records exact output-value counts, every unresolved item and these stored-state
results.

## API and UI

- `GET /v1/companies/{company_id}/model-outputs/current` returns current-contract
  snapshots and explicit model availability/quality states.
- `GET /v1/companies/{company_id}/model-outputs/history` returns current and
  historical snapshots, newest effective legacy revision first; `model_key` can
  filter the history.
- `GET /v1/universe/model-output-summary` exposes current model states for the
  Universe view.

The Company view shows the scenario outputs, model currency status, model status,
recorded/effective time, data-quality issues and expandable history. The Universe
view shows available/partial states, Weighted Fair Value and Expected Cash-Flow
IRR and supports coverage filtering and IRR display ordering. Missing values stay
“Not supplied”; no output is turned into zero, a rank, a gate, or a recommendation.
Values with unknown currency are not converted or compared against a market quote.

## Ownership and next migration

The application is canonical for the imported output snapshots and their history.
The legacy workbook remains the model-authoring system for assumptions,
projections, formulas, model construction, and outputs for unmapped models. Model
outputs do not own lifecycle, scores, target allocations, holdings, market facts,
or ranking definitions. No Expected IRR is computed by the app in this milestone.

Native model revisions are implemented separately for three parity-proven
methodologies: UFCF DCF, owner cash flow and residual income. They remain distinct
from these imported normalized snapshots. See [financial-models.md](financial-models.md).
Other model types still belong to their legacy authoring workflows until each is
separately modeled and reconciled.

The imported `Expected Cash-Flow IRR` field preserves the workbook's published
label/value; it does not certify canonical shareholder-cash-flow semantics. For
example, the P-GOOGL reference solves enterprise UFCF IRR. Preserve those values as
legacy method outputs until each return method is bridged and tested against the
application's explicit shareholder-cash-flow definition. The per-tab status,
currency, lifecycle and migration plan is in the
[model migration inventory](model-migration-inventory.md).
