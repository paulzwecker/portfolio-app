# Native financial-model input migration

## Scope and source

The repeatable importer reads cached OOXML values from the frozen
`reference/workbook/Portfolio_Watchlist.xlsx` snapshot with SHA-256
`27f1889a7185e8759486409490db4d52c694f0084d0a914b234a1e251ab78ce9`. It never
evaluates workbook formulas or writes source prices into the market-data domain.
Workbook source dates are not trustworthy; new accepted revisions use application
acceptance time and retain the source effective date as unknown.

The initial reviewed batch accepted these five tab mappings:

| Tab       | Lifecycle | Native method                        | Listing/model currency | Mapping version             |
| --------- | --------- | ------------------------------------ | ---------------------- | --------------------------- |
| `P-GOOGL` | Portfolio | 10-year secular-growth-fade UFCF DCF | GOOGL · NASDAQ · USD   | `legacy-native-input-v1`    |
| `W-TOST`  | Watchlist | 10-year owner-cash-flow              | TOST · NYSE · USD      | `legacy-native-input-v1`    |
| `P-ASML`  | Portfolio | 10-year secular-growth-fade UFCF DCF | ASML · AMS · EUR       | `legacy-ufcf-dcf-cohort-v1` |
| `P-ISRG`  | Portfolio | 10-year secular-growth-fade UFCF DCF | ISRG · NASDAQ · USD    | `legacy-ufcf-dcf-cohort-v1` |
| `P-MA`    | Portfolio | 10-year secular-growth-fade UFCF DCF | MA · NYSE · USD        | `legacy-ufcf-dcf-cohort-v1` |

The three batch-2 mappings share the existing five-year UFCF DCF revision schema and
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

At the end of batch 2, the active tracked population was 21 Portfolio and 71 Watchlist model tabs:

| Lifecycle        | Native editable | Coverage | Published outputs still output-only |
| ---------------- | --------------: | -------: | ----------------------------------: |
| Portfolio        |         4 of 21 |    19.0% |                                  17 |
| Watchlist        |         1 of 71 |     1.4% |                                  70 |
| **Active total** |     **5 of 92** | **5.4%** |                              **87** |

The total is still modest because readiness requires both safe inputs and
tab-specific parity. Output-contract availability alone is not import readiness.

## Active UFCF DCF screens at the batch-2 assessment

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

## Next migration work at the batch-2 assessment

Start the next DCF remediation with `P-AMD`: resolve the source's current-market vs
fully diluted share basis and require all return-stream checks to pass. Then trace
the expected-return and terminal-flow discrepancies in `P-ADYEN`, `P-BKNG`,
`P-CELH`, and `P-MELI`. Review the later-year fade mapping for Amazon, Hims & Hers,
and Microsoft separately. Keep MSCI, NVO, and GEV blocked until their explicit data
gaps are resolved. After the active DCF work, assess the materially different
Portfolio owner-cash-flow variants (`P-CPRT`, `P-MORN`, `P-UBER`) one at a time.

No next batch is implied by this recommendation.

## Portfolio native-model coverage batch 3 — 2026-10-09

The local PostgreSQL baseline was 6 of 21 Portfolio companies with native accepted
models. This batch accepted exactly three new model/revision pairs and left the
previous accepted revisions unchanged:

| Tab    | Company     | Exact valuation listing | Model/revision input mapping     | Return methodology            |
| ------ | ----------- | ----------------------- | -------------------------------- | ----------------------------- |
| P-AMZN | Amazon      | AMZN · NASDAQ · USD     | Explicit UFCF growth, Years 6–10 | UFCF_ENTERPRISE_HMODEL_IRR v1 |
| P-HIMS | Hims & Hers | HIMS · NYSE · USD       | Explicit UFCF growth, Years 6–10 | UFCF_ENTERPRISE_HMODEL_IRR v1 |
| P-MSFT | Microsoft   | MSFT · NASDAQ · USD     | Explicit UFCF growth, Years 6–10 | UFCF_ENTERPRISE_IRR v1        |

The parity-only source report now passes all nine mapped tabs: GOOGL, AMZN, HIMS,
ISRG, MA, MSFT, CPRT, UBER, and Watchlist TOST. For each new model, all 30
projection checks and 22 normalized output/return-stream checks pass. The importer
uses the source's exact Bear/Base/Bull Year 6–10 growth rates from B206:D210.
Amazon and Hims' Expected IRR terminal stream uses Year 10 UFCF plus a Gordon
terminal without the 2.5 terminal-growth premium that their Fair Value formulas
include. Microsoft's return stream includes the premium and retains the standard
enterprise UFCF return definition. These are not converted to shareholder IRR.

The source workbook has no trustworthy effective date. Each accepted revision
uses application acceptance time and retains its source workbook hash/tab/cell
provenance. The batch-3 apply report records three imports; its replay records
zero new imports and four already-imported mapped rows (the three new Portfolio
models and TOST). Existing Portfolio revisions were not duplicated. The detailed
reports are [batch 3 dry run](reconciliation/portfolio-native-model-coverage-batch-3-dry-run-2026-10-09.json),
[apply](reconciliation/portfolio-native-model-coverage-batch-3-apply-2026-10-09.json),
and [replay](reconciliation/portfolio-native-model-coverage-batch-3-replay-2026-10-09.json).

Current Portfolio native-model coverage is 9/21 (42.9%), up from 6/21 (28.6%).
Watchlist remains 1/71 (Toast); total active native coverage is 10/92 (10.9%).
The remaining 12 Portfolio companies without native accepted input revisions
include output-only and still-blocked source models. The existing source inventory
is the 2026-10-05 population snapshot; the newer reconciliation reports carry the
subsequent readiness and acceptance evidence.

The accepted calculations are complete but their exact-listing quotes were stale
at acceptance (2026-10-02). Portfolio Rank's read-only current-input preview has
zero ranked entries: 16 remain DATA_CHECK due incomplete current market weights,
and five companies lack accepted targets. Amazon and Microsoft currently show the
market-weight blocker; Hims has no target. No ranking run was added. No
Execution Pace run exists; each new model's read-only preview is REVIEW because
of incomplete holdings/targets and stale prices. Refreshing canonical market
data and resolving held/target coverage is required before these models become
actionable Portfolio inputs.

### Remaining high-value blockers

- AMD still needs its legacy current-market diluted-share basis reconciled with
  the native fully diluted-share enterprise-cost basis. No share count was
  changed to force parity.
- ADYEN, BKNG, CELH, MELI, and NVO still have source return-stream or output
  differences; NVO remains tied to the exact Copenhagen B listing and DKK.
- MSCI's source base capex/revenue input remains invalid for the current UFCF DCF
  schema; MORN's source hurdle cache remains missing.
- P-SPGI remains a bespoke SOTP model; it is not forced into UFCF DCF.

The next worthwhile migration slice is to resolve AMD's source share basis with
an explicit economic mapping, then revisit remaining return/output discrepancies
individually. Do not batch-import unresolved tabs.

## Watchlist native-model coverage batch — 2026-10-09

Using the reconciled local PostgreSQL database, this batch accepted native
editable owner-cash-flow models for Axon Enterprise (`W-AXON`), Comfort Systems
USA (`W-FIX`), Rubrik (`W-RBRK`) and Veeva Systems (`W-VEEV`). Each maps to its
exact existing common-stock listing and USD model currency: AXON · NASDAQ, FIX ·
NYSE, RBRK · NYSE and VEEV · NYSE. The models retain the shared
`OWNER_CASH_FLOW_EQUITY_IRR` v1 methodology and the reviewed mapping version
`watchlist-owner-cf-2026-10-09-v1`.

The source-price parity checks passed for each new model: 123/123 projections and
22/22 normalized output/return-stream checks. The source layout is preserved,
including Axon's reported net debt at `B18`, which is explicitly sign-converted
to the canonical net-cash convention. FIX's small cached-output rounding
differences use a maximum `0.0000005` comparison tolerance, bounded by half of
the source's six-decimal cached precision; assumptions were not adjusted to
force parity. The complete source-cell comparisons and accepted revision
receipts are in the [parity report](reconciliation/watchlist-native-model-coverage-parity-2026-10-09.json),
[dry run](reconciliation/watchlist-native-model-coverage-dry-run-2026-10-09.json),
[apply report](reconciliation/watchlist-native-model-coverage-apply-2026-10-09.json),
and [idempotent replay](reconciliation/watchlist-native-model-coverage-replay-2026-10-09.json).

The database accepted four new first revisions. Replaying the same import
accepted zero new revisions and recognized all eight mapped, already accepted
source models. The existing Toast revision and all Portfolio revisions were
unchanged. No schema change or workbook date was inferred.

Watchlist native editable coverage increased from 1/71 (1.4%) to 5/71 (7.0%).
Portfolio coverage remains 9/21 (42.9%), so active Portfolio plus Watchlist
native coverage is now 14/92 (15.2%). All five Watchlist-native models use the
same owner-cash-flow equity method/version and USD currency, establishing a
method-comparable cohort. This is not current Expected IRR availability: the
latest exact-listing prices for the four new models are dated 2026-10-02 and
stale under the application freshness policy. Their accepted model outputs
therefore retain null current Expected IRR with `STALE` price status. Toast's
latest quote is also outside the current Watchlist Rank freshness window.

The read-only Watchlist Rank preview after acceptance contains 55
`DATA_CHECK`, 16 `INPUTS_UNAVAILABLE` and zero ranked Watchlist entries. It
does not create a ranking run; the existing immutable v5 run remains historical.
The 55 data checks comprise 31 legacy outputs with unknown currency, 23 with an
unclassified return method, and Toast's stale captured-price reference. The 16
unavailable entries include 12 imported contracts without numeric Expected IRR
and the four new models whose exact-listing prices are stale. Refreshing the
four new prices is necessary, but not sufficient for a rank: the unresolved
legacy methods and currencies still prevent the single-cohort rank from
selecting a population. The new models do not change lifecycle, targets,
holdings, model methodology or execution state.

The following candidates remain deliberately unaccepted:

| Tab     | Assessment        | Reason                                                                                                                                                                                     |
| ------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `W-PME` | `DATA_CHECK`      | All 123 projection checks pass, but only 14/22 normalized outputs match. The source Fair Value/return path still needs an evidenced mapping; the AUD listing and currency remain explicit. |
| `W-GEV` | `PARTIAL_MAPPING` | Base Year 10 UFCF growth is missing at source cell `J24`; no value was inferred.                                                                                                           |
| `W-KXS` | Not mapped        | Its legacy model mixes CAD and USD unit bases. It remains out until an exact economic/currency mapping is evidenced.                                                                       |

Other Watchlist owner-cash-flow tabs remain outside this accepted cohort unless
their layout and methodology are independently mapped and pass the same strict
projection/output parity. The legacy expected-return figures are preserved as
owner-cash-flow equity returns, not relabeled as enterprise UFCF or as a
forecast of actual shareholder distributions.

The next high-value sequence is to refresh prices for the exact AXON/FIX/RBRK/VEEV
listings and continue the reviewed B4 operating-company owner-cash-flow cohort
only for tabs whose exact listing, currency and input layout are confirmed and
whose full source parity passes. This also reduces the unclassified legacy
return population that currently blocks Watchlist Rank. Keep `W-PME` blocked
until its remaining output differences are explained. Defer `W-GEV` until its
missing Base Year 10 source input is authoritatively recovered; its enterprise
return method would also need a documented treatment alongside the equity-return
cohort. No ranking run or further model migration is implied by this batch.

## Milestone 6.3 parity receipt and application-state boundary — 2026-10-06

The current parity-only report is
[`native-model-input-import-2026-10-06.json`](reconciliation/native-model-input-import-2026-10-06.json).
It records six `PARITY_PASS` models (`P-GOOGL`, `P-ISRG`, `P-MA`, `P-CPRT`,
`P-UBER`, and `W-TOST`), ten `DATA_CHECK` rows, and two `PARTIAL_MAPPING` rows.
It records zero imported revisions, zero already-imported rows, and
`canonical_application_state: NOT_QUERIED`. The four Portfolio candidates under
the latest remediation (`P-ISRG`, `P-MA`, `P-CPRT`, `P-UBER`) therefore do not
represent four new database revisions: the earlier applied receipt already
contains `P-ISRG` and `P-MA`; only `P-CPRT` and `P-UBER` are new parity candidates.

The prior applied batch and replay remain in the repository as historical
application evidence for `P-GOOGL`, `W-TOST`, `P-ASML`, `P-ISRG`, and `P-MA`.
The latest source assessment classifies `P-ASML` as `DATA_CHECK`; this newer
assessment does not change or delete the earlier accepted revision. A current
database query is still required to establish which accepted revisions are
present today.

Return-method parity is recorded separately from canonical shareholder-return
comparability. The receipt has seven source-method return parity passes and nine
return data checks; all 16 rows with a mapped Expected IRR are marked
`NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR`. The DCF mappings preserve their
enterprise-UFCF return basis and do not relabel legacy values as shareholder IRR.
No assumptions or effective dates were invented, and no revision was applied by
the parity-only run.
