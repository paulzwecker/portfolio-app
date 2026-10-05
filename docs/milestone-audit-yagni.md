# Milestone audit and YAGNI pass

Audit date: 2026-10-05  
Scope: Milestones 0 through 2A, including the controlled workbook import. Milestone
2B and later work was reviewed only as roadmap context; it was not implemented.

## Overall assessment

The milestones are implemented to their documented boundaries. ?Complete? here does
not mean that missing ranking inputs, unsupported market listings, FX, or model outputs
have been fabricated. Milestone 1C correctly stops at durable ranking definitions,
source observations, and explicit availability states. Milestones 1D and 2A are
canonical for the records and exact identities that reconcile, while surfacing source
coverage gaps.

| Milestone                                 | Audit result                                                              | Evidence and boundary                                                                                                                                                                                                                                                                                                                                                                  |
| ----------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0 ? platform foundation                   | Achieved                                                                  | Next.js, FastAPI, local PostgreSQL configuration, SQLAlchemy/Alembic, generated contracts, app shell, and environment checks are present. Historical clean source-copy setup and startup verification are recorded in `verification.md`; current API readiness and schema are healthy.                                                                                                 |
| 1A ? identity, lifecycle, portfolio       | Achieved                                                                  | Company/security/listing identity, explicit append-only lifecycle, holdings/cash snapshots, and accepted strategic targets are relational and covered by PostgreSQL integration tests. Current values are not inferred without prices.                                                                                                                                                 |
| 1B ? score assessments                    | Achieved                                                                  | Four independent, versioned score definitions and append-only assessments; null/missing states and correction history are covered. The controlled import carries current source assessments only; it does not invent historical score history.                                                                                                                                         |
| 1C ? ranking infrastructure               | Achieved within the requested infrastructure scope                        | Portfolio, Watchlist, and Research remain separate. Runs preserve as-of state and unavailable/excluded/not-migrated results. Numeric ranking calculations remain deliberately unavailable because their canonical inputs are not migrated.                                                                                                                                             |
| 1D ? controlled workbook import           | Achieved for mapped records; source gaps remain                           | Reconciliation reports zero stored-state mismatches for compared records, but returns `RECONCILED_WITH_SOURCE_GAPS`: 219 companies, 90 securities/listings, 214 lifecycle states, 24 holding/cash rows, 16 target allocations, 506 score assessments, and 657 cached rank entries. Workbook observation dates, unresolved mappings and duplicate/malformed rank cells remain explicit. |
| 2A ? market facts and portfolio valuation | Achieved for supported snapshot identities; aggregate remains unavailable | 65,535 daily prices, 71 regime snapshots and two corporate actions reconcile to the cached workbook outputs. The latest snapshot is imported and idempotent. No dated FX series or supported dated prices for two held listings means base-currency total/current weights remain null, as required.                                                                                    |

The detailed source findings are in [`workbook-import.md`](workbook-import.md),
[`market-data.md`](market-data.md), and the machine-readable
[2A reconciliation](reconciliation/market-data-2026-10-05.json). Milestone verification
history is in [`verification.md`](verification.md). The roadmap correctly leaves
canonical model-output ingestion as Milestone 2B.

## YAGNI review

No domain table or behavior was removed. The history, source receipts, explicit
missing-data states, and direct/inverse dated-FX support each serve an accepted
milestone requirement. Combining the two importers or replacing their domain-specific
reports with a generic ingestion framework would obscure meaningful differences
between canonical portfolio state and dated market observations.

The implementation has not added a generic rules/scoring engine, generic event
sourcing, a provider-plugin system, a valuation/model schema, authentication, a broker
ledger, or a chart/table framework ahead of a concrete requirement. The single price
chart remains a small SVG view; current comparisons do not need an additional table
package. The existing `@next/env` dependency is required by `apps/web/next.config.mjs`;
`httpx2` is required by the installed Starlette `TestClient`. The other reviewed web
runtime dependencies are used by the shell, UI primitives, icons, or contract layer.
No dependency removal was appropriate.

One stale browser assertion used old portfolio copy. It now checks the current explicit
coverage wording; this changes no application behavior. The domain query/service
modules have grown as the vertical slices accumulated. Splitting them solely by line
count would add churn; revisit domain-level file boundaries when Milestone 2B adds its
own model-output operations.

## Verification during this audit

- `npm run check`: passed, including lint, format, TypeScript/mypy, 39 Vitest tests,
  62 pytest tests, API/TypeScript contract consistency, and production build.
- PostgreSQL integration selection: 24 passed; Alembic migration tests run from a
  clean schema in the dedicated `_test` database.
- Read-only imported-data browser suite: 18 passed on desktop/mobile; four seed/write
  cases were skipped on the canonical application database. Those four passed in a
  separate demo-seed browser run using a temporary schema in the dedicated `_test`
  database; its fixture server removed the schema on shutdown.
- `npm run db:check`: no new upgrade operations. API readiness reported current schema.
- Reapplying the 2A snapshot returned `ALREADY_APPLIED`; observation counts were
  unchanged.

The source workspace does not contain Git metadata, so this review is saved as a
working-tree document rather than a commit or tracked-file diff.

## Remaining scope

- Numeric ranking generation remains blocked by unmigrated Portfolio Score, Expected
  IRR and Research Sort Key inputs.
- The legacy portfolio import still has unresolved mappings/source errors; details
  remain in its original reconciliation record.
- Market data has no runtime refresh provider or dated FX source. Eleven ready legacy
  listings lack exact application identities, thirteen more source rows are marked
  `NEEDS MAPPING`, three `6146.T` rows conflict with the declared `TYO:6146` symbol,
  and 61 accepted price rows retain `UNSPECIFIED` quality.
- SPYY and the held NYSE TSM ADR have no supported dated prices. The TPE ordinary
  listing is not substituted for the ADR. No current total or weights are reported
  until all holdings and cash can be valued with fresh prices and dated FX.
- No model assumptions, normalized model outputs, valuation engines, Expected IRR or
  execution logic were added. Proceed to Milestone 2B only as an explicit next task.
