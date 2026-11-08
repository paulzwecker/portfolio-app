# Active workstream

## C2.3 guided ledger onboarding — INTEGRATE / BLOCKED release

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
