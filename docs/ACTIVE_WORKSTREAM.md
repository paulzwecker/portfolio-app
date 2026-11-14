# Active workstream

## Investor research journey — acceptance frozen (2026-11-14)

`codex/investor-research-journey` starts at main `ddbacbc` after owner-merged
PRs #34, #36 and #35. Independent recovery package [PR #37](https://github.com/paulzwecker/portfolio-app/pull/37)
remains frozen for owner review. No ingestion/scheduler changes belong here.

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
