# Canonical investment thesis and evidence

## Ownership and boundaries

The thesis domain records source-linked investment opinions by company and
preserves the complete revision history. A thesis does not change lifecycle,
target weights, holdings, scores, model assumptions, Expected IRR, ranks or
execution decisions. It does not calculate an investment recommendation.

Thesis statements and claims are authored opinions. A linked filing or reported
financial observation remains a distinct canonical fact and is displayed with its
own publication/period, provider, currency, quality and recorded-time metadata.
Evidence can support a claim, contradict it, or provide context; the system does not
score evidence strength or resolve disagreements automatically.

## Relational model

- `InvestmentThesisRevision` is an immutable full snapshot for a company research
  stream. It records company/optional security identity, contract and external
  revision IDs, author/source, observation and application recorded times, thesis
  statement, confidence, rationale, uncertainty, status and a content fingerprint.
- `InvestmentThesisClaim` records keyed claims for competitive advantages,
  durability, growth drivers, principal risks, thesis breakers, catalysts,
  important developments and unresolved questions. Claim status and confidence
  are explicit, and a claim can carry its own uncertainty.
- `InvestmentThesisEvidence` relates a claim to a source document, an exact
  reported-fundamental observation, or a source URL/identifier. The relationship is
  `SUPPORTS`, `CONTRADICTS` or `CONTEXT`. Canonical document and observation rows
  remain linked by immutable foreign keys; their facts are not copied into thesis
  records.

Each publication is a complete snapshot of the current thesis stream. Claims
removed or changed in a later snapshot remain visible in prior revisions. A
withdrawal is a new empty `WITHDRAWN` revision; it never deletes the prior thesis.
Stable `claim_key` values help the external author keep a claim's identity across
snapshots. Claim keys are scoped to one revision, so changed statements remain
traceable through the revision that published them.

Canonical filing and reported-fundamental evidence must belong to the same company.
When a thesis is security-scoped, linked security-specific evidence must match that
security; company-level facts can still support the thesis. External URLs must use
HTTPS. Publication dates provided on a citation do not rewrite canonical source
dates.

## External publication contract

`InvestmentThesisContractV1` versions `1.0.0` and `1.1.0` are the portable
full-snapshot contracts for the Sheets research agent. Version `1.1.0` optionally
adds `trigger_references` containing canonical trigger IDs and the existing
`NOISE`, `INCREMENTAL`, or `MAJOR-STRUCTURAL` classification with rationale. A
linked trigger must belong to the company, the cited observation cannot predate
trigger detection, and trigger-linked publications require independent HTTPS
source evidence. Accepted links are immutable and appear with the revision history.
The contracts publish through `POST
/v1/investment-thesis-revisions`; `GET /v1/companies/{company_id}/thesis` returns
the current selected revision and descending history per stream. The caller uses
canonical company/security/source IDs and does not connect to PostgreSQL.

The first revision uses `supersedes_revision_id: null`. Each later revision names
the current canonical thesis revision. A stale base returns HTTP 409. An exact
external revision replay returns HTTP 200 `ALREADY_PUBLISHED`; reusing an external
revision ID with changed content returns HTTP 409. New publications return HTTP 201. The author must publish a complete reviewed snapshot; unfinished Sheets edits
remain outside the canonical domain.

```json
{
  "contract_type": "InvestmentThesisContractV1",
  "contract_version": "1.0.0",
  "company_id": "<canonical-company-uuid>",
  "security_id": null,
  "stream_key": "investment-thesis",
  "external_revision_id": "thesis-2026-10-15-r1",
  "supersedes_revision_id": null,
  "author_id": "research-agent",
  "source_id": "google-sheets",
  "source_reference": "https://docs.google.com/spreadsheets/d/<id>/edit#gid=<tab>",
  "observed_at": "2026-10-15T09:00:00Z",
  "status": "PUBLISHED",
  "thesis_statement": "Recurring customer demand may support long-duration compounding.",
  "confidence": "MEDIUM",
  "rationale": "Why the current evidence supports this view.",
  "uncertainty": "What remains unresolved.",
  "claims": [
    {
      "claim_key": "renewal-economics",
      "claim_type": "COMPETITIVE_ADVANTAGE",
      "status": "UNDER_REVIEW",
      "statement": "Renewals may reinforce customer switching costs.",
      "confidence": "MEDIUM",
      "uncertainty": "Cohort data is incomplete.",
      "evidence": [
        {
          "relationship": "SUPPORTS",
          "source_document_id": "<canonical-source-document-uuid>",
          "reported_fundamental_observation_id": null,
          "source_name": "Issuer annual report",
          "external_identifier": "annual-report-2025",
          "source_url": null,
          "published_at": "2026-02-20",
          "excerpt": "Short supporting passage.",
          "note": "Relevant section or context."
        }
      ]
    }
  ]
}
```

## Historical reads

The read API accepts optional `as_of=YYYY-MM-DD` and timezone-aware `known_at`
cutoffs. The former selects thesis revisions authored by the requested date; the
latter limits the result to revisions recorded by the application at that time.
When both are supplied, `known_at` cannot exceed the end of the `as_of` date.
Reads select from stored revisions and never rebuild old opinions from current
claims or evidence. The agent-supplied `observed_at` is provenance rather than a
cryptographically verified timestamp; `recorded_at` is assigned by the
application.

Evidence response data exposes the linked source document and, for reported facts,
the exact observation ID, metric, reporting period, value, currency, unit, filing,
provider, quality, source URL and recorded time. This makes late or uncertain source
coverage visible during historical review.

## Company Explorer and integration limits

The Company Explorer presents the current thesis, keyed claims, confidence,
uncertainty, supporting/contradicting/contextual evidence and source facts. Prior
snapshots are expandable. There is no thesis editor in the web UI in this slice;
publication is intended for the external research workflow.

The API follows the existing private-service trust boundary and adds no new
authentication or authorization system. Expose it to a Sheets research agent only
through the trusted application boundary. This contract is separate from
`ResearchRevisionContractV1`: thesis opinions do not become forecasts, analyst
consensus, model inputs or score assessments automatically. No real thesis data is
seeded or fabricated by this milestone.

## Google Sheets transport

The bridge reads the fixed `Application Thesis Inbox` tab and queues complete
`InvestmentThesisContractV1` snapshots for explicit review in `/model-sync`.
Preview and acceptance reuse the canonical thesis publisher, including company and
security validation, evidence ownership, optimistic supersession and exact replay
behavior. At least one claim must carry source evidence for a Sheets publication.
Captured contracts and reviewer decisions remain separate from consensus and model
history. The copy-ready workbook instructions are in
[`ResearchThesisAgentInstructions.md`](../tools/google-sheets/ResearchThesisAgentInstructions.md).
