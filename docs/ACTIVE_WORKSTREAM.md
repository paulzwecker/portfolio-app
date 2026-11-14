# Active workstream

## Investment return hurdle explorer - acceptance frozen (2026-11-14)

Branch `codex/investment-decision-cockpit` starts at main `866723e`, after owner-merged
PR #38. [PR #39](https://github.com/paulzwecker/portfolio-app/pull/39) is the independent,
completed SEC refresh slice and stays frozen. This work is preserved separately for
later integration; it will not be mixed into that PR or open a competing PR while
it remains open. Owner edits, stash, worktrees and accepted history remain intact.

### Discovery decision

| Rank | Investor workflow                             | Decision value / reuse / correctness / delivery / data dependence                                 |
| ---- | --------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| 1    | Accepted model to required-return entry price | High value; existing native engines; explicit reversible analysis; no market feed needed          |
| 2    | Research changes and return attribution       | Useful, but existing history and four-factor attribution already deliver most of it               |
| 3    | Actuals versus accepted model and consensus   | Valuable but explicit native fiscal anchors and source observations are missing; never infer them |
| 4    | Compare candidates with holdings              | Existing method-aware Decisions comparison and allocation context already cover this              |

### Frozen acceptance

- Company/Portfolio -> exact native model in Valuation -> explicit hypothetical
  required return and optional entry price -> explainable backend result.
- Reuse accepted DCF (including H-model), owner-cash-flow and residual-income
  return streams. Keep probabilities, terminal proceeds, timing, share basis and
  all accepted assumptions fixed. Enterprise return never becomes shareholder IRR.
- Show the required entry price, Bear/Base/Bull price context and cash-flow basis.
  Reconcile the weighted result through the existing native IRR engine. This is
  neither Fair Value nor a recommendation or guarantee. No target is preselected.
- Preserve model/revision/listing/currency and effective/recorded provenance.
  Reject stale or future-known revisions; unavailable, stale or conflicting quotes
  do not become current observations. The hypothetical analysis remains available
  without a quote. Hide the panel without usable native inputs.
- Use shared UI with keyboard/mobile/light/dark coverage. One read-only API/browser
  journey and independent financial/isolation review. No writes, model acceptance,
  new schema, providers, services, dependencies or top-level dashboard.

Implementation is in progress. Current schema remains `b59f16c8a203`; no migration
is planned. A new read-only API will require an API-first coordinated release.
Production controls, ingestion and model acceptance remain separately gated.

Deferred: operating-driver solver, fiscal mapping, new cross-company ranking,
consensus activation, source ingestion and further broad UI redesign. Production
real-data activation remains a separate priority: last recorded November 14 readback
has zero prices/FX/facts/filings/consensus; recovery and verified source access remain
prerequisites. See the independent PR #39 handoff for the completed refresh slice.
