## Current slice — fail-closed Booking SEC identity binding (2026-11-20)

The real Booking SEC pilot now ties every staged candidate to a
**point-in-time, operator-reviewed SEC CIK** returned in the restricted
`CompanyAgentContextV1.sec_identity`. The field exposes only public issuer
identity/evidence, not holdings or research. For BKNG, the CLI blocks a
missing/invalid/ambiguous/mismatched CIK even when the company name and
listing ticker appear correct. No company ID is guessed or provisioned.

An isolated test covers known-at exclusion, a valid reviewed mapping and
ambiguous CIK rows; the full Booking evidence → review integration test also
asserts that the scoped context supplies the exact SEC identity. This is
code-only; the hosted canonical BKNG UUID/read token remains an operator gate.

---

## Latest development checkpoint — Booking Holdings SEC pilot (2026-11-20)

PR #42 now supports a **real tracked issuer (BKNG)** alongside the earlier
Uber public-source rehearsal. Booking's official Form 10-Q for Q3 2026
(SEC accession `0001075531-26-000045`, filed November 3) is represented
by a reviewed source pack: 345 million booked room nights, 21 million flight
tickets and USD 54,461 million gross bookings. The published data are
rounded to millions; all three observations retain `APPROX` qualifiers,
`reported_at=null`, economic period, original USD/units and SEC provenance.
No GAAP revenue, consensus, guidance or financial forecasts are inferred.

- New fixed issuer verifier `BKNG_Q3_2026_SEC_10Q` uses one official SEC
  HTML URL, bounded bytes/time, no redirects and operator-supplied
  `SEC_USER_AGENT` for fair access. It rejects issuer, quarter, year
  column, reporting scale or amount conflicts; it never self-accepts.
  Production public-page bytes **have not been fetched through the new
  adapter**; offline tests use a small synthetic HTML table fixture,
  while published figures were cross-checked with official filings.
- Reuses `CompanyAgentContextV1`, the exact BKNG listing and the existing
  reviewed SEC CIK crosswalk (`0001075531`), rather than hard-coding
  or inventing a company UUID. The operator runbook contains a SELECT-only
  crosswalk check. An absent/mismatched crosswalk blocks live onboarding.
- The existing default-off handoff/agent proposal/human reviewer pipeline
  supports Booking with no new API/database table or paid provider.
  A disposable PostgreSQL test seeds synthetic BKNG identities and reviewed
  CIK mapping, then verifies definition acceptance → KPI proposals →
  independent human approval → accepted readback and replay. No production
  acceptance, workbook mutation, schema migration or deployment.
- Focused [Booking workflow CI run](https://github.com/paulzwecker/portfolio-app/actions/runs/44712143955)
  passed **41 source/unit/integration tests** and Python typing/formatting.
  The canonical formatter was committed; its one-time workflow was removed.
  Exact latest-head broad CI remains the protected merge gate and is not
  a prerequisite to selecting the next development slice.

**Operator-only next step:** obtain an independently authorized live
read-only BKNG company UUID/CIK confirmation and scoped API token, then
perform a live official filing fetch and private shadow preview. If the
live HTML differs from the synthetic table layout, fail closed and refine
the adapter without accepting any data. Proposal POST, canonical acceptance,
live credentials, production deployment and merge require separate owner
authorization.

---

## Latest development checkpoint — verified candidate handoff (2026-11-20)

On the same open draft PR #42, added a **manual, default-off**
`data_universe_proposal_handoff` command. It re-verifies the exact official
Uber source before reading the scoped company API, produces an owner-only
review plan and stages only the batch whose dependencies are accepted.
With missing metric definitions, KPI and guidance candidates are deferred
until a fresh company-context read confirms reviewer acceptance.

A candidate POST requires an explicit reviewed external batch ID, matching
full issuer-page SHA-256, separate CLI submission enablement, dedicated agent
token and the API's existing proposal/write guards. Exactly **one** batch is
submitted per invocation. Server response identity and payload are validated;
the candidate still goes through the existing human preview/decision UI.
There is **no automatic acceptance, model update, scheduled job, extra table,
paid provider, source Sheet write or production configuration**.

Focused disposable PostgreSQL + unit verification passed **27/27** and Python
mypy passed in [run 44708861038](https://github.com/paulzwecker/portfolio-app/actions/runs/44708861038).
The two temporary formatter runs overlapped; one formatting commit was accepted
without rewriting history, and the workflow was subsequently removed.
A final small offline-no-submit test was added; exact-head CI on the latest
branch remains a separate merge gate. Do not interpret focused fixture tests as
live canonical data acceptance.

**Next highest-value operational dependency:** authorize a strictly scoped,
read-only canonical UUID/token and run the verified shadow plan for an actual
eligible company. Production proposal submission/acceptance require separate
explicit authorization; never infer them from this implementation. Until
authorized, prioritize verified public source coverage for genuinely held
businesses rather than new generic infrastructure.

---

## Active draft integration — PR #42 (2026-11-20)

Single working PR: https://github.com/paulzwecker/portfolio-app/pull/42
Branch: `feat/api-first-company-observations`. **Do not merge or deploy** without
owner review; no production migration, Sheet edit, source activation, or real
canonical observation acceptance is authorized.

Completed code slices on this branch (development state, not production claims):

- Append-only company metric definitions, operating actuals, management guidance
  and revision-scoped model-driver records, all separate from reported statements
  and provider consensus.
- `CompanyAgentContextV1`: bounded canonical agent company context with explicit
  portfolio selection, point-in-time controls and source/availability status.
- Typed `MetricDefinitionBatchV1`, `KPIObservationBatchV1` and
  `GuidanceObservationBatchV1` candidates sharing one review inbox. Dedicated
  role credentials, idempotent submission, deterministic preview/fingerprint,
  owner acceptance/rejection and canonical append-only publication. Default-off
  proposal and acceptance switches.
- Synthetic PostgreSQL tests for accepted definition → KPI → guidance → correction,
  idempotency/conflicts/stale reviewer previews; public Uber Q3 2026 IR numbers
  used only in an **isolated test fixture**.
- Dedicated, default-off, allowlisted DATA_UNIVERSE_STEWARD read-only credential
  for GET CompanyAgentContextV1, with private portfolio/research/model sections
  suppressed; broad application proxy authorization is unchanged. Credentials
  are not provisioned, no new app or agent has been activated.
- **New development slice:** one disabled-by-default, manually invoked Google
  Sheets Observation Inbox bridge. Reuses the existing read-only double-capture
  Sheets client and typed observation `submit()` service, creating candidates
  in the same proposal table as API agents. Full review authority remains
  unchanged. The inbox is never written to by the bridge. Synthetic PostgreSQL
  tests cover replay, invalid/mismatched IDs, partial scans and reviewer
  acceptance. Not live-configured; no owner workbook was edited.
- Read-only `data_universe_shadow` CLI stages structured local draft batches
  from scoped company context + a human-reviewed public issuer evidence pack.
  It refuses incomplete history and duplicate/conflicting facts, uses no
  observation proposal credentials or write APIs, and stores private output
  outside Git. The published Uber Q3 2026 test pack covers trips, Gross
  Bookings, and Q4 guidance. Live hosted shadow execution remains unverified.

- **Investor-facing Company Explorer:** new Operating KPIs tab reuses the
  accepted CompanyAgentContextV1 response to show actuals, management
  guidance, selected financial consensus (separately), and accepted
  revision-scoped Bear/Base/Bull driver paths. Strict period/scope/unit checks
  prevent misleading comparison. No new data provider or schema.

- **Native driver publication v1.3:** optional explicit company operating
  driver paths in the existing DCF portable model contract, validated against
  the canonical metric dictionary, surfaced in the reviewed model input diff
  and appended only with the accepted revision. The Company Explorer Operating
  KPIs tab reads those accepted paths; no new inference or financial calculation.
  Synthetic model publication/replay/negative permission tests added. No live
  model or Sheets edit performed.

- **End-to-end operating-data reviewer UI:** Next.js server proxy now
  allowlists the canonical agent-context read and dedicated observation
  reviewer operations, using a separate server-only reviewer token.
  Company Explorer exposes the existing review queue and two-step decisions
  without creating another acceptance path. No live credential configured.
- **Evidence-safe operating BASE review:** Company Explorer now highlights
  differences between a sole verified comparable actual and a pre-result
  accepted BASE assumption, with exact source/model revision and a metric
  filter action. No verdict without issuer report timing, with a late
  expectation, or with multiple comparable current actuals. JSON scope
  ordering is normalized. Per-model driver truncation and missing metric
  definitions are flagged instead of hidden. No valuation/trading mutation.
- **Data & Universe shadow correctness:** source pack publication must not
  postdate its authoring or canonical knowledge cutoff; KPI quality mismatch
  and model-driver metric permission mismatch are human conflicts, not false
  MATCHED results. Focused regression tests and domain docs added.
- **Real primary-source verification:** explicit `--verify-public-source` checks
  only Uber's November 4, 2026 Q3 issuer release with a bounded public HTTPS
  GET, no redirect or private secret. It validates table/year/scale, two actuals
  and the separate next-quarter guidance; a mismatch fails before canonical
  API read. The report records a source SHA-256 or NOT_CHECKED.
  The temporary live issuer check **passed** on November 20, 2026
  ([GitHub run 44696041668](https://github.com/paulzwecker/portfolio-app/actions/runs/44696041668):
  SOURCE_MATCHED, 3 facts, SHA-256 prefix `af725f990041e608`).
  Temporary workflow removed; no recurring source job remains.
- **Agent-to-reviewer integration:** new isolated PostgreSQL test exercises a
  synthetic UBER canonical identity, scoped context, source-checked evidence
  pack, staged three typed drafts, agent submission, separate reviewer preview/
  fingerprint/acceptance, accepted context readback and idempotent no-draft
  comparison. This tests a real issuer's numbers but **not production data**.
  Focused disposable-PostgreSQL CI passed **1/1** on Nov 20
  ([run 44698784806](https://github.com/paulzwecker/portfolio-app/actions/runs/44698784806))
  after adding explicit fixture flushes for Company → Security → Listing FK order.
  The preceding broad CI passed 588/589 integration tests; its sole failure
  was this synthetic insert-order setup, not a canonical workflow assertion.
  Full exact-head CI on the cleaned branch remains the final merge gate.

Current next gate: exact-head CI, then independent operator authorization for
a live canonical company UUID allowlist/read token and real-database shadow
comparison. No production database or workbook write, source activation,
proposal acceptance, migration, deployment or protected merge is authorized.

Verification: PR #42 previously passed all three required CI jobs on
`a005893f` (Quality/contracts/build, PostgreSQL integration and Windows
migration compatibility). New Nov 20 commits require fresh **exact-head**
checks; consult the PR, not an older commit, for the final verdict. The
temporary formatter workflow used in development was removed.

Next high-value gates: resolve any current-head CI failure, then obtain
separate authorized read-only company scope/credential setup and prove one
real disclosure → canonical comparison → owner-reviewed draft journey.
Only then expand vetted free/public issuer coverage. No live credentials,
production migration, model acceptance, Sheets edits, scheduler enablement,
protected merge or deployment are authorized. Full CI remains a **merge
gate**, not a pause between compatible increments.

---

# Active workstream

## Integrated Portfolio Research delivery — INTEGRATE, 2026-11-15

Owner explicitly requested consolidation of Agents 1–8. Integration on
`codex/integrated-delivery` was fast-forwarded into the existing
[PR #39](https://github.com/paulzwecker/portfolio-app/pull/39), not a competing PR.
Main `866723e` contains recovery tooling (#37) and investor UI (#38). PR #39
`69371f1` supplies SEC/manual/scheduled refresh; market/FX `b432335`, expectations
`c45f4e6` and investment return-hurdle `33cedff` remain preserved. Other branches,
worktrees, owner edits and stash are untouched. No protected merge or deployment.

### Frozen acceptance before integration

1. Preserve the existing Portfolio → exact company → prices → Financials/filings
   and expectations → valuation/research → portfolio navigation using shared UI.
2. Compose one private real-source isolated journey with the same AMZN identity for
   market observations and estimates; keep supported SEC issuers distinct. Verify
   native-price/dated-FX EUR valuation against raw evidence and fictional quantities.
3. Retain reported observations, provider forecasts, uncertain EPS and accepted
   model assumptions as separate categories. Do not infer fiscal anchors, transactions,
   historical portfolio performance, adjustments or absent data.
4. Integrate the already-complete read-only return-hurdle explorer. Independently
   verify native-model economics, scenario probabilities, quote provenance and
   unchanged accepted state with explicitly fictional model fixtures.
5. Rerun existing real SEC and market manual/scheduled refresh journeys; durable
   identity survives reloads, bounded work persists observations and partial/failure
   states remain visible. No new worker, scheduler or consensus UI refresh endpoint.
6. Run comprehensive relevant backend integration, unit/contract/schema/deployment
   checks, production-build browser tests and desktop/mobile light/dark review.
   Fix proven in-scope blockers only, then freeze one updated owner-reviewable PR.

### Known data and operational limits

Prior evidence: isolated MSCI 1,596 facts/310 filing references; Microsoft 1,909/428;
AMZN 255 native closes and USD/EUR + DKK/EUR 518 FX observations through November 13;
eight AMZN revenue/EPS forecasts across four periods captured November 15.
All four private source API replays pass on the integrated code. Authentic recordings/screenshots remain
private where source redistribution terms require it. Surrounding holdings, cash,
targets and native-model examples are fictional, never live owner observations.

ECB/SEC public access is usable within existing policies. EODHD documented demo
supports bounded private evaluation only; production execution stays rejected.
Broader zero-cost equity/consensus access is unverified. EPS basis remains DATA_CHECK;
one estimates capture is not a historical revision series. FMP and Yahoo remain
inactive without verified free entitlement. No paid dependencies are required.

Fresh guarded read-only checks at 01:14–01:19 UTC on November 15 verify exact Neon
primary identity, schema `b59f16c8a203`, accepted canonical receipt and the 22-listing,
two-pair approved market window. All six observation categories remain zero;
22 holdings, two cash rows, one target revision and 16 targets are unchanged.
The live API is ready/current and its authenticated portfolio read returns one
portfolio. SEC preview is blocked: zero reviewed CIK mappings for 21 held issuers.

No production backup is established by #37. A destination, key custody and isolated
restore target still need approval and the existing interactive rehearsal. The old
Neon branch expires November 15 at 14:18:37 CET; the configured recovery connection
does not match current endpoint inventory, so fresh recovery readback stopped.
Four disposable database archive/encryption/restore checks pass, which does not
establish production recovery. No credentials, settings or production data changed.

Live Render is `9a27353`; Vercel production is `866723e`. Render Auto-Deploy after
checks and Blueprint Auto Sync are enabled; Vercel's schema hook permits production
builds. **Deployment is not frozen.** Direct Render service write/ingestion/manual/
recurring/workbook/FMP flags are false and Sheets polling is zero. SEC contact is
absent directly on the service; linked environment-group contact remains unverified.

### Release boundary and next action

Local integration passes: 1,092 backend units (two platform skips), 530 web tests,
four source-backed PostgreSQL/API replays, four cross-feature native-price/model
boundary cases, four archive/encrypted recovery checks, and 157 authenticated
production-build browser cases (61 explicit opt-ins skipped). Six real-source
desktop/mobile journeys pass in light/dark themes: the combined investor journey,
market manual/scheduled increment and Microsoft SEC manual/scheduled refresh.
Types (256 Python files and TypeScript), lint, formatting, contracts, build and 21
deployment checks pass. Production dependency audit reports zero vulnerabilities.

The broad local database sweep was stopped after fixture errors during concurrent
shared-server work; it is not a full pass. Both affected files pass serially (13
cases) without application changes. Separate parallel cleanup had exhausted the
test server's lock budget; no server configuration was changed. The complete
569-case PostgreSQL suite is a required CI gate on the PR's exact head, alongside
Quality/contracts/build and Windows migration compatibility. Consult current PR
checks for the final result; prior-head checks never substitute. Scope is frozen
with no remaining code blocker; ENGINEERING_READY requires all three gates green.
Independent financial/isolation and visual reviews found no remaining A-class
blocker. Existing single-snapshot history-panel clutter is deferred B-class polish.

The new `GET /v1/financial-models/{id}/return-hurdle` endpoint and additive native-price
fields require an API-first release. No migration is introduced. Release is
**REQUIRES_COORDINATED_RELEASE; RELEASE_READY=false; DATA_OPERATIONALLY_VERIFIED=false**.
Before merge the owner must freeze Vercel production, authorize the API-first
release and verify the matching Render API, then separately release the frontend.
CI success is not release or data-operational readiness. PR #39's description and
checks hold the current review verdict; do not merge while live release controls
would cause an unauthorized deployment.
Live authenticated UI readback is unverified because frontend Basic Auth credentials
are not present locally; no authentication was guessed or bypassed.

After this milestone: approved recovery rehearsal, then exact SEC/ECB production
activation through existing guards. Broader source coverage, guidance ingestion,
model fiscal alignment, new comparison analytics, Sheets publication and generic
infrastructure are deferred rather than blockers for the selected journey.
