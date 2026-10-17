# Canonical agent-authored research

## Ownership and boundaries

The research domain stores published, source-linked forecasts and qualitative
company assessments from the external research workflow. It does not replace:

- Third-party consensus observations, which retain provider continuity and analyst
  coverage in the consensus domain.
- Accepted financial-model assumptions, projections or outputs, which remain in
  method-specific model revisions and use deterministic application calculations.
- Canonical investment scores, which remain separately authored, dimensioned score
  assessments.
- Investment theses and keyed claims, which have their own full-snapshot history and
  evidence relationships. See [investment-thesis.md](investment-thesis.md).

A research forecast is not automatically copied into a model assumption, consensus
observation, score, rank or decision input. This milestone does not use research
forecasts in ranking, Expected IRR, temporal forecast-versus-actual alignment or
other investment calculations.

## Supported objects

`ResearchRevision` is an immutable publication in a stable company research stream.
It retains the canonical company and optional security identity, stream key,
external revision ID, contract version, author/source, source reference, author
observation time, application recorded time, rationale, uncertainty, status and
content fingerprint. `supersedes_revision_id` points to the preceding canonical
revision in that same stream. A new publication never edits the old revision.

Each revision can include period-aligned forecast rows for Revenue, EPS, EBIT,
EBITDA, Free Cash Flow and Diluted Shares. Periods use an explicit annual/quarterly
kind, fiscal year and FY/Q1-Q4 label; `period_end` is retained when known and is not
inferred from the calendar year. Scenario labels are POINT, BEAR, BASE and BULL.
Monetary values require an explicit ISO currency and the unit `currency` or
`currency/share`; share counts require the `shares` unit and no currency. Values use
exact `NUMERIC(38,12)` storage.

Forecast and assessment states are AVAILABLE, UNAVAILABLE or DATA_CHECK. AVAILABLE
requires a value or narrative. UNAVAILABLE requires a null value/narrative and an
explicit reason. DATA_CHECK carries a reason and may retain a provisional value or
narrative. An explicit numeric zero remains different from an unavailable null.

Qualitative assessment types are intentionally limited to BUSINESS_OUTLOOK,
COMPETITIVE_POSITION and KEY_RISKS. They contain narrative, uncertainty and a
non-numeric confidence label; they do not reuse score dimensions or score ranges.
Evidence rows link to an existing company source document, an external identifier,
or an HTTPS URL, with an optional excerpt and note.

## Publication contract

`ResearchRevisionContractV1` versions `1.0.0` and `1.1.0` are supported external
publication envelopes. Version `1.1.0` optionally adds `trigger_references` with
canonical trigger IDs and the existing `NOISE`, `INCREMENTAL`, or
`MAJOR-STRUCTURAL` classification plus rationale. Trigger references are
company-validated, cannot be observed before trigger detection, and require HTTPS
source provenance plus an independent source evidence item. Accepted links remain
immutable alongside the research revision. A Sheets agent sends a complete JSON contract to `POST
/v1/research-revisions`; it needs application API access, not PostgreSQL access. Use
canonical company/security UUIDs. A security must belong to the named company, and
linked source documents must belong to that company.

`stream_key` is a stable caller-defined research series within the company. The
first publication uses `supersedes_revision_id: null`. Each later publication must
name the current canonical revision ID. A stale or missing base returns HTTP 409.
An exact replay of the same external revision ID and fingerprint returns HTTP 200
`ALREADY_PUBLISHED`; reusing the ID with changed content returns HTTP 409. A new
publication returns HTTP 201 `PUBLISHED`. `WITHDRAWN` is a new empty revision that
withdraws the current stream without deleting history.

Example shape (fields abbreviated):

```json
{
  "contract_type": "ResearchRevisionContractV1",
  "contract_version": "1.0.0",
  "company_id": "<canonical-company-uuid>",
  "security_id": "<canonical-security-uuid-or-null>",
  "stream_key": "research-agent/company-outlook",
  "external_revision_id": "research-2026-10-15-r2",
  "supersedes_revision_id": "<current-research-revision-uuid-or-null>",
  "author_id": "research-agent",
  "source_id": "google-sheets",
  "source_reference": "https://docs.google.com/spreadsheets/d/<id>/edit#gid=<tab>",
  "observed_at": "2026-10-15T09:00:00Z",
  "status": "PUBLISHED",
  "rationale": "What changed and why this forecast is supportable.",
  "uncertainty": "Key unresolved evidence or range of outcomes.",
  "forecasts": [
    {
      "metric": "REVENUE",
      "period_type": "ANNUAL",
      "fiscal_year": 2027,
      "fiscal_period": "FY",
      "period_end": "2027-12-31",
      "scenario": "BASE",
      "value": "1250000.00",
      "currency": "USD",
      "unit": "currency",
      "availability_status": "AVAILABLE",
      "confidence": "MEDIUM"
    }
  ],
  "assessments": [],
  "evidence": [
    {
      "source_name": "Issuer annual report",
      "external_identifier": "annual-report-2025",
      "source_url": "https://issuer.example/reports/2025.pdf",
      "published_at": "2026-02-20",
      "note": "Evidence supporting the period assumptions."
    }
  ]
}
```

The API validates metric/unit/currency compatibility, fiscal-period labels, identity,
timestamps, value/null status semantics, duplicate period/scenario rows, evidence
links and the supersession base before storing the revision and its child records in
one transaction. The external author should keep unfinished work in Sheets and
publish only a complete reviewed contract. No Google API or database credential is
needed by the contract itself.

## Reads and point-in-time behavior

- `GET /v1/companies/{company_id}/research` returns current revision and descending
  history for each stream.
- Optional `as_of` and timezone-aware `known_at` parameters bound author observation
  time and application recorded time. When both are supplied, `known_at` cannot be
  after the end of the `as_of` date.

The query never reconstructs an older forecast from a newer value. A publication
received later is absent from earlier `known_at` results even if its author-provided
`observed_at` is earlier. The API cannot independently verify when an external agent
actually made a forecast, so `observed_at` remains source-provided provenance while
`recorded_at` is assigned by the application.

## Company Explorer

The Explorer labels the section as agent-authored research, shows author/source,
source links, forecast period/scenario, value/unit/currency, confidence, availability,
rationale and uncertainty, and lets users expand prior revisions. Zero is rendered
as a value; unavailable inputs remain labeled and null. No research forecast is
displayed inside the analyst consensus or model assumption panels.

The API follows the repository's current private-service trust boundary. It does not
add public API authentication in this milestone; keep the service behind the existing
trusted local/reverse-proxy boundary when allowing an external agent to reach it.

## Google Sheets transport

The Sheets bridge reads the fixed `Application Research Inbox` tab and exposes
pending/accepted/rejected proposals in `/model-sync`. Its explicit preview and
accept operations call this same domain publisher; there is no second forecast
schema or alternate storage path. The bridge requires at least one source evidence
item, retains each captured contract and row location, and shows stale
`supersedes_revision_id` values as conflicts. See
[`google-sheets-sync.md`](google-sheets-sync.md) for the inbox protocol and
[`ResearchThesisAgentInstructions.md`](../tools/google-sheets/ResearchThesisAgentInstructions.md)
for concise workbook-agent instructions.
