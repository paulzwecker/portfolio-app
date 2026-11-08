# Active workstream

## Historical market-data reliability integration

Branch `codex/market-history-coverage` includes current `origin/main` at
`aef35724120d63d608d6ffdc6f10f88d41eff27f`. The working checkpoint before integration
was `f28b1e2`. Repository visibility is public. Preserve predecessor worktrees,
the owner edits and private evidence. No PR existed at the start of this review.

This engineering checkpoint delivers an investor investigation workflow through
Company Explorer and Operations. It includes source-stream/adjustment conflicts,
searchable returned observations, bounded schedule review, provider diagnostics,
run-pinned pagination and explicitly requested checkpoint reconciliation.

## Integration acceptance

- Verify ordinary entry points, API authentication and PostgreSQL read-only behavior.
- Run repository checks, relevant PostgreSQL integration tests and desktop/mobile
  browser coverage. Inspect synthetic screenshots and fix review findings.
- Confirm migration files and model metadata stay compatible with the production
  schema contract. Record fresh live evidence separately from the recorded marker.
- Publish one cohesive PR after local acceptance. Owner review controls merging.

The engineering checkpoint is IMPLEMENTATION_COMPLETE and LOCAL_VERIFIED.
`npm run check` passed with 333 web tests, 929 backend units and two skips.
Relevant PostgreSQL integration covered 112 cases across the initial selection
and a focused rerun after fixture corrections. The full managed browser run passed
95 cases with 35 explicit fixture/live-only skips. The affected Operations journey
passed again at desktop/mobile widths. Synthetic screenshots were visually reviewed.

The second-pass review added alert checks for known adjustment labels and listing
currency, plus HTTP authentication/read-only transaction coverage. It corrected
fixture URL/receipt typing, auth-mode configuration and a numeric-correction fixture
to retain its economic adjustment basis. Mypy passes all 223 source/test files.

## Release assessment

Current classification is **BLOCKED** pending fresh production target verification.
The existing read-only guard returned `read_target_preflight_failed` with an underlying
PostgreSQL connection `OperationalError`. The recorded schema attestation is
`b59f16c8a203`; this branch adds no migration. Provider configuration and production
alias enforcement still require current verification at release time.

Fresh Render read-only inspection found the intended `portfolio-api` service on
`main`, live deployment `dep-dbobrqbl550s7399afg0` at `aef3572`, and Auto-Deploy
enabled with `checksPass`. This supersedes the older freeze observation. Vercel
plan/check enforcement and Blueprint sync were unavailable in this inspection.

Follow the existing [deployment runbook](deployment-and-migrations.md). Hosted
setting changes, live provider activation, recovery operations and model acceptance
retain separate owner approvals. C2.2's hosted ingestion and two monitored refresh cycles
remain outstanding operational acceptance criteria.

## Next action

Publish the single integration PR as draft while the live target check is blocked.
Owner review and fresh release verification precede merging. Additional venue schedules
require reviewed source evidence. Detailed earlier evidence and production recovery
history remain in the [historical handoff](history/market-history-build-through-2026-11-08.md).

Canonical behavior lives in [market data](market-data.md),
[historical bootstrap](historical-market-data-bootstrap.md),
[attention](attention-center.md) and the [roadmap](../ROADMAP.md).
