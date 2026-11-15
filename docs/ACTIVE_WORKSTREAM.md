# Active workstream

## Integrated Portfolio Research delivery — INTEGRATE, 2026-11-15

Owner explicitly requested consolidation of Agents 1–8. Integration is staged on
`codex/integrated-delivery` before a history-preserving update of the existing
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
production-build browser cases (61 explicit opt-ins skipped). The two new combined
real-source desktop/mobile journeys pass in light/dark themes. Types (256 Python
files and TypeScript), lint, contracts, build and 21 deployment checks pass. Full
PostgreSQL CI and refreshed source-specific UI refresh runs are still in progress.
Independent financial/isolation and visual reviews found no remaining A-class
blocker. Existing single-snapshot history-panel clutter is deferred B-class polish.

The new `GET /v1/financial-models/{id}/return-hurdle` endpoint and additive native-price
fields require an API-first release. No migration is introduced. Release is
**REQUIRES_COORDINATED_RELEASE; RELEASE_READY=false; DATA_OPERATIONALLY_VERIFIED=false**.
Before merge the owner must freeze Vercel production, authorize the API-first
release and verify the matching Render API, then separately release the frontend.
CI success is not release or data-operational readiness. PR #39 is temporarily
draft while its expanded integration evidence and latest-head CI are refreshed.
Live authenticated UI readback is unverified because frontend Basic Auth credentials
are not present locally; no authentication was guessed or bypassed.

After this milestone: approved recovery rehearsal, then exact SEC/ECB production
activation through existing guards. Broader source coverage, guidance ingestion,
model fiscal alignment, new comparison analytics, Sheets publication and generic
infrastructure are deferred rather than blockers for the selected journey.
