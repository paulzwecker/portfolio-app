# Active workstream

## C2.3 observed dividends and tax activity — BUILD

Branch `codex/portfolio-ledger-income` starts from main `deda2ce`, the verified
merge of [PR #26](https://github.com/paulzwecker/portfolio-app/pull/26).
No open PR was present at this run's start. Predecessor branches, stash and private
artifacts are preserved. The consolidated release's verification remains in
[dated history](history/data-ledger-build-through-2026-11-08.md) and PR #26.

## Outcome and scope

Extend the existing ledger preview/review/publication workflow with evidenced
account DIVIDEND receipts, explicit withholding/fees and standalone TAX debits.
Use existing exact-decimal accounting, identity locks and immutable receipts.
`portfolio-ledger-preview-v2` / `settled-booking-v2` explicitly opts into income.
V1 packets and hashes remain compatible. See the
[ledger contract](portfolio-ledger.md#observed-income-and-taxes).

Gross, fees and withholding use the observed settlement currency. Quote currency
is independent. No provider payout inference, automatic FX, position change or
reinvestment is introduced. A paid-after-sale dividend can reference an existing
unheld listing; the exact identity remains locked and hash-bound. Companyless ETFs
retain their own identity. Source review must catch overlapping statement evidence.

## Verified increment

- 93 focused ledger unit tests pass, including v1 hash replay, v2 opt-in, exact
  precision, full withholding/zero, native currencies, missing/error values,
  income-only identity binding and tax-before-income overdraft detection.
- 77 focused web contract/proxy/publication tests pass. API contracts regenerated.
- 73 focused PostgreSQL ledger API/review/publication cases pass on independently
  verified loopback `_test` infrastructure and disposable schemas. New coverage
  proves income preview leaves records unchanged, review is explicit, publication
  changes only the intended snapshot/cash with exact replay, failed publication
  rolls back flushed records, and income-only identity drift blocks acceptance.
- Two real-API desktop/mobile income journeys pass through the existing Next.js
  proxy, including exact 10-place values, evidence, review confirmation and readback.
  Protected canonical-state hashes remain unchanged. Visual inspection confirms
  readable wrapping and no horizontal overflow. Fixture shutdown removes its schema.
- Backend strict mypy passes all 213 source/test files without incremental cache.
  Web lint/typecheck, generated contract check and documentation checks pass.
- Independent review preserves v1 hashes/outputs, source/identity locks, explicit
  paid currency and withholding, and separate acceptance/publication authority.
  Only synthetic local verification was performed; no real account data was used.

## Next action

This income slice is IMPLEMENTATION_COMPLETE and LOCAL_VERIFIED. Continue the
ledger milestone with paired, evidenced same-currency internal cash transfers
between declared accounts. Preserve per-account checks, consolidated conservation,
source lineage and the existing review/publication gates. Broker imports still
need a reviewed first format and real private sample; lot/FX/performance policy
remains separate. Use focused tests and incremental commits. No PR or full-suite
integration was performed during this BUILD increment.

## Independent release gates

The merged release requires the additive schema chain `9f2a6d4c81b7` →
`a832e94d6f10` → `b59f16c8a203`. This run does not establish current cloud state.
Follow [native release/migration controls](deployment-and-migrations.md) with fresh
current-state recovery protecting accepted holdings before separately authorized
migration/deployment. The historical empty pre-import branch is insufficient.
Income support adds no schema migration and grants no production write authority.
Provider enrichment/refresh, ledger ownership and investment acceptance retain
separate approvals. Local production/rehearsal/background flags stay disabled.

Highest-value operational follow-up remains held-listing price/FX enrichment and
two monitored refresh cycles, followed by reviewed SEC identities and coverage.
