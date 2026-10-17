# Free consensus source feasibility — 2026-10-11

## Finding

There is no provider we can currently promote as a permitted, verified primary
source for the application as a general private platform. FMP documents the
richest estimate fields and says its estimate feed contains timestamped
historical revisions, but its published free personal-use terms do not allow
copying/downloading the data into this application's database or displaying it
through an internal/multi-user application without a specific agreement. Alpha
Vantage is the other official zero-price API candidate, but its free license is
also limited to private individual use. Its docs advertise annual and quarterly
Revenue and EPS estimates, analyst counts, and revision history without enough
schema or history detail to verify the fiscal-period, currency, analyst-count,
revision-timestamp, or historical-depth semantics. The demo request did not
return estimate data; it returned the instruction to claim an API key.

If the application is operated only by one individual for that person's own
investment research, Alpha Vantage is a conditional pilot candidate. If it is
used on behalf of a company, partnership, trust, organization, advisor, or other
association, its free terms do not fit; obtain written permission or use a
licensed source. This is an operational assessment, not legal advice.

No source observations were inserted, no canonical provider mapping was added,
and no ingestion schedule was enabled. Current database-backed evidence from
the 2026-10-10 operational report remains 0 primary-provider mappings and 0
primary-provider observations. The existing legacy baseline has 64 Portfolio
and 3 Watchlist values, all `DATA_CHECK` because vendor, currency and absolute
fiscal period are absent. None is a usable point-in-time consensus history.

## Comparison

| Source                                | Public fields and historical depth                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Access, terms and limits                                                                                                                                                                                                                                                                                                                                                          | Identity, period and currency                                                                                                                                                                                                                                                                           | Assessment / effort                                                                                                                                                                                                                                                      |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Alpha Vantage**                     | Official `EARNINGS_ESTIMATES` documentation claims annual and quarterly Revenue and EPS estimates, analyst count, and revision history. No EBIT/EBITDA estimate fields, dated revision schema, historical start date, or point-in-time snapshot guarantee is documented.                                                                                                                                                                                                               | Official API uses a free key; general free use allows 25 requests/day, but endpoint-specific free entitlement is not explicit. The terms limit use to private individual activity and classify use on behalf of an organization as commercial. The terms do not clearly specify rights to retain/redisplay API data in this application's database/UI. No key is configured here. | Request is keyed by provider symbol. Exact venue/security match, reported currency, units, fiscal-year labels and period-end rules still need a payload-level pilot.                                                                                                                                    | **Conditional raw-response pilot** for individual-only use after endpoint entitlement and retention/display rights are clarified. Low effort for one-symbol capture; medium effort to establish mapping, schema and data-quality behavior.                               |
| **FMP**                               | Official endpoint documentation exposes Revenue, EPS, EBIT, EBITDA and analyst counts/ranges; FMP support says its estimate feed retains 10+ years where available and describes historical estimates as revision-based and timestamped. The stable endpoint schema documents the fiscal period date but not an as-of/vintage query contract or a revision timestamp field. The current application adapter only captures current annual/quarter responses and normalizes Revenue/EPS. | Basic advertises 250 calls/day, but the estimates endpoint is marked limited access and free-plan entitlement is not established. FMP's published personal-use terms prohibit copying/downloading without written approval and display through multi-user/internal applications without a specific agreement; organizational use requires appropriate terms.                      | FMP describes estimate currency as the currency reported in the financial statements. Its overall service claims broad multi-exchange coverage, but estimate endpoint coverage and exact listing/symbol matches were not tested. Current local state has no FMP key, mappings or provider observations. | **Best documented field/history potential, but not a compliant free source for this application's canonical storage/display path under the published personal-use terms.** Keep dormant unless FMP gives written storage/display rights and endpoint access is verified. |
| **Yahoo Finance**                     | Web pages display estimate information for some companies, but no official public financial-estimates API was found. No supported point-in-time revision dataset was established.                                                                                                                                                                                                                                                                                                      | Yahoo's current Terms prohibit automated collection from its services without express prior permission. The public chart interface and third-party packages do not grant permission to collect estimate pages.                                                                                                                                                                    | Public pages can be listing-oriented, but automated exact listing, fiscal-period, currency and history reconciliation cannot be relied on or tested here.                                                                                                                                               | **Do not automate.** No adapter or scraping fallback.                                                                                                                                                                                                                    |
| **finanzen.net**                      | Its help center says estimates are among data sourced from FactSet; no permitted public estimate API or historical revision contract was found.                                                                                                                                                                                                                                                                                                                                        | finanzen.net explicitly states that extracting its data is not allowed, including automated extraction through an API and manual copying from the website.                                                                                                                                                                                                                        | Public display does not supply an allowed machine-readable identity, fiscal-period or currency contract for this application.                                                                                                                                                                           | **Do not extract.** No adapter or manual-data import.                                                                                                                                                                                                                    |
| **MarketScreener**                    | Public pages provide financial/market data, but this assessment did not copy or automate their estimate tables. A dated point-in-time history contract was not established.                                                                                                                                                                                                                                                                                                            | Terms provide a personal, non-collective consultation right and restrict downloading beyond personal limited-time use, reproduction, transmission, redistribution and exploitation, including non-commercial use. No permitted public API was found.                                                                                                                              | No machine-readable identity/period/currency contract verified.                                                                                                                                                                                                                                         | **Do not automate or copy.** No adapter.                                                                                                                                                                                                                                 |
| **SEC / issuer filings and releases** | Free primary sources for reported actuals, company guidance and filings; they are not sell-side consensus.                                                                                                                                                                                                                                                                                                                                                                             | Official public endpoints and issuer publications are appropriate for factual actuals/guidance subject to their access rules.                                                                                                                                                                                                                                                     | Strong issuer/reporting-period identity where applicable; guidance periods and metrics vary.                                                                                                                                                                                                            | **Useful complement for actuals and guidance only.** Do not label guidance as consensus or infer analyst estimates.                                                                                                                                                      |

The source terms and feature statements used for this comparison are linked to
the providers' own documentation: [Alpha Vantage estimates API docs](https://www.alphavantage.co/documentation/),
[Alpha Vantage free-use terms](https://www.alphavantage.co/terms_of_service/),
[Alpha Vantage usage limits](https://www.alphavantage.co/support/),
[FMP financial-estimates API](https://site.financialmodelingprep.com/developer/docs/stable/financial-estimates),
[FMP estimate-history FAQ](https://site.financialmodelingprep.com/faqs?code=statements),
[FMP pricing](https://site.financialmodelingprep.com/developer/docs/pricing),
[FMP Terms of Service](https://site.financialmodelingprep.com/terms-of-service),
[Yahoo Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html),
[finanzen.net automated-extraction notice](https://hilfe.finanzen.net/hc/de/articles/7444475913244-Hinweis-zum-automatisierten-Auslesen),
[finanzen.net data sources](https://hilfe.finanzen.net/hc/de/articles/360014725599-Datenaktualisierung),
and [MarketScreener terms](https://www.marketscreener.com/navigation/contrat-4T.htm).

## Representative coverage assessment

The current active universe has 21 Portfolio and 71 Watchlist companies. The
operational coverage receipt records exact listings for all Portfolio companies
and 61 Watchlist companies; 10 Watchlist companies still lack exact canonical
listings. The provider-source reports show no Alpha Vantage mappings or live
queries, so **verified Alpha Vantage coverage is 0/21 Portfolio and 0/71
Watchlist**. This is a verification count, not a claim that the provider has no
data.

The appropriate first pilot cohort is deliberately small and listing-diverse:

- Portfolio: Microsoft (`NASDAQ:MSFT`, USD), Amazon (`NASDAQ:AMZN`, USD), ASML
  (`AMS:ASML`, EUR), Adyen (`AMS:ADYEN`, EUR), and Taiwan Semiconductor
  Manufacturing (exact canonical listing/currency must be checked before
  choosing a provider symbol).
- Watchlist: Axon (`NASDAQ:AXON`, USD), Comfort Systems (`NYSE:FIX`, USD),
  Rubrik (`NYSE:RBRK`, USD), and Veeva (`NYSE:VEEV`, USD). Include at least one
  unresolved Watchlist listing only after that canonical identity is resolved;
  do not treat a company-level provider symbol as proof of listing equivalence.

These are proposed test cases, not source-coverage results. No API key was
available and no provider was queried for issuer estimates. Alpha Vantage's
symbol-only request surface does not establish exchange/listing identity by
itself. Provider symbol, security basis and currency require independent
evidence before any canonical mapping is accepted.

## Read-only proof of concept

`apps/api/src/portfolio_api/consensus_estimate_probe.py` adds an isolated
Alpha Vantage raw-response probe using the shared `ProviderQuery` and
`RawProviderRecord` boundary. It accepts exactly one explicitly mapped company
per request, hashes the returned bytes, records the local retrieval timestamp,
sanitizes the API key out of the source URL/errors, and rejects provider error
messages and a mismatched response symbol when one is present. It has no
normalizer, database access, canonical persistence path or scheduler.

The free demo endpoint was exercised from Alpha Vantage's official example; it
returned a message asking the caller to claim a key rather than a data payload.
Accordingly, no estimate values, currency, field names, analyst counts, fiscal
periods or provider-supplied source timestamps have been validated. Unit tests
use a transport fixture only to verify the raw-record boundary and key
sanitization; they are not source-field or parity tests. A real one-company
probe requires an authorized key and is intentionally left for an operator.

For an individual who qualifies under the provider's free terms, the probe can
be run without touching PostgreSQL:

```powershell
$env:ALPHA_VANTAGE_API_KEY = "<your key>"
node scripts/uv.mjs run --locked --project apps/api python -m portfolio_api.consensus_estimate_probe `
  --company-id <canonical-company-uuid> `
  --provider-symbol <independently-reviewed-provider-symbol>
```

The command writes one raw payload and its retrieval/hash metadata to stdout;
it does not store the payload. Use it only after confirming that the account and
use qualify under Alpha Vantage's terms. Do not use this command from a company
or multi-user deployment under the free personal license.

## Recommendation

1. **Primary zero-cost source:** Alpha Vantage is a conditional candidate only
   for one individual's private, non-commercial research, and only as a
   raw-response pilot until data retention/display rights are clarified. Do not
   designate it canonical until a real response verifies identity, fiscal period,
   currency, units, field semantics and revision timestamps/history depth. For
   an organizational or multi-user platform, there is currently no verified
   zero-cost primary source; do not use the FMP free plan as an implicit workaround.
2. **Complementary sources:** SEC/issuer filings for actuals and issuer guidance
   only. Keep guidance distinct from analyst consensus. No publicly accessible
   website reviewed here has a demonstrated permitted estimates API suitable as
   a fallback. FMP is the strongest technical candidate if the application
   obtains written rights for canonical storage/display and confirms endpoint
   entitlements; do not treat the free personal plan as permission.
3. **Not reliably available now:** permitted free EBIT/EBITDA consensus, an
   audited worldwide listing/currency crosswalk, validated annual/quarter period
   rules, actual analyst counts, and usable vendor-stamped estimate revisions.
   FMP documents these richer fields and a historical feed, but the application's
   current adapter does not access that history and the relevant access/license
   conditions are unresolved. Alpha Vantage may provide part of the set for
   specific symbols, but its payload has not been verified.
4. **History strategy:** once licensing and schema are verified, start
   prospective polling and retain the exact raw payload, provider symbol,
   retrieval/recorded timestamps, fiscal period, value, units/currency,
   analyst count and response hash. Do not backfill older observation dates
   from a current response. If the general free allowance remains 25 requests
   per day, 92 company requests require at least four quota days per universe
   pass (assuming one request returns annual and quarterly data); record each
   company's actual capture time and do not present the entire pass as
   synchronous. Estimate Momentum still needs same-provider annual Revenue/EPS
   snapshots at the relevant 12M/6M/3M reference points with resolved absolute
   periods and passing currency/unit quality. A current response's aggregate
   revision fields cannot substitute for those snapshots.

## Current blockers

- No authorized Alpha Vantage key is configured; live provider fields remain
  unverified.
- The free plan's individual-only use boundary must match the actual operator
  and deployment model, and data retention/display rights need clarification.
- No Alpha Vantage company/listing symbol crosswalk or currency evidence exists.
- The official documentation does not define the estimate payload schema or
  the dates/depth/meaning of its claimed revision history.
- Current canonical consensus coverage remains 0 primary providers; the legacy
  workbook values remain `DATA_CHECK` and Estimate Momentum remains unavailable.

See the machine-readable companion
[`consensus-free-source-feasibility-2026-10-11.json`](consensus-free-source-feasibility-2026-10-11.json).
