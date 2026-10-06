# Canonical Research Rank

Research Rank answers **what deserves research attention next?** It orders research
work only. It is not an investment-attractiveness score and is separate from
Watchlist Rank, Portfolio Rank, target weight, and Execution Pace.

## Documented Research Sort Key

The `Portfolio_Watchlist.xlsx` source formula uses explicit lifecycle and research
bucket checks, then calculates:

```text
Candidate - High: 200000 - persistent deep-dive priority seed
Candidate - Low:  100000 - persistent deep-dive priority seed
blank seed:       substitute 50000, as the workbook formula explicitly does
```

Only explicit `CANDIDATE` lifecycle companies with an exact `Candidate - High` or
`Candidate - Low` bucket enter the ranked cohort. Higher key ranks first; canonical
registry ticker ascending breaks ties. The persistent seed lives in
`Candidate Ranking!A:B` and is linked by ticker. The source's 50,000 blank-seed
fallback is retained and shown in each applicable input snapshot.

No research-completeness score, expected return, quality score, model status, target,
holding, or Execution Pace is part of this formula. Lifecycle is an eligibility
boundary only; Research Rank never changes lifecycle.

## Canonical inputs and as-of behavior

The focused importer reads only the candidate bucket, candidate ticker, and linked
priority seed. It records the workbook SHA-256 and cell references in an append-only
`research_priority_inputs` record. It does not import Research Universe narratives,
other workbook tabs, cached rank positions, or financial data. Re-running the same
workbook hash is idempotent. A changed workbook hash appends a new source revision.

The workbook does not document when a bucket or seed became effective. The importer
therefore records the real import `recorded_at` time and does not invent an earlier
effective date. A ranking run can use the imported values only if they were recorded
by that run's `as_of` time. `DATA_CHECK` source inputs stay visible without being
ranked; missing lifecycle/bucket evidence remains `INPUTS_UNAVAILABLE`. Non-candidate
lifecycle states are `NOT_ELIGIBLE`.

```powershell
npm run db:import-research-priority                 # dry run
npm run db:import-research-priority -- --apply       # append source inputs
```

The workbook is an import source, never a runtime dependency. The ordinary API and
UI read canonical PostgreSQL state.

## Application coverage and workbook reconciliation

The scoped source scan found 98 Candidate High/Low rows, no duplicate/malformed seed
or bucket rows, and no unresolved company mappings. Nine rows have blank seeds and
use the documented fallback. The idempotent import inserted 98 rows; a replay
inserted zero.

The initial canonical Research Rank run covers 219 companies: 96 ranked, five
`INPUTS_UNAVAILABLE`, and 118 `NOT_ELIGIBLE`. Those five unavailable rows lack
point-in-time lifecycle history, so the system cannot safely decide cohort
membership. Current canonical `CANDIDATE` membership and source bucket/seed remain
separate facts.

The formula reproduces five representative source top ranks (NBIS, PGR, TMUS, CBOE,
TXN) and their cached sort keys exactly. The workbook's cached Research Rank column
is not a reliable full-universe parity target: only 36 of 97 numeric cached ordinal
positions agree with the current documented tier/seed sort, and one additional
cached rank is malformed. For example, cached FICO rank 1 is stale relative to its
current documented inputs (sort key 99,997; recomputed position 25). The application
calculates from the documented source fields, never copies stale rank cells into a
new run. Details are in
[`reconciliation/research-rank-activation-2026-10-06.json`](reconciliation/research-rank-activation-2026-10-06.json).

Universe supports recording and inspecting Research Rank runs; Company shows the
company's current and prior run context. The same endpoints and immutable-run model
can support a future Research Pipeline. No dedicated pipeline workflow or native
bucket/seed authoring form is included yet; source values currently enter through
the narrow, auditable importer.
