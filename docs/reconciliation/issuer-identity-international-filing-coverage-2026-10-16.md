# Milestone 10F — Issuer Identity & International Filing Coverage

**Result: CONDITIONALLY IMPROVED.** The identity false negatives are fixed without
loosening issuer identity, all ten missing active Watchlist listing records are
now resolved, and the bounded live SEC retry has loaded facts for all 27 already
reviewed CIKs. International issuer coverage remains limited to SEC filers and
the company/regulator sources already represented in the domain; no unverified
non-US adapter was added.

## SEC identity review

The earlier Company Facts run rejected 12 responses because SEC endpoint
`entityName` strings differed in punctuation, Unicode spacing, capitalization or
common legal suffix expansion. For all 12, the SEC CIK in the response matched
the exact mapped CIK; the SEC submissions name and official ticker/exchange
identity confirmed the same registrant. These were not parent/subsidiary cases
or issuer renames. No CIK mapping changed.

| Company                            | CIK          | Reviewed mapping label                      | Company Facts label                                  | Disposition                                |
| ---------------------------------- | ------------ | ------------------------------------------- | ---------------------------------------------------- | ------------------------------------------ |
| Copart                             | `0000900075` | `COPART INC`                                | `COPART, INC.`                                       | Accept punctuation                         |
| MercadoLibre                       | `0001099590` | `MERCADOLIBRE INC`                          | `MercadoLibre, Inc.`                                 | Accept case/punctuation                    |
| Mastercard                         | `0001141391` | `Mastercard Inc`                            | `Mastercard Incorporated`                            | Accept equivalent suffix                   |
| Microsoft                          | `0000789019` | `MICROSOFT CORP`                            | `MICROSOFT CORPORATION`                              | Accept equivalent suffix                   |
| dLocal                             | `0001846832` | `dLocal Ltd`                                | `DLocal Limited`                                     | Accept case/equivalent suffix              |
| Novo Nordisk                       | `0000353278` | `NOVO NORDISK A S`                          | `NOVO NORDISK A/S`                                   | Accept punctuation                         |
| Intuitive Surgical                 | `0001035267` | `INTUITIVE SURGICAL INC`                    | `Intuitive Surgical, Inc.`                           | Accept case/punctuation                    |
| Morningstar                        | `0001289419` | `Morningstar, Inc.`                         | `MORNINGSTAR, INC.`                                  | Accept case/non-breaking space             |
| Taiwan Semiconductor Manufacturing | `0001046179` | `TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD` | `Taiwan Semiconductor Manufacturing Company Limited` | Accept equivalent suffixes                 |
| Veeva Systems                      | `0001393052` | `VEEVA SYSTEMS INC`                         | `Veeva Systems Inc.`                                 | Accept case/punctuation                    |
| Comfort Systems USA                | `0001035983` | `COMFORT SYSTEMS USA INC`                   | `COMFORT SYSTEMS USA, INC.`                          | Accept case/punctuation/non-breaking space |
| Axon Enterprise                    | `0001069183` | `AXON ENTERPRISE INC`                       | `AXON ENTERPRISE, INC.`                              | Accept punctuation                         |

The validator now requires the provider response record ID, the reviewed CIK
mapping and the payload's own CIK to agree exactly. It normalizes Unicode,
punctuation and case, and equates only terminal `Inc`/`Incorporated`,
`Corp`/`Corporation`, `Ltd`/`Limited` and `Co`/`Company` variants. All other name
tokens must still match. A true rename such as Facebook/Meta, or a parent versus
subsidiary, will remain a data check and needs a separately reviewed identity
decision. No historical alias table was introduced.

## Live SEC reconciliation

The first corrected Company Facts run (`b2720941-32df-44fa-b74e-215bca7df51b`)
returned all 27 mapped issuer records: 12 `IMPORTED`, 15 `ALREADY_IMPORTED`,
13,426 facts inserted, and zero normalization errors or missing provider
responses. It reported 27 taxonomy mapping warnings, which identify standard
concepts outside the current canonical allowlist. The repeated replay
(`40e2e88a-431e-45d1-b3d8-4095fa0e7109`) returned 27 `ALREADY_IMPORTED`, inserted
zero facts and kept the total at 26,808. Both runs are recorded `PARTIAL` because
the full active universe contains companies without a reviewed SEC CIK and the
adapter intentionally maps only its supported concepts.

| Coverage                           |               Before 10F retry |                    After retry |
| ---------------------------------- | -----------------------------: | -----------------------------: |
| Reviewed SEC CIK identities        | 27 (20 Portfolio, 7 Watchlist) | 27 (20 Portfolio, 7 Watchlist) |
| Portfolio companies with SEC facts |                        11 / 21 |                        20 / 21 |
| Watchlist companies with SEC facts |                         4 / 71 |                         7 / 71 |
| Canonical reported observations    |                         13,382 |                         26,808 |
| `DATA_CHECK` observations          |                            408 |                            900 |

The 900 data checks are preserved: 891 possible restatements and 9 changed
observations in amended filings. The other 329 amended-filing observations are
unchanged and remain `PASS`. These statuses do not erase the original values or
publication dates. Adyen remains unmapped because the available SEC
[submissions record](https://data.sec.gov/submissions/CIK0001788707.json) does not
identify the ordinary-share reporting entity tracked by the application; that
SEC identity is not used as a substitute for the Amsterdam listing.

The replay of SEC submissions (`54911873-c315-4319-96dc-be3030434714`) reused all
5,721 existing supported filing records, imported zero duplicates, and recorded
zero metadata conflicts, unlinked amendments or document quality checks. Its
`PARTIAL` status reflects 18,721 unsupported filing forms excluded by the current
document contract; it is not a failed request for the supported forms.

## Exact active listing reconciliation

Before this milestone 82/92 active companies had canonical listing records: all
21 Portfolio companies and 61/71 Watchlist companies. The ten missing Watchlist
identities are now source-linked in the provider crosswalk and canonical
PostgreSQL. Provider symbol, exchange code, instrument type and quote currency
were checked against live Yahoo chart metadata; those lookups validated mapping
only and did not import market-price or FX observations.

| Company                | Canonical listing | Security / currency        | Primary identity evidence                                                                                                                                                            |
| ---------------------- | ----------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Accelleron Industries  | `SWX:ACLN`        | Registered shares / CHF    | [Issuer share information](https://accelleron.com/investors/share-information)                                                                                                       |
| BONESUPPORT Holding AB | `STO:BONEX`       | Ordinary shares / SEK      | [Issuer share information](https://www.bonesupport.com/en-eu/investors/the-share/)                                                                                                   |
| Exosens                | `PAR:EXENS`       | Ordinary shares / EUR      | [Euronext-hosted 2025 universal registration document](https://live.euronext.com/sites/default/files/esg_document_files/2026-03/601064_Exosens_URD%202025_VA_2026-03-26_10%3A49.pdf) |
| Fabrinet               | `NYSE:FN`         | Ordinary shares / USD      | [SEC annual filing](https://www.sec.gov/Archives/edgar/data/1408710/000140871026000028/fn-20260626.htm)                                                                              |
| INVISIO AB             | `STO:IVSO`        | Ordinary shares / SEK      | [Issuer listing confirmation](https://corp.invisio.com/news-and-events/pressrelease/invisio-upgraded-to-large-cap-list-on-nasdaq-stockholm)                                          |
| Medistim ASA           | `OSL:MEDI`        | Ordinary shares / NOK      | [Euronext Oslo security page](https://live.euronext.com/en/product/equities/NO0010159684-XOSL/company-information)                                                                   |
| Meta Platforms         | `NASDAQ:META`     | Class A common stock / USD | [SEC 2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/1326801/000162828026003942/meta-20251231.htm)                                                                           |
| Nova Ltd               | `NASDAQ:NVMI`     | Ordinary shares / USD      | [SEC 2025 Form 20-F](https://www.sec.gov/Archives/edgar/data/1109345/000117891326000504/zk2634307.htm)                                                                               |
| Rheinmetall AG         | `ETR:RHM`         | Bearer shares / EUR        | [Issuer share information](https://www.rheinmetall.com/en/investor-relations/share/basic-information)                                                                                |
| VINCORION SE           | `ETR:V1NC`        | Bearer shares / EUR        | [Issuer share information](https://ir.vincorion.com/basicinformation)                                                                                                                |

After import, all 92 active companies have exact canonical listings (21/21
Portfolio and 71/71 Watchlist). Replaying the listing importer returned
`ALREADY_APPLIED`; a fresh crosswalk preview is `READY` with zero additions and
zero unresolved identities. Evidence URLs for Meta and Nova were corrected to
their exact SEC filings in both the source crosswalk and the corresponding
canonical listing metadata.

## International reporting-source decision

No non-US adapter was added. The access and maintenance boundaries are not yet
uniform enough to support a safe general implementation:

- SEC 20-F/6-K reporting already supplies primary filings and facts for some
  foreign issuers, including companies with exact US-listed or SEC-registered
  identities. It does not establish coverage for every local listing.
- EU ESEF provides a structured annual-report format, but issuer/OAM discovery,
  availability and publication metadata remain jurisdiction-specific. [ESMA's
  ESEF guidance](https://www.esma.europa.eu/issuer-disclosure/electronic-reporting)
  is a format reference, not a single filings API.
- Japan's [EDINET API guidance](https://disclosure2.edinet-fsa.go.jp/week0020.aspx)
  requires registration/API-key setup and Japanese-language operational
  documentation; no local key or tested mapping cohort is configured.
- Canada's [SEDAR+ terms](https://systems.securities-administrators.ca/terms-of-use/)
  restrict automated searching and extraction, so it is not a permissible
  scraping target.
- Company-published reports and regulator portals in Taiwan, Australia, the UK
  and Switzerland remain candidates for company-specific evaluation. Their
  publication time, statement taxonomy, currency and permitted automated access
  must be validated before writing canonical facts.

For now, continue the SEC path only for reviewed CIKs. A focused non-US pilot
should begin only after one exact issuer/source pair has documented permitted
access, stable period and publication metadata, and a deterministic mapping to
the existing canonical facts. Adyen is still a priority human identity/source
review; its local annual report is not converted into facts by this milestone.

## Remaining blockers

- Adyen is the only Portfolio company without SEC Company Facts coverage; its
  ordinary listing remains intentionally separate from the known SEC ADR entity.
- 64 Watchlist companies remain without reviewed CIKs. SEC ingestion is not
  assumed for companies that do not report to the SEC.
- 900 potential-restatement/amended-filing observations are explicit review
  states, not silently selected values.
- New listing mappings do not themselves provide prices or dated FX. Fresh
  market-data ingestion must populate those observations independently.
- The SEC facts allowlist intentionally excludes nonstandard concepts and the SEC
  submissions adapter excludes unsupported forms. No non-US adapter or report
  content downloader was introduced.

Machine-readable counts, identities, run IDs and mapping decisions are in
[`issuer-identity-international-filing-coverage-2026-10-16.json`](issuer-identity-international-filing-coverage-2026-10-16.json).
