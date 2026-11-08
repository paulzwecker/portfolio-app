# Personal Universe — Architecture & Migration Strategy

- **Version:** 1.1
- **Date:** 2026-11-07
- **Status:** Owner-confirmed target. Implementation and operational evidence live in `ROADMAP.md`
- **Audience:** Project owner, AI coding agents, future maintainers

> **North star:** A new personal application should primarily require defining its purpose and domain behavior—not rebuilding authentication, design, API conventions, database infrastructure, deployment, or operational safeguards.

## 1. Executive decision

Build a **Personal Universe** as a **modular monolith**: one Git repository, one deployed Next.js web application, one deployed FastAPI service, and initially one Neon PostgreSQL database. The root page is a private **App Hub** (an app-store-style launcher). Each personal application is an internally modular product that reuses the same platform foundation.

This is deliberately optimized for **one primary developer, personal use, low concurrency, low recurring costs, and agent-assisted development**. It is not an enterprise multi-tenant SaaS architecture. The system should nevertheless preserve clear contracts so an application can be extracted into its own deployment if future security, reliability, or performance needs justify doing so.

The owner prioritizes a useful Portfolio application, then operational maturity and
incremental platform extraction. Small shared foundations can emerge earlier from
real Portfolio needs. This is the default economic footprint. Security, reliability
and measured total cost may justify a separately reviewed isolation boundary.

**Decision summary**

| Concern              | Initial choice                                             | Important qualification                                                                         |
| -------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Source control       | One monorepo                                               | Explicit ownership and dependency rules                                                         |
| Browser experience   | One Next.js application on one Vercel project              | All apps share a release; app routes are modules, not independently deployed Next.js apps       |
| Backend              | One FastAPI process on one Render web service              | App-specific routers and services; one process is a shared failure/resource boundary            |
| Database             | One Neon project, initially one PostgreSQL database        | App-owned PostgreSQL schemas for new domains; retain Portfolio's `public` schema initially      |
| Identity             | One supported login/session system                         | Authorization enforced on every trusted API operation; UI visibility is not a security boundary |
| Design               | Shared tokens, shell, and reusable components              | Domain-specific interactions remain app-owned                                                   |
| Application creation | Versioned module template + generator + agent skills       | Human approval for migrations, permissions, production changes, and release                     |
| Release              | Native Render/Vercel deployments with shared compatibility | CI/owner review protect main. Migrations and data operations have separate gates                |

**Cost objective:** Avoid buying separate Neon, Render, or Vercel services solely because a new application is added. This is a deployment design goal, **not a guarantee of a fixed bill**: usage, compute, storage, bandwidth, background work, and provider plan limits can still increase costs.

## 2. Scope and guiding principles

1. **One hood, many apps.** A shared app portal and common runtime contain independently understandable functional modules.
2. **Modularity without microservices.** Prefer explicit boundaries within one process over a distributed system too early.
3. **One canonical owner per fact.** Sharing a database does not mean every app can read or modify every table.
4. **Extract proven patterns.** Reuse what Portfolio already does well; introduce shared abstractions when demonstrated by a second consumer.
5. **Small, reversible changes.** Never combine a web-route move, API rewrite, and database schema relocation in one migration.
6. **Agents implement; owner approves risk.** Agent-generated code must pass automated and human review before privileged deployment, schema mutation, or production ingestion.
7. **Correctness before cosmetics.** Financial calculations, source provenance, immutability, and source-of-truth contracts must survive every platform refactor.
8. **Default to least privilege.** Private application access, authenticated API calls, scoped database permissions, and secure secrets management are foundational.
9. **Portability is an escape hatch.** Make app modules sufficiently isolated that a future split is possible, but do not incur microservice overhead now.

### Non-goals for the initial platform

- Independent infrastructure stacks or repositories for every personal app.
- Building a universal schema-less CRUD engine, general-purpose workflow builder, or visual database editor.
- Moving all Portfolio SQL tables from `public` to `portfolio` as a prerequisite to launching the hub.
- Rewriting Portfolio's valuation engines, APIs, and research workflows merely to conform to new folder names.
- Full enterprise IAM, multi-tenant billing, organization management, or authorization administration for a single-user private tool.
- Automatic AI-generated production migrations or unattended publication of new applications.
- Migrating or mixing corporate/GBU data, infrastructure, or governance into this personal platform.

## 3. Logical architecture

```text
                         PRIVATE PERSONAL UNIVERSE

                     your-domain.example / (App Hub)
                                  |
                  One authenticated Next.js deployment
                                  |
             +--------------------+-------------------+
             |                    |                   |
       /apps/portfolio      /apps/planning      /apps/<new-app>
             |                    |                   |
        Portfolio UI         Planning UI          App-specific UI
             +--------------------+-------------------+
                                  |
                   Authenticated server-side proxy
                                  |
                      One deployed FastAPI service
                                  |
             +--------------------+-------------------+
             |                    |                   |
       portfolio router      planning router      other routers
             |                    |                   |
       Portfolio domain      Planning domain      Other domains
             +--------------------+-------------------+
                                  |
                       One PostgreSQL database
                                  |
             +--------------------+-------------------+
             |                    |                   |
          public.*             planning.*          platform.*
       (Portfolio legacy)     (new app)       (shared metadata)
```

**Important distinction:** `apps/web` and `apps/api` are **deployable units**; `portfolio`, `planning`, and other apps are **domain modules** within them. Do not create a second Next.js server or FastAPI deployment every time a new application is generated.

### Operational consequences

- One change to the shared web or API process can affect every app; cross-app smoke tests are mandatory.
- All modules share resource capacity. An expensive financial backfill must be bounded and must not block ordinary interactive requests.
- A dedicated worker or external schedule may eventually be needed for expensive jobs; do not assume background tasks running inside a sleeping web service are reliable.
- A future application may be isolated into another service or database if the shared deployment stops meeting security, latency, resource, or availability needs.

## 4. Target monorepo layout

The following is a **target structure**, not a request to create empty directories or move everything at once.

```text
personal-universe/
├── apps/
│   ├── web/                                 # ONE Next.js application / Vercel project
│   │   └── src/
│   │       ├── app/
│   │       │   ├── page.tsx                  # App Hub at /
│   │       │   ├── (platform)/               # Shared account/settings/auth flows
│   │       │   ├── apps/
│   │       │   │   ├── portfolio/             # Portfolio routes
│   │       │   │   ├── planning/              # Example future app routes
│   │       │   │   └── <app-id>/
│   │       │   └── api/                      # Trusted same-origin API proxy
│   │       ├── features/
│   │       │   ├── portfolio/
│   │       │   ├── planning/
│   │       │   └── <app-id>/
│   │       └── components/                  # Web-local integration components
│   │
│   └── api/                                 # ONE FastAPI application / Render service
│       └── src/
│           ├── portfolio_api/               # Existing implementation, initially untouched
│           └── platform_api/
│               ├── main.py                  # Router composition / platform bootstrapping
│               ├── core/                    # Auth verification, DB, errors, logging
│               └── modules/
│                   ├── planning/
│                   └── <app-id>/
│
├── packages/
│   ├── ui/                                  # Shared components and design tokens
│   ├── auth/                                # Client/server auth contracts, not secrets
│   ├── contracts/                           # OpenAPI/typed cross-module interfaces
│   └── app-registry/                        # Validated app metadata
├── python/
│   └── platform-core/                       # Small reusable FastAPI/DB primitives
├── templates/
│   └── app-module/                          # Working, versioned example template
├── tools/
│   └── create-app/                          # App module generator
├── skills/                                  # AI agent playbooks
├── docs/
│   ├── architecture/
│   ├── domain-catalog/
│   └── runbooks/
├── AGENTS.md
└── package.json
```

**Do not perform a mass rename** of `portfolio_api`, the existing npm workspaces, route paths, tables, or deployment files. Preserve current behavior through compatibility adapters and gradual migration.

### Web routing

| Route                 | Responsibility                                                         |
| --------------------- | ---------------------------------------------------------------------- |
| `/`                   | Private App Hub, showing only apps available to the authenticated user |
| `/apps/portfolio`     | Portfolio landing page                                                 |
| `/apps/portfolio/...` | Portfolio feature pages                                                |
| `/apps/<app-id>/...`  | Other app pages                                                        |
| `/api/...`            | Same-origin Next.js server/proxy endpoints where needed                |

During migration, keep established Portfolio URLs working through redirects, route adapters, or parallel route support until tested. Avoid breaking deep links or saved application state.

### Backend routing

Use one FastAPI app that includes versioned, app-scoped routers (for example `/api/v1/portfolio/...` and `/api/v1/planning/...`). Existing Portfolio routes may remain available during transition. Do not rename established endpoints without a compatibility and contract plan.

## 5. App registry and private App Hub

The App Hub is an **application catalog**, not a second business-logic system. App metadata should be machine-readable and used to drive both portal cards and architecture checks.

Illustrative `app.yaml`:

```yaml
schemaVersion: "1"
app:
  id: planning
  name: Planning
  description: Private planning and task tracking
  icon: clipboard-list
  route: /apps/planning
  status: active
ownership:
  webModule: planning
  apiModule: planning
  databaseSchema: planning
security:
  requiresAuthentication: true
  permissionNamespace: planning
release:
  lifecycle: development
```

The registry should validate uniqueness of app IDs, routes, module ownership and database schemas. Its values **do not grant access**; an authenticated backend independently enforces permissions.

The hub should provide a consistent visual card for each registered and permitted application, with name, purpose, optional status and a direct route. App-specific menus appear after launching an app; the shell continues to provide global navigation back to the hub.

## 6. Shared platform products

### 6.1 UI and UX (`@personal/ui` — provisional name)

Start by identifying proven generic Portfolio components. Likely candidates include:

- Design tokens: typography, spacing, neutral colors, semantic statuses, density, motion and accessibility.
- Application shell, page header, breadcrumbs, sections, responsive navigation and page templates.
- KPI/metric cards, compact dashboards, reusable data-table shell, search/filter controls, chart containers and legends.
- Forms, validation messages, confirmation dialogs, detail drawers and empty/loading/error/unauthorized states.
- Source/freshness indicators that are domain-neutral.

Retain domain-specific portfolio tables, valuation charts, score rules and financial calculations within Portfolio. Extract components incrementally and demonstrate them in a reference/gallery page. Maintain accessibility, keyboard navigation, dark/light theme behavior if supported, and desktop/mobile responsiveness.

**Design rule:** Shared look and interaction quality; not forced identical content or page layouts.

### 6.2 Authentication and authorization

Design for one personal identity first:

- Choose a supported OIDC/OAuth provider and verify identity on a trusted server.
- Protect the hub and every app page/API as appropriate. An authenticated browser session alone does not authorize backend writes.
- Ensure Render/FastAPI can verify the trusted identity and relevant app permissions (via a secure gateway and/or validated token), rather than trusting arbitrary browser-provided headers.
- Use secure session cookies, CSRF protections for cookie-authenticated mutations, appropriate token validation, secret rotation, and per-environment configuration.
- Begin with an explicit approved-user allowlist and app-scoped permissions; evolve beyond this only when a real additional-user need arises.
- Avoid introducing a second identity store or custom password system merely to create the portal.
- Never rely on client-side hidden buttons as the authorization boundary.

**Authentication implementation is a security milestone:** Select a concrete provider after inspecting actual hosting constraints. Do not declare the platform secure merely because an `auth` package exists.

### 6.3 API and domain contracts

All modules should follow consistent conventions for:

- Versioned API paths and typed input/output validation (Pydantic/OpenAPI/TypeScript).
- Standardized error envelopes, pagination/filtering, request IDs and safe logging.
- Feature-specific service boundaries; calculations and business rules belong in the backend, not duplicated in React.
- Runtime validation at external boundaries, including provider data and AI-generated inputs.
- Contract compatibility and consumer tests.
- Explicit missing/unknown states rather than coercion to a plausible value.

App modules should not import one another's private implementation directly. Shared concepts belong in documented contracts or a small platform package; cross-app business requests should use an approved service/domain API.

### 6.4 Database and transaction safety

**Initial choice:** one Neon project and one PostgreSQL database. Add new application-owned schemas (`planning.*`, etc.) and a small `platform.*` schema for genuine shared platform metadata.

**Portfolio migration exception:** existing Portfolio domain tables are currently in `public.*`. Leave them there through the initial canonical bootstrap and stabilization. Treat them as Portfolio-owned by policy. Moving them into `portfolio.*` is **optional future work** requiring independent migration and rollback testing.

Baseline standards for new app modules:

1. Define an explicit table/schema owner, approved relationships and stable IDs.
2. Use SQLAlchemy models and reviewed Alembic migrations; never modify production schema through startup `create_all()` or ad hoc agent SQL.
3. Each business mutation has a clear transaction boundary: all related writes succeed together or roll back together.
4. Use database constraints for key invariants and application-level validation for domain rules.
5. Use optimistic concurrency or equivalent conflict checks for edits that may race, plus idempotency keys/receipts for replayable operations.
6. Keep audited history append-only where the domain requires it; do not blanket-apply event sourcing to every table.
7. Enforce trusted actor identity, app-scoped permissions, ownership and useful audit metadata.
8. Restrict cross-schema access. A shared physical DB is not an authorization mechanism; use least-privilege DB roles where practical.
9. Run migrations first in an isolated database/schema and verify upgrades, compatibility and recovery before production.
10. Guard production writes, migrations, destructive operations and import/reconcile flows behind explicit, scoped authorization.

Initially use **one coordinated Alembic migration chain** for the single backend. Add automated migration-ownership checks so an unrelated app migration cannot silently modify Portfolio-owned tables. Separate migration streams can be considered later if the complexity actually warrants them.

### 6.5 App-owned vs shared data

- Each app declares the domain facts it owns, reads, derives and imports.
- Shared business concepts require documented identity, meaning, read/write authority and compatibility rules.
- Other applications reference or consume a domain contract; they do not create parallel authoritative copies without a reviewed purpose.
- Imported external facts retain source/provenance/freshness, and the ingest process must not silently overwrite newer accepted application state.
- Avoid generic cross-app direct table joins as the primary integration contract, even if a shared DB makes them technically possible.

For Portfolio specifically, preserve the reviewed Company → Security → Listing identity model, financial-model semantics, revision history, currency boundaries, explicit lifecycle, and the distinct roles of Google Sheets and canonical Neon state during migration.

### 6.6 Agent skills and engineering standards

Store short, tested playbooks for recurring tasks, such as:

- `create-application`: generate a module, register routes, and deliver a working end-to-end example.
- `create-domain`: discover existing contracts before adding tables or fields.
- `review-database-change`: assess migration scope, transaction boundaries, conflicts and rollback.
- `review-api-change`: enforce versioning, runtime validation, permission checks and API contracts.
- `review-ui`: verify design-system reuse, usability, desktop/mobile and accessibility.
- `prepare-release`: verify CI, deployment assumptions, data operations and approval gates.

Agent skills guide implementation; **CI policies, tests and permissions enforce the actual boundaries**. An agent should not bypass a failing invariant by editing its test or guard without a documented, reviewed reason.

## 7. Application factory contract

A future command such as `npm run create:app -- planning` is a **target experience**, not an existing command.

Given an application ID, title, purpose and initial feature, the generator should:

1. Check the app registry and domain catalog for duplicate IDs, routes, tables and capabilities.
2. Generate app-specific Next.js routes/features using the shared shell and approved UI primitives.
3. Generate a FastAPI router, Pydantic schemas, a service layer and typed frontend contracts.
4. Propose app-owned database tables/migration files **without applying them to production**.
5. Generate unit, API-integration, database-transaction, authorization and browser smoke-test fixtures.
6. Register the app in the App Hub and validate metadata consistency.
7. Generate a short app README, data-ownership statement and operating notes.
8. Run local quality gates and output a concise implementation/approval report.

The generated app should compile and pass baseline tests **before adding business complexity**. New applications should default to private and disabled/unreleased until reviewed.

**Reuse proof:** First establish the module conventions with a second small, real application (for example planning/tasks) with at least one complete CRUD workflow, a table, form, KPI card, authenticated API, app-owned schema, audit behavior and browser tests. Confirm it appears in the hub and coexists with Portfolio **without requiring another Neon, Render or Vercel deployment**.

## 8. CI, release and architectural enforcement

At minimum, the shared CI pipeline should enforce:

| Rule                  | Enforcement                                                                               |
| --------------------- | ----------------------------------------------------------------------------------------- |
| Code quality          | Lint, formatting, type checks, unit tests and production build                            |
| Module ownership      | Import-boundary rules, app manifests and schema ownership checks                          |
| API compatibility     | Generated-contract and consumer compatibility checks                                      |
| DB safety             | Migration graph check, isolated integration tests, negative permission/concurrency tests  |
| Data safety           | Secret scanning, source-data policy, no raw private snapshots in Git/CI artifacts         |
| UI quality            | Reusable component contract, accessibility checks and representative responsive E2E tests |
| Shared-runtime safety | Cross-app smoke tests on changes to platform packages or the shared shell/API             |
| Production safety     | Owner-reviewed release, explicit migrations, guarded data operations and recovery plan    |

Avoid treating a green unit suite as evidence that production data has been reconciled. Keep **implementation-complete**, **staging-verified**, and **production-ready** separate statuses.

### Release and versioning

- One Vercel project and one Render service means the applications **share a deployment and rollback boundary**.
- Independently version internal app contracts and feature manifests as useful, but do not imply that each module has a physically independent cloud release.
- Prefer small backward-compatible changes and phased rollout with clear migration compatibility windows.
- Production data imports and cloud background jobs need separate operational approval from a normal code release.
- Capture a reproducible deployment record (Git commit, dependency lockfiles, schema version, contract versions, environment, and approval).

## 9. Security, privacy, recovery and operating costs

- Verify repository visibility, tracked sensitive financial/model data, and historical Git objects before publishing or broadening access. Deleting a file in a new commit does **not** remove its prior Git history.
- Keep credentials in approved environment secret stores or ignored local configuration, never in Git or app manifests.
- Verify production recovery options before important migrations/imports; test restore procedures using disposable environments.
- Use least-privilege application credentials, timeouts, rate limits, bounded background work and safe request logging.
- Keep provider refresh jobs, imports and other expensive work outside critical request/response latency where feasible.
- Monitor shared Neon compute/storage and Render/Vercel resource utilization. If one module dominates or threatens other apps, isolate that module instead of forcing strict one-service purity.
- A single shared database and runtime increase blast radius. Any new app that needs materially stronger isolation should trigger an architecture review.

## 10. Capability-led sequencing

[PRODUCT_VISION.md](../PRODUCT_VISION.md) owns the destination and useful Portfolio
release outcomes. [ROADMAP.md](../../ROADMAP.md) is the single execution queue and
capability/evidence inventory. Its C0–C7 milestones replace duplicated phase lists.

Portfolio's reconciled real-data research, valuation and decision workflows come
first. Operational safeguards mature with every privileged operation. Proven shared
components and security conventions may improve early. Major platform extraction
and the App Hub follow useful Portfolio workflows and adequate operational controls.
A real second app validates module ownership and reuse before a generator automates
its repeated structure. Preserve the existing Portfolio routes and tables throughout.

The shared deployment has a compatibility and rollback boundary, implemented through
[native provider releases](../deployment-and-migrations.md). This architecture does
not require a custom release orchestrator. Schema changes remain separately reviewed,
rehearsed and owner-authorized with appropriate recovery protection.

## 11. Decision gates and change discipline

| Proposed operation                                 | Default posture                                                                |
| -------------------------------------------------- | ------------------------------------------------------------------------------ |
| Add a UI component or application page             | Agent may implement in a feature branch; test and review                       |
| Add new app-owned REST endpoint                    | Agent may implement; authorization/contract tests required                     |
| Add app-owned PostgreSQL table                     | Agent may propose migration; isolated test first, production approval required |
| Modify another app's table or API contract         | Cross-app impact review required                                               |
| Change auth/session/permissions                    | Explicit security review and negative tests                                    |
| Import or synchronize authoritative financial data | Source identity, ownership, freshness, preview and approval gates              |
| Apply production migration or destructive change   | Verified target, current backup, explicit approval and rollback plan           |
| Enable unattended ingestion/schedulers             | Separate operational review, bounded cost and failure handling                 |
| Rewrite Git history to remove sensitive data       | Dedicated repository/privacy remediation plan; never incidental cleanup        |
| Split an app into its own deployment               | Evidence-based architecture decision, not default scaffolding                  |

## 12. Architecture questions intentionally left open

Resolve these through small proofs of concept **before implementation in production**, not speculation:

- Exact OIDC provider, session technology, and trust boundary between Vercel and Render.
- Whether named PostgreSQL schemas plus shared DB roles provide sufficient isolation for all intended future apps; introduce dedicated roles where warranted.
- Whether the platform module composition needs more than the existing npm workspace and FastAPI structure before considering another build framework.
- Reliable scheduled job execution and costs under the selected Render/Vercel plans.
- How much of the existing Portfolio UI should move into `packages/ui` versus remain a local feature.
- Whether Portfolio should ever move from `public.*` to `portfolio.*`; **not required for initial success**.
- Exact domain, naming, versioning and public URL choices for the app hub.

## 13. Instructions for AI coding agents

Before any substantive implementation:

1. Read `AGENTS.md` and this architecture decision; inspect the relevant existing app and contract.
2. Classify the task as **platform-shared**, **app-owned**, **migration/operations**, or **cross-app**.
3. Identify affected schemas, APIs, auth boundaries, source authority and other consumer modules.
4. Prefer the smallest backward-compatible change; do not perform speculative generalization or mass rewrites.
5. Reuse shared components and established domain patterns before adding another implementation.
6. Keep changes to Portfolio financial logic semantically identical unless explicitly approved and parity tested.
7. Add/execute appropriate unit, integration, auth-negative, database and E2E tests.
8. Verify that the shared web/API deployment still serves unaffected apps after platform changes.
9. Preserve data provenance and the distinction between missing and zero.
10. Do not initiate production writes, migrations, external ingestion, recurring schedules, credential changes or Git history rewrites without specific operator approval.
11. Report what was implemented, what was actually tested, what remains unverified, and the precise next approval gate.

**The app factory is successful only when the second app becomes easier to ship without making Portfolio less reliable.**
