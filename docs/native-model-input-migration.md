# Native financial-model input migration

## Scope and source

The repeatable importer reads cached OOXML values from the frozen
`reference/workbook/Portfolio_Watchlist.xlsx` snapshot with SHA-256
`27f1889a7185e8759486409490db4d52c694f0084d0a914b234a1e251ab78ce9`. It never
evaluates workbook formulas or writes source prices into the market-data domain.
Workbook source dates are not trustworthy; new accepted revisions use application
acceptance time and retain the source effective date as unknown.

Only these five tab mappings are enabled for accepted native revisions:

| Tab       | Lifecycle | Native method                        | Listing/model currency | Mapping version             |
| --------- | --------- | ------------------------------------ | ---------------------- | --------------------------- |
| `P-GOOGL` | Portfolio | 10-year secular-growth-fade UFCF DCF | GOOGL · NASDAQ · USD   | `legacy-native-input-v1`    |
| `W-TOST`  | Watchlist | 10-year owner-cash-flow              | TOST · NYSE · USD      | `legacy-native-input-v1`    |
| `P-ASML`  | Portfolio | 10-year secular-growth-fade UFCF DCF | ASML · AMS · EUR       | `legacy-ufcf-dcf-cohort-v1` |
| `P-ISRG`  | Portfolio | 10-year secular-growth-fade UFCF DCF | ISRG · NASDAQ · USD    | `legacy-ufcf-dcf-cohort-v1` |
| `P-MA`    | Portfolio | 10-year secular-growth-fade UFCF DCF | MA · NYSE · USD        | `legacy-ufcf-dcf-cohort-v1` |

The three new mappings share the existing five-year UFCF DCF revision schema and
deterministic engine. They preserve their exact company, security/listing, and
currency links; the importer requires one exact non-demo application listing match.
Mapping versions are per batch so extending the importer does not change the
idempotency keys of the first two accepted revisions.

## Repeatable workflow

The default command performs a read-only dry run and writes the latest batch report:

```powershell
npm run db:import-native-models
```

Review `docs/reconciliation/native-model-input-import-batch-2-2026-10-05.json`.
Accept only the reviewed, parity-passing mappings with:

```powershell
npm run db:import-native-models -- --apply
```

An applied replay is safe. The source workbook hash, tab key, and mapping version
identify an import; a stable external revision ID and input digest prevent duplicate
accepted history. An identical replay reports `ALREADY_IMPORTED`; a changed digest
or an existing model without its receipt is blocked for manual reconciliation.
The report `native-model-input-import-batch-2-replay-2026-10-05.json` records the
verified idempotent replay. The original applied first-batch result remains at
`native-model-input-import-batch-1-2026-10-05.json`.

The importer records source tab/cell references, workbook hash, model currency,
exact application listing ID, effective/recorded timestamps, deterministic
recalculation and an append-only `financial_model_migration_assessments` receipt.
The workbook's cached quote is used only to reproduce source return calculations
and is tagged `PARITY_ONLY_NOT_STORED_AS_MARKET_DATA`. Current application outputs
are recalculated from canonical, listing-specific market observations.

## Applied batch and coverage

The first import accepted `P-GOOGL` and `W-TOST`. This Portfolio DCF sub-batch then
accepted `P-ASML`, `P-ISRG`, and `P-MA`. Each new model reconciles 30 of 30 projection
checks and 22 of 22 normalized-output and return-stream checks. Output comparisons
allow at most `0.0000005`, half a unit at six-decimal source precision; projection
comparisons use `0.0000001`. The detailed values, source references, identities and
application recalculations are in the batch-2 report.

All three new application recalculations had fresh exact-listing prices at import
time and produced complete current outputs. Their source parity receipts remain
separate from those time-varying current outputs.

The active tracked population is 21 Portfolio and 71 Watchlist model tabs:

| Lifecycle        | Native editable | Coverage | Published outputs still output-only |
| ---------------- | --------------: | -------: | ----------------------------------: |
| Portfolio        |         4 of 21 |    19.0% |                                  17 |
| Watchlist        |         1 of 71 |     1.4% |                                  70 |
| **Active total** |     **5 of 92** | **5.4%** |                              **87** |

The total is still modest because readiness requires both safe inputs and
tab-specific parity. Output-contract availability alone is not import readiness.

## Remaining active UFCF DCF screens

The batch-2 report screens the other 11 active UFCF DCF tabs. No assumptions from
these rows were accepted:

| Tabs                                             | Status            | Finding                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------ | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `P-ADYEN`, `P-AMD`, `P-BKNG`, `P-CELH`, `P-MELI` | `DATA_CHECK`      | Five-year projections generally reconcile, but at least one reported return/output check does not. For AMD, the source initial-cost stream uses current market diluted shares (`B25`), while the canonical DCF input uses fully diluted shares (`B24`); preserve both bases until the return bridge is deliberately mapped. |
| `P-AMZN`, `P-HIMS`, `P-MSFT`                     | `DATA_CHECK`      | The source Y6–Y10 UFCF paths do not reconcile to the currently supported fade input. No later-year values are inferred or replaced.                                                                                                                                                                                         |
| `P-MSCI`                                         | `DATA_CHECK`      | The base capex/revenue input at `B21` is `-6.24` and fails canonical input validation. It remains unchanged and unimported.                                                                                                                                                                                                 |
| `P-NVO`                                          | `BLOCKED`         | The model uses DKK per Copenhagen B share, but the exact application listing and matching price basis remain unresolved. No alternate ADR is substituted.                                                                                                                                                                   |
| `W-GEV`                                          | `PARTIAL_MAPPING` | The Base Y10 UFCF growth target is missing at `J24`; the importer does not infer it.                                                                                                                                                                                                                                        |

The batch report records per-cell parity comparisons for mapped candidates and the
source-level reason for candidates that cannot be mapped. `P-ASML`, `P-ISRG` and
`P-MA` are the only new Portfolio DCF rows in this batch with full engine parity.

## Semantic and ownership boundaries

The legacy GOOGL DCF return is an enterprise UFCF/terminal-value return against
implied enterprise cost. The new DCF cohort retains the same source label and
method-specific interpretation. It is not relabelled as canonical shareholder
distribution IRR. A difference in expected-return or terminal cash-flow outputs is
a blocker, not a reason to silently alter methodology.

Native models own only accepted assumptions, deterministic projections and
normalized outputs. They do not set lifecycle, scores, target weights or holdings.
No financial-model schema migration or new valuation methodology was needed for this
batch.

The Company Explorer's **Model migration status** section reads the updated
inventory plus native revision and parity receipts. It shows these accepted rows as
native/editable and retains imported-output-only, blocked and legacy-only states for
the other rows. It remains available at
`GET /v1/companies/{company_id}/model-migration-status`.

## Next migration work

Start the next DCF remediation with `P-AMD`: resolve the source's current-market vs
fully diluted share basis and require all return-stream checks to pass. Then trace
the expected-return and terminal-flow discrepancies in `P-ADYEN`, `P-BKNG`,
`P-CELH`, and `P-MELI`. Review the later-year fade mapping for Amazon, Hims & Hers,
and Microsoft separately. Keep MSCI, NVO, and GEV blocked until their explicit data
gaps are resolved. After the active DCF work, assess the materially different
Portfolio owner-cash-flow variants (`P-CPRT`, `P-MORN`, `P-UBER`) one at a time.

No next batch is implied by this recommendation.
