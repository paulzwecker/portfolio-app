# Google Sheets risk assessments

Risk assessments are qualitative research judgments authored by the Sheets research
agent and accepted into append-only application history after explicit review. They
are separate from the numeric canonical Risk score and from deterministic portfolio
exposure, concentration, valuation, ranking and Execution Pace calculations.

## Contract and baseline

The portable contract is `RiskAssessmentContractV1` version `1.0.0`. It is a full
snapshot for one `portfolio_id` and `stream_key`, with a unique
`external_revision_id`, optimistic `supersedes_revision_id`, author/source identity,
`authored_at`, `published_at`, summary, rationale and `COMPLETE` or `PARTIAL`
coverage. Partial coverage requires a note. Findings use stable keys and state their
company or portfolio scope, category, severity, confidence, status, change direction,
rationale and zero or more evidence references.

Every contract must identify the exact state that the research agent reviewed:

- portfolio-state contract version `1.0.0`
- published state fingerprint
- holdings snapshot ID
- accepted target revision ID, or explicit `null`
- valuation cutoff

The API reconstructs the cited state at `valuation_as_of` and verifies both its
identifiers and fingerprint. It then compares that baseline with current canonical
state. A changed holdings/target or changed price/FX valuation produces
`STALE_PORTFOLIO_STATE`; stale holdings and incomplete current valuation have their
own states. A stale assessment remains visibly linked to the older snapshot and can
enter accepted history only after a reviewer checks an explicit acknowledgement.
Acceptance never relabels the cited baseline as current.

The fingerprint deliberately excludes request-time valuation mode/cutoff and
holdings-age display fields. Freshness and valuation availability are checked as
separate baseline states; actual position, target, quote, FX and quality inputs remain
fingerprinted. A new market observation can therefore make a prior assessment stale
without changing its stored historical baseline.

Supported finding categories include business, financial, geographic, currency,
business-model, regulatory, governance, geopolitical, portfolio concentration and
exposure, thesis change and other. Severity is `LOW`, `MEDIUM`, `HIGH` or `CRITICAL`;
confidence is `LOW`, `MEDIUM`, `HIGH` or `UNASSESSED`. Evidence can point to a source
document, reported-fundamental observation, thesis revision/claim, external source
identifier or HTTPS URL. Canonical references must exist and company-scoped evidence
must match its finding's company.

The domain persists each accepted revision, its finding snapshot and source links.
Rows are append-only. Reusing an external revision ID with different content is a
conflict; concurrent revisions based on an older accepted revision are conflicts;
identical inbox replay does not create another revision. Review candidates and sync
runs are separately retained. Rejection is a final review decision, not deletion.

## API and review

The fixed `Application Risk Assessment Inbox` is the only workbook range read for
these contracts. It uses the same five-column append-only chunk protocol as model
contracts, but a separate tab, candidate table and review flow:

- `GET /v1/google-sheets-risk-sync/status`
- `POST /v1/google-sheets-risk-sync/connection-test`
- `POST /v1/google-sheets-risk-sync/check`
- `GET /v1/google-sheets-risk-sync/candidates` and `/runs`
- `POST /v1/google-sheets-risk-sync/candidates/{id}/preview`, `/accept` or `/reject`
- `GET /v1/portfolios/{portfolio_id}/risk-assessments`
- `GET /v1/companies/{company_id}/risk-assessments`

The `/model-sync` page includes the separate assessment review area. Preview shows
baseline state and finding-level changes. Acceptance requires a named reviewer and
note; stale or incomplete baselines also require an explicit acknowledgement. No
contract automatically alters holdings, targets, financial-model assumptions,
canonical Risk scores, lifecycle, rankings or Execution Pace.

The Company Explorer shows company-linked findings and prior accepted revisions.
Portfolio shows accepted portfolio-level findings. The Attention Center emits only
active `HIGH`/`CRITICAL` findings marked `NEW` or `WORSENING`, with direct links to
the accepted assessment; ordinary unchanged findings remain in the research view.
Deterministic current weights and currency exposures remain the Portfolio API's
observed calculations and are not copied into this qualitative assessment domain.

## Workbook publication

Keep research drafting separate from publication. The agent prepares a complete
contract in `Risk Assessment Contract!A1`, based on a recently published
`Application Portfolio State`, and uses the workbook menu item **Publish risk
assessment to application inbox**. The adapter appends to the fixed risk inbox,
detects exact replay, and rejects reuse of one external revision ID for changed or
incomplete content. It does not write to the model inbox or portfolio-state tab.
The app then checks, validates, previews and waits for a human review decision.

`tools/google-sheets/README.md` contains the agent-facing publication checklist and
required fields. No risk assessment is migrated from workbook cells automatically.
