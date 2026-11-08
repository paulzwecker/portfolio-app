# Candidate portfolio ledger

C2.3 implements source-bound opening/ending reconciliation, settled-activity
projection and durable candidate/review receipts. [The roadmap](../ROADMAP.md) owns delivery status and
[Portfolio architecture](architecture/portfolio-application.md#transaction-ledger-transition-planned)
owns cutover/ownership boundaries. Canonical observed snapshots and independent
strategic targets retain authority.

## Contract and scope

`portfolio-ledger-preview-v1` accepts one current complete snapshot, explicit
opening accounts/balances and up to 1,000 activity records. It permits 20 accounts,
1,000 opening position rows and 100 opening cash rows across those accounts.
`settled-booking-v1` supports BUY, SELL, DEPOSIT, WITHDRAWAL and FEE.

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
   observed snapshot, exact listing/security identities and `anchor_sha256`.
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

Open Portfolio → Ledger review (`/portfolio/ledger`). Download the private anchor,
prepare the typed ledger JSON and choose it using the file control. Files stay in
page memory until explicit validation. The browser forwards the original financial
text to the API, with a 1 MB UTF-8 limit and existing authentication/origin controls.
UUID display metadata is normalized separately. Clearing/changing files cancels
pending requests and removes previous results.

The screen distinguishes opening/ending matches, blocked activity and missing
observations. Filter by comparison, account and differences, inspect exact native
values and source/hash evidence, or download the private report. Missing rows retain
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

## Remaining acceptance gates

Dated ownership cutover and current-holdings integration remain outstanding.
Cost lots, gains, TWR/XIRR, dividends, transfers, executed FX and broker imports
require their documented contracts and evidence. Opening quantities supply an
inventory boundary. Historical cost and capital flows require separate source evidence.

Production cutover requires separately reviewed account/basis/source scope, zero
unexplained reconciliation differences, ownership policy, schema/write authorization
and a verified current-state recovery procedure. A successful preview grants no
production or investment authority.
