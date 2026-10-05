# Canonical filings and source documents

## Purpose and boundaries

The source-document catalog records primary-source documents that support later
human or agent research. It stores identity, dates, provider provenance and stable
links. It does not download filing bodies, summarize documents, extract facts, or
run AI interpretation. Reported financial facts remain in the reported-fundamentals
domain; source-document metadata does not replace them.

Each `SourceDocument` is immutable. A `SourceDocumentBatch` records SEC ingestion
scope, provider and normalizer versions, raw-payload digest, timestamps and
reconciliation counts. Replaying the same SEC payload with the same normalizer
version is idempotent. Changed metadata for an already-known external identifier is
reported as a conflict and does not rewrite the prior document. `/A` filings retain
their original SEC form and accession and link to a captured original when the
same canonical company, base form and reporting period are known. An unlinked
amendment remains visible with `DATA_CHECK` quality.

## Sources and supported types

The live provider adapter is U.S. SEC EDGAR submissions. It supports 10-K, 10-Q,
8-K, 20-F and 6-K, including their `/A` amendments. The filing index URL is the
canonical reference; individual filing documents and exhibits stay on SEC's site.
The adapter consumes each reviewed company's submissions JSON and any valid
historical submissions files linked by that response. Only exact, operator-reviewed
SEC CIK mappings are accepted. Tickers and company names are never used to guess a
CIK.

Annual reports and earnings releases can be registered as issuer/company source
references with document types `ANNUAL_REPORT` and `EARNINGS_RELEASE`. These
references require HTTPS and are link-only: the application does not claim to have
retrieved a file. `OTHER` is available for a reviewed source document not covered
by the canonical types. The metadata supports an optional jurisdiction and optional
security reference when the document is listing-specific.

SEC's submissions API is public and does not require an API key. Its API
documentation describes the submissions JSON and linked historical files:
[SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
The adapter identifies itself with `SEC_USER_AGENT` and waits between requests to
remain under SEC fair-access limits. SEC publishes a 10 requests/second ceiling and
asks automated clients to avoid excessive request rates:
[SEC fair-access rate controls](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits).

## Operator workflow

First add and verify an SEC CIK mapping using the reported-fundamentals mapping
command. Record a stable SEC evidence URL and provider-reported company name; do
not add a mapping based only on ticker similarity:

```sh
npm run db:sync-reported-fundamentals -- map \
  --company-id <company-uuid> \
  --cik <10-digit-cik> \
  --provider-company-name "<name shown by SEC>" \
  --evidence-source "https://www.sec.gov/edgar/browse/?CIK=<cik>"
```

Set `SEC_USER_AGENT` in the local environment to an application name and monitored
contact email, then ingest one company or every company with a reviewed mapping:

```sh
npm run db:sync-source-documents -- sync --company-id <company-uuid>
npm run db:sync-source-documents -- sync
```

The command prints a batch receipt with imported/reused documents, unsupported
forms, malformed rows, unlinked amendments and metadata conflicts. An unmapped
company is reported as `UNMAPPED_SEC_IDENTITY`; there is no inferred fallback.

Issuer annual reports and earnings releases can be registered through
`POST /v1/companies/{company_id}/source-documents`. For example:

```json
{
  "provider_id": "company_source",
  "source_name": "Example issuer investor relations",
  "source_jurisdiction": "GB",
  "external_identifier": "annual-report-2025",
  "document_type": "ANNUAL_REPORT",
  "title": "Annual report 2025",
  "reporting_period": "FY 2025",
  "fiscal_year": 2025,
  "fiscal_period": "FY",
  "period_end": "2025-12-31",
  "published_at": "2026-02-20",
  "canonical_url": "https://investors.example.test/reports/2025.pdf",
  "actor": "LOCAL_USER"
}
```

The reference operation is append-only and idempotent for the same provider and
external identifier with matching company, type, URL and title. A conflicting
reuse returns an error so the operator can investigate it. Use a durable issuer
document identifier rather than a display title where possible.

## Read API and point-in-time behavior

`GET /v1/companies/{company_id}/source-documents` returns filing/source metadata,
the SEC identity status, source count and document rows. It supports:

- `document_type` to filter a canonical type;
- `as_of=YYYY-MM-DD` to limit documents by filing/publication date;
- `known_at=<timezone-aware timestamp>` to limit results to documents already
  retrieved and recorded by that time;
- `limit` from 1 to 200.

The record distinguishes source dates (`filed_at`, `published_at`, `period_end`)
from `retrieved_at` and `recorded_at`. SEC submissions do not always provide a
reporting-period end, so those rows remain visible with `DATA_CHECK` rather than
having a date inferred from the fiscal calendar. `recorded_at` reflects when the
application accepted the immutable metadata and is not represented as a filing
date.

## Storage and retention

PostgreSQL stores compact canonical metadata and compressed SEC submissions JSON
responses in the shared raw-payload table with provider record ID, URL, media type,
SHA-256, retrieval time and a batch foreign key. It does not store SEC filing
bodies, exhibits, issuer PDFs or earnings-release contents. Stable SEC/issuer URLs
are the source references; content integrity is provided for retained submissions
metadata, not for linked documents.

SEC submissions are public, but public availability is not a blanket license to
republish all linked content. Issuer IR documents and future provider content can
have separate licensing and retention terms. Before body downloads or durable
document archiving are added, review the applicable source terms, retention rules,
copyright restrictions, storage cost and access controls. A later document-body
store should use durable object storage plus relational metadata and checksums,
with a provider-specific retention policy. Google Sheets is not a runtime source.

## Current coverage and gaps

The adapter is jurisdiction-specific to SEC/United States identities and forms.
Annual reports and earnings releases are supported as manual HTTPS references,
not through a live issuer-relations crawler. No non-U.S. regulator adapter,
company-site discovery, full-text storage, document version comparison, content
extraction, or AI interpretation is included. Coverage depends on reviewed SEC CIK
mappings; unsupported and unmapped companies remain explicit. Future filing-derived
facts should link to the exact accession/document ID that supports them.
