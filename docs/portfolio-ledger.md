# Candidate portfolio ledger

C2.3's first slice implements a read-only, source-bound opening reconciliation and
settled-activity projection. [The roadmap](../ROADMAP.md) owns delivery status and
[Portfolio architecture](architecture/portfolio-application.md#transaction-ledger-transition-planned)
owns cutover/ownership boundaries. Canonical observed snapshots and independent
strategic targets retain authority.

## Contract and scope

`portfolio-ledger-preview-v1` accepts one current complete snapshot, explicit
opening accounts/balances and up to 1,000 activity records. It permits 20 accounts,
1,000 opening position rows and 100 opening cash rows across those accounts.
`settled-booking-v1` supports BUY, SELL, DEPOSIT, WITHDRAWAL and FEE.

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
5. Retain input and report privately. `input_sha256` binds version, anchor, accounts,
   evidence, ordered activity and all consumed listing identities. Reordering input
   collections preserves replay; changed financial values or provenance change the hash.

Both endpoints run inside a PostgreSQL read-only, repeatable-read transaction.
The psycopg read-only setting is restored to its exact prior value when returning
the connection to the pool. Existing API authentication and database guards apply.

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

## Remaining acceptance gates

This slice has no ledger persistence, acceptance, cutover or current-holdings switch.
It provides candidate balances and opening comparisons. Ending broker-statement
reconciliation, a review UI, durable revisions/receipts and transaction correction
semantics remain follow-up work. Cost lots, gains, TWR/XIRR, dividends, transfers,
executed FX and broker imports require their documented contracts and evidence.
Opening quantities never establish historical cost or capital flows.

Production cutover requires separately reviewed account/basis/source scope, zero
unexplained reconciliation differences, ownership policy, schema/write authorization
and a verified current-state recovery procedure. A successful preview grants no
production or investment authority.
