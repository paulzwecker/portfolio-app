# Active workstream

## C2.3 settled income and internal cash transfers — BUILD

Continue branch `codex/portfolio-ledger-income`, based on main `deda2ce`, the merge
of [PR #26](https://github.com/paulzwecker/portfolio-app/pull/26). No open PR is
present for this milestone. Predecessor branches, stash and private artifacts are
preserved. Income was committed through `0a57454`; transfer implementation starts
at `7e3b82b`. This is a BUILD checkpoint, with integration/PR work still deferred.

## Operational scope in isolated development

The existing preview → saved candidate → explicit review → separate publication
workflow supports v2 DIVIDEND, TAX and paired CASH_TRANSFER records. V1 and existing
v2 hashes/replay remain compatible. Exact behavior lives in the
[ledger contract](portfolio-ledger.md).

- Income uses observed settlement currency, explicit gross, fees and withholding.
  Listing quote currency stays independent. No payout, FX or reinvestment is inferred.
- Internal cash transfers require equal amounts/currency and the same settled
  instant across two declared brokerage accounts. Both source keys are mandatory,
  duplicate-checked, hash-bound and retained in review/correction history.
- Transfers preserve consolidated cash and all quantities. Account reconciliation
  and intermediate overdrafts remain blocking. Different-time settlement,
  cross-currency, outside-portfolio and security transfers require later contracts.
- Candidate acceptance preserves canonical holdings/targets. Publication retains
  its separate typed confirmation, ownership/recovery attestations and DB guard.

## Verification

- 113 focused ledger units pass, including exact conservation, missing/zero,
  precision, source reuse, mismatched legs, overdrafts and account reconciliation.
  The historical v2 income hash and every output match pre-transfer `0a57454`.
- 78 web contract/proxy/publication tests pass. Original financial text and both
  transfer evidence records survive source-file inspection and saved replay.
- The 76-case PostgreSQL sweep passed 75 and exposed an order-only income assertion.
  Exact identity-keyed quantities plus row counts replace the ordering assumption;
  all six affected income/transfer lifecycle cases pass on rerun. These prove
  preview immutability, explicit review/publication, idempotency, rollback,
  changed-receipt acknowledgements and rejected packets leaving no records.
- Two real-API desktop/mobile transfer journeys pass with exact ten-place values,
  account drill-down, both source records and explicit review/readback. Protected
  canonical-state hashes are unchanged. Visual inspection confirms wrapping and
  no horizontal overflow. The bounded fixture removed its own schema on shutdown.
- Strict backend mypy covers 215 source/test files. Web types/lint, generated
  contracts, formatting and documentation checks pass. Independent review retains
  scope, evidence, identity and authorization invariants. No new migration is needed.

## Next action

Income and paired-cash-transfer slices are IMPLEMENTATION_COMPLETE and
LOCAL_VERIFIED. Continue with evidenced same-listing security transfers between
declared accounts, retaining exact quantities and explicit unavailable acquisition
basis/gains. Both account statements must reconcile. Broker onboarding needs a
reviewed first format/private sample; lot, FX and performance policy stay separate.
Use focused checks and incremental commits. Reserve comprehensive testing and one
cohesive PR for the settled-ledger integration milestone.

## Separate operational gates

Cloud state was not reverified. The merged release's reviewed chain remains
`9f2a6d4c81b7` → `a832e94d6f10` → `b59f16c8a203`. Follow
[native release/migration controls](deployment-and-migrations.md), with fresh
current-state recovery protecting accepted holdings before separately authorized
migration/deployment. The historical empty pre-import branch is insufficient.
Production writes, provider activation, ledger ownership and model acceptance keep
their separate gates. Local production/rehearsal/background flags remain disabled.
Highest-value operational follow-up is held-listing price/FX enrichment and two
monitored refresh cycles, followed by reviewed SEC identities and coverage.
