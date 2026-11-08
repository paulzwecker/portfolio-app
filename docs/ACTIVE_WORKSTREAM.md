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
- Focused backend mypy and frontend typecheck pass.
- Durable review/publication, rollback and responsive real-API browser evidence
  remain the next required checks. This is implementation/local evidence only.

## Next action

Add synthetic PostgreSQL lifecycle/rollback regressions, complete exact record
presentation and desktop/mobile real-API review, then record a reviewed BUILD
checkpoint. Use focused tests. No PR or full-suite integration during this increment.

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
