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

### Statement-period identity

SEC `fy` and `fp` describe the filing's reporting context. They are not a reliable
standalone identity for the economic period of a comparative fact: a later 10-K can
repeat the prior year's value while carrying the later filing year. Statement views
therefore group by the economic period bounds and retain all filing-context labels in
the source history. A fiscal column label is emitted only when an eligible
contemporaneous annual or discrete-quarter filing supports it. The implementation does
not infer a fiscal year from a calendar date. This distinction prevents duplicated
columns and misleading relabeling while preserving every correction and alternative
source for audit.

## API and Company Explorer

- `GET /v1/reported-fundamental-definitions` returns canonical metrics and declares
  free cash flow as derived.
- `GET /v1/companies/{company_id}/reported-fundamentals` returns coverage, resolved
  periods, source alternatives, provenance, conflicts and optional `period_type`,
  `as_of` and `known_at` filters.
- `GET /v1/companies/{company_id}/financial-statements` composes the selectable
  statement workspace. Its `period_type` (`ANNUAL` or `QUARTERLY`), bounded
  `period_limit`, `as_of` and `known_at` parameters select unique economic periods
  while retaining the nested source records needed for audit. Reported observations
  sharing metric, statement, duration/instant, period bounds, currency and unit share
  one table cell even when later comparative filings carry different SEC `fy`/`fp`
  context. Direct contemporaneous filing labels are preferred; ambiguous labels are
  left date-only. Balance-sheet instants are included only when their period end is
  aligned with an eligible duration period.

The Company Explorer Financials view uses a selectable metric table and a chart of
selected rows. It keeps reported actuals, provider-continuous consensus and
agent-authored forecasts separate, preserves currency/unit facets, and opens a shared
source drawer for filing corrections and revision history. It does not compute
financial ratios in the browser. Missing, stale, conflicting or unknown-basis values
remain explicit rather than becoming zero or a passing observation.

## Historical coverage snapshot (2026-10-05)

The local canonical database contains 219 companies: 21 Portfolio, 71 Watchlist,
122 Candidate/Drop and 5 without a current lifecycle. There are currently **0 verified SEC CIK mappings
and 0 reported-fact observations**, so coverage is 0/219 overall, 0/21 Portfolio
and 0/71 Watchlist. The source mix is consequently empty: no SEC facts or normalized
provider facts have been imported. The adapter and its synthetic test fixtures do
not count as production data coverage.

At the time of this snapshot, no legacy workbook statement values had been bulk
migrated. Non-US private/exchange-listed issuers may not have SEC Company Facts
records; the IFRS allowlist is intentionally narrow; custom tags and non-standard
periods are not mapped; SEC facts alone do not provide a second source for conflict
resolution; and Company Facts response history cannot reconstruct application
knowledge before ingestion.

## Current operational coverage (2026-10-10)

The current local database has reviewed SEC CIK mappings for 20/21 Portfolio
companies and 7/71 Watchlist companies, but still has **zero canonical reported
fundamental observations**. The unmapped Portfolio company is Adyen: its SEC CIK
record is for a depositary-receipt entity, not the operating issuer's reported
financial statements, so it is not used as a shortcut for its Amsterdam ordinary
listing. See the SEC [Adyen submissions record](https://data.sec.gov/submissions/CIK0001788707.json).

Mapped identifiers were checked against the SEC's [official company ticker and
exchange file](https://www.sec.gov/files/company_tickers_exchange.json) and
issuer filings. Four Watchlist mappings have matching canonical listing identities:
Axon (CIK 0001069183), Comfort Systems USA (0001035983), Rubrik (0001943896) and
Veeva Systems (0001393052). Meta Platforms (0001326801), Fabrinet (0001408710) and
Nova (0001109345) have company-level SEC mappings, but their listing identities
remain unresolved and their prices are not substituted.
EDGAR facts and submissions ingestion is still blocked because a monitored contact
email has not been configured for `SEC_USER_AGENT`. No SEC source rows are claimed
until a live worker run succeeds. The latest counts and run ledger are in the
[Milestone 6.10 operational report](reconciliation/operational-data-activation-2026-10-10.md).

## Milestone 10B coverage and recovery (2026-10-16)

This section is the 10B point-in-time result, captured before Milestone 10F. The
later 10F reconciliation below supersedes its zero-observation and missing-agent
configuration statements; the historical 10B result is retained for audit.

A fresh query of the canonical PostgreSQL database still finds **0 reported facts
and 0 filing records** across the active 21 Portfolio and 71 Watchlist companies.
This is not a normalization or migration failure: the latest persisted SEC runs
for both Company Facts and EDGAR submissions are `BLOCKED / MISSING_SEC_USER_AGENT`
(2026-10-10), and this machine still has no `SEC_USER_AGENT` value. The SEC
adapter remains fixture-tested; there was no live request in this milestone, so
SEC endpoint connectivity is not yet verified. Do not put a fabricated or
unmonitored contact in the user agent. Add a genuine monitored contact to the
ignored local `.env` and then run:

```powershell
npm run db:sync-reported-fundamentals -- sync
npm run db:sync-source-documents -- sync
```

The exact current company-by-company record is
[`canonical-fundamentals-data-recovery-2026-10-16.json`](reconciliation/canonical-fundamentals-data-recovery-2026-10-16.json).
It records before/after coverage, identity and listing status, per-company facts,
filings, consensus provenance, market-price timestamps, and evaluation eligibility.
The 10B before and after counts are equal because no source observations were
written.

There are reviewed CIK mappings for 20/21 Portfolio companies and 7/71 Watchlist
companies. Adyen remains unmapped: the known SEC record is a depositary-receipt
entity, while the canonical listing is the Amsterdam ordinary share. Four of the
seven mapped Watchlist companies have resolved listing identity; the Meta,
Fabrinet and Nova mappings are issuer-level only. There are 57 Watchlist companies
with listings but no reviewed SEC CIK (42 NYSE/Nasdaq listings and 15 non-US
listings), plus 7 companies with no canonical listing. These are mapping-review
work, not permission to infer a CIK from a similar name. The SEC's [official
ticker/exchange crosswalk](https://www.sec.gov/files/company_tickers_exchange.json)
is suitable evidence for exact ticker, exchange and registrant matches; mappings
should be recorded only after confirming all three against the canonical company
and listing. The report lists all affected companies. SEC mapping does not change
the listing's trading currency or the issuer's reporting currency.
All 92 company-level `reporting_currency` values are currently null. Imported
facts still carry the currency/unit actually reported in the source; do not fill
this company attribute from listing currency.

### Historical timestamp integrity

The active Portfolio/Watchlist history has 271,900 daily-close rows from
2016-10-07 through 2026-10-15. Every row has the application's `recorded_at`, and
none has a source `observed_at`. Yahoo's historical bar timestamp identifies the
market session; it does not establish when the provider first made that bar
available. No timestamps were backfilled. All 276 current-quote rows do carry
source and recorded times. A regression test now protects the daily-bar null
observation time, and the temporal-alignment integration test verifies that an
otherwise recorded daily bar with no source time is `DATA_CHECK` and cannot be a
historical return baseline.

The database also contains 67 legacy workbook estimate rows for 18 active
companies, all without a reliable point-in-time observation timestamp. There are
no dated non-legacy provider consensus observations. Those rows remain historical
legacy evidence only; they do not qualify for consensus benchmarking or Estimate
Momentum. No current estimates were backdated into a revision history.

### Non-US primary-source candidates

No non-US adapter or financial fact was added. Source review identified the
following primary-document candidates for a later source-specific ingestion slice:

- EU issuers: issuer ESEF annual reports and the relevant national OAM, following
  [ESMA's ESEF guidance](https://www.esma.europa.eu/issuer-disclosure/electronic-reporting).
- UK: FCA [National Storage Mechanism](https://www.fca.org.uk/markets/primary-markets/regulatory-disclosures/national-storage-mechanism)
  and issuer annual/interim reports.
- Canada: issuer filings on [SEDAR+](https://www.securities-administrators.ca/national-systems/about-sedar/).
- Australia: [ASX company announcements](https://www.asx.com.au/markets/trade-our-cash-market/announcements.e79)
  and issuer annual/interim reports.
- Taiwan: [MOPS](https://mops.twse.com.tw/?lang=tw) issuer filings; TSMC's mapped SEC
  registrant is a complementary 20-F/6-K source.
- Japan: [EDINET filing data](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WEEK0060.html)
  and issuer reports.
- Switzerland: issuer reports and [SIX official notices](https://www.six-group.com/en/market-data/news-tools/official-notices.html);
  a dated notice is source metadata, not a substitute for statement facts.

Access method, terms, machine-readable format and publication timestamps must be
checked before any adapter is enabled. ESEF is a reporting format, while national
OAMs and issuer/regulator portals provide jurisdiction-specific publication
records; none is treated as one unified API.

### Verification

The fundamental normalizer tests assert exact annual and quarterly period
boundaries, fiscal labels, currencies, units and filing dates. The database
integration tests cover replay idempotence, append-only possible restatements,
supersession, and `known_at` look-ahead limits. See the later Milestone 10F section
for live SEC status and the latest verified counts.

## Milestone 10F issuer identity and live coverage (2026-10-16)

The 12 Company Facts responses rejected in the earlier bounded run were all
verified as formatting-only issuer-name differences. The CIK, SEC submissions
record and official SEC ticker/exchange identity were consistent. The importer
now requires an exact CIK in the response body and an exact mapped CIK/source
record, then permits only Unicode/punctuation/case normalization and equivalent
terminal legal suffixes (`Inc`/`Incorporated`, `Corp`/`Corporation`,
`Ltd`/`Limited`, `Co`/`Company`). Other name stems remain unequal; a historical
rename or parent/subsidiary relationship still needs an explicitly reviewed
identity mapping. No CIK mapping was changed by this fix.

The live Company Facts retry fetched all 27 verified SEC identities. It added
13,426 observations for the 12 newly accepted issuer responses and reused the
13,382 already stored observations. A repeated live replay returned all 27 as
`ALREADY_IMPORTED`, inserted zero observations and kept the total at 26,808. The
run remains `PARTIAL` because the active universe contains 65 companies without a
reviewed SEC CIK and because unmapped standard taxonomy concepts are deliberately
reported as warnings; it had zero response-identity errors and no missing
responses for the 27 mapped issuers.

Current SEC Company Facts coverage is 20/21 Portfolio companies and 7/71
Watchlist companies, with 26,808 observations total. Adyen remains unavailable:
its known SEC identity is a depositary-receipt entity and is not used to stand in
for the canonical Amsterdam ordinary share. Of the 900 `DATA_CHECK` facts, 891
are potential restatements and 9 are changed facts from amended filings. These
append-only observations remain visible for review; none were suppressed to
improve coverage. Fact currencies, units, reporting periods and filing dates
remain source-derived, not inferred from trading listings.

The active reviewed CIK set remains 20/21 Portfolio and 7/71 Watchlist. The 64
other Watchlist companies still need exact issuer mapping before SEC import; the
current list is in the [machine-readable 10F report](reconciliation/issuer-identity-international-filing-coverage-2026-10-16.json).
The related source-document replay reused 5,721 existing filing records for those
27 issuers, imported zero duplicates, and reported zero metadata conflicts,
unlinked amendments and document quality checks. It is `PARTIAL` because 18,721
SEC submission forms are outside the supported document contract, not because
the 5,721 supported filings failed.
