# Active workstream

## Agent 6 - statement coverage extension (acceptance frozen 2026-11-15)

The owner requests additional public fundamentals on the same compatible PR #39.
Extend the completed MSCI workflow with **Microsoft only**, subject to exact official
CIK/legal-entity/listing review. Validate annual and discrete-quarter revenue,
earnings, operating results, available cash-flow and balance observations against
actual filing evidence. Preserve June fiscal-year labels, units, comparative facts,
source dates, unavailable values and partial/conflicting coverage.

Reuse the existing private recording, durable refresh and statement resolver in
isolated PostgreSQL/API/UI. Capture at most nine official requests: submissions,
Company Facts, up to five index-linked history pages, one annual and one quarterly
filing. Stop on access denial or identity mismatch. Retain independent source checks
and an unapproved mapping proposal privately. No production mapping, backup, write,
deployment, additional issuer, derived-ratio expansion or new infrastructure.
Passing MSCI and Microsoft evidence ends this extension; do not expand its scope.

## Real-source SEC refresh - integrated acceptance (2026-11-15)

Continue the existing [PR #39](https://github.com/paulzwecker/portfolio-app/pull/39),
branch `codex/financial-refresh-slice`, based on main `866723e`. Main already
includes PR #37 recovery tooling and PR #38 investor UI. The independent return-hurdle
workflow remains preserved at `33cedff` on `codex/investment-decision-cockpit`; it
does not belong in this data milestone. Owner edits, worktrees and stash are intact.

Frozen outcome is complete locally: exact MSCI identity (`CIK0001408198`) -> official
SEC facts/submissions -> existing durable manual/scheduled ingestion -> disposable
PostgreSQL -> Financials charts/tables, source evidence and filing history. No new
schema, API contract, worker framework, service or paid dependency. A real-history
table overflow was fixed in its existing shared scroll container.

Three serial official requests on November 14 UTC used the existing configured SEC
contact. The private, hash-verified recordings retain original capture times and
exact issuer/listing evidence. Offline replay uses a fictional portfolio allocation;
these are **real-source isolated observations, not production observations**.
Manual and scheduled readback reconciles **1,596 facts and 310 filing references**.
FY2025 revenue is USD 3,134,459,000; Q3 2026 revenue is USD 892,000,000, with exact
fiscal dates, units, accession evidence and distinct capture/recording timestamps.

Both receipts correctly remain **PARTIAL**: 545 unmapped concepts, 419 excluded
YTD/unclassified durations, 39 potential-restatement facts, six unlinked amendments
and 1,210 unsupported filing forms. Gross profit stays unavailable. Filing records
are metadata/references, not downloaded document bodies; the default UI/API view is
bounded to 100 of the retained 310. Do not present this as complete SEC coverage.

Desktop and mobile real-API browser journeys pass: queued identity survives
navigation/reload, persisted values appear without reloading Financials, source
links match accessions, Operations submits both bounded domains, and a three-day
late scheduled pass preserves counts. Same-day replay makes no new transport call.
All tables outside ingestion/jobs retain their full content hashes. Original
fictional rehearsals separately verify new-period updates, outages and conflicts.
Independent raw-source, financial/API and visual reviews found no A-class blocker.

Verification: 977 backend units (two platform skips), 492 web tests, 11 focused
rehearsal/recording checks, 28 browser-server regressions, contracts, types, lint
and 21 deployment tests pass. The broader managed production-build browser suite
passes 147 cases (55 opt-in skips); latest-head CI results are kept in PR #39.
Reproduce via [testing](testing.md#recorded-official-sec-responses-through-the-investor-ui).
Screenshots show isolated real SEC data:
[annual desktop](design/screenshots/real-sec-annual-desktop.png),
[quarterly mobile](design/screenshots/real-sec-quarterly-mobile.png),
[source evidence](design/screenshots/real-sec-source-desktop.png).

## Release and operational boundary

**CONFIGURATION_REQUIRED.** No migrations or new API dependency. Review/deploy
schema gates match the existing attestation `b59f16c8a203`, zero pending revisions,
unchanged migration fingerprint. Hosted commits/deployment controls have not been
newly attested. Owner review and release-control verification precede release.
No merge, deployment, cloud change, production query/write or scheduler activation
occurred in this extension. Freeze scope after passing integration checks.

Production remains **NOT STARTED** for financial-data activation. Last recorded
November 14 read-only inventory: 22 positions, two cash rows, one target revision;
zero prices, FX, facts, filings or consensus. This is historical evidence, not a
new production readback. The 22-listing + two-FX preview was READY without fetching
provider data. Yahoo automation permission and a complete free equity source remain
unverified. See [provider decision](financial-data-provider-decision.md).

Smallest next operator sequence:

1. Approve an owner-controlled encrypted off-provider destination, key custody and
   isolated restore target; execute the merged [recovery runbook](encrypted-production-recovery.md)
   with its confirmations. No current-state production backup has been executed.
   The old Neon branch expires November 15 at 14:18 CET and is not durable recovery.
2. Approve the exact MSCI mapping and bounded SEC ingestion scope, verify the
   production SEC contact/configuration, then run the existing target-bound preview
   and guarded checkpoints. Reconcile canonical records and authenticated live UI.
3. Prove one controlled incremental refresh before separately activating the
   [existing-host SEC schedule](recurring-operations.md#zero-cost-sec-scheduling-proposal).

Defer broader analytics, Sheets recovery/publication, generic worker work, UI polish
and full-document ingestion. Next independent data capability: official ECB
historical USD/EUR and DKK/EUR reference rates through existing ingestion, preserving
direction, attribution and missing days. No paid fallback or new infrastructure.
