# AGENTS.md — Personal Universe / Portfolio

## Mission and precedence

Build the Portfolio Research Platform as the first application in a private, modular Personal Universe. Deliver useful, reliable investment workflows—not a spreadsheet clone or infrastructure for its own sake.

Follow explicit owner instructions, this file, scoped `AGENTS.md` files, then relevant approved domain/architecture contracts. When documents disagree, **preserve established financial and production behavior**; record the conflict and seek a decision rather than inventing a rule. Do not treat planned features as implemented.

## Read before work

- `docs/PRODUCT_VISION.md` — product outcomes and non-goals.
- `ROADMAP.md` — current task, dependencies, acceptance criteria and verified progress.
- `docs/architecture/personal-universe.md` — repository/platform target; read for shared-platform changes.
- `docs/architecture/portfolio-application.md` — Portfolio domain, data ownership, models and integration; read for Portfolio changes.
- `docs/domain-model.md` — canonical identity, lifecycle, scores and portfolio contracts when relevant.
- `docs/financial-models.md` — supported methods, return definitions and accepted revision semantics for model work.
- Applicable `apps/web/AGENTS.md`, `apps/api/AGENTS.md`, and relevant domain/model/source contracts when touching those areas.

Read only documents relevant to the change. Existing detailed financial/domain documentation remains authoritative for its own domain; these summaries do not supersede it.

## Non-negotiable invariants

- Identity: **Company → Security → Listing**. Ticker is not company identity. Keep reporting, model, listing and portfolio currencies distinct.
- Keep the decision hierarchy explicit: 10Y Durability, Compounder Quality, credible per-share compounding, valuation/Expected IRR, portfolio fit, then execution. Keep Durability (0–5), Quality (0–5), Execution (1–5) and Risk (1–5, higher is riskier) independent; do not add an opaque composite or infer lifecycle.
- Investment decisions are separate: external facts → financial models → interpretation → portfolio construction → execution. Rankings, prices, model outputs or holdings must never silently infer lifecycle, overwrite assumptions, or rewrite strategic targets.
- Lifecycle is explicit: `PORTFOLIO`, `WATCHLIST`, `CANDIDATE`, `DROP`. Durability, Quality, Execution and Risk scores retain their independent definitions. Preserve existing approved investment rules.
- Keep valuation methodology and return basis explicit. In particular, legacy enterprise UFCF IRR is **not** automatically comparable to shareholder cash-flow IRR. Preserve Bear/Base/Bull semantics, native model parity and accepted revision history.
- Where defined, Expected Cash-Flow IRR is based on probability-weighted expected shareholder cash flows; the investor hurdle is a required-return/risk-adequacy measure, not WACC; Weighted Fair Value is a valuation reference, not a fixed-horizon stock-price forecast. Preserve legacy method-specific return definitions rather than relabeling them.
- Missing is not zero. Preserve units, timescopes, provenance, observed/effective/recorded times, immutable accepted history, and conflict detection. Do not fabricate source data.
- Google Sheets remains authoritative for legacy workflows until explicitly migrated. Accepted canonical application revisions live in PostgreSQL. Use versioned, hash-verified, typed transfer packages and reviewed ownership transitions; never silently overwrite newer accepted state.
- One shared web/API/DB deployment is the long-term platform direction, **not** permission for mass restructuring, cross-app table access or changes to production.

## Financial-model publication direction

Agents maintain methodology-specific models in Google Sheets and explicitly publish complete revisions. Use producer-neutral, versioned model contracts and source adapters. Ordinary worksheet edits stay drafts. Reuse the model inbox, native engines and immutable review workflow. See `docs/model-publications.md`. Future policy-controlled promotion requires a separately approved policy, tests and activation authorization.

## Technical ownership

- Next.js owns presentation and interaction; it does not implement financial, ranking, scoring, portfolio or reconciliation calculations. FastAPI owns validation, deterministic models and analytics; PostgreSQL owns migrated canonical state and history.
- External facts flow from provider/source evidence through typed raw observations and domain normalization into canonical data. Do not silently blend provider conflicts or fabricate effective, observed, publication or recording times.
- For historical analysis, distinguish reporting/economic period, effective/publication time, observation/retrieval time and recorded time. Do not use later-known information in an earlier state.
- Keep implementation explicit and domain-scoped. Avoid generic rule engines, event sourcing or new infrastructure without a demonstrated need.

## Autonomous execution loop

1. Read `ROADMAP.md` execution cursor; inspect Git state, relevant code and prerequisites.
2. Select the next **ready**, smallest user-valuable subtask; avoid speculative infrastructure.
3. Implement, run meaningful checks and independently review correctness, security, integration and UX. Fix findings.
4. Record actual evidence, blockers, decisions and exact next step in `ROADMAP.md` **after each subtask**. Never mark an unverified task complete.
5. If blocked, log the cause and proceed only to an independent ready task. Do not repeatedly retry unchanged failures.
6. At the milestone gate run integrated checks, review the diff, reassess roadmap against the product vision, push a dedicated branch and open a PR when permitted. Record PR URL. PR creation does **not** authorize merge or deployment.
7. Keep a single unambiguous execution cursor; preserve progress across agent sessions. Do not silently change the product vision, financial policy, security boundaries or authority model.

## Git, tests, and evidence

Preserve unrelated edits and untracked files. No force-push, history rewrite, destructive cleanup or mixing unrelated changes. Commit coherent units; never commit secrets, private financial packages, source snapshots or sensitive diagnostics. Verify repository visibility before publishing. Use separate implementing/reviewing agents when practical; CI and human review are the real gates.

Report distinctly: `IMPLEMENTATION_COMPLETE`, `LOCAL_VERIFIED`, `LIVE_SOURCE_VALIDATED`, `PRODUCTION_PREVIEW_VERIFIED`, `PRODUCTION_READY`, and `PRODUCTION_APPLIED`—only with actual evidence. Check applicable unit/integration/type/contract/migration/authorization/E2E tests. Validate desktop and mobile when UI changes; report unavailable browsers honestly. Do not weaken tests, invariants or guards just to get a green result.

## Permission boundary

Autonomous: local code, documentation, isolated DB tests/migrations, authorized read-only source/Neon checks, commits, feature-branch push and PR creation. Terminal access does not prove network authorization.

**Require separate explicit owner authorization** for production schema or data writes, production deployments, modifying authoritative Google Sheets, approving financial models or research decisions, changing live credentials/auth configuration, enabling recurring ingest/jobs, merging protected PRs where review is required, and destructive or history-rewriting Git actions. Before any authorized production action verify exact target, scope, immutable inputs, preview, recovery point, and rollback path. Never bypass sandbox/network/DB safeguards.

When blocked by an approval gate, prepare a precise, read-only handoff and continue unrelated safe work when available.
