# Native financial-model input migration

The first real model-input batch is limited to the two active tabs with reviewed,
tab-specific native parity fixtures: `P-GOOGL` and `W-TOST`. It imports no other
assumptions and adds no methodology. The source is the frozen
`reference/workbook/Portfolio_Watchlist.xlsx` snapshot with SHA-256
`27f1889a7185e8759486409490db4d52c694f0084d0a914b234a1e251ab78ce9`.

## Repeatable workflow

The CLI reads cached workbook values, maps explicit source cells, verifies the
source hash against the reviewed inventory, resolves the exact company and
valuation listing, recalculates through the canonical deterministic engine, and
compares projections and normalized outputs. It never evaluates workbook formulas
or writes source prices into the market-data domain. The default is a read-only
dry run:

```powershell
npm run db:import-native-models
```

Review `docs/reconciliation/native-model-input-import-2026-10-05.json`. Accept
parity-passing records with:

```powershell
npm run db:import-native-models -- --apply
```

The same command is safe to repeat. The source workbook hash, tab key and mapping
version identify the imported record; a stable external revision ID and input
digest prevent a duplicate accepted revision. An identical repeat reports
`ALREADY_IMPORTED`; a changed digest for an existing import key is blocked for
review. A later workbook snapshot or reviewed mapping version can be imported as a
distinct revision after its parity checks pass.

Each accepted native model records the exact listing identity and model currency,
the source workbook/hash/tab and mapped source references, the acceptance-time
revision timestamp, deterministic projections and normalized outputs. The workbook
has no reliable effective date, so the accepted time is not presented as the
workbook's historical effective date. The append-only
`financial_model_migration_assessments` record stores mapping version, source hash,
input digest, status and the detailed comparison report.

## First-batch result

| Tab       | Lifecycle | Native method                        |              Listing | Projection checks | Output/return checks | Status        |
| --------- | --------- | ------------------------------------ | -------------------: | ----------------: | -------------------: | ------------- |
| `P-GOOGL` | Portfolio | 10-year secular-growth-fade UFCF DCF | GOOGL · NASDAQ · USD |             30/30 |                22/22 | `PARITY_PASS` |
| `W-TOST`  | Watchlist | 10-year owner-cash-flow              |    TOST · NYSE · USD |           123/123 |                22/22 | `PARITY_PASS` |

All 197 comparisons pass using the report's recorded per-comparison tolerance. The
GOOGL projection set compares discounted UFCF rows across Bear/Base/Bull and the
three scenarios' years 6–10 cash flows. TOST checks scenario revenue, owner cash
flow, per-share values, present values, terminal values and its normalized
valuation/return stream. The report includes source sheet/cell, actual and expected
values, absolute difference and tolerance for every check.

The legacy workbook snapshot has no trustworthy effective date. Its cached price
cells (GOOGL USD 343.50 and TOST USD 29.79) are used only to reproduce the source
return calculations and are explicitly tagged `PARITY_ONLY_NOT_STORED_AS_MARKET_DATA`.
Accepted model outputs recalculate from the canonical exact listing price facts.
At acceptance, both listings had a fresh 2026-10-01 observation under the
application's five-day freshness rule (GOOGL USD 338.24; TOST USD 29.23). These
prices can change independently of the imported model revision; they do not alter
the source parity receipt.

The parity assessment and current output availability are distinct. A source
comparison may pass even if a later canonical price becomes stale or unavailable;
then price-dependent outputs remain null with the current data-quality reason.
Tests use isolated databases without prices and assert that those outputs remain
partial and null.

The workbook's GOOGL `Expected Cash-Flow IRR` is an enterprise UFCF and terminal
value return against implied enterprise cost. It is preserved for legacy parity
and is not the canonical probability-weighted shareholder-distribution IRR.
TOST's owner-cash-flow return stream also does not prove that every modeled owner
cash-flow amount is a guaranteed distribution. Neither method is silently
relabelled. A future methodology bridge requires separate evidence and approval.

The report is from an applied run and records both accepted model/revision IDs and
the successful idempotent replay (`ALREADY_IMPORTED` for each tab). Current
inventory coverage is 1 of 21 Portfolio model tabs and 1 of 71 Watchlist model
tabs, or 2 of the 92 active model tabs. Those are the only two tabs currently
marked ready for native input import, so the first ready batch is 2 of 2.

## Deferred and blocked population

No candidate in the selected first batch was blocked or partially mapped. Remaining
active tabs stay output-only when a published normalized snapshot exists, and
explicitly unavailable when it does not. The inventory marks 94 of the 96
published output-contract tabs as still lacking native model inputs after this
batch. Eleven tabs have `NOT_MAPPED` output contracts, eight have no contract, and
`W-PLEJD` has an identity/data check. The inventory carries per-tab blockers and
proposed batches; its most useful next group is the active Portfolio DCF cohort
`P-ADYEN`, `P-AMD`, `P-AMZN`, `P-ASML`, `P-BKNG`, `P-CELH`, `P-HIMS`, `P-ISRG`,
`P-MA`, `P-MELI`, `P-MSCI` and `P-MSFT`, after tab-specific mapping and parity
fixtures are reviewed. Keep `P-NVO` out until its Copenhagen listing/currency and
matching price are confirmed. No follow-on group is imported by this milestone.

The Company Explorer's **Model migration status** section distinguishes native
editable revisions and parity issues from imported-output-only, unsupported,
legacy-only and not-yet-imported models. The endpoint is
`GET /v1/companies/{company_id}/model-migration-status`; it reads the reviewed
inventory plus native revisions, parity receipts and output snapshots, without a
workbook runtime dependency.
