# Active workstream

## Company refresh continuity — integration

`codex/company-refresh-continuity` is [PR #35](https://github.com/paulzwecker/portfolio-app/pull/35),
integrating main `9939fe3` after owner-merged PRs #34 and #36.
Company Explorer restores queued and running company jobs after navigation and
reload, displays multiple active requests and the latest completed outcome, and
continues polling the existing durable operations pipeline. A bounded, read-only
API filters by exact company before limiting and prioritizes active jobs. Mismatched,
unavailable or timed-out history keeps actions disabled with a retry. Existing
worker, admission, deduplication and production activation controls are unchanged.

Local integration evidence: 99 relevant API/database tests, all 471 web tests,
eight synthetic desktop/mobile browser journeys, full API type and lint checks,
frontend production build, contract and deployment-gate tests. The journeys cover
reload, multiple active jobs, timeout/retry, older APIs and retained old and new
terminal outcomes. Desktop/mobile screenshots were inspected. Independent review
found and verified a fix for a newer outcome hidden by a recovered older receipt.
No migration or production action was performed.

After the preliminary integration of `387ec6d`, 471 web tests, 21 isolated
company-refresh/API tests, contract comparisons, both offline schema gates,
21 deployment tests and documentation checks passed. Eight synthetic
desktop/mobile refresh journeys passed against the isolated API; the active
request layouts were inspected. Repeat affected checks after integrating #36.

After integrating `9939fe3`, 481 web tests, 21 isolated company-refresh/API
tests, contract comparisons, both offline schema gates, 21 deployment tests and
the documentation check passed. The first concurrent web run and isolated
browser startup timed out under load; the web suite passed when rerun serially.

Release status: BLOCKED. On November 14, the owner reported Render Auto-Deploy
after CI, Blueprint Auto Sync on, and a Vercel hook permitting production when
the schema gate passes. These are not a deployment freeze; the owner must freeze
both providers before merge. Fresh Neon identity/schema and deployed commits also
remain unverified. Older APIs lack the
new route, so keep Vercel production builds frozen and deploy and verify the API
before the frontend under separate authorization; until then controls fail closed.
Production ingestion and scheduler activation remain separately gated.

For a separately authorized release: keep both provider freezes in place through
owner merge and record the exact merged main SHA and passing checks. Verify the
live Neon identity/revision and provider state, then release that SHA to the existing
Render API and verify its commit, live/ready health and authenticated read-only
`GET /v1/companies/{company_id}/job-requests`. Only then may the owner release the
same SHA to Vercel through the reviewed schema-aware hook and GitHub Deployment
Checks, and verify the production alias, authenticated health and Company Explorer.
Stop on a mismatch; do not force-promote or enable ingestion or schedules.

Alternatively, the owner may separately authorize an API-first release with
Render Auto-Deploy after CI left on. Before merge, freeze Vercel production and
verify the exact Blueprint sync effects and existing runtime settings; do not treat
this alternative as already authorized. Verify the resulting exact Render SHA and
health before releasing the matching Vercel build through the existing gates.

## Previous Financials availability — merged

[PR #36](https://github.com/paulzwecker/portfolio-app/pull/36) merged into main as
`9939fe3`, following merged [PR #34](https://github.com/paulzwecker/portfolio-app/pull/34). Company Financials
now hides the unsupported growth/ratios category and suppresses empty chart controls
and zero-count cards when no aligned cells exist. Sources, SEC coverage, time filters
and quality-checked cells stay accessible; zero remains a valid chartable value.
Source filters can hide and restore the chart without hiding their own controls.
Retained flagged values now announce their status to screen readers.

The next BUILD increment defaults the chart to another eligible reported metric,
or an eligible forecast if no reported metric can be charted. An explicit empty
selection stays empty. Coverage counts and source messages now use displayed
periods, and out-of-window observations cannot enable a chart checkbox. Seventeen
focused web tests, lint/typecheck and a synthetic Company Explorer journey at
desktop and mobile widths passed; independent review identified these issues and
confirmed that a suspected consensus mapping issue is not currently reachable.

Local evidence: all 475 web tests, lint/typecheck, frontend production build, 22
deployment/documentation checks and both offline schema gates passed. A synthetic
Company Explorer journey covers placeholder rows, conflicts, source toggles and
populated data at mobile and desktop widths. Two browser checks used the real
isolated empty API response, verified source access and unchanged protected state,
and were inspected in light and dark themes. Independent review found no remaining
concrete blocker. No schema, financial calculation, provider or production changes.
Frozen acceptance: suppress unsupported empty controls; retain source and quality
evidence; chart only aligned eligible values, including zero; preserve explicit
selection. The full 478-test web suite, lint, production build, documentation and
deployment checks passed. Desktop/mobile journeys passed with synthetic data and
with the isolated API; empty-state light/dark layouts were inspected. Independent
review found no blocker. A pre-existing selection that persists after a period or
source change is deferred. This slice creates no financial observations. The owner
reported deployment controls verified on November 11; the current November 14
settings permit automatic deployment. The live schema and deployment commits remain
independently unverified. Production release remains BLOCKED until checked.
Source access and recovery gates for real data are separate.

After integrating `387ec6d`, the 478 web tests, lint, frontend build, contract
comparisons, both offline schema gates, 21 deployment checks and documentation
check passed. The Company Explorer synthetic desktop/mobile journey and the two
isolated-API desktop/mobile empty-state journeys also passed. The November 11
deployment-control verification does not establish the current live schema or SHA.

## Previous SEC issuer review — merged

[PR #34](https://github.com/paulzwecker/portfolio-app/pull/34) merged into main
as `387ec6d`. Acceptance for this increment: an explicit issuer can be reviewed
without database writes or SEC calls; the existing target and schema checks remain
mandatory; issuer evidence is consistently checked across mapping and fundamentals
bootstrap; conflicting mappings and legacy invalid records fail closed. URL syntax
is not proof of issuer identity. No schema or production configuration changed.

The preview and sequential conflict checks passed 25 focused checks against synthetic
PostgreSQL data, including target mismatch and zero writes; focused Ruff checks pass.
Both supported mapping writers now take the same nonblocking transaction lock and
require READ COMMITTED; canonical reconciliation also rejects legacy ambiguity.
An isolated synthetic SEC rehearsal covers issuer preview through Company Explorer APIs;
113 relevant tests passed, including the read-only guard and legacy-identity cases.
Ruff, focused mypy, documentation checks and both offline schema-gate modes passed.
After reconciling PR #33, 19 focused issuer, fundamentals and market-scope tests,
documentation and both offline schema-gate modes passed again.
Independent review found no additional proven blocker for this narrow slice. No UI
changed; this is operator preparation, not live-data activation.
This lock does not constrain older deployed processes or direct SQL; production
mapping remains disabled until those writers are drained and the updated paths are
separately released. A contact-bearing SEC user agent is needed for live source
requests. Real issuer verification and ingestion are separate follow-on operations.
Production backfill and unattended refresh remain conditional on verified recovery,
provider terms, reconciliation and the owner's explicitly scoped approvals.
The owner reported verifying deployment controls on November 11. Production release remains BLOCKED
pending fresh schema and deployed-commit verification; the checked-in attestation
alone is not live production evidence.

## Previous C2.2 Portfolio valuation evidence

[PR #33](https://github.com/paulzwecker/portfolio-app/pull/33) merged as `715820e`; its production deployment is not verified here.

Portfolio now presents per-listing weights, supplied FX details and all valuation
gaps without calculating financial results in the browser. Operations provides a
read-only market-scope review: exact selected identities, mapping status, snapshot
completeness and quantities, with an explicit limit and warning when identities are
omitted. Missing, zero and partial data remain distinct. The existing multi-portfolio
selection limitation is disclosed; this milestone does not alter writer selection.

The repository quality check, relevant isolated PostgreSQL suite, managed desktop
and mobile browser tests and real local API browser journeys passed. Independent
review findings on snapshot completeness, decimal precision and accessibility were
fixed. No migration was added. **CONFIGURATION_REQUIRED**: verify current provider
controls and live revisions; the additive API must be deployed and checked before
the frontend. A merge is not deployment authorization. Real provider ingestion
and unattended refresh remain separately gated by source permission, current
recovery and the approved operational procedure. Sensitive operator evidence stays
outside this public repository.

## Previous C3.1 SEC provenance milestone

The [frozen milestone](sec-provenance-integration.md) is isolated on
`codex/sec-provenance-integration` from `main` `2dfef5b` (merged PR #30),
with [PR #32](https://github.com/paulzwecker/portfolio-app/pull/32) merged as
`976fa2b`.
It adds issuer and filing provenance warnings, evidence-time boundaries, and
fail-closed Sheets publication. It introduces no migrations. The original
`codex/sec-coverage-readiness` retains all deferred refresh ownership, Sheets
recovery and migration work; it must be reconciled after this milestone merges.
This milestone did not authorize production ingestion, publication, migration or deployment.
Local verification: `npm run check`, the relevant isolated PostgreSQL suite,
authenticated publication-denial cases, 42 managed desktop/mobile browser cases
(12 intentionally skipped), four isolated SEC browser cases, and visual review.
The repository schema gate matches the recorded `b59f16c8a203` attestation; this
is not fresh production evidence. Release classification: CONFIGURATION_REQUIRED
until current schema, both providers' live revisions/controls and safe API/frontend
ordering are verified. New publication is disabled; drain older processes before
any separately authorized rollout. Exact Sheets outcome resolution and all refresh
ownership extensions remain deferred on the original branch.

## Previous guided ledger onboarding evidence

Historical snapshot: PR #30 has since merged.

Branch `codex/ledger-opening-onboarding` contains implementation `18f1f15` and
merge `813651e` from updated main `e070406` ([merged PR #29](https://github.com/paulzwecker/portfolio-app/pull/29)).
The owner edits, predecessor branches/worktrees and private source artifacts remain
preserved. [Draft PR #30](https://github.com/paulzwecker/portfolio-app/pull/30)
is blocked pending current provider-control evidence; do not merge or deploy it.

Completed PRs stay frozen for owner review. Continue independent milestones from
updated main, or record an explicit stacked branch when a dependency is unmerged.
Fetch and reconcile remote merges at the start of each run while preserving work.

At `/portfolio/ledger`, the opening builder collects explicit evidenced accounts,
exact listing quantities and native-currency cash. A statement can be SHA-256
hashed locally or identified by an existing hash/reference. Drafts remain in page
memory. Submission reuses the authenticated read-only preview and its anchor/hash
checks. The source-date acknowledgement resets after edits. Download/re-upload
preserves exact financial text and account IDs. Separate saved-candidate decisions
retain their existing server authorization.

The opening workflow is LOCAL_VERIFIED with 96 focused web checks, 67 native ledger
unit tests, 13 isolated PostgreSQL/API cases and six managed desktop/mobile browser
checks. Synthetic light/dark screenshots were visually reviewed. Typecheck,
production build and focused lint pass. All selections passed again after merging
PR #29. Both offline schema-gate modes match `b59f16c8a203` with no pending range.
The new API regression checks v2 at the exact anchor boundary with zero
activity, deterministic replay and unchanged canonical state.

The latest BUILD restores the form's unchanged downloaded opening packet for the
current anchor, preserving account IDs and exact decimal text. It rejects packets
containing activity, ending statements or additional fields, and asks for the
date acknowledgement again. A pending older document hash cannot overwrite a newer
hash after restoration. Continue with guided activity and ending observations.
Verification passed 98 focused web tests and ten managed desktop/mobile browser
cases using synthetic data. Typecheck, production build, focused lint and docs
checks passed. The mobile light-theme layout was visually inspected.

## Current cash activity increment

The guided review now accepts evidenced DEPOSIT, WITHDRAWAL, FEE and TAX records
after an opening reconciles. Account, type, amount, currency, sequence, timestamp,
cutoff and source evidence are explicit. Native preview results display account
and portfolio balances. Editing invalidates the result, and the cash draft must be
discarded before switching its opening or source file. Full activity packets can
be downloaded and replayed in the existing file workflow. At that checkpoint,
guided trade/dividend/transfer entry and ending statements were outstanding.

Verification passed 112 focused web tests, 14 isolated PostgreSQL/API cases and
12 managed desktop/mobile browser cases using synthetic data. Typecheck, the
production build, focused lint and docs checks passed. Mobile and desktop layouts
were visually reviewed. No production operation was involved.

## Current cash restoration increment

A downloaded guided cash packet can be revalidated against the current anchor and
reopened for editing. Account and activity IDs, source evidence, timestamps and
exact decimal text are retained. Restoration refuses unsupported activity, ending
statements, stale anchors, numerical financial literals and additional fields.
The original file remains available for the existing file-review workflow.
Focused verification passed 114 web tests and 14 synthetic desktop/mobile browser
cases, including reload, identical replay and refusal of unsupported activity.
Typecheck, production build, focused lint and documentation checks passed. The
resumed mobile form was visually reviewed.

## Current ending statement increment

The guided workflow adds independently entered ending positions, cash and source
evidence for every opening account at the existing cutoff. Fields start empty, the
user confirms the observation time, and the API evaluates missing rows, zeroes and
differences. Edits invalidate the result. Discarding the ending draft returns the
previous packet for revalidation. At that checkpoint guided restoration remained open.
Preview cutoff and ending timestamps are checked at full fractional precision.
The increment passed 120 focused web tests, 15 isolated PostgreSQL/API cases and
28 synthetic desktop/mobile browser checks. Build, typecheck, focused lint and
documentation checks passed. Desktop and mobile synthetic layouts were inspected.

## Current ending restoration increment

An unchanged downloaded ending packet can be revalidated and reopened when its
statement matches or has only ending-observation mismatches. The form retains
account IDs, exact amounts and evidence, and asks for cutoff confirmation again.
Discard returns the original packet for revalidation. Unsupported, altered or
lossy packets stay in the file workflow. Account labels use stable IDs even if
the statement order differs from the opening account order.
Focused verification passed 123 web tests and 32 synthetic desktop/mobile browser
cases, including matched and blocked statement reload, correction, discard and
revalidation. Typecheck, build, focused lint and documentation checks passed.
The resumed desktop and mobile layouts were visually inspected.

## Current trade activity increment

The guided activity form supports evidenced BUY and SELL records for listings in
the verified anchor, alongside existing cash records. Listing and trading currency,
exact quantity, gross settlement cash, explicit fees/taxes and both dates come from
the source; replay and date/balance checks remain in the API. Mixed packets retain
identity, precision and evidence on restoration. Other listings and activity types
remain in the existing file workflow; no cost basis or FX is inferred.
Focused checks passed 136 web tests, 16 isolated PostgreSQL/API cases and 34 synthetic
desktop/mobile journeys, including trade download and restoration. Typecheck,
production build and focused lint passed; the synthetic desktop and mobile forms were inspected.

## Current dividend activity increment

The guided activity form now accepts evidenced dividends for verified anchor
listings, with explicit gross receipt, fees and withheld taxes. The actual cash
currency may differ from the listing currency; there is no inferred conversion.
Existing preview validation owns charge limits and native-currency replay. Exact
input and evidence survive download, revalidation and ending-statement restoration.
Focused checks passed 146 web tests and 17 isolated PostgreSQL/API cases, including
a cross-currency receipt and rejection of charges above gross. All 36 synthetic desktop/mobile ledger journeys passed; the dividend journey was
rerun after adding guidance against duplicate withholding. Screenshots were
reviewed. Production build, typecheck and focused lint passed.

## Current internal cash transfer increment

The guided form accepts paired internal cash transfers between two independently
identified brokerage accounts. Both legs require their own exact amounts, currency,
settled timestamp and source evidence; API validation owns matching and replay.
Restoration retains both legs, and duplicate source keys fail closed. The transfer
option is unavailable unless the opening contains two evidenced brokerage accounts.
Focused checks passed 157 web tests and three isolated PostgreSQL transfer API
cases and 38 synthetic desktop/mobile journeys, including the form, download and
restoration. Build, typecheck, focused lint and documentation checks passed.
Synthetic desktop and mobile forms were visually reviewed. No production or schema
changes were made.

## Current internal security transfer increment

The guided form accepts paired security transfers between evidenced brokerage
accounts, with independent listing, quantity, timestamp and source evidence for
each leg. The user explicitly acknowledges unavailable acquisition basis; no
lot, gain, ADR conversion or sale is inferred. The API validates matching legs
and source quantities. Downloaded and ending-review packets retain all evidence.
Focused checks passed 170 web tests and three isolated PostgreSQL security-transfer
API cases and 40 synthetic desktop/mobile journeys, including basis acknowledgement
and restoration. Build, typecheck, focused lint and documentation checks passed;
synthetic desktop and mobile layouts were inspected. No production changes were made.

## Non-anchor listing lookup API

An authenticated read-only exact-ticker lookup returns at most 50 reviewable
identity candidates, flags truncation, missing/invalid currency and demo records,
and keeps the snapshot anchor unchanged. Names, share class and demo status are
lookup context; the existing preview hash binds the core listing identity instead.
Three focused isolated PostgreSQL/API tests pass, including non-anchor purchase replay
and 50/51-result boundaries. The guided activity and ending forms now integrate this lookup.

## Guided non-anchor listing increment

Guided activity can select a canonical non-anchor listing from an exact-ticker
lookup, keeping lookup results separate from the opening anchor. Preview rejects
changed or omitted consumed identities, and all consumed identities are visible
in the evidence drawer, including activity-only listings. Activity and ending
reviews restore from revalidated preview identities. Display names, share class
and demo labels are lookup context, not hash-bound facts. Exact-ticker search
reports unsupported and truncated results; companyless ETFs remain companyless.
Verification passed 176 focused web tests, three isolated PostgreSQL/API tests,
48 synthetic desktop/mobile journeys, typecheck, build, focused lint and contract
checks. Synthetic desktop and mobile layouts were inspected.
The frontend lookup requires the matching API endpoint; coordinate API availability
before using it. No schema migration is introduced.

## Native guided candidate journey

The exact-ticker lookup now passes through the authenticated read-only Next.js
proxy with one bounded query and a validated, ticker-bound response. A synthetic
real-API/PostgreSQL browser journey covers guided opening, non-anchor purchase,
ending reconciliation, source identity, save and explicit review. Desktop cancels
the synthetic decision; mobile confirms it. The fixture permits only local test
receipt writes and protected holdings/targets hashes remain unchanged. Focused
proxy tests cover production authentication and HTTPS; the native browser fixture
itself runs with local development authentication. Two desktop/mobile journeys,
96 focused web tests, one isolated PostgreSQL fixture-guard test, typecheck, build,
focused lint and generated-contract checks passed. The fixture shut down and
removed its own schema. No production operation was performed.

## Next increment and release boundaries

Integration review identified an unexpected holding present only on an ending
statement. The ending builder now accepts the same exact-listing search and passes
its reviewed identity to the preview drift guard. An unexplained holding remains a
blocked mismatch; it never creates an inferred trade. Demo status from a restored
preview is explicitly unavailable until searched again. The isolated real-API
desktop/mobile journey covers the mismatch and rejects altered preview identity.

Fresh read-only Neon project/branch/endpoint and TLS-verified `neondb.public`
revision evidence matched `b59f16c8a203` and the offline schema attestation.
The active GitHub `main` ruleset requires a PR, resolved review threads and the
three strict CI checks, with no configured bypass actors. Current Render/Vercel
release controls remain unverified through available read-only access. The frontend's new listing
lookup also requires the new API endpoint; release API first, then frontend, under
separate approval. Do not infer deploy safety from matching schema or green CI.

Complete the release review. Reuse the versioned ledger contract, server calculations,
immutable review packets and explicit decisions. Preserve the observed holdings,
strategic targets and unavailable acquisition basis. A reviewed first broker format,
lot/FX policy, historical completeness and genuine TWR/XIRR remain later work.

This increment adds no schema or provider configuration. Its milestone remains
subject to verified provider release controls before merge or deployment. Integration
checks passed `npm run check` (442 web and 929 API unit tests, 2 skipped), 452
isolated PostgreSQL integration tests (4 skipped), 48 managed desktop/mobile
browser tests and two real-API browser journeys. The updated synthetic desktop and
mobile ending form was visually inspected; independent review found no actionable
security or financial-integrity issue. No hosted verification is implied.
Price/FX enrichment, recovery operations, production
ledger cutover, model acceptance and provider activation require their own scope
and authorization. No production writes or provider configuration changes ran.

[Ledger behavior](portfolio-ledger.md) owns this contract and workflow.
[The roadmap](../ROADMAP.md) owns priority. The previous market integration and
live-read evidence are preserved in the [dated handoff](history/market-history-build-through-2026-11-08.md).
