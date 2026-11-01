# Google Sheets UFCF DCF Model Package v2

## Purpose

`financial-model-package-v2` extends the read-only direct-Sheets package
workflow to a small allowlist of UFCF DCF layouts whose source mappings and
native numerical parity are already reviewed. It is not a general spreadsheet
parser. Unknown model keys, currencies, tab dimensions, required formulas,
range sets, source types or model mappings fail closed.

The v2 exporter reuses `SheetsPortfolioReader`, typed source-cell evidence,
the existing DCF input mappers and `calculate_ufcf_dcf` parity path. Captured
packages remain unaccepted proposals. Capture, dry-run, inspection and
validation do not connect to PostgreSQL or create model revisions. Contract v1
and its P-GOOGL canonical preview/acceptance path remain unchanged.

## Reviewed template registry

The registry lives in
`apps/api/src/portfolio_api/financial_model_package_templates.py`. It contains
explicit identities, mapping versions, source ranges, tab dimensions and
formula-presence signature cells. Those cells must remain formulas, while the
native-engine parity check validates their captured results. This is structural
metadata; financial values are never stored in the registry.

| Model     | Template                                       | Reviewed source distinction                                                                          | Return method               |
| --------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------- |
| `P-GOOGL` | `p-googl-ufcf-growth-grid`                     | Existing five-year scenario grid with Year 10 UFCF growth represented across the scenario growth row | Enterprise UFCF IRR         |
| `P-CPRT`  | `portfolio-ufcf-explicit-terminal-growth`      | Five-year operating grid with explicit Bear/Base/Bull Year 10 growth cells                           | Enterprise UFCF IRR         |
| `P-AMZN`  | `portfolio-ufcf-explicit-year-six-to-ten-tail` | Five-year operating grid plus explicit annual UFCF growth for years 6–10                             | Enterprise UFCF H-model IRR |

Each model has a separately declared range set. All mappings are checked
against the existing exact company/listing/currency identity contracts and
`model_input_migration` mapper. A tab name alone is not considered sufficient
evidence of compatibility.

The return methodology and enterprise perspective are carried into the
package. They are not relabeled as canonical shareholder IRR and remain
incomparable to shareholder-return models.

## Package and consistency semantics

The package contains:

- exact model and listing identity, template and mapping versions, currency,
  units, methodology version and return semantics;
- native DCF inputs and separately identified source-published outputs;
- the raw Google Sheets entered formula, effective value, formatting and
  typed blank/zero/error state for every declared source cell;
- source Drive identity hash, modification time, optional Drive revision,
  spreadsheet tab identity, complete qualified ranges and a source-observation
  consistency label;
- a content-derived external revision ID, input digest and explicit
  `PROPOSAL_NOT_ACCEPTED` state.

Google Sheets does not provide a transactional multi-range snapshot. Capture
checks source metadata and tab structure before and after two complete reads;
all typed cells and formulas must match between those reads. The package is an
observed stable source state, not a transactional snapshot. Exact decimals are
stored as decimal strings in canonical JSON. XLSX caches are not read by the
live exporter.

Validation reconstructs the native DCF input from the preserved typed cells,
checks the input and external revision hashes, and replays the existing DCF
engine against the published projection, valuation and return-stream cells.
Projection and output differences are blocking. Historical workbook parity
fixtures are not used to overwrite current source assumptions.

## Operator workflow

Run from the repository root in the configured Windows environment. The
service account requires Viewer access to the configured native spreadsheet.
The command prints only sanitized metadata and stores model cells and detailed
reconciliation privately under `%LOCALAPPDATA%\PortfolioResearch\workbook-snapshots`.

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'

# Bounded live read, validate, but do not store a package.
npm run db:export-dcf-model-package -- capture `
  --model-key P-CPRT `
  --store $store `
  --dry-run `
  --confirm-read-only-source-capture

# Store a content-addressed package after the dry run passes.
npm run db:export-dcf-model-package -- capture `
  --model-key P-CPRT `
  --store $store `
  --confirm-read-only-source-capture
```

Use one of the reviewed keys `P-GOOGL`, `P-CPRT` or `P-AMZN`. Record the
returned run ID and payload SHA-256 locally. Inspect and validate by exact
identifiers:

```powershell
$runId = '<private-run-id>'
$packageHash = '<64-character-payload-sha256>'
npm run db:export-dcf-model-package -- inspect --store $store --run-id $runId --payload-sha256 $packageHash
npm run db:export-dcf-model-package -- validate --store $store --run-id $runId --payload-sha256 $packageHash
```

Do not place package contents or detailed reconciliation reports in Git, CI,
issues or task messages. The package exporter has no accept, database preview,
or production-import command. The existing canonical package importer remains
v1/P-GOOGL-only; a later import milestone must explicitly extend its validated
identity and revision workflow before v2 packages can be previewed or accepted.

## Onboarding another model

1. Establish exact company, security, listing and currency identity from
   reviewed canonical evidence.
2. Audit the worksheet's input and output formulas. Do not rely on tab-title
   similarity or an XLSX calculation cache.
3. Confirm that the existing native DCF schema and engine represent the source
   economics without changing return semantics.
4. Add a new explicit `DcfModelTemplate` entry with its own template ID,
   mapping version, ranges, minimum dimensions and signature cells.
5. Reuse or add a deterministic source mapper only when its mapping is
   independently parity-backed. Keep return method, units and currency exact.
6. Add a source-fixture capture/replay test proving projections and published
   outputs reconcile with the existing engine, plus unsupported-layout and
   source-change tests.
7. Add the model key only after its source contract and parity review pass.

Never add financial values, captured packages, company-specific assumptions or
source workbook contents to the template registry or tests.
