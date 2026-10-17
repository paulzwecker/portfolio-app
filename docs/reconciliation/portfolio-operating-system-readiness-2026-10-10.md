# Portfolio Operating System Readiness Review

**Review date:** 2026-10-10 (Europe/Berlin)  
**Canonical store reviewed:** local PostgreSQL  
**Result:** **NOT_READY**

## Decision

The application is operational enough to inspect canonical state, edit and recalculate a supported model, and produce repeatable research-rank results. It cannot yet reliably support regular Portfolio and Watchlist decisions: only 5 of 21 held-company quotes are fresh, current portfolio weights are unavailable, no Portfolio or Watchlist company is ranked, and all Portfolio Execution Pace states require review. The local provider refresh failed without inserting observations; no fallback or fabricated data was used.

The machine-readable evidence, including detailed layer counts and workflow results, is in [portfolio-operating-system-readiness-2026-10-10.json](portfolio-operating-system-readiness-2026-10-10.json).

## End-to-end findings

| Layer                            | Readiness evidence                                                                                                                                                                                                                                                        | Result                                                                                               |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Identity and lifecycle           | 219 companies; 21 Portfolio, 71 Watchlist; 5 companies lack current lifecycle. Portfolio exact held listings are mapped 21/21. Watchlist exact listing mappings are 61/71.                                                                                                | Portfolio identity is usable; Watchlist gaps remain.                                                 |
| Market facts and FX              | 284,876 daily prices, 20,830 FX observations, 880 corporate-action observations. Only 5/21 held-company quotes are fresh; 16 are stale. Required portfolio FX pairs are mapped and dated through 2026-10-09.                                                              | Portfolio valuation is `INCOMPLETE_PRICE_COVERAGE`. Corporate-action observations remain unverified. |
| Provider operations              | FX worker is fresh. Market, corporate-action, fundamentals, filings, and consensus workers have unknown freshness; no daily schedule is configured. The exact-listing CPRT refresh was attempted twice and outbound connections were refused; zero records were inserted. | Current ingestion cannot be relied on as a regular operating process.                                |
| Fundamentals and filings         | No reported-fundamental observations, source documents, or SEC CIK mappings.                                                                                                                                                                                              | Not operational.                                                                                     |
| Consensus and Estimate Momentum  | 67 legacy observations exist, all marked `DATA_CHECK` and dated 2026-09-12; no primary-provider observations or company momentum signals are available.                                                                                                                   | Not operational for decision use.                                                                    |
| Models and return interpretation | Native editable models exist for 9/21 Portfolio and 5/71 Watchlist companies. Return history has 273 points, but 222 methods are unclassified and 259 points lack retained share-price basis.                                                                             | Useful supported cohorts exist; broad cross-company/historical comparison remains limited.           |
| Portfolio construction           | 16/21 companies have explicit target rows. Current weights are unavailable; the holdings snapshot itself is complete and includes a standalone SPYY security and two cash positions.                                                                                      | The target architecture is incomplete for current allocation analysis.                               |
| Decision layers                  | Portfolio Rank: 0/21 ranked. Watchlist Rank: 0/71 ranked. Research Rank: 96 ranked, 5 unavailable. Execution Pace: 0/21 available; 21 review.                                                                                                                             | Research prioritization works partially; investment and execution decisions are not ready.           |
| UI/API                           | Health, Universe, Portfolio, Watchlist, Attention, and ranking/execution endpoints responded. Desktop/mobile live browser checks passed and the portfolio now exposes standalone holdings and incomplete valuation states.                                                | Inspectable and explicit about missing state, but it cannot supply the missing decision inputs.      |

## Workflow exercises

- **Ingestion:** attempted an exact `NASDAQ:CPRT` refresh. The provider connection was refused (Windows error 10061); the importer reported `PARTIAL`, with zero price, FX, corporate-action, or raw rows inserted. This correctly leaves the prior observations unchanged.
- **Model revision:** in a rolled-back database transaction, recalculated Alphabet’s supported UFCF model from revision 1 into a candidate revision 2. It generated 30 projection rows and complete outputs, including Expected IRR `0.126895355129343155`. Assumptions were identical; the rehearsal revision was not retained.
- **Ranking and execution:** called Portfolio, Watchlist, and Research Rank, plus Execution Pace, twice each against the same transaction state. Entry statuses, reasons, and ordering repeated. All rehearsal writes were rolled back.
- **Historical alignment:** queried Alphabet as of 2026-09-30 with a same-day knowledge cutoff and later outcome cutoff. The query returned `NO_MODEL_FORECAST`, `NO_MAPPING` for consensus, and `NOT_REPORTED` for actuals; it did not create data. A knowledge timestamp later than the forecast cutoff was rejected with HTTP 422. This verifies cutoff enforcement, while available live records do not demonstrate a populated forecast-to-actual comparison.
- **Repeated refresh:** provider retry remained a zero-row `PARTIAL` result. No accepted revisions, holdings, targets, lifecycle, canonical external observations, or decision snapshots from the exercises were retained.

## Targeted fixes made

1. Market-data imports with fetch, mapping, or normalization gaps now report `PARTIAL` and return a nonzero CLI status. A clean no-op can still report `APPLIED`. Regression tests cover partial provider and mapping failures.
2. The Portfolio page now displays standalone positions from the canonical overview, including listing/currency, quantity, quote date/freshness, and valuation state. This makes SPYY visible without changing holdings or duplicating valuation logic.
3. Live desktop and mobile E2E expectations now test current explicit missing/freshness states instead of stale fixed-value assumptions.

## Blockers and priority

1. **Restore reliable market-data operation.** Outbound access to the configured provider was refused; 16 held-company quotes are stale and no routine daily schedule is configured. Restore the machine/network provider path, run the documented exact-listing ingestion cycle, then confirm fresh dated quotes and ledger entries before recalculating decisions.
2. **Complete authored Portfolio targets.** AMD, Celsius Holdings, Hims & Hers, MSCI Inc., and Novo Nordisk have no target row. Obtain documented target evidence and record explicit values; do not infer zero.
3. **Re-establish decision coverage from canonical inputs.** Once price and target gaps are resolved, refresh model reference prices and rerun Portfolio Rank and Execution Pace using the existing decision workflows. Portfolio Rank is currently blocked by 16 incomplete weights and 5 absent targets.
4. **Resolve Watchlist identity and return metadata.** Ten Watchlist companies lack exact listing mappings; 23 legacy methods are unclassified, 31 legacy currencies unknown, and 12 legacy outputs lack numeric Expected IRR. Resolve from source evidence and retain enterprise/equity distinctions.
5. **Operate primary source pipelines.** SEC mappings, `SEC_USER_AGENT`, provider estimate mappings/`FMP_API_KEY`, and the regular worker schedule are absent. Configure these before expecting filing, fundamentals, or Estimate Momentum coverage.
6. **Improve historical return evidence prospectively.** Preserve missing share-price bases, method classifications, and event dates as missing. Capture them with future accepted revisions and observations; do not reconstruct unsupported history.

## Verification

- `npm run db:check`: passed; no schema drift.
- `npm run check`: passed; lint, formatting, web typecheck, strict API typing, frontend tests (87), API tests (226), contract checks, and production build.
- `npm run test:integration`: passed; 43 PostgreSQL-backed tests.
- Live desktop/mobile Playwright: 6 passed, including real frontend → API → PostgreSQL flows, explicit incomplete portfolio valuation, and distinct TSM listing identities.
- Live API/database workflow rehearsal: passed for health, model recalculation, repeated decision computation, and temporal cutoff rejection; writes rolled back.
- `git diff --check`: passed.

The review did not start the Research/Thesis phase.
