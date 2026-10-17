# Milestone 6.10 — Operational Data Activation & Coverage

This report uses a fresh read of the canonical local PostgreSQL database at
2026-10-10 19:03 UTC, after bounded market/FX polling and exact SEC identity
mapping. Historical migration receipts are not counted as fresh provider coverage.
The machine-readable results are in
[`operational-data-activation-2026-10-10.json`](operational-data-activation-2026-10-10.json).

## Current coverage

| Domain                  |                           Portfolio |                          Watchlist | Milestone 6.10 result                                                                                                                     |
| ----------------------- | ----------------------------------: | ---------------------------------: | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Current market quotes   |          21/21 before → 21/21 after |          5/71 before → 61/71 after | Fresh exact-listing quotes for all mapped companies; 10 Watchlist companies still have no canonical listing.                              |
| Listing identity        |                               21/21 |                              61/71 | Unchanged; no lookalike securities were assigned.                                                                                         |
| Daily market history    |              21/21 mapped companies |             61/71 mapped companies | 84 exact active/held listing responses; 336 new historical price observations on first run. Ten Watchlist companies remain unrepresented. |
| SEC issuer mapping      |                           0 → 20/21 |                           0 → 7/71 | 27 exact, evidence-backed CIKs; Adyen is intentionally unmapped.                                                                          |
| Reported fundamentals   |                                   0 |                                  0 | SEC ingestion blocked by missing `SEC_USER_AGENT`; no facts are claimed.                                                                  |
| Filing/source documents |                                   0 |                                  0 | EDGAR submissions ingestion blocked by missing `SEC_USER_AGENT`; no filing rows are claimed.                                              |
| FMP consensus           |                  0 FMP observations |                 0 FMP observations | No API key or primary mappings; 64 Portfolio and 3 Watchlist legacy rows remain `DATA_CHECK`.                                             |
| FX                      | 9 currency pairs have dated history |                  Same shared pairs | TWD/EUR now has 2,607 current daily rows, up from four rows across two effective dates.                                                   |
| Corporate actions       |  Observed actions remain unverified | Observed actions remain unverified | 880 `DATA_CHECK` action observations across 45 active listings; no action was promoted to verified.                                       |

The active scope is 21 Portfolio and 71 Watchlist companies. The worker selected
84 exact provider-mapped listings, including the standalone held ETF. On the first
bounded Yahoo refresh it received 470 daily price rows and inserted 336. It had
zero fetch failures and zero normalization rejections. The repeat fetched 418 rows
and recorded one new provider-sourced quote observation that superseded its prior
observation; it did not produce a duplicate with the same source identity. A later
TWD/EUR replay inserted zero rows after the successful first import of that exact
source history.

The ten Watchlist companies still lacking canonical listings are Accelleron,
BONESUPPORT, Exosens, Fabrinet, INVISIO, Medistim, Meta Platforms, Nova,
Rheinmetall and VINCORION. Exact listing identity remains the constraint for quote
coverage. No economically different listing was substituted.

## Provider diagnosis and factual-data changes

Yahoo chart ingestion is operational for the mapped listing scope. One earlier
TWD/EUR request failed with Windows connection error 10061 because that process
sent traffic through the local non-listening proxy at `127.0.0.1:9`. A bounded
replay with process-scoped `NO_PROXY` entries for Yahoo's two chart hosts
succeeded. This is a local proxy route issue, not a Yahoo symbol or normalizer
failure. The original failed run remains in the ingestion ledger.

Yahoo's direct `TWDEUR=X` history endpoint returned one dated observation for the
ten-year request. The exact reciprocal `EURTWD=X` returned 2,613 source bars with
TWD currency and `CURRENCY` instrument identity. The FX adapter now applies a
validated reciprocal only for canonical TWD/EUR, while preserving provider symbol,
source orientation, raw response and normalization provenance. The accepted
current series covers 2016-10-05 through 2026-10-09. Older direct-pair raw receipts
remain available for audit. The detailed source/freshness semantics are in
[`market-data.md`](../market-data.md).

Yahoo daily prices and FX observations are real provider observations. Yahoo
corporate actions are still unverified source facts: the database count increased
from 879 to 880 unverified observations. Price history remains split-adjusted
according to the existing provider semantics; corporate actions are not applied
to adjusted prices a second time. Dividend/split verification against primary
issuer or exchange evidence is outstanding.

## SEC and consensus activation

The SEC official company/ticker/exchange registry and issuer filing pages support
20 Portfolio CIK mappings and seven Watchlist mappings. Axon, Comfort Systems USA,
Rubrik and Veeva also have canonical listing identities; Meta Platforms, Fabrinet
and Nova have exact company-level CIK mappings but still lack canonical listing
rows. Their exact CIK identities are recorded with SEC evidence URLs.
The official [SEC company ticker/exchange file](https://www.sec.gov/files/company_tickers_exchange.json)
supports the Portfolio mapping set; individual issuer filing records confirm the
seven additional Watchlist identities ([Axon](https://www.sec.gov/Archives/edgar/data/1069183/000162828026025550/annualreportarsproxycombob.pdf),
[Comfort Systems USA](https://www.sec.gov/Archives/edgar/data/1035983/000110465926086255/0001104659-26-086255-index.htm),
[Rubrik](https://www.sec.gov/Archives/edgar/data/1943896/000194389626000060/0001943896-26-000060-index.htm),
[Veeva](https://www.sec.gov/Archives/edgar/data/1393052/0001393052-26-000032-index.htm),
[Meta](https://www.sec.gov/edgar/browse/?CIK=0001326801),
[Fabrinet](https://www.sec.gov/Archives/edgar/data/1408710/000140871026000028/0001408710-26-000028-index.htm) and
[Nova](https://www.sec.gov/Archives/edgar/data/1109345/000117891326000504/0001178913-26-000504-index.html)).

The SEC facts and EDGAR submissions adapters were exercised through the scheduled
worker, but each correctly recorded `BLOCKED / MISSING_SEC_USER_AGENT`. A valid
user-agent must include the application name and a monitored contact email. The
missing Portfolio mapping is Adyen. The SEC record at
[CIK 0001788707](https://data.sec.gov/submissions/CIK0001788707.json) identifies
an Adyen N.V. depositary-receipt entity; using that CIK for the operating issuer's
Company Facts would conflate different issuer identities. No non-US regulator or
company-source fundamentals adapter is active in this milestone.

The FMP worker recorded `BLOCKED / MISSING_FMP_API_KEY`. There are also no reviewed
FMP primary-provider mappings. No FMP request or synthetic current consensus was
created. The 64 Portfolio and 3 Watchlist workbook estimate records remain
`DATA_CHECK`; they lack provider continuity, currency and sufficient resolved
fiscal/observation history. Estimate Momentum remains unavailable. Once FMP is
licensed and configured, the application must begin capturing new point-in-time
observations; it cannot reconstruct consensus history from current values.

## Operational evidence and integrity

The bounded worker ledger now contains two partial market-data runs, two partial
corporate-action runs, four complete FX runs, one failed FX run retained for the
proxy diagnosis, and three blocked provider runs (SEC facts, EDGAR submissions,
FMP estimates). Replays create linked run and attempt records. Raw Yahoo payloads
remain available. Source changes are appended/superseded according to the existing
domain rules. We did not enable an unattended schedule or launch a broad historical
backfill.

The pipeline path remains provider response → preserved raw payload/receipt →
typed normalization → canonical observation → read-only domain queries and
analytics. Portfolio valuation uses exact-listing prices and dated FX. Native
model revisions keep their original reference-price basis; current quotes do not
rewrite assumptions or author revisions. Rank and Execution Pace consume the
existing canonical query outputs. No change was made to models, holdings, targets,
lifecycle, ranking history or execution history. See the prior
[price-dependency analysis](market-price-dependency-analysis-2026-10-10.md) for the
full consumer-by-consumer trace.

## Remaining priorities

1. Configure `SEC_USER_AGENT` locally with a monitored email, then run the bounded
   SEC fundamentals and submissions worker for the 27 reviewed issuer identities.
2. If an FMP license is available, configure `FMP_API_KEY` in the ignored local
   `.env`, review exact company/provider mappings, and start point-in-time estimate
   capture. Do not backfill current values as history.
3. Resolve the ten exact Watchlist listing identities before trying to fetch their
   market data.
4. Verify corporate actions against primary sources before treating them as
   confirmed, and add non-US filings/fundamentals sources in priority order for
   active Portfolio issuers.

The full repository check passed with 88 frontend and 232 backend tests, lint,
formatting, both typechecks, OpenAPI/TypeScript contract checks and the production
build. PostgreSQL integration tests passed (43) using the dedicated isolated test
database. The default browser suite passed 24 checks with 10 opt-in live/database
cases skipped. Separate live desktop/mobile browser checks then passed for
frontend → API → PostgreSQL readiness and exact-listing Market facts. Alembic found
no pending migration, and the live API reported a current schema.

No secret values are stored in the repository. No Milestone 6.11 work was started.
