# Active workstream

## Bounded SEC refresh � acceptance frozen (2026-11-14)

Branch `codex/financial-refresh-slice` starts at main `866723e`, owner-merged
[PR #38](https://github.com/paulzwecker/portfolio-app/pull/38). GitHub had no open
PR at intake. Owner checkout edits, private references, stash and prior branches
remain intact. No production changes or paid services belong in this milestone.

Frozen user outcome: Company Explorer requests verified-issuer SEC facts/filings;
Operations requests both domains across the bounded held/Watchlist scope; existing
durable requests survive navigation/reload; the existing importer persists validated
observations and the current APIs/UI display them. The equivalent SEC-only daily
cycle drains eligible manual work and catches up once after a missed run. Failures,
partial/currency-conflicting responses and source provenance stay visible. All
accepted holdings, targets and model contents remain unchanged.

Acceptance uses explicitly recorded **fictional** SEC responses in a disposable
loopback PostgreSQL schema. It establishes actual queue/import/database/API/browser
integration, not real-source coverage or production activation. No new API contract,
schema, queue, worker framework or service is needed. Existing guards/defaults remain.

Implementation and local acceptance are complete. The narrow `cloud_cron --scope
sec-data` path, active-request deduplication and active-first history reuse existing
services. Company and Operations actions retain durable source receipts and refresh
open data after completion. The exact one-shot runner shares the recurring lock;
an expanded receipt stays within the mobile viewport.

Evidence: 969 backend unit tests, 492 web tests, 86 relevant integration tests,
four one-shot lock tests and two new real PostgreSQL/API/CLI rehearsals passed.
The complete refresh browser journey passed on desktop/mobile: zero to four facts
and two filings, 13 simulated provider attempts, no provider network. It verifies
reload recovery, missed-run coalescing, no-fetch replay, outage, partial coverage and
unchanged contents of every table outside ingestion/jobs. The broader managed
production-build browser suite passed 147 cases (53 opt-in cases skipped).
Lint, formatting, types, contracts and 21 deployment tests pass. Independent backend
and visual reviews found no remaining A-class blocker. Screenshots use fictional
data: [mobile receipt](design/screenshots/sec-refresh-mobile.png),
[Operations](design/screenshots/sec-refresh-operations.png),
[new financial period](design/screenshots/sec-refresh-financials.png).

Release classification: **CONFIGURATION_REQUIRED**. The schema gate matches
`b59f16c8a203` with no pending migrations or changed migration bytes; API contracts
are unchanged. Current hosted commits/deployment controls are not newly attested.
Owner review and release-control verification precede any merge/deployment. The
free existing-host schedule is proposed and locally exercised, not registered.

Delivery review: freeze this completed scope for one PR and owner review. Defer
expanded receipt density, legacy Operations controls, ECB FX adapter, free equity
prices/consensus, expanded analytics, generic scheduling and further UI redesign.
Do not expand Sheets or recovery work. The source decision and scheduling proposal
are in [provider decision](financial-data-provider-decision.md) and
[recurring operations](recurring-operations.md).

Production remains NOT STARTED for this work. Last recorded November 14 read-only
Neon evidence: `b59f16c8a203`, 22 accepted positions, two cash rows, one target
revision; zero prices, FX, facts, filings and consensus. Market preview was READY
for 22 listings + two FX pairs, with no provider requests. Recovery destination/key
custody and restore rehearsal, monitored SEC contact/reviewed issuer mappings,
provider permission and exact activation approvals remain operational gates.
The expiring Neon branch is not a durable backup. Use the merged
[recovery runbook](encrypted-production-recovery.md); no backup is executed here.
Next operational action: approve the recovery destination/key custody and isolated
restore target, supply a monitored SEC contact, then run the reviewed recovery and
bounded verified-issuer preflight. Next independent data capability is official ECB
historical FX, preserving published direction, reference-rate semantics and missing
days; it does not need another generic worker or queue.
