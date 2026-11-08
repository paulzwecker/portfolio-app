# Candidate portfolio ledger

C2.3 implements source-bound opening/ending reconciliation, settled-activity
projection and durable candidate/review receipts. [The roadmap](../ROADMAP.md) owns delivery status and
[Portfolio architecture](architecture/portfolio-application.md#transaction-ledger-transition-planned)
owns cutover/ownership boundaries. Candidate review and publication have separate
authorization. Immutable snapshots retain read-model history; strategic targets
have independent ownership.

## Contract and scope

`portfolio-ledger-preview-v1` accepts one current complete snapshot, explicit
opening accounts/balances and up to 1,000 activity records. It permits 20 accounts,
1,000 opening position rows and 100 opening cash rows across those accounts.
`settled-booking-v1` supports BUY, SELL, DEPOSIT, WITHDRAWAL and FEE.

`portfolio-ledger-preview-v2` explicitly opts into `settled-booking-v2`, adding
DIVIDEND, TAX and paired CASH_TRANSFER / SECURITY_TRANSFER records. Existing v1/v2 packets, projections and receipt hashes retain
their original meaning. A v1 packet cannot contain these new kinds. Both versions
use the same review/publication workflow and existing migrated receipt tables.

### Paired internal cash transfers

A v2 CASH_TRANSFER is one ordered activity containing a source debit and a
required `destination` receipt. Both legs explicitly declare account, currency,
positive amount, timezone-aware settled booking instant and source document/record
evidence. The legs must have equal amounts/currency and the same absolute booking
instant, with distinct source keys. Both accounts must be declared evidenced
brokerage accounts inside the same portfolio, and they must differ.

Replay debits the source and credits the recipient at that single sequence,
preserving consolidated native-currency cash and all security quantities. Source
overdrafts block the packet, even when later activity repairs the closing balance.
Account-level ending observations must reconcile independently of portfolio totals.
The receipt evidence participates in duplicate-source checks, immutable input
hashes, saved records and correction acknowledgements. A reviewed correction
replaces the complete paired activity under its existing activity ID.

This scope requires two matched, already-settled observations. Different booking
instants require an explicit future in-transit accounting contract. Cross-currency
movement and outside-portfolio accounts remain unsupported.
Fees/taxes require separate evidenced rows. Do not also enter the matched legs as
external DEPOSIT/WITHDRAWAL rows; exact source-key reuse is rejected, and original
statement review must catch differently keyed duplicates. Internal movement grants
no income, external capital-flow, performance or ownership inference.

### Paired internal security transfers

A v2 SECURITY_TRANSFER declares the source account, exact `listing_id`, positive
`quantity`, settled instant and source record. Its required `destination` declares
the receiving account, the same listing/quantity/instant and independent receipt
evidence. Both accounts must be declared evidenced brokerages inside the portfolio.
The two source keys join duplicate checks, hashes and correction acknowledgements.

Replay moves only quantity between accounts, preserving consolidated holdings and
all currency cash. A short source position blocks review even if a later return
repairs the closing position. Both account statements must reconcile, including
explicit zero source positions after a whole-position transfer. Exact listing
identity is verified, locked and hash-bound, including companyless ETFs. Different
listings of the same security, ADR conversions and share-class exchanges require
separate reviewed contracts.

`basis_status` must explicitly be `UNAVAILABLE`. Acquisition dates/costs and gains
remain unavailable in this quantity-only ledger contract. Retain original lot/cost
evidence privately for later reviewed lot accounting. Known basis claims and extra
cost fields are rejected. Separate evidenced cash rows cover any fees/taxes.
Both legs require the same absolute settled instant; in-transit and external
transfers remain outside this contract. Transfer records grant no sale, income,
performance or investment-acceptance inference.

### Observed income and taxes

A DIVIDEND record declares an exact `listing_id`, settlement `currency`, positive
`gross_cash`, nonnegative `fees` and nonnegative `taxes` (withholding), including
explicit zero charges. It retains the common account, settled booking timestamp,
sequence and source document/record evidence. Net cash is gross less fees and
withholding; charges exceeding gross are rejected. Full withholding preserves an
explicit zero receipt. A separate TAX record debits its positive `amount` in the
stated currency. Do not record the same withholding both inside a dividend and as
a separate TAX row. Duplicate source keys remain blocked; source review must also
identify differently keyed duplicates from overlapping statements.

All dividend amounts use one observed account-settlement currency, which can
differ from the listing quote currency. The broker evidence must supply every
amount in that currency. The application performs no implicit conversion or
reconstruction of an original announced payout/rate. Unconverted multi-currency
legs require a future explicit FX contract. Dividends do not alter quantities or
require a current position, since an evidenced payment can arrive after a sale.
Their listing identity is still verified, locked and hash-bound, including a
companyless ETF or a security absent from current holdings. Provider action data
alone cannot create an account dividend. Automatic reinvestment requires a
separate evidenced purchase. Income, external funding and strategic targets keep
their distinct meanings. No yield, cost basis or performance is inferred.

An optional `ending_statement` contains an `effective_at` equal to `as_of` and
per-account observations with account ID, evidence, positions and cash. Its scope
uses the declared opening accounts. Every account, including empty accounts,
requires an ending observation. Unknown accounts/listings, duplicate rows/evidence,
invalid times and missing amounts fail closed. Per-account and consolidated
comparisons preserve missing/extra rows and explicit zeroes. Differences use
candidate minus observed. Portfolio totals cannot cancel account-level blockers.
Source document authenticity/completeness remains an operator review requirement.

- Opening accounts declare a broker or `UNALLOCATED_OPENING`. Source evidence
  must support the allocation. An unallocated opening can reconcile quantities
  and cash; subsequent activity requires an evidenced brokerage account.
- Each opening/account and activity row has a source document SHA-256 and stable
  source-record ID. Repeated source keys, activity IDs, sequence numbers and
  duplicate opening assets within an account are rejected.
- Quantities and amounts use exact decimal strings within existing canonical
  quantity limits. Missing, formula errors, floats, negative charges and nonfinite
  amounts are invalid. Fees and taxes require explicit amounts, including zero.
- Trades use exact canonical listing IDs. Companyless ETFs retain their security/
  listing identity. Gross cash is the observed settlement amount in listing currency.
  BUY subtracts gross cash, fees and taxes; SELL adds gross cash less fees/taxes.
  FEE and WITHDRAWAL subtract cash; DEPOSIT adds cash. No conversion is inferred.
- The opening must reproduce every observed quantity and native-currency cash
  row, including explicit zero rows. Missing and extra opening keys stay separate
  from numerical differences. A complete reconciled opening supplies the initial
  booking inventory; an evidenced new purchase/deposit may introduce a new asset.
- Activity is ordered by booking instant, then explicit sequence. It must be
  strictly after the opening boundary and within `as_of`. The source timestamp's
  UTC offset is preserved. Trade date must precede/equal settlement date, which
  must precede/equal the source-local booking date. Ambiguous or unsettled activity
  needs source correction/review before entering this contract.
- Each account must remain nonnegative after every booking. A later deposit or
  purchase cannot repair an earlier overdraft/short. Per-account and consolidated
  outputs must fit canonical storage bounds. Decimal arithmetic uses a controlled
  precision independent of the caller's context.

The preview preserves `anchor_recorded_at`. `as_of` is the economic booking cutoff
for a reconstruction using current evidence. Historical knowledge/performance
coverage requires its own reviewed contract. Source statement completeness,
broker allocation and settled-balance basis remain evidence/review requirements.

## Read-only API workflow

1. `GET /v1/portfolios/{portfolio_id}/ledger/anchor` returns the current complete
   observed opening snapshot, exact listing/security identities and `anchor_sha256`.
   After publication this remains the original reviewed opening anchor.
   Snapshot content/provenance and listing identity, currency and identity-source
   reference are hash-bound. Current partial/unavailable observations block preview.
   Future-effective or future-recorded snapshots cannot become the current anchor.
2. Prepare a private `PortfolioLedgerPreviewCreate` JSON using that snapshot ID/hash.
   Full fields are defined in OpenAPI and `portfolio_ledger_contracts.py`. Preserve
   source statements and evidence outside Git. Use explicit opening rows rather
   than inventing purchases, capital contributions, acquisition costs or brokers.
3. `POST /v1/portfolios/{portfolio_id}/ledger/preview` validates/replays those exact
   values. A changed current snapshot or identity invalidates the anchor with 409.
   A different portfolio cannot reuse it. Invalid activity/identity returns 422.
4. Review every opening comparison and blocking issue. `OPENING_RECONCILED` means
   opening values match and the candidate projection passes supported constraints.
   `BLOCKED` identifies opening differences, negative balances or storage overflow.
   Opening mismatches suppress projected balances. Intermediate failures remain
   blocking even if final balances recover.
   `ENDING_RECONCILED` additionally requires exact ending-account and total matches.
   `ending_status` distinguishes absent, matching, mismatched and unevaluated
   statements. A matching ending cannot clear an earlier booking failure.
5. Retain input and report privately. `input_sha256` binds version, anchor, accounts,
   evidence, ordered activity and all consumed listing identities. Reordering input
   collections preserves replay; changed financial values or provenance change the hash.
   Ending observations and their consumed listing identities join this binding.
   Opening-only packets retain their existing v1 input hashes.

Both endpoints run inside a PostgreSQL read-only, repeatable-read transaction.
The psycopg read-only setting is restored to its exact prior value when returning
the connection to the pool. Existing API authentication and database guards apply.

## Portfolio review screen

Open Portfolio → Ledger review (`/portfolio/ledger`). The guided opening review
collects explicit brokerage or unallocated opening accounts with source evidence,
exact listing quantities and native-currency cash. It starts with empty fields.
Reference holdings can be inspected while account allocation remains an evidenced
user declaration. Confirm the source balances use the displayed anchor date.
Edits reset that acknowledgement and invalidate the prior result.

Hash a nonempty statement up to 10 MiB locally with browser SHA-256, or enter an
existing document hash and source-record reference. Statement bytes remain local.
Reconciliation sends entered balances and evidence through the existing read-only
preview, bound to the verified snapshot/hash. Amounts retain decimal text and
explicit zeros. The opening uses v2 at the anchor instant with empty activity and
an absent ending statement. Native validation owns financial constraints and
comparisons. Acquisition basis remains unavailable. Clearing the draft removes
its in-memory accounts and cancels outstanding statement hash results.
An unchanged opening review JSON downloaded from this form can replace the draft
for the same anchor. Restoration preserves account IDs, exact amounts and evidence,
and requires the source-date confirmation again. Packets with activity, ending
statements, changed anchors or other fields use the existing file review workflow.

After a guided opening reconciles, the screen can add evidenced BUY, SELL, DIVIDEND,
DEPOSIT, WITHDRAWAL, FEE, TAX, CASH_TRANSFER and SECURITY_TRANSFER records for declared brokerage accounts. Each
record has an explicit type, sequence, settled timestamp with UTC offset, currency,
document hash and source-record reference. Trades additionally require a verified
anchor listing in its trading currency, exact quantity and gross settlement cash,
explicit fees and taxes (including zero), and trade and settlement dates. Dividends
require an anchor listing, gross cash, explicit fees and withheld taxes; the received
cash currency can differ from the listing currency. The API rejects charges above
gross cash. Record withheld tax once, using the same cash currency as the receipt.
No FX,
acquisition basis or historical transactions are inferred. The user supplies the
review cutoff. The API owns ordering, dates, balance and source validation and
calculates candidate balances. The activity draft must be discarded before its
opening or source file is changed. Revalidate an unchanged downloaded review JSON
to resume; account and record IDs, evidence and exact amounts remain intact.
Guided internal cash transfers require two evidenced brokerage accounts and
independently entered debit and receipt amounts, currencies, booking timestamps
and source keys. Security transfers likewise require two independent matching
listing/quantity observations and explicit acknowledgement that acquisition basis
is unavailable. The API verifies the legs and source holdings. Other activities,
listings outside the anchor or extra fields use the file workflow.

After a guided opening or supported activity review reconciles, the ending form accepts
independently entered positions, native cash and source evidence for every account
at the existing review cutoff. Fields start empty. The user confirms the observation
time, and the API distinguishes missing rows, explicit zeros and differences.
Edits invalidate the prior result. An unchanged downloaded guided ending packet
can be revalidated and reopened for editing when it reconciles or has only ending
observation differences. Restoration retains every source field and requires a new
cutoff confirmation. Discarding an edited ending returns the original packet for
revalidation. Packets the form cannot reproduce remain in the file workflow.
Preview cutoff and ending timestamps are compared at full fractional precision
across UTC offsets before a result is shown.

For activity and ending observations, prepare the typed ledger JSON and choose it
using the file control. Files stay in
page memory until explicit validation. The browser forwards the original financial
text to the API, with a 1 MB UTF-8 limit and existing authentication/origin controls.
UUID display metadata is normalized separately. Clearing/changing files cancels
pending requests and removes previous results.

The screen distinguishes opening/ending matches, blocked activity and missing
observations. Filter by comparison, account and differences, inspect exact native
values and source/hash evidence, or download the private report and exact review
JSON. The review JSON preserves its decimal text and stable account IDs for replay
and later evidenced additions. Missing rows retain
their explicit state beside zero balances. Account differences remain visible even
when portfolio totals match. A successful review remains a candidate result.

With the local API connected to an approved read target, the private-file workflow is

```powershell
$ledgerApi = 'http://127.0.0.1:8000/v1/portfolios/<portfolio-uuid>/ledger'
$reviewDirectory = Join-Path $env:LOCALAPPDATA 'PortfolioResearch/ledger-review'
# Use an existing private directory and prepare input.json after inspecting anchor.json.
Invoke-WebRequest "$ledgerApi/anchor" -OutFile (Join-Path $reviewDirectory 'anchor.json')
Invoke-WebRequest "$ledgerApi/preview" -Method Post -ContentType 'application/json' `
  -InFile (Join-Path $reviewDirectory 'input.json') `
  -OutFile (Join-Path $reviewDirectory 'preview.json')
```

## Durable candidate and review API

This locally verified API increment requires additive migration `a832e94d6f10`
after `9f2a6d4c81b7`. Its two tables retain immutable typed packets, saved previews,
source/input/packet/preview hashes and append-only terminal reviews. Production
migration requires a separately reviewed current-state recovery and owner authorization.
Readiness checks retain exact schema-head enforcement.

1. Obtain/review the read-only preview above. Submit `POST /v1/portfolios/{id}/ledger/candidates`
   with `submission_id`, required nullable `expected_base_candidate_id`,
   `expected_input_sha256`, a reason and the complete typed `proposal` packet.
   The first base is null. The server locks the portfolio and consumed identities,
   recalculates the packet and checks the exact source/input hash before storing it.
2. Inspect `GET .../ledger/candidates` and `GET .../ledger/candidates/{candidate_id}`.
   The bounded list exposes current accepted candidate/revision and summary metadata.
   Detail replays hash-verified saved input/output and reports added, changed and
   removed activity IDs plus opening-account changes relative to the explicit base.
   These reads use the existing read-only, repeatable-read dependency.
3. Submit `POST .../ledger/candidates/{candidate_id}/review` with `decision`,
   `expected_base_candidate_id`, `expected_input_sha256`, `expected_preview_sha256`
   and a reason. `REJECT` records a terminal rejection, including superseded candidates.
   `ACCEPT` additionally requires true `source_evidence_reviewed`,
   `account_allocation_reviewed`, `settled_balance_basis_reviewed` and
   `full_replacement_reviewed`, plus the exact `acknowledged_changed_activity_ids`
   and `acknowledged_removed_activity_ids` sets. Empty sets must be explicit.
4. Acceptance requires a fresh `ENDING_RECONCILED` result identical to the saved
   input and preview hashes and the still-current accepted base. Source/identity,
   calculation, anchor or base changes require a newly reviewed candidate.
   Blocked/opening-only candidates can be retained and rejected.
5. Corrections are complete replacement packets on the accepted base, retaining
   the opening anchor/hash, account ID set and a nondecreasing cutoff. Removed
   activity is excluded only from that new packet's projection after explicit
   acknowledgement. Original packets/reviews remain available. Canonical source
   snapshots and strategic targets retain their independent authority.

Every mutation is one atomic transaction. Shared portfolio/source locks serialize
review, canonical snapshot writers and workbook refreshes. Fresh locked identity
reads refresh retained ORM objects. Duplicate submissions are bound to canonical
packet content, portfolio, input hash, base and reason, independently of collection
order or caller submission ID. Exact replay returns the original receipt without
new records. Reusing an ID for different content, conflicting terminal decisions
or stale bases returns 409. A replay of historical receipt data grants no new approval.
The ORM protects both receipt tables from updates/deletes, following existing history
conventions. Database administrators remain outside this application authority boundary.

Remote requests use existing private-owner API authentication and database target
guards. Model proposal credentials grant no remote ledger access. Local development
retains the existing trusted-local authentication policy. The production write flag must be
separately authorized in the approved operator scope; it defaults to false.
The browser now exposes saving, candidate history and explicit decisions. After
validation, enter a candidate reason and save the exact source-bound packet.
Choose a saved candidate to inspect balances, account allocation, activity/source
records, hashes and base history, or download its private packet/receipt.
Acceptance requires individual source/account/basis/full-replacement checks and
separate acknowledgement of every changed/removed activity ID. Enter a rationale,
review the decision and confirm its input hash. Cancellation before confirmation
creates no review. A confirmed request may complete after navigation or a lost
response; reload history to inspect its terminal receipt. The client performs no
automatic mutation retries. Stale bases, conflicts and authorization failures stay
explicit, with fresh server checks at acceptance.

The `ledger-review` browser fixture permits only inserts into candidate/review
receipts in a verified loopback `_test` database and random test-owned schema.
Other HTTP mutations, canonical SQL writes, schema changes and cross-schema inserts
are rejected. Ordinary browser scenarios retain SQL read-only access. For a bounded
synthetic rehearsal, start `npm run test:e2e:api -- --scenario ledger-review
--lifetime-seconds 600` with child-process `BROWSER_API_PORT=8015`. Run
`node scripts/browser.mjs test portfolio-ledger-decisions.spec.ts --workers=1`
with `E2E_LEDGER_REVIEW_API=1`, matching loopback `API_BASE_URL`/`BROWSER_API_PORT`
and the local web port. Follow the existing [browser setup](codex-cloud-development.md#portfolio-data-rehearsal).
Normal fixture shutdown removes its own schema. Screenshots remain ignored.

## Dated ownership and holdings publication

`portfolio-ledger-publication-v1` is locally verified through the API and synthetic
Portfolio readback. Additive migration `b59f16c8a203` follows `a832e94d6f10` and
retains publication lineage, reviewed command, plan hash and resulting snapshot hash.
Production schema/application compatibility, a current-state recovery point and
separate owner authorization precede migration, deployment or publication.

1. Read `GET /v1/portfolios/{id}/ledger/candidates/{candidate_id}/publication-preview`.
   This is SQL read-only/repeatable-read. The candidate must be the current accepted
   revision with fresh, matching opening/ending evidence and exact source/calculation
   hashes. Review the current snapshot, proposed quantities/currency cash, account
   scope, original anchor and previous publication. Store the exact plan privately.
2. Scope is explicitly `WHOLE_PORTFOLIO`. The first effective cutoff is the packet's
   evidenced closing-statement time. Later publications retain that original cutover
   and opening, and require strictly later evidenced cutoffs. Existing snapshot
   uniqueness remains enforced. A same-cutoff correction can be reviewed in candidate
   history but needs a new closing observation before publication. Source/identity,
   accepted-base, current snapshot or plan changes require renewed review. Existing
   future snapshots block publication.
3. Prepare `LedgerPublicationCreate` with `expected_plan_sha256`, required nullable
   `expected_previous_publication_id`, the exact returned `confirmation_phrase`
   entered in `confirmation`, a rationale in `reason`, and explicit true
   `ownership_transfer_reviewed`, `whole_portfolio_scope_reviewed`,
   `current_state_recovery_verified` and `holdings_confirmation`. Recovery confirmation
   records the operator's attestation. It follows independent verification of actual
   recovery access/retention. Reading this contract grants no production authority.
4. After separately scoped approval, an authenticated operator may call
   `POST .../ledger/candidates/{candidate_id}/publish` through the existing API and
   database-target guard. In Portfolio ledger history, open the accepted candidate,
   load its read-only publication plan and review the exact before/after native
   balances. Enter a rationale and the returned typed phrase, explicitly attest the
   four ownership/scope/recovery/holdings checks, then review and separately confirm
   publication. Keep production write authorization false
   during preparation. The server rechecks the plan under shared portfolio/identity
   locks before atomically inserting one snapshot and one immutable receipt.
5. Read `GET .../ledger/ownership`, Portfolio overview and the returned receipt.
   Reconcile every quantity and native cash row, original snapshot, source hashes,
   previous publication and independent target revision. Publication timestamps are
   normalized to UTC for stable hash/replay, retaining effective/recorded distinctions.
   `ALREADY_PUBLISHED` returns the original plan/receipt identity. Exact command replay
   returns the original receipt; changed commands conflict. Failed transactions leave
   neither a snapshot nor an ownership receipt. No retry or recovery runs automatically.

After publication, normal observed/manual snapshot writes are blocked. Full workbook
sync previews report `HOLDINGS_OWNERSHIP_TRANSFERRED`; field-scoped workbook
reconciliation remains future work. Acquisition and other independent domain review
paths retain their existing contracts. Portfolio displays ledger ownership and routes
review to ledger history. An unlinked snapshot cannot silently supersede the ledger
read model. Earlier snapshots and point-in-time visibility remain available.
Downgrade fails closed once publication history exists. Rolling back to code that
lacks this ownership boundary requires a separately reviewed recovery/release plan.

For read-only UI rehearsal use the existing browser server with `--scenario
ledger-owned --lifetime-seconds 180`, `BROWSER_API_PORT=8016`, and matching loopback
`API_BASE_URL`. Run `portfolio-ledger-ownership.spec.ts` with
`E2E_LEDGER_OWNERSHIP_API=1`. Seeding publishes only synthetic records inside the
verified local test schema before serving; all browser requests then use SQL
read-only access. Normal shutdown removes that fixture's schema.

For the publication UI rehearsal use `--scenario ledger-publication
--lifetime-seconds 120`, `BROWSER_API_PORT=8017` and matching loopback
`API_BASE_URL`. Run `portfolio-ledger-publication.spec.ts` with
`E2E_LEDGER_PUBLICATION_API=1`, reusing the local web server and selecting one
Playwright project per fresh fixture. Seeded acceptance is fictional. During
serving only the exact seeded portfolio/candidate's publish route can write,
using compiled inserts into snapshot/position/cash/publication tables within the
verified loopback `_test` schema. Candidate decisions and every unrelated mutation
remain blocked. The original opening, targets and other table counts are protected.
Desktop exercises normal confirmation; mobile simulates a response lost after the
actual isolated commit and verifies the immutable receipt through read-only checks.
Plan/source conflicts and missing server authorization clear all approval inputs.
No publication retry runs automatically. Use normal bounded server shutdown so
only its own schema is removed. Screenshots remain ignored.

## Remaining acceptance gates

The publication approval UI is LOCAL_VERIFIED with synthetic desktop/mobile
journeys. Real account/source scope review, milestone integration checks and
production ownership activation remain outstanding.
Cost lots, gains, TWR/XIRR, dividends, transfers, executed FX and broker imports
require their documented contracts and evidence. Opening quantities supply an
inventory boundary. Historical cost and capital flows require separate source evidence.

Production cutover requires separately reviewed account/basis/source scope, zero
unexplained reconciliation differences, ownership policy, schema/write authorization
and a verified current-state recovery procedure. A successful preview grants no
production or investment authority.
