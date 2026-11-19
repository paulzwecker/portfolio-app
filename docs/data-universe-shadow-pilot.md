# Data & Universe Steward: first API-first shadow pilot

## Outcome

A small, operator-invoked Python CLI reads a **single company** through the
dedicated read-only API credential and compares the returned canonical KPI
history/guidance with an explicitly reviewed primary-source evidence pack.
It prepares typed `MetricDefinitionBatchV1`, `KPIObservationBatchV1`,
and `GuidanceObservationBatchV1` *drafts* where data is genuinely missing.

No new framework, database table, scheduler, paid source, agent account, or
production write privilege is introduced. **The CLI makes only one API GET
request and never POSTs proposals or accepts anything.**

It also supports an offline scoped-context JSON file for synthetic testing.
The production/hosted environment has not been accessed or activated.

## Primary-source rehearsal: Uber Q3 2026

The tracked illustrative source pack is:

`apps/api/tests/fixtures/data_universe_uber_q3_2026.json`

It cites Uber investor relations' November 4, 2026 Q3 release:
https://investor.uber.com/news-events/news/press-release-details/2026/Uber-Announces-Results-for-Third-Quarter-2026/default.aspx

The release reports **4,061 million trips**, **$59,819 million Gross Bookings**
(Q3 2026), and **$63.25–65.25 billion Q4 2026 Gross Bookings guidance**.
Unlike rounded headlines, the actuals retain the detailed millions values.
The source gives a publication *date*, not an exact UTC publication instant:
`reported_at` and `issued_at` remain null instead of being invented.

The fixture's `authored_at` is the synthetic pack preparation timestamp, not
the issuer's publication timestamp. The source pack is reviewed input, not
proof that an autonomous browser fetched or validated the release.

## Local operator command

With an approved read token privately configured in the environment and the
company's exact UUID resolved from canonical identity:

```sh
export DATA_UNIVERSE_READ_TOKEN="(private operator secret)"
node scripts/uv.mjs run --locked --project apps/api \
  python -m portfolio_api.data_universe_shadow \
  --api-base-url https://your-approved-api-host.example \
  --company-id YOUR-CANONICAL-UBER-UUID \
  --source-pack apps/api/tests/fixtures/data_universe_uber_q3_2026.json \
  --output /tmp/uber-shadow-first-run.json
```

Do not put a real token or private output into Git, Google Sheets, prompts,
test snapshots or CI logs. Output must be outside the repository; the CLI creates
it with owner-only permissions and refuses overwrites. Hosted credential setup
and running against live accepted state require operator authorization.

For offline synthetic tests, replace `--api-base-url` with
`--context-file /path/to/isolated-scoped-context.json`, using a matching
synthetic company UUID and UBER listing. No token or external network is needed.

## Fail-closed comparison semantics

- Company ID must match the selected canonical identity; ticker must match a
  canonical listing. A full portfolio-context response is rejected.
- Defining metric semantics with an existing incompatible metric ID is a
  **conflict**, not a silent dictionary rewrite.
- Matching accepted observations produce no proposal.
- Existing observations with conflicting values produce a **human correction
  requirement**. The CLI deliberately does not invent supersession IDs.
- Truncated or unsupported KPI/definition/guidance history cannot prove a
  missing observation. The result reports `INCOMPLETE_CONTEXT` instead of
  staging unreliable additions.
- Missing metric definitions are drafted separately. Associated KPI/guidance
  drafts explicitly require definition acceptance first.
- Stable local batch keys are computed from pack contents, selected company
  identity and pack authoring timestamp. Re-running the same inputs produces
  the same drafts; no submission occurs.

The output is `DataUniverseShadowReportV1`: source reference and date, context
knowledge cutoff, per-metric findings, fully typed local proposal drafts, and
`writes_performed=false`.

## Evidence boundary and next step

Synthetic unit tests validate the report against accepted, missing, conflicting,
and truncated-context cases. This proves only deterministic local behavior.
To demonstrate a *real* API-first steward, an operator must authorize a hosted
read token/company allowlist, run the CLI on that exact approved company, and
check the output against the source release and current database state.
A subsequent agent may research and author the same evidence pack, but must
still submit any proposed accepted change through the existing human reviewer
workflow, not by direct SQL or workbook edits.

The CLI never retrieves issuer pages or scrapes arbitrary websites; source-pack
authoring and public disclosure verification are intentionally separate from
the canonical-read and proposal-comparison logic.
