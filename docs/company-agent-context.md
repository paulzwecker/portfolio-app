# CompanyAgentContextV1 — read-only company research context

The canonical endpoint is `GET /v1/companies/{company_id}/agent-context`.
It combines existing accepted PostgreSQL domains into one typed response for
research agents. It does not introduce new state, calculations, providers, or
automatic write privileges.

## Request and identity

- `company_id`: canonical company UUID (not ticker or a workbook row).
- Optional `portfolio_id`: explicit portfolio selection. With exactly one
  eligible portfolio it is implicit; with multiple portfolios, the response
  marks portfolio context `AMBIGUOUS` until a portfolio is supplied.
- Optional `as_of` (economic date) and `known_at` (timezone-aware database
  knowledge cutoff). Without cutoffs, the endpoint gives a current view.
  When specified, knowledge is conservatively bounded by the as-of day.
- Unknown company and non-existent portfolio/cutoff return 404; invalid
  timestamps produce 422.

The response includes canonical company/security/listing identities, accepted
portfolio holdings and strategic targets, KPI actuals and management guidance,
selected-provider consensus, latest accepted research/thesis streams, accepted
native-model revision outputs and published driver paths, plus imported current
model-output snapshots when requested without historical cutoffs.

## Coverage and response budgets

Each section has `status`, optional `reason`, `latest_recorded_at` and
`truncated`. `NO_DATA` is not zero; `PARTIAL` means the bounded response
omitted further records. The default budgets are:

| Domain | Maximum returned |
| --- | ---: |
| Metric definitions | 80 |
| KPI observations | 80 |
| Active guidance observations | 40 |
| Selected-provider consensus periods | 24 |
| Latest research / thesis streams | 8 each |
| Native models / imported current outputs | 8 each |
| Explicit model-driver rows per native model | 90 |

Research revision subcollections and thesis claims/evidence are also trimmed
with `truncated=true` in their section. Full histories are available at the
stable API resource links included in `resource_links` and model revision
history links. The context is a working brief, not a database export.

Existing selected-provider logic is reused; providers are never blended.
Consensus periods contain only their current selected observation in this
payload; full provider history remains available from the consensus endpoint.

Guidance is selected by issuance/recording time, **not by whether its target
period has ended**. Corrected observations keep original source and supersession
semantics. All values retain their original units, scales, qualifiers and
currencies. Research and thesis streams include their latest revision even if
withdrawn, so an agent never mistakes the earlier publication as still active.
Native revisions are selected from accepted immutable history only.

Imported current model-output snapshots do not have a verified historical
context read. When a historical cutoff is requested they are explicitly marked
`UNSUPPORTED` instead of returning present-day output.

## Security and operations

The normal app endpoint retains the trusted local and server proxy behavior;
model-proposal credentials do not grant context-reading rights. A separate,
disabled-by-default `DATA_UNIVERSE_STEWARD` token can be configured for
a strict allowlist of company UUIDs. It works only for the exact company
`GET /agent-context` route, never for arbitrary resource links, write
endpoints or the broader portfolio API. For this role, the response keeps
company identity, KPI definitions/actuals, management guidance and selected
consensus; it never queries or returns portfolio holdings/targets, research
or thesis content, native models, or imported model outputs. Restricted sections
are explicitly `UNSUPPORTED`, not missing data; links requiring broader
authorization are omitted. Full details and safe activation instructions:
[data-universe-read-access](data-universe-read-access.md).

Do not put proxy secrets or read tokens in ChatGPT prompts, workbook cells,
source documents or public Git. Credentials must be provisioned through an
approved operator secret store. This code introduces no migration, production
activation or live-source permission.

The implementation reuses the existing portfolio overview and selected-provider
consensus readers. Those readers still traverse portfolio and provider history;
future performance tuning should happen at their canonical domain boundary,
not by reimplementing calculations in this contract.
