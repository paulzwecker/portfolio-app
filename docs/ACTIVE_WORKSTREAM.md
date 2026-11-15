# Active workstream

## Free analyst expectations — frozen local slice, 2026-11-15

`codex/free-expectations` is stacked on `codex/official-fx-valuation` (`b432335`),
which retains frozen [PR #39](https://github.com/paulzwecker/portfolio-app/pull/39)
head `69371f1`. Preserve that independently reviewed SEC milestone. This work has
no competing PR; reconcile the stack after owner integration. Main remains
`866723e`. Owner worktree edits, branches and stash remain untouched.

### Frozen outcome and source truth

One exact Amazon/NASDAQ/USD mapping → documented free EODHD demo → existing
immutable consensus storage → API → Company Explorer Financials. No new queue,
table, migration, paid dependency, guidance framework or production activation.

One authorized public demo request on November 15 at 00:51:48 UTC produced eight
real observations: revenue and EPS for FY2026, FY2027, FY2026 Q4 and FY2027 Q1.
Means, analyst ranges and counts are retained. Four revenue observations are
eligible; four EPS observations remain DATA_CHECK because accounting basis is
unverified. Forty-seven ended-period rows are excluded. One snapshot establishes
no historical revision series; relative EPS lookback fields are not dated history.

USD is supported only for this constrained issuer by independently reviewed USD
reporting/listing identity and the provider's reporting-currency endpoint policy.
The conflicting generic CurrencyCode wording is disclosed in the canonical
[consensus reference](consensus-estimates.md#bounded-eodhd-private-evaluation-2026-11-15)
and observation evidence; never generalize it to ADRs or other issuers.
Demo evaluation/storage is permitted, but production entitlement and sustainable
broader coverage are not established. Authentic payloads, values and screenshots
remain in the private report store, never public Git.

### What works and verification

`CONSENSUS_PROVIDER=eodhd_demo_estimates` is explicit and isolated-only. Existing
external-ingestion CLI and scheduled entry share durable runs, exact frozen identity,
advisory locking and a one-request/ten-credit bound. Missing mappings, identity
changes and production targets stop before fetch. Partial receipts expose EPS
uncertainty and unmapped companies. Replays cannot replace a provider. Default FMP
configuration and existing activation gates remain unchanged.

The source-backed isolated PostgreSQL/API check verifies all eight raw values,
ranges/counts, annual/quarterly periods, per-observation freshness, immutable
retrieval time, same-day reuse, later scheduled replay, pre-capture knowledge cutoff
and unchanged full-content hashes of unrelated tables. The later replay uses the
same recording, not a new source observation. Fictional research context is never
presented as the owner's production portfolio. The browser is read-only; no new
consensus UI refresh action or unattended timer is enabled.

Desktop/mobile browser journeys pass in light/dark themes: chartable revenue,
explicit uncertain EPS, sources/ranges/counts, reload persistence, no page errors
or overflow and unchanged protected state. Independent accounting/ingestion review
found no remaining blocker. Reproduction: [private rehearsal](testing.md#private-consensus-source-rehearsal).

Final checks: 1,059 backend unit tests (two skips), 500 web tests, 62 relevant
PostgreSQL/adapter checks, the private source-backed API replay and two real-source
desktop/mobile journeys pass. Lint, formatting, Python/TypeScript types, OpenAPI
contracts, production frontend build, documentation/source-data policy and 21
deployment checks pass. Review/deploy schema gates match `b59f16c8a203` with no
pending revision and unchanged fingerprint
`de9fb593f76ec72261ef40bb3d88a12751b0e114c81fc48f08f96dee48be73f2`.
The fresh feature branch has no remote CI claim; those are local verification results.

### Release and operational boundary

**CONFIGURATION_REQUIRED for release; production ingestion NOT STARTED.** No
schema or API-shape changes in this increment. The inherited market slice requires
API-first deployment for its additive fields. Current hosted commits/control
settings were not reverified, so this is not SAFE_TO_MERGE_AND_DEPLOY or a deployment
approval. Production demo execution is deliberately rejected.

The latest production readback remains the prior November 15 00:18 UTC guarded
check: exact target/schema `b59f16c8a203`, canonical receipt, 22 holdings and two FX
pairs matched; prices, FX, corporate actions, facts, filings and estimates were all
zero. No fresh production query or write occurred in this estimates run. Accepted
holdings, cash, targets and models remain unchanged.

Production still needs an approved encrypted off-provider backup destination, key
custody and isolated restore target, then the existing guarded backup/restore
rehearsal. The expiring Neon branch is not durable recovery. No source, cloud,
credential, Sheets, model-acceptance or scheduler setting was changed.

### Next and deferred

Next highest-value outcome: execute the already-prepared real SEC and ECB scopes
once exact mapping/source and recovery approvals exist. Agent 7's isolated 255 AMZN
native closes and 518 ECB FX observations through November 13 remain preserved on
the parent branch. Do not expand this narrow estimates slice while those operational
gates wait. Broader lawful free estimates, verified EPS basis, actual/model
comparisons and real prospective revisions remain explicit coverage gaps, not
mandatory blockers for the demonstrated local workflow.
