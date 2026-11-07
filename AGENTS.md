# Portfolio agent entrypoint

Build Personal Universe, a private extensible app store with a unified App Hub and
shared identity, design, navigation, API/database conventions and safe operations.
Portfolio Research is the flagship. Make its real-data investment workflows useful
before major platform extraction. Prefer one Next.js/Vercel, FastAPI/Render and
Neon stack where cost, security and reliability support it. Follow owner instructions,
this file, scoped `AGENTS.md` files and relevant domain contracts in that order.
Resolve conflicting documents by preserving established financial and production
behavior, recording the conflict and obtaining a decision where required.

## Read selectively

1. Read `ROADMAP.md` for the cursor and `docs/ACTIVE_WORKSTREAM.md` for current
   build context, then inspect Git/worktrees before work.
2. Use `docs/README.md` to find the applicable contract or runbook.
3. Read `docs/PRODUCT_VISION.md` for product outcomes and
   `docs/architecture/portfolio-application.md` for Portfolio architecture.
4. Read scoped API/web guidance when touching those areas. Read the platform
   architecture only for shared-platform work. Historical reports are supporting
   evidence for their recorded date.

## Preserve the contracts

- Identity follows Company → Security → Listing. Keep currencies, share bases,
  fiscal periods, effective/observed/recorded times and source evidence explicit.
- Each model/listing/method has independent inputs, outputs and immutable revisions.
  Company valuation synthesis requires an explicit, versioned economic contract.
  Enterprise UFCF IRR and shareholder-return methods retain distinct semantics.
- Preserve Bear/Base/Bull probabilities, native parity and investment rules.
  Durability, Quality, Execution and Risk remain independent. Lifecycle is explicit.
- Missing values remain unavailable. Keep holdings, strategic targets, investment
  interpretation and execution authority separate.
- Provider refresh and transaction-based portfolio accounting are core outcomes.
  Preserve verified snapshots during ledger migration. Never infer past trades,
  acquisition costs or performance from current holdings. See Portfolio architecture.
- Sheets is the agent modeling workspace. Completed model publications cross a
  versioned contract into review proposals. PostgreSQL owns accepted revisions.
  See `docs/model-publications.md` and `docs/financial-models.md`.
- FastAPI owns financial validation/calculation. Next.js owns presentation.
  Reuse existing engines, source adapters, worker patterns and typed contracts.

## Execute and record

Preserve branches, stashes, edits and private artifacts. Continue an applicable open
feature PR with unfinished work. Keep completed PRs stable during owner review.
Choose the highest-value ready capability in `ROADMAP.md`, checking its actual
data, code and authorization dependencies. Prefer a complete investor workflow over
another preparation layer. If an owner gate blocks it, advance an independent ready
capability. Shared foundations may emerge early from demonstrated Portfolio needs.
Commit coherent increments. Verify focused behavior, integration and
security, then perform an independent second-pass review. Validate desktop/mobile
for UI changes. Fix findings before declaring completion.

Update the concise roadmap after each subtask with actual evidence and the next
step. Put lasting behavior in its canonical reference, commands in runbooks and
long evidence in dated history. At an integration boundary push the feature branch
and open or update one cohesive PR. Distinguish implementation/local verification,
live-source validation, production preview and production application. Feature code,
fixture tests and historical local coverage establish their own scope. Require
current target-bound reconciliation and user readback for operational claims.

## Authorization and privacy

Local code, documentation, isolated tests/migrations, authorized read-only source
checks, commits, feature pushes and PRs are autonomous. Separate owner authorization
is required for production writes/migrations/deployments, source Sheets edits,
model/research acceptance, live credential/provider changes, recurring activation,
protected merges and destructive/history-rewriting Git actions.

Before an authorized production action verify the exact target, scope, immutable
inputs, preview, recovery and rollback procedure through existing guards. Terminal
access alone grants no network or production authority. Keep credentials, private
workbooks, model packages and sensitive reports outside public Git and task logs.
