# Legacy financial-model migration inventory

Assessment date: 2026-10-05. The machine-readable, per-tab inventory is
[`reconciliation/model-migration-inventory-2026-10-05.json`](reconciliation/model-migration-inventory-2026-10-05.json).
It describes the committed `Portfolio_Watchlist.xlsx` snapshot (SHA-256
`27f1889a7185e8759486409490db4d52c694f0084d0a914b234a1e251ab78ce9`). The
workbook does not record a trustworthy effective date.

The inventory contains 116 `P-` / `W-` model tabs alongside 219 registry companies.
It records source population, identity, lifecycle, currency, output-contract and
per-tab readiness evidence; accepted application state is recorded separately in
the import assessments and reconciliation reports. The initial two-model import is
at [batch 1](reconciliation/native-model-input-import-batch-1-2026-10-05.json), and
the reviewed Portfolio DCF sub-batch is at
[batch 2](reconciliation/native-model-input-import-batch-2-2026-10-05.json). See
the [import runbook](native-model-input-migration.md) for the safety gates and
current coverage.

## Rebuild and interpretation

The deterministic inventory command reads cached OOXML values from the checked-in
workbook. It does not evaluate formulas, access PostgreSQL, or modify application
state:

```powershell
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.model_migration_inventory `
  --output docs/reconciliation/model-migration-inventory-2026-10-05.json
```

Methodology families are a first-pass classification from each tab's title and
explicit currency/unit labels. They are not a full formula audit or parity
acceptance. `PASS` is only the workbook's normalized-output contract status; it
does not prove that the assumptions fit a native schema. The JSON preserves each
source title, exact/suggested identity, lifecycle evidence, currency evidence,
output status, method family, blocker and recommended batch. The API test rebuilds
the inventory from the exact source snapshot and compares it with the checked-in
artifact.

`READY_FOR_NATIVE_IMPORT` means that the tab's assumptions and methodology have a
representative tab-specific native parity fixture. It does not mean the import has
already happened. Where the original effective date is unknown, a future initial
application revision must use the explicit application acceptance time and retain
the workbook's original effective time as unknown.

## Population and methodology

Lifecycle uses the `Universe Registry` rule: positive current or target weight
means Portfolio; otherwise both cached weights and an explicit recognized research
bucket are required. A `P-` / `W-` tab name is not lifecycle authority.

| Source-title methodology family         |   Total | Portfolio | Watchlist |   Drop | Unresolved lifecycle | Native support                                                                                                               |
| --------------------------------------- | ------: | --------: | --------: | -----: | -------------------: | ---------------------------------------------------------------------------------------------------------------------------- |
| Secular-growth-fade UFCF DCF            |      24 |        14 |         1 |      9 |                    0 | DCF family exists; `P-GOOGL`, `P-ASML`, `P-ISRG` and `P-MA` have tab-specific parity proof.                                  |
| Owner-cash / owner-earnings             |      74 |         6 |        58 |      8 |                    2 | Owner-cash family exists; only `W-TOST` has tab-specific parity proof. Financial/business variants need separate review.     |
| Residual income                         |       2 |         0 |         0 |      2 |                    0 | Native residual-income family exists; `W-HDFC` has parity proof but is Drop. `W-SOFI` is also Drop and is not parity-proven. |
| SOTP or SOTP hybrid                     |       3 |         1 |         0 |      0 |                    2 | No native SOTP method. `P-SPGI` is the active exact-identity example; the two component tabs lack exact identity.            |
| Other / method not established by title |      13 |         0 |        12 |      0 |                    1 | No shared native method can safely be inferred from the tab label.                                                           |
| **Total**                               | **116** |    **21** |    **71** | **19** |                **5** |                                                                                                                              |

The method families describe tab labels, not necessarily identical formula
architectures. The 74 owner-cash/earnings titles include financial, credit, banking,
brokerage, insurance and asset-manager businesses whose economics are not the
supported Toast model. The inventory separately flags 10 unsupported active
specializations: `W-AFRM`, `W-ARES`, `W-BAM`, `W-CSU`, `W-HOOD`, `W-IBKR`, `W-JDG`,
`W-KNSL`, `W-NU` and `W-PLMR`. `P-SPGI` is the eleventh active unsupported method
case because its published model combines a RemainCo DCF and linked SOTP.

Five active tab-specific fixtures prove native parity: `P-GOOGL`, `P-ASML`,
`P-ISRG`, and `P-MA` (Portfolio), plus `W-TOST` (Watchlist). These are
`READY_FOR_NATIVE_IMPORT`; the first controlled import and the later DCF sub-batch
are recorded separately in the [migration runbook](native-model-input-migration.md)
and their reconciliation artifacts. `W-HDFC` remains a parity-proven method example
but `LEGACY_ONLY` while lifecycle is Drop.

## Output contract and readiness

| Current normalized-output state | Tabs | Interpretation                                                                                                                       |
| ------------------------------- | ---: | ------------------------------------------------------------------------------------------------------------------------------------ |
| Published                       |   96 | Workbook contract status is valid and the source ticker/layout checks pass. This is output availability, not native input readiness. |
| Data check                      |    1 | `W-PLEJD` says `PASS`, but `BA3` contains `272.75` instead of `PLEJD`; its cached allocation fields also leave lifecycle unresolved. |
| Not mapped                      |   11 | All 11 are currently Drop. Keep the source outputs unavailable.                                                                      |
| No contract                     |    8 | Six are Drop; `P-MELI-SOTP` and `P-SPGI-CIQ` are separate unresolved component tabs.                                                 |

The current contract therefore has 97 raw `PASS` labels, but only 96 published
rows pass the importer's identity/layout checks. Five active tabs are ready for
native input import. Do not use the output `PASS` rate as a coverage or readiness
measure.

The output contract explicitly documents model currency on 54 tabs and leaves 62
unknown. A separate source-unit review finds a single currency in the model's
Unit/Basis cells (or an explicit model-currency statement) on 106 tabs; 10 remain
ambiguous or undocumented in the model body. The source-unit review does not
rewrite the output-contract currency state. Among resolved active Portfolio and
Watchlist tabs, 51 output contracts still have unknown currency metadata, although
most have a single explicit source unit to map. Eight active tabs still lack a
single currency assignment under the inventory rule; three of those have mixed
currency signals in Unit/Basis cells (`W-KXS`, `W-MMYT` and `W-ONON`).

Source blockers to resolve or retain explicitly:

- `P-MELI-SOTP` has a title suggesting MercadoLibre, but no exact registry identity;
  do not attach it to `MELI` by suffix or name alone.
- `P-SPGI-CIQ` has no exact company/component identity, published contract or
  identified currency. Confirm whether it is a linked SPGI component before mapping.
- `W-PLEJD` has a ticker/layout mismatch (`BA3=272.75`) and unresolved cached
  lifecycle. Its title says Watchlist, but that does not repair the registry gap.
- `W-ARENIT` and `W-ENGCON-B` also have blank cached allocations, so lifecycle is
  unresolved despite model tabs and output contracts being present.
- `P-NVO` is explicitly DKK per Copenhagen B share. Confirm that exact listing and
  matching price; never replace it with the USD ADR without a sourced ADR ratio and
  FX path.
- `W-DLO`, `W-RDDT` and `W-TSM` have `W-` tabs while registry membership resolves
  to Portfolio. Registry lifecycle and exact listing identity take precedence over
  sheet naming. TSM's model states a TWD local-ordinary basis; keep it separate
  from the held USD ADR.
- Output-contract currency remains unknown for `W-TOST` even though its model input
  unit explicitly says USD and its parity fixture uses USD. Preserve both facts
  until the output-contract metadata is repaired.

No tab is marked `NOT_RELEVANT`: the `P-` / `W-` population contains model or
company-research material. Dropped rows are `LEGACY_ONLY`, not deleted or treated
as current migration targets.

## Expected-return semantic boundary

The canonical application definition is an IRR over probability-weighted explicit
shareholder cash flows. It does not average scenario IRRs; dividends are explicit
cash flows and terminal proceeds remain separate. Legacy output labels do not
guarantee that definition:

- The `P-GOOGL` reference solves a probability-weighted enterprise UFCF and
  terminal-value return against the implied enterprise cost. It is not a
  shareholder-distribution IRR.
- Owner-cash tabs calculate returns from their own owner-cash-flow assumptions and
  terminal conventions; do not assume every modeled owner-cash dollar is an
  explicit shareholder distribution.
- Residual-income and other financial-company tabs may report an implied equity
  return using dividends and terminal equity value.

Preserve each legacy value, label, methodology and source as observed. Do not
recompute historical values or silently relabel them as canonical shareholder
cash-flow IRR. Add a method-specific bridge and fixture before comparing or
replacing them with the canonical definition.

## Recommended migration order

1. **Completed:** `P-GOOGL` and `W-TOST` were imported first; a reviewed Portfolio
   UFCF DCF sub-batch then imported `P-ASML`, `P-ISRG` and `P-MA`. All accepted
   workbook source dates remain unknown and revisions use application acceptance
   time.
2. Resolve identity, lifecycle and source data checks: the SOTP/component identities,
   `W-ARENIT`, `W-ENGCON-B` and `W-PLEJD`. These are prerequisites, not invented
   assumption imports.
3. Continue the active DCF work from the [batch-2 screening report](reconciliation/native-model-input-import-batch-2-2026-10-05.json).
   `P-ADYEN`, `P-AMD`, `P-AMZN`, `P-BKNG`, `P-CELH`, `P-HIMS`, `P-MELI`,
   `P-MSCI` and `P-MSFT` have explicit parity or input-data failures under the
   current engine; `W-GEV` lacks a required Base Y10 UFCF growth target. Hold `P-NVO`
   for exact listing/currency confirmation. Do not import these until their
   tab-specific blocker is resolved and parity passes.
4. Map the six active Portfolio owner-cash variants independently:
   `P-CPRT`, `P-MORN`, `P-UBER`, `W-DLO`, `W-RDDT` and `W-TSM`. These are not all
   interchangeable with the Toast model.
5. Prove the first active SOTP for `P-SPGI`; retain the two unresolved SOTP tabs
   until exact component identity is known.
6. Review remaining active Watchlist operating-company owner-cash models in small
   currency/layout cohorts, then choose one active financial or bespoke model at a
   time (bank, broker, insurer/asset manager, serial acquirer) for any new native
   methodology work.
7. Leave all 19 Drop models `LEGACY_ONLY` unless an explicit lifecycle change
   reopens them.

The JSON inventory records exact batch membership and per-tab blockers. This is a
recommendation only; no following batch is implemented automatically.
