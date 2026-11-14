# Active workstream

## Investment return hurdle explorer - complete, scope frozen (2026-11-14)

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

### Delivered and verified locally

Portfolio -> Company -> Valuation now explains the entry price supported by the
accepted native cash flows at an explicitly entered return. Optional hypothetical
price produces the native modeled IRR. The panel shows scenarios, annual/terminal
PV contributions, exact model revision and quote provenance. Changing inputs
hides the old result. Missing quotes retain valid hypothetical analysis; missing
native inputs hide the panel. No assumptions or investment decisions are saved.

[Financial methodology](financial-models.md#hypothetical-return-hurdle-explorer) and
[reproduction](testing.md#return-hurdle-investor-journey-fictional-data) are canonical.
The service uses exact Decimal arithmetic and reconciles returned prices through
the existing native IRR engine. Independent review reconstructed 16 raw-fixture
PV/IRR cases across standard DCF, H-model, owner cash flow and residual income.
Financial, proxy/isolation and visual second passes found no remaining A blocker.

- 997 backend units passed; two existing Windows platform-specific tests skipped.
- 98 relevant native-model/API/fixture cases passed, including 19 PostgreSQL tests.
  An unrelated full-database sweep was stopped at 11% without observed failures;
  it is not claimed as a full pass. No broader worker/recovery changes were made.
- 513 web tests passed. Lint, formatting, strict types (237 Python files), generated
  contracts, repository policy, documentation links and 21 deployment tests pass.
- Production-build authenticated browser suite: 157 passed, 53 explicit opt-ins
  skipped. This includes 10 explorer cases for normal, stale, mismatched, older-API
  and delayed-response behavior across desktop/mobile.
- Four additional real PostgreSQL/FastAPI/Next.js desktop/mobile journeys pass:
  all three native models, priced and unpriced states, 10% -> 12% recalculation,
  light/dark, source disclosure and return to Holdings. Accepted revision JSON,
  protected portfolio state and table counts remain unchanged; zero UI writes.
- Fixtures are explicitly fictional; no live provider request or production
  observation was used. [Desktop](design/screenshots/return-hurdle-desktop.png) and
  [mobile](design/screenshots/return-hurdle-mobile.png) show those local fixtures.

### Integration and release handoff

**Engineering: acceptance complete, no remaining A-class code blocker.** Preserve
this branch for review after the independent PR #39; do not create a competing PR
or expand its frozen SEC scope. Main was re-fetched at `866723e`. Future integration
must preserve both sets of fixture scenarios in `apps/api/tests/browser_server.py`
and reconcile the roadmap/handoff/testing documentation semantically.

**Release: REQUIRES_COORDINATED_RELEASE.** New dependency:
`GET /v1/financial-models/{id}/return-hurdle`, with exact base revision and explicit
return/optional entry price. No new migrations, services, providers or dependencies.
Schema review/deploy gates match the existing owner attestation at `b59f16c8a203`,
zero pending revisions and unchanged history hash
`de9fb593f76ec72261ef40bb3d88a12751b0e114c81fc48f08f96dee48be73f2`.
This is repository compatibility evidence, not a new live production attestation.

Before an authorized release, reverify live schema, API/frontend commits and
deployment controls. Keep Vercel production builds frozen; release and verify the
API first, then release the matching frontend. An older API yields a clear
unavailable message. Neither this branch nor green checks authorize merge/deploy.
No production settings, data, ingestion, model acceptance or ledger ownership changed.

Deferred: operating-driver solver, fiscal mapping, new cross-company ranking,
consensus activation, source ingestion and further broad UI redesign. Production
real-data activation remains a separate priority: last recorded November 14 readback
has zero prices/FX/facts/filings/consensus; recovery and verified source access remain
prerequisites. See the independent PR #39 handoff for the completed refresh slice.
Next highest-value task remains verified financial-data activation through the
existing guarded pipeline once recovery/source prerequisites are satisfied, then
actuals-versus-model analysis only when explicit fiscal anchors exist.
