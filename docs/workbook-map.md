# Workbook reference map

Status: controlled migration map through Milestone 3D and model-population assessment;
inspected 2026-10-05.
This is a scoped data migration, not workbook-wide reverse-engineering
or financial-model calculation parity acceptance. See [workbook-import.md](workbook-import.md)
and [model-output-ingestion.md](model-output-ingestion.md) for importer operation,
exact transformations, data-quality treatment, and reconciliation.

## Reference artifacts

| Repository path                               | Current treatment                                                                                                                                     | Mapping status                                                                                                                                              |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reference/workbook/Portfolio_Watchlist.xlsx` | Scoped source for universe, lifecycle, holdings, targets, scores, cached ranks, model-output contract/revision history, and one ETF identity mapping. | Selected value/formula caches inspected; workbook observation date is unknown. SHA-256: `27F1889A7185E8759486409490DB4D52C694F0084D0A914B234A1E251AB78CE9`. |
| `reference/workbook/Market Data.xlsx`         | Scoped source for exact listing mappings, daily market prices, corporate actions, quality and price-regime snapshots.                                 | Workbook SHA-256 is recorded in [market-data.md](market-data.md); price facts are ingested by the separate `db:import-market-data` command.                 |

The running application does not read from or write to these files. The importer is
an explicit local command. Explicit user instructions, `AGENTS.md`, `README.md`, and
`docs/` govern ownership and scope. The workbook remains migration evidence only
where a specific domain behavior is being deliberately migrated.

## Ranking semantics inspected

These rules were taken from the indicated canonical `Universe Registry` formulas
and associated visible portfolio/watchlist populations. They establish definition
metadata and population semantics. Cached position observations have now been
imported as described below; the application still does not calculate ranks.

| Concept        | Workbook evidence                                                                                                     | Documented ordering and population                                                                                                                             | Milestone 1C state                                                                                                                                                                                                  |
| -------------- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Portfolio Rank | `Universe Registry!L4`; Portfolio Score in column O; Portfolio view filters positive Current Weight or Target Weight. | Non-empty Portfolio Score descending, ticker ascending for ties. The active decision population includes companies with positive current or target allocation. | Cached source values imported where available: 21 `RANKED`, 5 `INPUTS_UNAVAILABLE`, 193 `NOT_ELIGIBLE`. Portfolio Score and numeric rank generation remain unmigrated; held weights still require market prices/FX. |
| Watchlist Rank | `Universe Registry!M4`; Expected IRR in column P; Watchlist population uses explicit `WATCHLIST` lifecycle.           | Expected IRR descending, ticker ascending for ties. A blank Expected IRR has no rank.                                                                          | Cached source values imported where unique: 57 `RANKED`, 17 `INPUTS_UNAVAILABLE`, 145 `NOT_ELIGIBLE`. Expected IRR/valuation and numeric rank generation remain unmigrated.                                         |
| Research Rank  | `Universe Registry!J4`; Research Sort Key in column Q; Research Universe links to the registry ranking.               | Research Sort Key descending, ticker ascending for ties. A blank key has no rank.                                                                              | Cached source values imported where unique: 72 `RANKED`, 26 `INPUTS_UNAVAILABLE`, 121 `NOT_ELIGIBLE`. Research Sort Key and calculated rank generation remain unmigrated.                                           |

The `Watchlist` sheet's **Portfolio Candidate Rank** in `Watchlist!A4` is a distinct
Fit Tier-first ordering followed by Expected IRR. It must not be substituted for the
canonical IRR-first Watchlist Rank. It is not implemented in this slice.

The import copies cached positive integer positions where the documented source
population has an unambiguous unique ordinal. It does not calculate or reconstruct a
rank. The source has 17 rank-position groups with duplicate cached ordinals despite
the documented ticker tie-break, plus two malformed cells. Every affected entry is
unavailable rather than shifted to a different position. Numeric rank-generation
behavior still requires migration of the documented upstream inputs, source-backed
fixtures, and reconciliation against the workbook.

## Other migrated domains

The controlled importer now maps the following limited sources:

| Domain                                | Authoritative source                                                                              | Boundary                                                                                                                                                                                                                                                |
| ------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Companies and lifecycle               | `Portfolio_Watchlist.xlsx`, `Universe Registry`                                                   | Registry ticker/name and Research Bucket, plus positive current/target membership according to the source lifecycle formula. Blank allocation caches remain null and can leave lifecycle unresolved.                                                    |
| Listings                              | `Market Data.xlsx`, `Listings` rows marked `READY`, plus two exact supported rows in `Price Feed` | TSM local ordinary (`TPE:2330`, TWD) and held ADR (`NYSE:TSM`, USD) remain distinct securities/listings for one company; SPYY remains a standalone ETF. Only complete supported identities import. Model currency is not treated as reporting currency. |
| Holdings                              | `Portfolio_Watchlist.xlsx`, `Current Holdings`                                                    | Native share quantities and separate cash-component balances. Aggregated Cash is excluded to avoid counting native cash twice. No prices, weights, or market values are copied.                                                                         |
| Target allocations                    | `Portfolio_Watchlist.xlsx`, `Target Architecture`                                                 | Explicit company target rows and zero values; no normalization. `RESERVE` remains outside company-target allocation and blocks import if positive.                                                                                                      |
| 10Y Durability and Compounder Quality | Corresponding score sheet, column G                                                               | Current visible assessment, adjacent rationale and source URLs where present. Duplicate summary/detail rows are not interpreted as history.                                                                                                             |
| Execution and Risk                    | Exact `Execution Score` and `Risk Score` rows on scoped per-company tabs                          | Current values only. No rationale is invented where the workbook provides none adjacent to the field.                                                                                                                                                   |
| Standalone ETF                        | `Portfolio_Watchlist.xlsx`, `Price Feed` exact SPYY row                                           | Used only to map the current ETF holding venue/currency. It is a standalone security, not a fictitious company. Its price row is not imported.                                                                                                          |

The importer report records the exact file hashes, mapped counts, source gaps, and
stored-state reconciliation. A workbook does not provide a reliable observation
date, so the importer's observation timestamp must not be cited as the original
effective date. Financial-model assumptions, prices, FX, and model calculations
remain owned by their current workbook/model workflows until separate parity
migrations accept them.

## Consensus estimate history mapping

The `Estimate History` sheet is the only scoped legacy source imported for consensus.
Column A supplies the snapshot date, B the ticker, C lifecycle, D/E Revenue FY+1/FY+2,
and F/G EPS FY+1/FY+2. Only those four raw estimate columns are migrated; formula-derived
Estimate Momentum fields H:R are excluded. The source artifact contains 79 company rows
dated 2026-09-12, of which 18 have at least one estimate and 67 estimate cells are
nonblank. All 79 tickers resolve to the workbook's exact Universe Registry identity.
The 67 imported decimals reconcile exactly to their source cells.

The sheet does not identify a consensus vendor, currency, analyst count, or absolute
fiscal-period end for the relative FY+1/FY+2 horizons. Those values therefore remain
legacy fallback observations with null currency/count/period end and `DATA_CHECK` state.
No Estimate Momentum output is migrated. The separate `Estimate Momentum` sheet has
approximate “12M/6M/3M ago” labels/source notes rather than trustworthy per-observation
timestamps, so it cannot establish point-in-time history. See the
[import reconciliation](reconciliation/consensus-estimates-legacy-2026-10-05.json)
and [canonical consensus policy](consensus-estimates.md).

## Map to record during later migrations

For the selected domain or calculation only, retain:

| Field             | Evidence to retain                                                                                                                                              |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Artifact identity | Original filename and content hash identifying the exact reference version.                                                                                     |
| Time              | Known observation/effective timestamp and its source; unknown timestamps stay unknown. Filesystem timestamps do not establish when financial data was observed. |
| Scope             | Domain, sheet/cell range, inputs, and selected authoritative outputs.                                                                                           |
| Ownership         | Market facts, authored assumptions, calculated outputs, lifecycle decisions, targets, and execution signals.                                                    |
| Semantics         | Units, currency, listing/share basis, formula dependencies, tie behavior, null/error meanings, and ambiguities.                                                 |
| Fixtures          | Representative observed inputs/outputs, including missing-data and edge cases.                                                                                  |
| Reconciliation    | Code module, regression tests, agreed tolerances, discrepancies, and parity status.                                                                             |
| Cutover           | Acceptance evidence, canonical owner, and remaining downstream dependencies.                                                                                    |

No ranking calculation has been migrated. Model-output snapshots reconcile at the
published-output and persistence boundaries only; this is not formula parity. See
[migration.md](migration.md) for the acceptance sequence and [domain-model.md](domain-model.md)
for relational boundaries.

## Milestone 2A market facts

The explicit market-data importer reads `Listings`, `Daily Prices`, `Corporate Actions`, `Price Regime` and `Data QA`. It imports a row only when the Market Data listing resolves to the exact application venue/ticker/currency and its provider symbol matches the explicit history mapping. It retains source quality states, blank quality, corporate-action metadata and the source regime label; it skips unsupported and conflicting rows. The three 6146 Yahoo `6146.T` rows are not silently aliased to `TYO:6146`; only its explicit `TYO:6146` row is retained, and the series remains DATA CHECK.

Numeric rolling price-regime outputs reconciled across 852 values with zero mismatches at 1e-7; computed trend and correction states reconciled across 142 values with zero mismatches. The broad Price Regime category is retained as an observed cached output because the source documentation does not specify its complete branching rule. Exact counts, quality groups, unsupported listing identities and the persisted import report are recorded in [market-data.md](market-data.md).

The market workbook contains no FX history. The Portfolio workbook cached USD/EUR figure has no effective timestamp, and its DKK conversion is implicit; neither becomes an FX observation. Price migration does not migrate valuation models, Expected IRR or ranking calculations.

## Milestone 2B model-output snapshots

`Portfolio_Watchlist.xlsx` exposes model output labels at `Model Contract!A5:A22`,
contract values/labels at each model tab's `AZ3:BA20`, and revision history at
`Model Revision History!A:Z`. Only explicit published contracts are eligible for
current outputs. The importer preserves unavailable and data-check status and
does not reuse stale values under `NOT MAPPED` or missing contract states.

Fair values, probabilities, Weighted Fair Value/Upside, Expected Cash-Flow IRR,
Hurdle, Expected Excess and Forward Fundamental CAGR are imported as cached output
values. The importer does not evaluate or migrate formula dependencies. It checks
the Bear/Base/Bull output cells in `P-GOOGL` (`E4:G4`), `W-HDFC` (`B77:D77`) and
`W-TOST` (`M46:M48`) against `BA4:BA6`, for nine exact Decimal comparisons in
total. Stored values are then reconciled field by field with PostgreSQL.

The workbook contains 97 model tabs labelled `PASS`, 11 labelled `NOT MAPPED`, and
8 with no contract status. One nominally published model, `W-PLEJD`, has a ticker
and contract-layout defect, so it is explicitly `DATA_CHECK` and its numeric
values are withheld. Two model tabs (`P-MELI-SOTP` and `P-SPGI-CIQ`) and one
history row (`TKO`) have unresolved company identities and are withheld. One
history row has a malformed/missing timestamp; it stays unknown. Forty malformed
history numeric cells remain null with source references. Model currency is
documented on 54 tabs and unknown on 62. The full count and issue details for the
exact artifact are stored in
[`reconciliation/model-output-2026-10-05.json`](reconciliation/model-output-2026-10-05.json).

The Milestone 2B output import did not accept model formula parity. Assumptions,
projections, model calculations, and all score/lifecycle/price/rank inputs remain
owned by their separate domains or legacy modeling environment. Legacy-workbook
score history migration is not part of the model-output import.

## Milestone 3A/3D native model parity

Native formula parity currently covers three deliberately selected model types:
the `P-GOOGL` 10-Year Secular Growth Fade UFCF DCF, the `W-TOST` owner-cash-flow
model and the `W-HDFC` residual-income model. Frozen representative fixtures compare
scenario fair values, normalized Weighted Fair Value/Upside, Expected Cash-Flow IRR,
Hurdle, Expected Excess and representative projection values. Each reconciles to
`1e-7`; details and method-specific formulas are in
[financial-models.md](financial-models.md). These fixtures establish three
methodologies, not a complete workbook cutover or batch migration of issuer inputs.

The separate read-only population inventory classifies all 116 `P-` / `W-` tabs by
title-level methodology, registry lifecycle, identity, output-contract state,
currency evidence, assumption-mapping readiness and recommended batch. It imports
no model inputs and does not elevate source contract `PASS` to formula parity. See
[model-migration-inventory.md](model-migration-inventory.md) and its
[machine-readable record](reconciliation/model-migration-inventory-2026-10-05.json).
