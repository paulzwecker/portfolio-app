# Active workstream

## C2.3 settled multi-account ledger — BUILD checkpoint complete

Continue branch `codex/portfolio-ledger-income`, based on main `deda2ce`, the merge
of [PR #26](https://github.com/paulzwecker/portfolio-app/pull/26). No open PR exists
for this milestone. Preserve all predecessor branches, stash and private files.
Income was committed through `0a57454`, cash transfers through `c9f58d7`, and
security-transfer implementation starts at `35c902e`.

## Current operational priority — schema recovery prepared

November 8 read-only investigation confirms Render rejected main `deda2ce` and
continues serving healthy `395f842`; Vercel production already serves `deda2ce`.
Owner health readback is OK, but the ledger page reports missing records and the
expected Render ledger-anchor endpoint returns 404. Candidate logs contain 85
schema mismatches. Neon remains `9f2a6d4c81b7`, with the accepted 209 companies,
22 positions, two cash rows and 16 targets totaling 1. Existing recovery is empty
and predates import. Private full inventory and 11 canonical content fingerprints
are retained outside Git. Automated authenticated browser inspection was blocked.

The [release runbook](deployment-and-migrations.md) records evidence, exact
read-only preflight and owner-gated freeze → fresh populated recovery → migration
→ reconciliation → native deployment. Repository-only schema attestation/gate is
LOCAL_VERIFIED with 16 deployment-policy checks, 55 readiness/preflight tests and
three disposable PostgreSQL migration/replay tests. Docs and privacy checks pass.
Applied migration history matches all 57 files in the live API commit.
The marker stays at the verified old head, so `deploy` deliberately fails closed.
No provider setting, recovery branch, schema, canonical row or authorization changed.
Keep this correction on the same milestone branch; no separate minor PR.

Next owner action is review/authorization of the deployment freeze and fresh
recovery creation. Migration and controlled deployment retain separate approvals.
The Vercel schema hook needs reviewed operator installation; local code alone
does not activate it. Resume the ledger INTEGRATE checkpoint below independently,
including this safeguard in the one cohesive PR.

## Complete bounded scope

The existing preview → saved candidate → explicit review → separately confirmed
publication workflow supports v2 DIVIDEND, TAX, CASH_TRANSFER and SECURITY_TRANSFER.
Exact contracts live in the [ledger reference](portfolio-ledger.md).

- Income uses observed settlement currency and explicit gross/fees/withholding.
  Native cash and quote currency retain their independent meaning.
- Paired transfers require two declared brokerage accounts and independent source
  records. Both legs match the same settled instant and exact amount/currency or
  listing/quantity. Evidence is duplicate-checked, hash-bound and reviewable.
- Cash transfers conserve portfolio cash; security transfers conserve portfolio
  quantities and all cash. Account-level reconciliation and chronological overdraft/
  short-position checks remain blocking, including full-transfer explicit zero rows.
- Security transfers require `basis_status=UNAVAILABLE`. Retain original lot/cost
  evidence privately for future reviewed accounting. Native dates/costs/gains stay
  unavailable. Cross-listing/ADR conversion, in-transit, external and FX transfers
  remain follow-on contracts. Fees/taxes need separately evidenced cash records.
- Candidate acceptance retains canonical snapshot/target authority. Publication
  keeps its independent typed confirmation, recovery/ownership attestations and
  database guard. No new schema migration is introduced by this branch.

## Verified checkpoint

- 135 focused ledger units pass. Exact precision, missing/zero states, matching
  legs, duplicate source keys, ordering, listing/basis rejection and conservation
  are covered. Historical v1 trade, v2 income and v2 cash-transfer replay matches
  every output field from `c9f58d7`; existing frozen v1/v2 hash tests pass.
- All 79 focused PostgreSQL API/review/publication/income/transfer cases pass in
  independently verified loopback `_test` schemas. They cover immutable previews,
  explicit review, publication/replay, rollback, source/identity drift, correction
  acknowledgements and malformed packets leaving no records or receipts.
- 79 web contract/proxy/publication cases pass. Both evidence records and original
  financial text survive inspection, staging and readback.
- Two real-API desktop/mobile security-transfer journeys pass, with exact ten-place
  quantities, account drill-down, unavailable basis and both source records. The
  protected canonical-state hash is unchanged during review. Visual inspection
  confirms readable wrapping and no horizontal overflow. The bounded fixture
  removed its own schema on normal shutdown. Earlier income/cash browser evidence
  is recorded in the preceding commits.
- Strict backend mypy passes 217 source/test files. Web lint/types, generated
  contracts, formatting, documentation links/tests and whitespace checks pass.
- Independent review preserves identity, evidence, financial/ownership separation
  and production authorization. This is synthetic/local verification only.

## Next action — INTEGRATE

The bounded settled-ledger BUILD scope is IMPLEMENTATION_COMPLETE / LOCAL_VERIFIED.
Safely fetch/reconcile latest main, run `npm run check`, the full applicable isolated
PostgreSQL selection and combined responsive/authenticated browser regressions.
Inspect final contracts, compatibility and privacy, fix findings, then push this
branch and open ONE cohesive PR for income/tax and paired account transfers.
Freeze the passing candidate for owner review. Broker imports, normalized account
management, lots/gains, FX/in-transit rules and genuine TWR/XIRR remain subsequent
capabilities with their own source/policy dependencies.

## Separate operational gates

Cloud state was reverified read-only above. The merged release's reviewed chain remains
`9f2a6d4c81b7` → `a832e94d6f10` → `b59f16c8a203`. Follow
[native release/migration controls](deployment-and-migrations.md), with fresh
current-state recovery protecting accepted holdings before separately authorized
migration/deployment. The empty pre-import recovery branch is insufficient.
Production writes, provider activation, source ownership and model acceptance keep
separate gates. Local production/rehearsal/background flags stay disabled.
Highest-value operational follow-up remains held-listing price/FX enrichment and
two monitored refresh cycles, followed by reviewed SEC identities and coverage.
