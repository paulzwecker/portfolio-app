# Canonical reported fundamentals

## Domain and source boundary

Reported financial statements are factual observations from a company filing.
`reported_fundamental_observations` stores the normalized facts; it does not store
valuation assumptions or derived ratios. The company is the identity owner for
consolidated statements. A security reference is optional for facts that genuinely
belong to a security. Listing currency is not used to infer reporting currency.

Each value carries its canonical metric and statement, annual/quarterly/instant
period, period start/end, fiscal year/period, filing date, observed and recorded
timestamps, currency and unit, provider entity/source, source filing/concept
provenance, revision context and quality. Exact numeric values use PostgreSQL
`NUMERIC(38,12)`. Raw provider bytes are gzip-retained in the shared
`external_raw_payloads` table, keyed to an immutable `reported_fundamental_batches`
receipt. `company_provider_identifiers` records the evidence and actor for the
operator-verified provider identity crosswalk.

The current canonical observed facts are revenue, gross profit, operating income,
net income, cash and equivalents, current debt, non-current debt, operating cash
flow, capital expenditures and diluted weighted-average shares. Debt components
stay separate; this layer does not calculate a debt total. Balance-sheet values are
period-end instants. Shares remain shares, while money facts preserve their source
currency. Source signs are retained, including for capital expenditures.

Free cash flow is identified in the API as a derived analytic, not a reported fact.
No FCF, growth rate or financial ratio is calculated in this slice. This avoids
silently choosing a source-specific FCF definition or assuming capex sign
conventions. A downstream analytic can be added once its inputs and definition are
specified and its outputs remain distinct from reported facts.

## Provider and mapping

The first adapter is SEC Company Facts, through the provider-neutral shared
`ProviderQuery` / `RawProviderRecord` boundary. SEC CIK mappings are exact, manually
verified crosswalk entries. The importer checks both the ten-digit CIK and SEC
issuer name against the mapping. It never discovers identity from a ticker or a
similar company name. US-GAAP and IFRS standard concepts are mapped through a narrow
explicit allowlist; issuer-extension tags are not inferred as canonical facts.
Unknown standard tags, unsupported periods and skipped year-to-date duration facts
are included in batch reconciliation counters/issues.

For local use, set `SEC_USER_AGENT` to an application label and contact email, for
example `Portfolio Research App analyst@example.com`. Review an SEC issuer page or
filing and record its official name and evidence URL for each mapping. Then run:

```powershell
npm run db:sync-reported-fundamentals -- map `
  --company-id <canonical-company-uuid> `
  --cik <10-digit-cik> `
  --provider-company-name "<SEC issuer name>" `
  --evidence-source "<SEC issuer or filing URL>"
npm run db:sync-reported-fundamentals -- sync --company-id <canonical-company-uuid>
```

Omit `--company-id` on `sync` to request all mapped companies. Network ingestion
requires explicit verified mappings and a contact-bearing SEC user agent. See the
[SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
for the official Company Facts interface and access requirements.

There is no normalized-vendor adapter in this slice. The domain can retain
complementary provider observations without changing its schema, but a provider
must receive an explicit mapping, source priority and reconciliation rules before
it is enabled. SEC facts currently have source priority 10; the reserved normalized
provider tier is 50. These are implementation policy values (recorded with the
normalizer version), not provider fields or a guarantee that every SEC fact is
complete or correct.

## Period, as-of and correction rules

The normalizer classifies durations only when the reported start/end span matches
an annual or discrete-quarter window. Year-to-date durations are not mislabeled as
quarterly facts, and instant balance facts have no fabricated period start. No
currency conversions or unit scaling are inferred. Unsupported or ambiguous
periods remain in raw evidence and reconciliation counts rather than becoming
canonical observations.

Every filing observation is immutable. An exact payload/normalizer replay creates
no new batch or fact rows. A later filing for the same provider concept and period
is appended and linked by `supersedes_observation_id`. If the number changed, the
record is labelled `POTENTIAL_RESTATEMENT` and `DATA_CHECK`; an `/A` filing is
identified as amended. The import does not claim a formal restatement solely from a
changed comparative value. Unchanged later comparative values remain separate
filing evidence. Cross-provider values are never overwritten by SEC values.

Resolution first selects the latest filing in each provider/concept lineage and
then applies source and reviewed concept-alias priority. If equally preferred
facts disagree, the API withholds the selected value and returns `CONFLICT`. A
lower-priority provider disagreement retains the preferred observation while
marking the period `CONFLICT` and exposing both observations. `DATA_CHECK` values
are also explicit. Missing metrics return `NOT_IMPORTED` with null dates and no
numeric value; zero is reserved for an actually reported zero.

`as_of` bounds the fiscal period end and filing date, preventing later filings from
being used for an earlier date. `known_at` additionally limits the observation and
recording timestamps to what the application had actually imported by that time.
Because the SEC endpoint returns current Company Facts history, records are
point-in-time usable only from when the application retrieves them; the importer
does not claim that SEC history was present in the application before that first
retrieval.

## API and Company Explorer

- `GET /v1/reported-fundamental-definitions` returns canonical metrics and declares
  free cash flow as derived.
- `GET /v1/companies/{company_id}/reported-fundamentals` returns coverage, resolved
  periods, source alternatives, provenance, conflicts and optional `period_type`,
  `as_of` and `known_at` filters.

The Company Explorer adds a reported-fundamentals panel with annual, quarterly and
instant views, per-metric current periods, units/currency, filing and provider
provenance, restatement and quality flags, and explicit not-imported states. It
does not compute financial ratios in the browser.

## Coverage and remaining gaps (2026-10-05)

The local canonical database contains 219 companies: 21 Portfolio, 71 Watchlist,
122 Candidate/Drop and 5 without a current lifecycle. There are currently **0 verified SEC CIK mappings
and 0 reported-fact observations**, so coverage is 0/219 overall, 0/21 Portfolio
and 0/71 Watchlist. The source mix is consequently empty: no SEC facts or normalized
provider facts have been imported. The adapter and its synthetic test fixtures do
not count as production data coverage.

The next coverage work is an identity review for active companies, followed by SEC
ingestion and statement-level reconciliation for representative issuers. Main
gaps are: no verified issuer crosswalks yet; non-US private/exchange-listed issuers
may not have SEC Company Facts records; the IFRS allowlist is intentionally narrow;
custom tags and non-standard periods are not mapped; SEC facts alone do not provide
a second source for conflict resolution; and Company Facts response history cannot
reconstruct application knowledge before ingestion. No legacy workbook statement
values were bulk-migrated in this slice.
