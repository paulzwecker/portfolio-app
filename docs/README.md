# Documentation index

## Authority and maintenance

| Information                              | Canonical owner                                       |
| ---------------------------------------- | ----------------------------------------------------- |
| Agent rules                              | [AGENTS.md](../AGENTS.md) and scoped API/web guidance |
| Personal Universe and Portfolio outcomes | [PRODUCT_VISION.md](PRODUCT_VISION.md)                |
| Current work and verified status         | [ROADMAP.md](../ROADMAP.md)                           |
| Financial/domain behavior                | Applicable reference below                            |
| Operational procedures                   | Safety/runbooks below                                 |
| Long results and past environments       | Dated history and reconciliation records              |

Read only the references needed for the task. Each PR updates its canonical
reference and a short roadmap entry. Preserve long results in dated history when
they would obscure current execution. Run `npm run docs:check` after link edits.

For model sync, start with [publications](model-publications.md) and
[Sheets synchronization](google-sheets-sync.md). For economic questions use
[financial models](financial-models.md) and [return semantics](return-semantics.md).
For database operations use [write targets](database-write-targets.md) and
[deployment/migrations](deployment-and-migrations.md). The
[production baseline](production-canonical-baseline.md) records verified cloud scope.

## Product and architecture

- [Product vision](PRODUCT_VISION.md)
- [Portfolio architecture](architecture/portfolio-application.md)
- [Shared design system and frontend conventions](design/design-system-and-frontend-architecture-11b.md)
- [Personal Universe architecture](architecture/personal-universe.md)
- [Explicit publication decision](architecture/decisions/001-explicit-model-publications.md)
- [Independent-model decision](architecture/decisions/002-independent-company-models.md)

## Models and publications

- [Agent Model Revision Proposals v1](agent-model-revision-proposals.md)
- [domain-model](domain-model.md)
- [Google Sheets UFCF DCF Model Package v2](financial-model-package-templates-v2.md)
- [Financial Model Package v1 — P-GOOGL Proof of Concept](financial-model-package-v1.md)
- [Multi-Archetype Financial Model Package v3](financial-model-package-v3.md)
- [Canonical financial models](financial-models.md)
- [Google Sheets model synchronization](google-sheets-sync.md)
- [Model and analytics bootstrap](model-analytics-bootstrap.md)
- [Model-only canonical identity bootstrap](model-identity-bootstrap.md)
- [Legacy financial-model migration inventory](model-migration-inventory.md)
- [Canonical model-output ingestion](model-output-ingestion.md)
- [Model publications](model-publications.md)
- [Financial model workspace operating procedure](model-workspace-operating-procedure.md)
- [Native Google Sheets canonical source-value bundle](native-google-sheets-source-value-bundle.md)
- [Native financial-model input migration](native-model-input-migration.md)
- [Agent-assisted research-to-model workflow](research-to-model.md)
- [Expected-return semantics and comparability](return-semantics.md)

## Source data and bootstrap

- [Canonical Portfolio Bootstrap (14B-R.4)](canonical-portfolio-bootstrap.md)
- [Cloud-native canonical baseline runbook](cloud-native-bootstrap-runbook.md)
- [Canonical consensus estimates](consensus-estimates.md)
- [Canonical external-data architecture](external-data-architecture.md)
- [External-data ingestion operations](external-data-operations.md)
- [Financial statements and evidence bootstrap](fundamentals-source-bootstrap.md)
- [Historical market-data bootstrap](historical-market-data-bootstrap.md)
- [Market data and current valuation](market-data.md)
- [Minimal Google Sheets Portfolio Bootstrap](minimal-sheets-portfolio-bootstrap.md)
- [Canonical reported fundamentals](reported-fundamentals.md)
- [Canonical filings and source documents](source-documents.md)
- [workbook-import](workbook-import.md)
- [Private workbook source acquisition](workbook-source-acquisition.md)
- [Workbook Sync Operations](workbook-sync-operations.md)
- [Workbook source ownership and future synchronization contract](workbook-sync-ownership.md)

## Portfolio and research

- [Candidate Research Pipeline](candidate-pipeline.md)
- [Estimate Momentum](estimate-momentum.md)
- [Execution Pace](execution-pace.md)
- [Forecast accuracy and consensus benchmarking](forecast-accuracy.md)
- [Canonical investment thesis and evidence](investment-thesis.md)
- [Portfolio experience](portfolio-dashboard.md)
- [Candidate portfolio ledger](portfolio-ledger.md)
- [Canonical Portfolio Rank](portfolio-rank.md)
- [Research Agent Operations Contract](research-agent-operations.md)
- [Canonical agent-authored research](research-forecasts.md)
- [Research Coverage & Review Queue](research-queue.md)
- [Canonical Research Rank](research-rank.md)
- [Research Event & Trigger Engine](research-triggers.md)
- [Google Sheets risk assessments](risk-assessments.md)
- [Temporal forecast and outcome alignment](temporal-alignment.md)
- [Thesis Watch integration](thesis-watch-integration.md)
- [watchlist-rank](watchlist-rank.md)

## Safety, development and operations

- [Attention Center](attention-center.md)
- [Milestone 13B — Neon Provisioning & Cloud Deployment Activation](cloud-deployment.md)
- [Codex Cloud development runbook](codex-cloud-development.md)
- [Company Explorer](company-explorer.md)
- [Verified database write targets](database-write-targets.md)
- [Scenario Calibration & Investment Decision Evaluation](decision-evaluation.md)
- [Native deployment and separately reviewed migrations](deployment-and-migrations.md)
- [Expected-return attribution](expected-return-attribution.md)
- [Expected-return history](expected-return-history.md)
- [Canonical PostgreSQL migration preparation](postgresql-migration.md)
- [Canonical production portfolio baseline](production-canonical-baseline.md)
- [Controlled production market and SEC ingestion](production-data-ingestion-operations.md)
- [Recurring Data & Research Operations](recurring-operations.md)
- [PostgreSQL development targets](remote-development-postgresql.md)
- [Testing and verification](testing.md)

## Historical entrypoints

- [Architecture reference](architecture.md)
- [Workbook Bootstrap Readiness Ledger](bootstrap-readiness-ledger.md)
- [Cloud-native bootstrap readiness](cloud-native-bootstrap-readiness.md)
- [migration](migration.md)
- [Milestone audit and YAGNI pass](milestone-audit-yagni.md)
- [Milestone 6.1 — Operational coverage and integrity audit](operational-coverage-audit.md)
- [Verification](verification.md)
- [workbook-map](workbook-map.md)

## Evidence, design and adapter directories

- [Implementation ledger through MP2.1](history/roadmap-through-mp2-preflight-2026-11-07.md)
- [Complete original roadmap](history/roadmap-through-mp1.md)
- [Historical verification](history/verification-through-2026-10.md)
- [Legacy architecture](history/architecture-through-2c.md)
- [Audit inventory of all 125 original Markdown files](history/documentation-audit-2026-11-07.md)
- [Sheets adapter and role instructions](../tools/google-sheets/README.md)
- `docs/design/` retains approved UX contracts and dated design verification.
- `docs/reconciliation/` retains source, parity and operational evidence by date.
- `docs/architecture/decisions/` records material architectural choices.

Distinct package v1/v2/v3 and minimal/full-workbook contracts remain available for
replay of their implemented workflows. Historical results establish their stated
scope and date. Reverify current target identity, configuration and approval through
the relevant operational runbook.
