# Market data and current valuation

Status: workbook migration and provider-backed market facts are available. The
provider path covers exact, reviewed active listing identities, dated portfolio FX,
daily prices, current quotes and listing-specific dividends/splits. It does not
implement valuation models, Expected IRR, execution recommendations, or ranking
calculations.

## Ownership and schema

`PriceObservation` records one provider observation for an exact application
listing and market session. It keeps the provider close, split-adjusted close,
optional total-return close and volume as exact `NUMERIC` values, together with
currency, provider symbol, adjustment basis, source-quality state and a source-cell
reference. Workbook sessions are stored at UTC midnight; that encoding does not
claim an intraday quote time. Observations cannot be edited or deleted through the
ORM.

`MarketDataBatch` stores the workbook SHA-256, an idempotency digest, source as-of
date, source update text, provider counts and reconciliation report. Re-importing
identical workbook content returns `ALREADY_APPLIED`. New workbook snapshots append
new source rows; they do not rewrite earlier observations.

`CorporateAction` stores listing-specific dividends and splits with effective and
observed times, raw provider cash units/currency, normalized cash amount/currency,
and verification state. Yahoo's historical `close` series is already adjusted for
stock splits (but not dividend reinvestment), so canonical split-adjusted prices do
not have a split applied a second time. Yahoo `adjclose` is retained separately as
the total-return series. Dividend amounts remain explicit action facts; they are not
added to quoted prices or portfolio market value. These source events are all
marked unverified because Yahoo is not an issuer confirmation source. Exact event
replays are idempotent, but amended provider events do not yet have a canonical
supersession chain; review them before using the action history in downstream
cash-flow calculations.

`PriceRegimeSnapshot` stores the documented rolling price measures, computed trend
and correction states, the source's dated regime label, the source quality and the
history/methodology reference. Numeric metrics and trend/correction labels are
recomputed from exact mapped split-adjusted closes and reconciled to the legacy
cached outputs. The broader `Price Regime` classification is retained as an
observed source value because the workbook documentation does not fully specify
every branch. It is not independently recreated by an inferred rules engine.

`FxObservation` is an append-only, exact positive rate with base/quote currencies,
effective and recorded timestamps, provider, source, actor and reason. A rate is
quoted as units of quote currency for one unit of base currency. The portfolio
query may use a direct observation or invert an explicitly observed reverse pair;
it never supplies a default rate. Yahoo Finance supplies explicit EUR crosses for
the currencies in the active/held listing set: AUD, CAD, CHF, DKK, GBP, JPY, SEK,
TWD and USD. Each source symbol is checked for its returned currency and
instrument type. The legacy market-data workbook contains no FX history, so
provider FX cannot be reconciled to a workbook FX series that does not exist.

## Source and repeatable import

The importer reads cached OOXML values from the committed workbook snapshot; it
does not connect to Google Sheets, evaluate formulas or make network requests.
Provider names are retained as provenance. Google Finance and Yahoo Finance Japan
are source-provider labels, not application runtime integrations.

Run the dry-run and review its JSON reconciliation before applying:

```sh
npm run db:import-market-data -- --report market-data-report.json
npm run db:import-market-data -- --apply --report market-data-report.json
```

The importer resolves each workbook `Listings` row through the application's exact
venue, ticker and quote-currency identity, then validates the exact provider symbol
and quote currency on each daily row. It never maps by ticker alone. A blank daily
provider symbol may use the explicit provider-symbol mapping in that exact
`Listings` row; the report records each such fallback. Other symbol mismatches,
unsupported listings and non-ready source mappings remain reported and skipped.

The workbook importer remains a frozen migration adapter. Provider ingestion is a
separate adapter over the provider-neutral contracts in
`portfolio_api.external_data`. `YahooFinanceProvider` currently implements those
contracts using Yahoo chart v8. Its checked-in crosswalk binds each canonical venue,
ticker, currency and security type to an exact provider symbol and verified
exchange/currency/instrument metadata; ticker-only matching is rejected. Provider
requests preserve raw response bytes in compressed `external_raw_payloads` rows,
with provider/schema identity, URL, retrieval time and content hash.

Run a preview, then apply the same repeatable import command:

```sh
npm run db:sync-market-data -- --lookback-days 3650 --report market-data-provider-report.json
npm run db:sync-market-data -- --lookback-days 3650 --apply --report market-data-provider-report.json
```

The default history window is ten years. Later runs begin after the latest accepted
provider daily observation and refresh the current quote; use `--start-date`
deliberately to request a known backfill window. Replaying an identical raw batch is
idempotent for a given normalizer version. The batch records that version
separately, so the same raw response can be deliberately re-normalized by a newer
version without changing the original receipt. Changed observations append
corrections linked by `supersedes` rather than rewriting accepted history. An
already-covered FX provider date is skipped on same-day reruns and will be requested
again on a later date.

Yahoo's raw `close` field is preserved in `provider_close`; for canonical listing
prices it is a split-adjusted, non-dividend-reinvested series. This adapter does
not claim to provide an unadjusted pre-split exchange close because Yahoo's chart
response does not provide one. `split_adjusted_close` is Yahoo's close converted
into the listing's canonical currency/unit. The exact source currency and
multiplier are retained: for example, Yahoo returns Judges Scientific in GBp,
while the listing is GBP, so the provider value is multiplied by 0.01 and both
facts are recorded. `total_return_close` comes from Yahoo `adjclose` and is kept
separate. Yahoo can revise adjusted history after corporate actions; changed price
facts append a superseding observation, and `known_at` queries return the version
available at that time. Duplicate bars for one exchange session are collapsed when
their close and adjusted-close values agree. If volume values disagree, canonical
volume stays null rather than selecting one bar. Conflicting prices for the same
canonical listing/date are rejected and reported.
Current-session partial daily bars are excluded; the current quote is a
distinct observation with the provider's quote timestamp.

The provider series is now eligible for current-price selection under the explicit
query ordering; the source/provider remains on every observation. If two sources
share an effective date, both remain stored. New source corrections are linked by
supersession; query selection favors the reviewed provider tier and only clean
observations. See [external-data architecture](external-data-architecture.md).

Only rows with a positive split-adjusted close are stored. `PASS` and
`PASS - VERIFIED FALLBACK` remain distinct; a blank source quality is retained as
`UNSPECIFIED`. These rows remain visible in history but cannot be used as a current
valuation quote. The current quote is the most recently recorded observation for
the latest market date. A quote is fresh for five calendar days; stale, missing or
quality-check observations remain explicit states.

## Factual price measures

The API recomputes measures using split-adjusted daily closes and completed market
sessions:

- 20-, 50- and 200-session simple moving averages;
- highest close in the latest 252 observations and drawdown from that high;
- distance from each moving average;
- 1-, 3- and 6-month returns using the source's 22-, 64- and 127-observation
  offsets;
- annualized sample standard deviation of the latest 20 close-to-close returns,
  multiplied by `sqrt(252)`;
- trend state from the latest close, 50- and 200-session averages, and 3-month
  return;
- correction state using the documented -5%, -10% and -20% drawdown thresholds.

Insufficient history leaves the affected field null. It is never filled with zero.
The source's broader regime label is shown alongside its source data-quality state
and as-of date.

## Current portfolio valuation

The API multiplies each observed quantity by its listing's fresh split-adjusted
close to produce a native-currency position value. It converts to portfolio base
currency only when a fresh, dated FX observation is effective no later than that
price/snapshot date and is within five calendar days. Holdings and price dates must
also be within five days. A portfolio total, current company weights and allocation
gaps are emitted only when the holdings snapshot is complete and every position and
cash balance can be valued in the base currency. Otherwise the aggregate stays
null and the response identifies the missing listing/cash/FX inputs. A valid
position-level native value may still be displayed.

Market values and current weights are factual context. The accepted target
architecture remains unchanged and separate. No price or currency operation owns
lifecycle, targets, scores, ranks, model inputs or execution decisions.

The Company view shows separate listing quotes, a responsive split-adjusted price
history chart, freshness and price-regime context. The Universe view shows each
supported listing and can filter companies with or without a fresh quote. The
Portfolio view shows listing-level values and only shows a base-currency total,
weights or target gaps when the coverage rules above are satisfied.

## Snapshot reconciliation and gaps

The imported Market Data workbook has SHA-256
`4880ef975d4b36288cede41c14e22d3a012b7dd0b877f2fd0cddc4bee06fc167`; its recorded
market as-of date is 2026-10-01 and its source update text is 2026-10-02 07:14
Europe/Berlin. The importer matched 88 exact application listings, inserted 65,535
daily price observations, 71 regime snapshots and two corporate actions. Price
quality counts are 65,473 `PASS`, one `PASS_VERIFIED_FALLBACK` and 61
`UNSPECIFIED`.

The numeric regime measures reconcile across 852 populated values with zero
differences at `1e-7` tolerance. Trend and correction states reconcile across 142
labels with zero differences. The one supported but short-history 6146 series has
only one accepted row because three Yahoo `6146.T` rows disagree with the explicit
`TYO:6146` history-provider symbol. The source's `DATA CHECK` regime remains marked
as such; source metrics that cannot be independently recomputed are retained only
with that quality flag.

Ten workbook listings with explicit `READY` identity mappings were added as
canonical security/listing records after checking the authoritative Listings rows
and provider exchange metadata. The ten active Watchlist companies still without a
canonical listing have unresolved identity or source mappings and remain excluded;
they are not assigned lookalike securities. The held NYSE TSM ADR uses its own
NYSE listing and Yahoo `TSM` series. The separate TPE ordinary share remains
distinct and is never substituted. The held standalone SPYY ETF uses its exact ETR
listing and Yahoo `SPYY.DE` series. No ADR ratio is inferred.

The provider load supplies fresh quotes and daily history beginning in October
2016 for all 84 reviewed active/held listing identities. The usable range starts
on the first provider observation for each listing; it is not backfilled across
market holidays or earlier gaps. The database contains about 2,600 dated records
per mapped EUR currency cross, beginning in October 2016 for AUD, CAD, CHF, DKK,
GBP, JPY, SEK and USD. TWD/EUR returned only two source observations on one
effective date, so it does not provide useful historical coverage. A reconciliation snapshot is stored in
[`reconciliation/provider-market-data-2026-10-05.json`](reconciliation/provider-market-data-2026-10-05.json).
The accepted provider ingestion receipt, including exact symbols and row counts,
is stored in
[`reconciliation/provider-ingestion-2026-10-05.json`](reconciliation/provider-ingestion-2026-10-05.json).
At the report date, 21/21 Portfolio companies and 61/71 Watchlist companies have
an exact canonical listing and provider series (82/92 active companies overall).
All 22 held positions have fresh prices from their exact listing identities; the
84 selected active/held listings have provider quote and history coverage. Ten
Watchlist companies remain unresolved and are listed in the report rather than
assigned lookalike tickers. The 22 positions and EUR/USD cash are valued using
fresh exact-listing prices and dated FX: EUR 56,580.48 total, with no position or
cash gaps. The positions contribute EUR 52,226.81 and cash contributes EUR
4,353.67. The portfolio total equals the recomputed component sum exactly at
stored precision.

The provider snapshot retains 856 unverified dividend observations and 22
unverified split observations across the selected listings. Yahoo's price history
is already split-adjusted, so those split events are not applied to prices again.
The stored cash actions remain source facts, not issuer-confirmed corporate-action
records. On the 2026-10-01 workbook comparison date, 71 exact-listing closes
overlap: 67 match within 0.0001 native-currency units, 68 within 0.01 and all 71
within 0.10. The largest difference is 0.07001 (APPF); differences reflect
provider price precision/source variation and are reported rather than rounded
into parity. Workbook-cached FX has no effective timestamp and DKK conversion is
implicit, so there is no legacy FX series against which to claim historical FX
parity.

The full machine-readable workbook import/reconciliation result is stored in
[`reconciliation/market-data-2026-10-05.json`](reconciliation/market-data-2026-10-05.json).
