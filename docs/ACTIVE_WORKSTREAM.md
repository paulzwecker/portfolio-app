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

Implementation and verification are in progress. Production observations remain
unverified/empty per the latest read-only activation evidence; representative
browser fixtures are not production ingestion. Recovery/provider activation is a
separate owner-gated workstream. No new architecture or optional analytics required.

The preceding integration handoff is preserved in Git at `ddbacbc`.

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
