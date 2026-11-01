# Financial model workspace operating procedure

The Company Explorer **Valuation** view is the review surface for accepted
financial models and agent-authored model proposals. PostgreSQL remains the
authority for accepted revisions. Imported published-output snapshots are
read-only evidence and are never presented as native calculations.

## Inspecting an accepted model

1. Open a company and select **Valuation**.
2. Review the accepted model's methodology, model currency, exact valuation
   listing, current output status, effective time, application-recorded time,
   source, and rationale.
3. Use the Bear/Base/Bull selector to inspect the accepted scenario values and
   retained assumptions. Expected return, hurdle, and excess return are shown
   only when supplied by the canonical model output and its return method.
4. Expand **Accepted revisions, imported outputs & migration diagnostics** to
   review immutable revision summaries, imported output history, numerical
   migration/parity status, and source quality details.
5. For input-level comparisons, open the applicable method editor. The editor
   loads only the selected methodology and offers its existing revision
   inspection/comparison workflow. DCF, owner-cash-flow, and residual-income
   inputs remain separate contracts and engines.

Missing outputs, stale prices, unsupported methods, absent history, and parity
checks stay explicit. They are never converted to zero or treated as a passing
calculation.

## Reviewing an agent model proposal

The proposal panel uses the reviewer-only
`GET /v1/model-revision-proposals?company_id=<canonical-company-uuid>&limit=100`
API, so unrelated submissions cannot hide older work for the current company.
It displays producer, external revision, canonical model/listing identity, base
revision, rationale, source reference, supporting evidence, and conflicts.

1. Select a proposal and verify that its source evidence and base revision are
   appropriate.
2. Select **Preview changes**. The backend validates the current base and
   recalculates through the existing deterministic method engine. A `READY`
   result shows input and output differences; `CONFLICT` and `INVALID` remain
   blocked with the server-provided reason.
3. Enter a review note. Acceptance is enabled only for a current `READY`
   preview with a preview fingerprint.
4. Select **Accept revision**, review the confirmation prompt, then select
   **Confirm acceptance**. The server rechecks the base and preview fingerprint
   in the acceptance transaction and appends an immutable canonical revision.
5. Alternatively, enter a review note, select **Reject proposal**, and confirm.
   Review decisions remain recorded in proposal history.

Previewing does not accept or persist a financial-model revision. A stale base,
changed market input, missing reviewer authorization, or conflicting proposal
must be resolved before acceptance. A successful acceptance refreshes the
Company Explorer model summaries; it does not change holdings, targets,
lifecycle, canonical scores, or execute a trade.

## Authentication and operations

The backend uses separate agent and reviewer role tokens. The web server must
hold `MODEL_PROPOSAL_REVIEWER_TOKEN` and forward it only to the dedicated
proposal reviewer routes; the token is never sent to the browser. The backend
also requires its normal `API_ACCESS_TOKEN` when remote access is enabled.
Configure the matching reviewer token and reviewer identity on the API side,
and the reviewer token in the web server environment. Do not expose either
role token to browser code or agent prompts. If the reviewer token is absent,
the proposal panel reports that reviewer access is unavailable and performs no
request to the API.

Agent submission remains a separate authenticated API operation using the
agent role token. The web review surface does not submit proposals and does not
automatically approve them. See [Agent model revision proposals](agent-model-revision-proposals.md)
for the versioned envelope, producer authentication, and endpoint details.

## Verification scope

The automated UI workflow uses synthetic API responses and runs in both
configured Playwright projects (desktop and mobile). It verifies proposal
discovery, deterministic preview display, note-required acceptance, explicit
confirmation, and accepted-revision acknowledgment. It does not establish that
a real package has been imported or that a live production reviewer credential
is configured. A production review requires the independently authorized
package import and deployed schema/API setup documented by the operator.
