# Active workstream

## Investor research journey — acceptance frozen (2026-11-14)

`codex/investor-research-journey` starts at main `ddbacbc` after owner-merged
PRs #34, #36 and #35; integrated main `9a27353` with the owner-merged recovery
package [PR #37](https://github.com/paulzwecker/portfolio-app/pull/37). No ingestion/scheduler changes belong here.

Acceptance for this milestone:

- Portfolio → exact held listing → financials/prices/valuation/evidence → holdings
  or allocation retains company and listing context, including reload/navigation.
- Quote and price history use the same canonical listing; missing prices never
  select a different listing silently. Held but unvalued is not “not held”.
- Useful observations lead. Empty optional research panels, unsupported exposure
  controls and unavailable portfolio performance do not dominate normal workflows.
  Missing, stale, partial, conflicting and failed-source states remain inspectable.
- Shared slate/orange/teal components; keyboard navigation and desktop/mobile,
  light/dark review. Existing financial meaning, APIs and data authority unchanged.
- Relevant integration checks and one cohesive PR. No production writes,
  deployment, migrations, scheduler activation or financial acceptance.

Implementation is complete; scope is frozen for owner review. Exact listing and
portfolio origin survive tabs, reload and same-company overview/evidence/source
links. Missing market history never substitutes another listing. Coverage labels
replace successfully empty optional cards; source errors and partial/conflicting
observations remain inspectable. Shared chart sizing preserves mobile axes and
historical chart colors now use the actual theme token format.

Verification: 483 web tests; lint/types/contracts and 21 deployment tests pass.
Full managed production-build browser suite: 147 passed, 51 scenario-gated skips.
Final relevant production-build rerun after link review: 8 passed. Ten additional
SEC/API-backed desktop/mobile journeys pass against disposable PostgreSQL with
read-only financial data and mocked job transitions; protected fingerprints remain
unchanged. Empty Financials also passed a real-API browser check. Light/dark and
390/1440px views were inspected; existing Portfolio checks also cover 320px. All
screenshots use fictional fixtures, not production observations.

[Before](design/screenshots/investor-journey-before.png) ·
[Overview](design/screenshots/investor-journey-overview.png) ·
[Prices](design/screenshots/investor-journey-prices.png) ·
[Mobile dark](design/screenshots/investor-journey-mobile-dark.png).

Second-pass review resolved source-link context loss and verified exact-listing,
held/unvalued, empty-assessment, error, conflict, keyboard and source-disclosure
behavior. No remaining engineering blocker for this UI deliverable. No API,
migration, ingestion, scheduler, deployment configuration or financial calculation
changes relative to latest main. Main `9a27353` integrated without history rewriting;
owner checkout edits, stash and other branches remain intact.

Release classification: CONFIGURATION_REQUIRED. The November 14 read-only Neon
check and unchanged migration graph match `b59f16c8a203`; the schema gate passes.
This PR adds no API dependency. Hosted Render/Vercel SHAs and release/freeze controls
are not freshly verified. Owner must verify those controls before merge/release;
this work does not authorize deployment. Latest-head CI must pass before owner merge.

Deferred: new analytics, performance without transaction history, expanded price
history beyond the existing 252-observation read, provider activation and further
UI redesign. The next highest-value task is the approved recovery/provider sequence
below, followed by genuine price/FX and fundamentals readback in these views.

Production activation evidence preserved from merged #37 (November 14): exact Neon
identity and `b59f16c8a203` matched; 22 accepted positions, two cash rows and one
target revision. Prices, FX, reported facts, filing records and consensus are zero.
Market preview READY: 22 listings + DKK/EUR and USD/EUR, 2025-11-10–2026-11-09,
no provider requests/writes. No reviewed production CIK mappings. No durable backup
has been executed. The expiring November 8 recovery branch is not durable protection.

Use the merged [encrypted recovery runbook](encrypted-production-recovery.md) and
[provider decision matrix](financial-data-provider-decision.md). Next operational
step remains an owner-approved encrypted destination/key custody and isolated
restore rehearsal, then verified provider access and one guarded checkpoint.
