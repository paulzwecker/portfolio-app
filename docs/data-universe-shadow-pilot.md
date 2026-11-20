# Data & Universe Steward: first API-first shadow pilot

## Outcome

A small, operator-invoked Python CLI reads a **single company** through the
dedicated read-only API credential and compares the returned canonical KPI
history/guidance with an explicitly reviewed primary-source evidence pack.
It prepares typed `MetricDefinitionBatchV1`, `KPIObservationBatchV1`,
and `GuidanceObservationBatchV1` _drafts_ where data is genuinely missing.

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
The source gives a publication _date_, not an exact UTC publication instant:
`reported_at` and `issued_at` remain null instead of being invented.

The fixture's `authored_at` is the synthetic pack preparation timestamp, not
the issuer's publication timestamp. The source pack is reviewed input, not
proof that an autonomous browser fetched or validated the release.

### Bounded primary-source verification (Uber pilot)

The optional `--verify-public-source` switch performs **one direct HTTP GET**
against that exact Uber investor-relations URL, with no redirects, cookies,
token or arbitrary target domain. It parses the main operating table only
when the issuer, release date, 2025 → 2026 columns and millions units are
unambiguous. The separately labeled Q4 outlook must contain the complete
Gross Bookings range. Values, scale, basis, fiscal period, qualifier, source
identity and the explicitly unknown publication time must match the reviewed
`DataUniverseEvidencePackV1` exactly. Any changed, inaccessible, oversized,
unexpected or ambiguous page **fails closed before the private context GET**.
This is a _narrow verified profile_, not generic automated issuer scraping.

The resulting private `DataUniverseShadowReportV1` adds
`source_verification.status=SOURCE_MATCHED`, the public page SHA-256, checked
UTC time, exact source URL and three matched fact IDs. Without the switch the
report instead explicitly says `NOT_CHECKED`. The hash identifies the fetched
bytes for operator audit; it is not a publication signature or evidence that
a later issuer revision remained unchanged. The source-check extracts
public numbers but never automatically publishes observations.

This is an opt-in source read, not a scheduled scraper, crawler or production
agent deployment. The isolated tests use a small synthetic HTML excerpt of
the externally cross-checked disclosed figures; they never issue a network
request. The one-time read-only GitHub Actions pilot on **November 20, 2026**
successfully fetched the live issuer page and matched all three facts:
[run #44696041668](https://github.com/paulzwecker/portfolio-app/actions/runs/44696041668).
The recorded page SHA-256 begins `af725f990041e608`. No canonical API,
database, source Sheet or private credential was used in that live source check.
The temporary workflow was removed; subsequent live checks remain explicit
operator invocations and may fail on publisher-side blocks.

## First held-company pilot: Booking Holdings Q3 2026

The new **BKNG** profile uses the original SEC Form 10-Q, accession
`0001075531-26-000045` (filed November 3, 2026), for the quarter ended
September 30, 2026:

https://www.sec.gov/Archives/edgar/data/1075531/000107553126000045/bkng-20260930.htm

The reviewed test pack
`apps/api/tests/fixtures/data_universe_bkng_q3_2026.json` carries exactly
three company-specific operating actuals: **345 million room nights**,
**21 million flight tickets**, and **USD 54,461 million total gross
bookings**. These are operating measures, not GAAP revenue. SEC tables
report them in _millions_, not exact underlying counts or dollars. Every
observation therefore preserves `value_qualifier=APPROX` and its scale,
and `reported_at=null` because the filing date is not an exact public
release instant. No model driver, guidance or return prediction is inferred.

### Canonical identity: SEC CIK before ticker

The issuer's public CIK is **0001075531**. The existing canonical
`company_provider_identifiers` table, not a ticker-only inference,
must already contain one operator-reviewed mapping to Booking Holdings.
The scoped `CompanyAgentContextV1.sec_identity` now returns a time-filtered
`MAPPED` SEC CIK only when the stored evidence URL and CIK pass existing
issuer-mapping validation. The shadow comparator **enforces** that the CIK
equals `0001075531`; missing, invalid or ambiguous mappings fail closed
_before_ any reviewed batch becomes eligible.
A read-only operator can inspect it with the following **SELECT only**,
alongside the exact security/listing identity:

```sql
SELECT c.id AS company_id, c.name, p.identifier_value AS sec_cik,
       l.ticker, l.venue, l.currency
FROM company_provider_identifiers AS p
JOIN companies AS c ON c.id = p.company_id
JOIN securities AS s ON s.company_id = c.id
JOIN listings AS l ON l.security_id = s.id
WHERE p.provider_id = 'sec_edgar'
  AND p.identifier_type = 'SEC_CIK'
  AND p.identifier_value = '0001075531'
  AND l.ticker = 'BKNG';
```

Continue only if the result identifies exactly one reviewed issuer/listing
with a matching Booking Holdings name and the supported USD common-stock
listing. **Do not** create a new company, invent a UUID, change a mapping
or infer identity from `BKNG` alone. A missing or conflicting crosswalk
blocks the live pilot until separately reviewed.

The scoped Data & Universe read token must have that UUID explicitly
allowlisted. Its context still hides private holdings, thesis and models.
After **separate read-only operator authorization**, the offline-first
command can be run with the exact UUID and private read token:

```sh
export SEC_USER_AGENT="(operator-configured SEC fair-access contact)"
node scripts/uv.mjs run --locked --project apps/api \\
  python -m portfolio_api.data_universe_proposal_handoff \\
  --api-base-url https://your-approved-api-host.example \\
  --company-id THE_REVIEWED_BOOKING_COMPANY_UUID \\
  --source-pack apps/api/tests/fixtures/data_universe_bkng_q3_2026.json \\
  --output /tmp/bkng-q3-2026-private-review-plan.json
```

The SEC public GET requires an operator-configured contact user-agent
(`SEC_USER_AGENT`). It uses the _single exact 10-Q URL_, HTTPS, bounded
bytes/time, no redirects and no paid provider. Any inaccessible, changed,
malformed, conflicting or ambiguous source fails closed. The default
command produces only an owner-only private review plan, not a proposal
POST. Agent submission, reviewer acceptance and production configuration
remain separate gates. Synthetic PostgreSQL tests prove the SEC CIK →
company/listing → reviewed definition/actual → accepted scoped-read
journey; **no production Booking UUID or live database read has been
established by this development slice**.

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
  --verify-public-source \
  --output /tmp/uber-shadow-first-run.json
```

Do not put a real token or private output into Git, Google Sheets, prompts,
test snapshots or CI logs. Output must be outside the repository; the CLI creates
it with owner-only permissions and refuses overwrites. Hosted credential setup
and running against live accepted state require operator authorization.

For offline synthetic tests, replace `--api-base-url` with
`--context-file /path/to/isolated-scoped-context.json`, using a matching
synthetic company UUID and UBER listing, and **omit**
`--verify-public-source`. No token or external network is needed.

An isolated PostgreSQL integration test proves the complete **public values →
typed local shadow drafts → dedicated agent proposal endpoint → human-role
preview/fingerprint/acceptance → accepted scoped context → zero duplicate
drafts** path. Its reviewer decisions and canonical writes occur **only**
against disposable test data. It does not show that production was migrated,
that a live owner-company read succeeded or that acceptance was approved.

## Verified proposal handoff (separate, default-off command)

The read-only shadow report remains unchanged. For a real operator to hand
verified facts into the **existing** human-review inbox, use
`portfolio_api.data_universe_proposal_handoff`. This command rechecks the
official issuer HTML and the latest scoped canonical context. It never
accepts canonical observations or calls reviewer endpoints.

Its normal mode is **dry-run**: it writes a private, owner-only
`DataUniverseReviewHandoffV1` report, never an API POST. The report
contains source SHA-256, comparison findings, typed eligible batches and
deferred batch types. Conflicting or incomplete canonical context yields
**no** eligible batches. If metric definitions are still missing, only
`MetricDefinitionBatchV1` is eligible; KPI/guidance batches remain deferred
until the reviewer accepts definitions and a fresh run reconfirms the data.

```sh
node scripts/uv.mjs run --locked --project apps/api \\
  python -m portfolio_api.data_universe_proposal_handoff \\
  --api-base-url https://your-approved-api-host.example \\
  --company-id YOUR-CANONICAL-UBER-UUID \\
  --source-pack apps/api/tests/fixtures/data_universe_uber_q3_2026.json \\
  --output /tmp/uber-review-plan.json
```

Only after inspecting that **exact plan** and obtaining separate operator
authorization for candidate writes, explicitly enable the dedicated agent
submission capability in the operator secret store (never in Git or a Sheet):

```sh
export DATA_UNIVERSE_PROPOSAL_SUBMIT_ENABLED=true
export OBSERVATION_PROPOSAL_AGENT_TOKEN="(private dedicated agent role token)"
node scripts/uv.mjs run --locked --project apps/api \\
  python -m portfolio_api.data_universe_proposal_handoff \\
  --api-base-url https://your-approved-api-host.example \\
  --company-id YOUR-CANONICAL-UBER-UUID \\
  --source-pack apps/api/tests/fixtures/data_universe_uber_q3_2026.json \\
  --submit \\
  --batch-id EXACT_READY_EXTERNAL_BATCH_ID_FROM_PLAN \\
  --source-sha256 EXACT_64_CHARACTER_ISSUER_SHA256_FROM_PLAN \\
  --output /tmp/uber-candidate-receipt.json
```

An explicit submission posts **at most one** freshly recomputed batch to
`POST /v1/company-observation-proposals`, using the separate agent token.
It validates a matching source hash and external batch ID, forbids redirects
and checks the server-returned company and proposal content. If the upstream
submission outcome is unknown, rerun the **same batch ID** rather than
minting a new one. The endpoint's replay/conflict and production-write gates
remain authoritative. Only the reviewer can preview/accept/reject, and no
acceptance credentials are used by this command. A source document changed
since dry-run requires a new reviewed plan, not a silent promotion.

Offline synthetic rehearsal uses `--context-file` and `--source-html`
instead of `--api-base-url`, and **cannot submit**. No live company read,
proposal submission or production write has been activated under this PR.
Both the CLI opt-in and the server's separate proposal feature/write gates
must be authorized before live candidate submission.

## Fail-closed comparison semantics

- Company ID must match the selected canonical identity; ticker must match a
  canonical listing. A full portfolio-context response is rejected.
- Defining metric semantics or enabling model-driver use with an existing
  incompatible metric ID is a **conflict**, not a silent dictionary rewrite.
- Matching accepted observations produce no proposal; an accepted PROVISIONAL
  actual does not count as the same quality as VERIFIED primary-source evidence.
  Such discrepancies require human review rather than silent upgrades.
- Evidence dated after pack authorship or the canonical knowledge cutoff is
  rejected before any missing-data drafts are prepared.
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
To demonstrate a _real_ API-first steward, an operator must authorize a hosted
read token/company allowlist, run the CLI on that exact approved company, and
check the output against the source release and current database state.
A subsequent agent may research and author the same evidence pack, but must
still submit any proposed accepted change through the existing human reviewer
workflow, not by direct SQL or workbook edits.

By default, the CLI does not retrieve issuer pages. The approved, fixed-URL Uber and Booking verifiers are the only
public-source GETs and remain deliberately separate from
the canonical-read and proposal-comparison logic. It never POSTs agent
proposals, accepts canonical changes or bypasses the human reviewer. Broader
company adapters must independently establish source rights, identity and
unit/period parsing before activation.
