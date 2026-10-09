# Milestone 6.1 — Operational coverage and integrity audit

- Audit date: 2026-10-06
- Evidence cutoff: 2026-10-05
- Scope: 21 Portfolio companies first, then 71 Watchlist companies (92 total).

This is a snapshot-based audit of the checked-in workbook and applied reconciliation receipts through October 5, 2026. The workspace database was not running, so the matrix does not claim a live PostgreSQL read. The full company-level matrix is in [operational-coverage-matrix-2026-10-06.json](reconciliation/operational-coverage-matrix-2026-10-06.json).

## Coverage by domain

| Domain | Portfolio | Watchlist |
| --- | ---: | ---: |
| Exact listing identity | COMPLETE: 21, IDENTITY_MAPPING: 0 | COMPLETE: 61, IDENTITY_MAPPING: 10 |
| Current quote | COMPLETE: 21, STALE: 0, IDENTITY_MAPPING: 0 | COMPLETE: 61, STALE: 0, IDENTITY_MAPPING: 10 |
| Historical daily prices | COMPLETE: 21, IDENTITY_MAPPING: 0 | COMPLETE: 61, IDENTITY_MAPPING: 10 |
| Dated FX (portfolio base EUR) | 8 of 9 required currency crosses have multi-year history; Portfolio valuation VALUED (22/22 positions) | Same FX source coverage; TWD/EUR has 2 observations and is DATA_CHECK |
| Corporate actions | DATA_CHECK: provider actions are unverified | DATA_CHECK: provider actions are unverified |
| Reported fundamentals | 0/21 | 0/71 |
| Consensus history | DATA_CHECK: 17/21; primary-provider coverage 0 | DATA_CHECK: 1/71; primary-provider coverage 0 |
| Filings/source documents | 0/21 | 0/71 |
| Published normalized model outputs | 21/21 | 71/71 |
| Accepted native models | 1/21 | 1/71 |
| Model currency/listing comparability | COMPLETE: 1, DATA_CHECK: 20 | COMPLETE: 1, DATA_CHECK: 59, IDENTITY_MAPPING: 10, METHODOLOGY_MISMATCH: 1 |
| Expected IRR values with comparable method | 21 published, 0 comparable | 59 published, 0 comparable |
| Strategic targets | 16/21; 5 absent | NOT_APPLICABLE |
| Cached source rank positions | 21/21 | 57/71; 14 unavailable |
| Canonical recalculated ranks | 0/21 calculated; 21 unavailable | 0/71 calculated; 71 unavailable |
| Estimate Momentum / Execution Pace | 0/21 / 0/21 | 0/71 / 0/71 |

Current quote observations are dated October 5, within the documented five-day window as of the audit date. No active listing quote is classified STALE. `6146` retains a legacy source-regime DATA_CHECK; that does not override the provider-backed daily price series. Corporate-action events are counted in aggregate (856 dividends and 22 splits), but the receipts do not give per-company action coverage and all captured events are unverified.

## Biggest blockers

1. **Return comparability:** 80 active tabs publish an Expected Cash-Flow IRR, but 0 are certified under one comparable shareholder-cash-flow method. The DCF, owner-cash-flow and financial-company return conventions differ.
2. **Company facts and source documents:** there are no reviewed SEC CIK mappings, reported-fundamental observations or source-document rows in the latest recorded state.
3. **Native model coverage:** only GOOGL and TOST have accepted native inputs with tab-specific parity. The other 90 active outputs are legacy output-only.
4. **Watchlist identity:** ten Watchlist companies lack exact canonical listings: ACLN (Accelleron Industries), BONEX (BONESUPPORT Holding AB), EXENS (Exosens), FN (Fabrinet), IVSO (INVISIO AB), MEDI (Medistim ASA), META (Meta Platforms), NVMI (Nova Ltd), RHM (Rheinmetall AG), V1NC (VINCORION SE). That blocks price, FX, filing and model/listing joins for those companies.
5. **Estimates and momentum:** 18 companies have one legacy estimate snapshot dated September 12 (24 days before this audit; no freshness SLA is defined); all 67 values are DATA_CHECK, primary-provider coverage is zero, and one snapshot cannot establish Estimate Momentum.
6. **Ranking inputs:** cached source positions exist, but no canonical rank calculation is generated. Portfolio Score is unmigrated; Watchlist expected returns are missing or method-incomparable.
7. **Target completeness:** five Portfolio companies have no explicit strategic target allocation. No zero target is inferred.

## Highest-leverage remediation batches

1. Resolve exact listing identities for ACLN (Accelleron Industries), BONEX (BONESUPPORT Holding AB), EXENS (Exosens), FN (Fabrinet), IVSO (INVISIO AB), MEDI (Medistim ASA), META (Meta Platforms), NVMI (Nova Ltd), RHM (Rheinmetall AG), V1NC (VINCORION SE) from issuer/exchange evidence, then add reviewed provider crosswalks. This removes a shared upstream blocker for prices, source mapping and currency comparisons.
2. Map primary filing/fundamental sources for active Portfolio companies by jurisdiction, beginning with exact legal issuer identities and evidence. Use SEC CIKs only where applicable; record unsupported jurisdictions explicitly.
3. Establish a common return-method bridge on representative DCF, owner-cash and residual-income models before comparing IRRs. Then review the active Portfolio DCF cohort and separate financial/bespoke methods under their own parity batches.
4. Select one consensus provider, map provider continuity and currency/listing identity, then backfill repeated point-in-time estimates for Portfolio first. Keep Estimate Momentum unavailable until sufficient history exists.
5. Review explicit targets for the five Portfolio companies without one. After Portfolio Score and comparable Expected IRR inputs are accepted, produce versioned Portfolio/Watchlist rank runs.
6. Resolve the model/listing currency bridge for SPOT (EUR model / USD listing), backfill TWD/EUR history, and review issuer-confirmed corporate actions before local-ordinary TSM comparisons or action-driven shareholder returns.

## Expected usability impact

The Portfolio can currently value its recorded holdings in EUR and has a published normalized model output for every active Portfolio company. Decision use is still constrained by non-comparable returns, only one accepted native model, absent reported facts/filings, and five missing strategic targets. The Watchlist has published outputs for all 71 companies, but ten lack canonical listings, 12 tabs (ABNB, AFRM, APP, CRWD, DASH, DYVOX, HUB, MIPS, MMYT, MPWR, SE, SECT-B) lack an Expected Cash-Flow IRR, none has a return certified as comparable, and only TOST is native. The identity and source-data batches would improve factual research coverage; the return bridge and rank-input work would improve decision ordering. Estimate Momentum and Execution Pace remain unavailable across both populations.

## Verification and unresolved data quality

The matrix generator checked workbook hashes against the applied model-output and estimate receipts, validated the 21/71 active scope, and joined model, estimate and listing data by exact registry ticker. Applied receipts report model output persistence reconciliation over 2367 values with 0 mismatches, and portfolio valuation reconciliation VALUED with 0 gaps.

Unresolved quality issues are the ten Watchlist listing identities; 51 active output contracts with undocumented model currency; the SPOT (EUR model / USD listing) model/listing currency mismatch; legacy model effective dates unavailable; method-specific IRR semantics; 67 consensus values lacking provider/currency/absolute periods; TWD/EUR history limited to two observations; and unverified corporate actions. No remediation or next milestone was started.

## Rebuild

```sh
node scripts/uv.mjs run --locked --project apps/api --no-sync python -m portfolio_api.coverage_audit --audit-date 2026-10-06
```
