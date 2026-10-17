# Milestone 10B — Canonical Fundamentals & Historical Data Recovery

Database-backed coverage was captured on 2026-10-16 from the canonical local
PostgreSQL database. The full per-company result is in
[`canonical-fundamentals-data-recovery-2026-10-16.json`](canonical-fundamentals-data-recovery-2026-10-16.json).

No observations were written during this milestone because the SEC user-agent
contact is not configured. Before and after coverage is therefore unchanged:

| Domain                                      |               Portfolio | Watchlist | Overall |
| ------------------------------------------- | ----------------------: | --------: | ------: |
| Canonical reported-fundamental observations |   0 facts / 0 companies |     0 / 0 |  0 / 92 |
| Canonical filing/source-document records    | 0 records / 0 companies |     0 / 0 |  0 / 92 |
| Reviewed SEC issuer mappings                |                 20 / 21 |    7 / 71 | 27 / 92 |
| Dated non-legacy consensus observations     |                       0 |         0 |       0 |

The latest stored SEC ingestion runs remain `BLOCKED / MISSING_SEC_USER_AGENT`.
This is a local configuration blocker, not evidence that the SEC endpoint failed.
The code requires an application label and a genuine monitored contact email.
`SEC_USER_AGENT` is currently unset, so no live SEC request was attempted in 10B.
The last stored failures are dated 2026-10-10; their recorded mapping count of 20
predates the current 27 reviewed mappings. All 92 company-level reporting
currency fields are null; source-reported fact currency must be retained per
observation and must not be inferred from the listing.
After adding `SEC_USER_AGENT` to the ignored `.env`, run:

```powershell
npm run db:sync-reported-fundamentals -- sync
npm run db:sync-source-documents -- sync
```

Do not fill in a guessed or fabricated address. If the provider then fails, the
new run ledger will distinguish HTTP/connectivity errors from normalization or
issuer-mapping issues.

Adyen is the only unmapped Portfolio issuer. Its known SEC CIK is for a
depositary-receipt entity rather than the Amsterdam ordinary issuer. Among the
Watchlist, 57 listing identities lack a reviewed SEC mapping (42 NYSE/Nasdaq and
15 non-US listings); 7 further Watchlist companies do not yet have a canonical
listing. The JSON inventory names each company and preserves its exact listing.
No CIK was inferred from a company-name similarity.

All 271,900 active-universe daily closes have `recorded_at`, but none has
provider `observed_at`; Yahoo historical bar timestamps identify session dates,
not when those values first became available. No historical time repair is
supportable from those payloads. All 276 current quotes have both timestamps.
The 67 legacy workbook estimate rows across 18 companies have no point-in-time
observation timestamp and remain ineligible for consensus history, forecast
benchmarking and Estimate Momentum. No historical estimates or facts were
fabricated.

Non-US document sources are identified for a later adapter review: national EU
OAM/ESEF and issuer reports, UK FCA NSM, Canadian SEDAR+, ASX announcements,
Taiwan MOPS, Japan EDINET, and SIX/issuer reporting for Switzerland. No adapter,
facts, or document records were added for these sources in this slice.

Normalization retains the existing canonical schema: annual, discrete-quarter
and balance-sheet instant facts; exact fiscal dates, currency and units; filing,
retrieval and recording times; taxonomy and source accession; and immutable
possible-restatement lineage. Exact period alignment, idempotent replay,
supersession and no-look-ahead behavior passed tests. The full integration suite
passed 91 tests, focused fundamental/price/temporal tests passed 22, and the new
database timestamp eligibility regression passed 1.
