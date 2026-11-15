# Active workstream

## Free market/FX vertical slice — 2026-11-15

Branch `codex/official-fx-valuation` is based on `69371f1` from the completed,
frozen [PR #39](https://github.com/paulzwecker/portfolio-app/pull/39). Preserve that
SEC review and its commits. This independent market slice has no competing PR;
integrate after the owner resolves #39. Main remains `866723e`. Other worktrees,
owner edits and the existing stash remain intact.

Frozen acceptance: one exact held listing with permitted real daily observations,
USD/EUR and DKK/EUR reference history, durable manual and scheduled ingestion,
canonical reconciliation, honest native-price charts and current EUR valuation.
No broad universe/provider framework, new tables, migrations or paid dependency.

### Source and production truth

Fresh guarded production read-only verification at 00:18 UTC on November 15 passed:
exact configured Neon primary identity, schema `b59f16c8a203`, accepted canonical
receipt, 22 held listings matching the existing crosswalk, two required FX pairs,
and the approved 2025-11-10–2026-11-09 window. It planned 24 logical requests but
made zero provider requests/writes. Production still has **zero prices, FX,
corporate actions, fundamentals, filing references and estimates**; 22 positions,
two cash rows, one target revision and 16 targets are preserved. Exact evidence
and identities remain in the private report store.

EODHD's documented no-signup demo supplies AMZN.US, the only held listing in its
reviewed equity demo set. Exact NASDAQ/USD/common-stock metadata and Amazon CIK
agree with the canonical listing and official SEC cover. Four bounded source
requests captured metadata, history, incremental history and empty split evidence.
Private evaluation/storage is permitted; data, screenshots and derived outputs
must not enter public Git. Demo access is not approved production entitlement.
ECB's official bounded CSV service permits free reuse with attribution and explicit
reciprocal-conversion disclosure. Six requests included one DKK timeout, which was
retried once; five succeeded. No accounts, paid tiers or cloud changes were used.

| Isolated canonical coverage | Initial window             | After controlled increment |
| --------------------------- | -------------------------- | -------------------------- |
| AMZN native daily closes    | 251, 2025-11-10–2026-11-09 | 255 through 2026-11-13     |
| USD/EUR reference rates     | 255, same window           | 259 through 2026-11-13     |
| DKK/EUR reference rates     | 255, same window           | 259 through 2026-11-13     |

Source bytes/timestamps are retained unchanged in private replay. No weekend rows
are fabricated. Portfolio quantities, cash and targets in the isolated example
are explicitly fictional; its EUR value is not the owner's production value.

### Implementation and verification

`FX_PROVIDER=ECB_REFERENCE` explicitly selects the new narrow adapter; existing
Yahoo defaults remain unchanged. `MARKET_DATA_PROVIDER=EODHD_DEMO` supports only
the reviewed isolated AMZN example and rejects production configuration/execution.
Manual requests and the existing `cloud_cron --scope public-market-data` share
provider services, durable daily ingestion identity, advisory locks and bounded
retries. The scope drains at most one eligible request and excludes SEC, FMP,
Sheets, models and research jobs. With only ECB selected it performs FX only.
No scheduler is registered; an existing-host daily trigger remains owner-gated.

Native close and total-return-adjusted price remain distinct; split-adjusted close
stays unavailable. Current position value may use an explicitly validated native
close times current quantity, then dated FX. Native history is separate from
split-adjusted analytics/models/IRR. Missing, conflicting or stale data remains
unavailable. The approved history alone is stale on November 15; the controlled
increment establishes current isolated valuation. Pre-capture historical queries
cannot see later observations. ECB original units per EUR are preserved and
converted reciprocally to EUR per foreign unit, rounded to canonical precision.

Local source-backed API acceptance passes: manual queue → provider replay →
PostgreSQL → API, then a scheduled incremental pass, same-day reuse, exact EUR
position/cash/portfolio reconciliation, unchanged protected-table content hashes.
Focused failures cover currency conflicts, unavailable pairs, no Yahoo fallback,
nonretryable single attempts and bounded retryable attempts. An existing retry
loop's missing terminal return was fixed after a failing test proved redundant
nonretryable requests. Independent review also fixed latest and historical native
price conflicts: unresolved latest evidence withholds valuation; an older conflict
withholds only the chart. Explicit corrections retain knowledge-cutoff semantics.
Frozen identity drift fails before any provider fetch or observation write.

Verification: 1,038 backend unit tests, 495 web tests, 143 selected PostgreSQL
integration checks, and 19 final source-replay/identity/native-valuation checks pass.
Desktop and mobile UI journeys pass with light/dark visual review: queued identity
survives navigation/reload, new observations update charts/values, delayed scheduled
work executes once, same-day repeats add no calls or rows. Private screenshots and
API readbacks remain outside Git; test schemas and servers were cleaned up.
Types (246 Python files and TypeScript), lint, formatting, OpenAPI contracts, frontend
production build, documentation, source-data policy and 21 deployment checks pass.
Review/deploy schema gates match `b59f16c8a203` with no pending revision and unchanged
migration fingerprint `de9fb593f76ec72261ef40bb3d88a12751b0e114c81fc48f08f96dee48be73f2`.
The private replay preserves actual capture times: future freshness checks require
a contemporaneous source bundle, not retimestamped observations.

### Release and next action

**CONFIGURATION_REQUIRED; production data operations NOT STARTED.** No migrations
or production changes. New API fields are additive/defaulted; deploy API before
using new native-price UI behavior. Hosted commit/control attestation remains
unverified this run. PR #39 remains unchanged and owner-controlled. Latest remote
main is already an ancestor; the separate feature branch is preserved for review
after #39, with no competing PR and no remote CI claim for this new slice.

The first operator action is still approval of the encrypted off-provider backup
destination, key custody and isolated restore target, then the existing guarded
backup/restore rehearsal. The old Neon branch expires November 15 at 14:18 CET
and is not durable recovery. ECB production source selection and a precise FX-only
write scope need separate approval; do not relabel it as the approved Yahoo run.
EODHD demo remains isolated-only. The other 21 held listings lack verified free
price coverage; do not silently fall back to Yahoo or paid data. SEC activation
proposals from #39 remain ready for separate mapping/recovery approval.

Next highest-value task: activate the reviewed ECB FX-only scope after recovery,
and establish permitted non-demo equity coverage for exact held instruments.
