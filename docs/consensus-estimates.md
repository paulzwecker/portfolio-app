# Canonical consensus estimates

## Canonical observation and time semantics

`consensus_estimate_observations` stores immutable provider-specific forward estimates for
revenue and EPS. Values use `NUMERIC(38,12)`. Annual and quarterly facts retain a
forecast-period label and, when the provider supplies one, the fiscal period-end date.
Revenue uses the provider's reported currency; EPS uses that currency per share.
Estimate mean, low/high range and analyst count stay separate. A missing average is not
stored as zero or as an observation. Missing currency, analyst coverage, or an
inconsistent range is explicit in the data-quality state and reason.

Every row points to an exact company/provider-symbol mapping, optional canonical listing,
raw-response batch, provider record and source reference. Snapshot/observed time is when
the application retrieved the provider response. `period_end` is the forecast fiscal
period end, not the time the estimate was observed. `recorded_at` is the database insert
time. An `as_of` query bounds snapshots; `known_at` additionally bounds observed and
recorded time. The first supported external endpoint returns the provider's present
estimates, so this application can only establish historical consensus prospectively as
it captures responses. It does not backfill earlier point-in-time values from the current
response.

An identical value captured during a later poll is a new dated snapshot. A changed
same-provider value for a fiscal period is appended as `REVISED` and links to the earlier
observation through `supersedes_observation_id`. Batch and observation history cannot be
updated through the application ORM. Replaying the same response with the same observed
time is idempotent.

## Identity and continuity policy

Provider mappings are evidence-backed, append-only assignments with an effective time,
recorded time, optional listing identity, optional reporting currency, and an evidence
reference for both identity and currency. Ticker similarity and listing currency do not
establish provider identity or estimate currency. Mapping the currency requires its own
source reference.

Each company has one canonical consensus stream at a time:

1. Use the effective primary provider mapping when one exists.
2. If that primary has no observations or a fiscal-period gap, return that gap as missing.
   Keep any fallback series visible separately; never fill or blend primary gaps.
3. If no primary mapping exists, select the fallback with the unique lowest priority.
   A priority tie is ambiguous and withholds source selection.
4. Preserve every provider's values and revision history in its own series. Never average
   providers or combine their mean, range, analyst count, or periods into one estimate.

Adding a new source assignment does not rewrite old mapping or observation history. An
`as_of` request resolves the mapping effective on that date, while `known_at` excludes
mappings and observations recorded later.

## Provider adapter and local workflow

The FMP adapter uses the stable annual and quarterly analyst-estimates endpoints behind
the shared `ProviderQuery` / `RawProviderRecord` and `DomainNormalizer` contracts. It
retains the raw JSON response and response hash, then normalizes only forward-period mean,
low/high estimates and analyst counts. Ended fiscal periods are excluded from the
consensus series. FMP's response date is treated only as fiscal period end; retrieval
time is recorded locally. FMP documentation describes annual and quarterly estimates,
revenue/EPS ranges and analyst counts, and explains that estimate revision history depends
on source coverage and access plan: [Financial Estimates API](https://site.financialmodelingprep.com/developer/docs/stable/financial-estimates),
[FMP estimate-history FAQ](https://site.financialmodelingprep.com/de/faqs?code=analyst).

Set `FMP_API_KEY` in the untracked local `.env`. For each issuer, review the provider's
symbol and currency, then record explicit evidence before sync:

```powershell
npm run db:map-consensus-estimates -- `
  --company-id <canonical-company-uuid> `
  --provider-id fmp_estimates `
  --provider-symbol <reviewed-provider-symbol> `
  --role PRIMARY `
  --evidence-source <provider-or-issuer-identity-url> `
  --effective-from 2026-10-05T00:00:00+00:00 `
  --currency USD `
  --currency-evidence-source <filing-or-provider-currency-url>

npm run db:sync-consensus-estimates -- --company-id <canonical-company-uuid>
```

Currency is optional when it cannot be verified; observations still persist with a
`DATA_CHECK` state and null currency. Omitting `--company-id` syncs all current FMP
mappings. No FMP network ingestion runs without `FMP_API_KEY` and explicit mappings.

The legacy importer is deterministic and safe to rerun:

```powershell
npm run db:import-consensus-estimates -- --apply `
  --report docs/reconciliation/consensus-estimates-legacy-2026-10-05.json
```

Omit `--apply` for a dry-run plan. The reconciliation report records the source checksum,
workbook rows, identity gaps and imported observation count.

## Legacy mapping and parity

The importer migrates only the raw forward Revenue FY+1/FY+2 and EPS FY+1/FY+2 cells
from the workbook's append-only `Estimate History` sheet. It excludes formula-derived
Estimate Momentum fields. The single available snapshot is dated 2026-09-12. Its rows
identify ticker/company and forecast horizon but do not establish provider, currency,
analyst coverage or an absolute fiscal period end. Therefore imported facts retain the
relative horizon and exact source cell, have null currency/count/period end, and are
marked `DATA_CHECK` as a legacy fallback baseline. Raw numeric parity is checked exactly;
this is not a claim that the vendor consensus semantics have been reconciled.

The separate `Estimate Momentum` sheet's “12M/6M/3M ago” labels and source notes do not
give a reliable per-value observation timestamp or consistent vendor identity. Those
values are not imported and no historical consensus is reconstructed from them. See the
[machine-readable import report](reconciliation/consensus-estimates-legacy-2026-10-05.json).

## API and Company Explorer

- `GET /v1/companies/{company_id}/consensus-estimates` returns continuity status, selected
  provider stream, separate alternatives, current values by fiscal period and their full
  captured histories. Optional `as_of` and timezone-aware `known_at` parameters support
  point-in-time reads.
- The Company Explorer shows the selected provider's revenue/EPS mean, range, currency,
  period, analyst count, freshness and data-quality reason. Each period expands into its
  append-only snapshots. Other providers stay under a separate source-history disclosure.

Consensus values are external observations. They never write native model assumptions,
financial-model revisions, lifecycle, scores, rankings or targets. Estimate Momentum is
not implemented by this slice.

## Coverage and Estimate Momentum readiness (2026-10-05)

The reconciled legacy snapshot contains 67 nonblank estimate values across 79 company
rows; all 79 workbook tickers resolve through the workbook's exact registry identity, and
the 67 value cells match the imported numeric values. Only 18 companies have at least one
usable estimate cell in this snapshot: 17 of 21 Portfolio companies and 1 of 71 Watchlist
companies. All imported values are `DATA_CHECK`; none has provider, currency,
analyst-count or absolute fiscal-period coverage. The importer has no duplicate accepted
observations on rerun. No FMP provider mappings or FMP observations are configured in the
current database, so primary-provider coverage is zero.

Estimate Momentum is not ready. It needs repeated point-in-time snapshots from an
explicitly selected primary provider, stable future-period identities, sufficient
coverage, and representative legacy comparison. The single legacy baseline is insufficient
to claim historical revision momentum.
