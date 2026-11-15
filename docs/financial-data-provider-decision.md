# Financial-data provider decision

Reviewed 2026-11-15 against official documentation. The owner's **zero-cost**
constraint supersedes the earlier paid-provider recommendation: no paid feeds,
subscriptions, scheduler services or additional hosting. The provider comparison
created no accounts or configuration changes. A separately bounded SEC source
capture is recorded in the active integration evidence.
Provider documentation establishes possible access, not exact coverage or production
activation. Private symbol and issuer evidence stays outside Git. The November 15
market/FX rehearsal below supplements the independently frozen SEC slice.

## Actual coverage requirement

The last read-only production inventory has 22 held listings: 11 NASDAQ, seven NYSE,
two Amsterdam, one Copenhagen and one Xetra; 18 USD, three EUR and one DKK.
There are 20 common-stock listings, one ADR and one ETF. Required market data is
historical daily prices plus DKK/EUR and USD/EUR for 2025-11-10 through 2026-11-09,
then bounded daily updates. Exchange support does not prove exact listing,
share-class, adjustment, currency or ETF coverage. Fundamentals require verified
issuer identities; ETF holdings do not imply issuer statements.

## Zero-cost decision

| Source                  | Evidence and limits                                                                                                                                                                                                                                                                                                                                                                       | Decision                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SEC EDGAR               | [Public Company Facts and submissions APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) need no API key. [Fair access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) requires an identified User-Agent and at most ten requests/second; the existing adapter is slower. APIs update as filings are disseminated.      | **Selected slice:** reuse existing facts/filings adapters and reviewed CIKs. Local recorded-fixture execution is independent of production recovery. A bounded capture passed using the existing local SEC contact; production contact/configuration and mapping approval remain unverified. Custom concepts, international reporting and historical filing pages can remain incomplete. |
| ECB reference rates     | [Official rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) include USD and DKK per EUR, normally published around 16:00 CET on working days. [Free reuse conditions](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html) require attribution and explicit identification of modifications. | **Isolated implementation and real-source reconciliation verified November 15.** Optional ECB adapter preserves per-EUR responses and reciprocals; 259 observations per pair through November 13 after the increment. These are reference rates, not trade-execution prices; do not invent weekend observations. Defer this independent adapter from the SEC refresh slice.              |
| Yahoo                   | Existing 24-subject database preview validates mappings, not access rights or responses. [Terms](https://legal.yahoo.com/ie/en/yahoo/terms/otos/index.html) restrict automated collection without express prior permission. No entitlement has been evidenced.                                                                                                                            | **Unavailable for unattended collection.** Keep disabled; private use alone does not establish automation permission. Do not probe unofficial endpoints or bypass access restrictions.                                                                                                                                                                                                   |
| Alpha Vantage free      | [Free access](https://www.alphavantage.co/support/api-key/) permits 25 requests/day with a key. [Daily-series documentation](https://www.alphavantage.co/documentation/) limits free compact responses to 100 observations; full history and daily-adjusted data require premium access.                                                                                                  | **Partial candidate only.** Does not establish the approved year of history or all exact holdings. No key, adapter, share-class/currency or coverage validation exists here; no paid upgrade is proposed.                                                                                                                                                                                |
| EODHD free              | [Published quota](https://eodhd.com/financial-apis/api-limits) is 20 calls/day; [free access](https://eodhd.com/financial-apis/quick-start-with-our-financial-data-apis) covers the past year for personal use with a key and advertises 500 initial bonus calls. Its no-signup demo covers only six named instruments.                                                                   | **Insufficient for all 22 daily listing refreshes under the published per-symbol path**, even with FX elsewhere. The rolling year also does not establish the full approved historical window today. No account was created; the separately bounded AMZN demo below is verified in isolation. Full free-account coverage remains unverified; paid Historian is out of scope.             |
| FMP / analyst estimates | The [free-plan FAQ](https://site.financialmodelingprep.com/faqs?code=company) describes a limited free tier, but does not establish free analyst-estimate endpoint entitlement, retention/display rights or exact currency/share-base coverage. Existing consensus adapter remains available in code.                                                                                     | **Unavailable until lawful free access and coverage are verified.** Keep FMP disabled; no paid plan or scraped analyst consensus is proposed. Missing estimates remain unavailable.                                                                                                                                                                                                      |

November 15 bounded EODHD demo access verifies one held listing, AMZN/NASDAQ/USD:
251 sessions in the approved window, 255 after increment through November 13.
Exact metadata agrees with official SEC identity. This indicative test-drive remains
isolated-only, not an approved production feed. Its [personal use](https://eodhd.com/help/personal-use),
[storage](https://eodhd.com/help/storage) and [private automation](https://eodhd.com/help/ai-tools)
guidance permits this private evaluation; all real data/screenshots/outputs stay out
of public Git. No account or paid trial was used. Stooq presented a browser-verification
challenge, which was not bypassed; Nasdaq website terms did not establish permission
for this automated analytical use. The other 21 holdings remain uncovered.

No free market provider has yet been verified for the complete held-listing scope.
That is an explicit operational limitation, not a claim that a permitted free source
cannot exist. Publicly viewable pages are not sufficient evidence for unrestricted
automated collection. Never bypass a paywall, CAPTCHA, authentication or anti-bot
restriction. Keep source identity immutable; never label an alternative feed as Yahoo.

## Smallest activation steps

### Analyst estimates: one isolated example, no broad free feed

The November 15 review found a concrete no-signup EODHD AMZN fundamentals demo,
including annual/quarterly revenue and EPS means, ranges and analyst counts. One
bounded request captured four forward periods, with eight canonical observations.
The ten-credit request is distinct from ten HTTP requests. Private access/storage
terms above permit the local evaluation; demo availability is not production-feed
entitlement or a reliability commitment. Exact Amazon USD identity is constrained
and disclosed; EPS accounting basis remains unverified. No historical revisions
are claimed from one capture. See [consensus semantics](consensus-estimates.md#bounded-eodhd-private-evaluation-2026-11-15).

| Alternative                    | Finding                                                                                                                                                       | Decision                                                                                   |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| ASML investor relations        | [Analyst coverage](https://www.asml.com/en/investors/shares/analyst-coverage) lists analysts, not a verified numeric consensus feed.                          | No automated numeric integration.                                                          |
| Equibles                       | [Pricing](https://equibles.com/pricing) places forecasts behind paid access.                                                                                  | Excluded by zero-cost policy.                                                              |
| Alpha Vantage / FMP            | No verified free estimate entitlement plus storage/display rights for this use. No new requests or accounts.                                                  | Existing adapters/probes remain inactive.                                                  |
| Yahoo / open-source collectors | Visible values and collector code do not grant source automation rights.                                                                                      | No unofficial endpoint probing or restricted scraping.                                     |
| Issuer guidance                | Amazon's [SEC-hosted release](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000038/amzn-20260930xex991.htm) contains dated management guidance. | Possible separate evidence category; not analyst consensus and not imported in this slice. |

No sustainable zero-cost production consensus source for all holdings has been
verified. Keep that coverage gap explicit. Do not expand this milestone into a new
guidance framework or a paid fallback. Existing SEC/ECB activation is the higher-value
operational next step once recovery and exact production approvals are satisfied.

### Existing SEC activation sequence

1. **Locally verified:** three official SEC requests captured MSCI Company Facts,
   submissions and one index-linked history file using the existing contact.
   Unchanged private recordings reconcile 1,596 facts and 310 filing references
   through manual/scheduled PostgreSQL/API/UI execution. Accepted-state fingerprints
   remain unchanged. PARTIAL receipts preserve unmapped concepts, potential
   restatements and unlinked amendments; this is not production coverage.
2. For production, approve the exact issuer mapping and bounded ingestion scope,
   verify the hosted `SEC_USER_AGENT` configuration, and execute the current-state
   encrypted backup/restore rehearsal in the [recovery runbook](encrypted-production-recovery.md)
   after destination, key custody and isolated restore-target approval. Local source
   success does not establish these production prerequisites.
3. Review the free existing-host scheduler proposal in
   [Recurring Operations](recurring-operations.md#zero-cost-sec-scheduling-proposal).
   Activation, credentials and production guards remain separately approved. No
   scheduler is registered by this package and no cloud settings are changed.

Keep paid services, FMP, Sheets publication, model acceptance and unrelated jobs
outside this slice. Recovery is a production prerequisite, not a reason to stop
isolated end-to-end development.
