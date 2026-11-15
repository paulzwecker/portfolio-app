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
Fresh integrated reconciliation is pending. Authentic recordings/screenshots remain
private where source redistribution terms require it. Surrounding holdings, cash,
targets and native-model examples are fictional, never live owner observations.

ECB/SEC public access is usable within existing policies. EODHD documented demo
supports bounded private evaluation only; production execution stays rejected.
Broader zero-cost equity/consensus access is unverified. EPS basis remains DATA_CHECK;
one estimates capture is not a historical revision series. FMP and Yahoo remain
inactive without verified free entitlement. No paid dependencies are required.

Current production read-only verification is in progress. No production backup is
established by #37: a destination, key custody and isolated restore target still
need owner approval and the existing interactive rehearsal. The old Neon branch
expires November 15 and is not durable recovery. All write/activation gates remain.

### Release boundary and next action

Engineering evidence is being refreshed; do not yet claim ENGINEERING_READY.
The new `GET /v1/financial-models/{id}/return-hurdle` endpoint and additive native-price
fields require an API-first release. No migration is introduced. Keep Vercel
production frozen until the owner authorizes and verifies the matching Render API,
then separately releases the frontend. Actual hosted commits/settings must be
verified; CI success is not release or data-operational readiness.

After this milestone: approved recovery rehearsal, then exact SEC/ECB production
activation through existing guards. Broader source coverage, guidance ingestion,
model fiscal alignment, new comparison analytics, Sheets publication and generic
infrastructure are deferred rather than blockers for the selected journey.
