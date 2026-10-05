"use client";

import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PendingOrError, useResearch } from "@/components/research-frame";
import {
  isCompanySourceDocuments,
  type CompanySourceDocuments,
  type SourceDocument,
} from "@/lib/domain-contracts";
import { date } from "@/lib/display";

function sourceDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
        new Date(`${value}T12:00:00`),
      )
    : "Date unavailable";
}

function SourceDocumentCard({
  document,
  related,
}: {
  document: SourceDocument;
  related: SourceDocument | undefined;
}) {
  const dateLabel = document.filed_at
    ? `Filed ${sourceDate(document.filed_at)}`
    : `Published ${sourceDate(document.published_at)}`;
  return (
    <Card className="min-w-0 shadow-none">
      <CardContent className="flex min-w-0 flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">
              {document.document_type.replaceAll("_", " ")}
            </Badge>
            {document.source_form && (
              <Badge variant="secondary">Form {document.source_form}</Badge>
            )}
            {document.is_amendment && (
              <Badge variant="secondary">Amendment</Badge>
            )}
            {document.data_quality === "DATA_CHECK" && (
              <Badge variant="destructive">Data check</Badge>
            )}
          </div>
          <h3 className="break-words text-sm font-semibold">
            {document.title}
          </h3>
          <p className="text-xs text-muted-foreground">
            {document.source_name}
            {document.source_jurisdiction
              ? ` · ${document.source_jurisdiction}`
              : " · Jurisdiction unknown"}
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>{dateLabel}</span>
            <span>
              Period · {sourceDate(document.period_end)}
              {document.fiscal_period ? ` · ${document.fiscal_period}` : ""}
            </span>
            {document.reporting_period && (
              <span>{document.reporting_period}</span>
            )}
          </div>
          {(document.amends_document_id || document.supersedes_document_id) && (
            <p className="text-xs text-muted-foreground">
              {document.amends_document_id ? "Amends" : "Supersedes"} ·{" "}
              {related?.title ?? "Related source is outside this view"}
            </p>
          )}
          {document.quality_reason && (
            <p className="rounded-md border border-dashed p-2 text-xs leading-5 text-muted-foreground">
              {document.quality_reason}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            {document.retrieved_at
              ? `Metadata retrieved ${date(document.retrieved_at)}`
              : "Reference registered without downloading the source document"}
            {` · recorded ${date(document.recorded_at)}`}
          </p>
          <p className="break-all text-[11px] text-muted-foreground">
            Source ID · {document.external_identifier}
          </p>
        </div>
        <a
          className="inline-flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-xs font-medium text-primary hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href={document.canonical_url}
          target="_blank"
          rel="noreferrer"
        >
          Open source
          <ExternalLink aria-hidden="true" className="size-3.5" />
        </a>
      </CardContent>
    </Card>
  );
}

function SourceDocumentContent({ data }: { data: CompanySourceDocuments }) {
  const byId = new Map(data.documents.map((item) => [item.id, item]));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            data.sec_identity_status === "MAPPED" ? "outline" : "secondary"
          }
        >
          SEC identity · {data.sec_identity_status.toLowerCase()}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {data.source_count} source{" "}
          {data.source_count === 1 ? "document" : "documents"}
          {data.as_of ? ` · as of ${sourceDate(data.as_of)}` : ""}
        </span>
      </div>
      {data.documents.length === 0 ? (
        <p className="rounded-lg border border-dashed p-4 text-sm leading-6 text-muted-foreground">
          {data.sec_identity_status === "MAPPED"
            ? "No supported filing or company-source documents have been captured yet."
            : "No source documents are recorded. SEC filing history requires an explicitly reviewed CIK mapping; no identity is inferred from ticker or company name."}
        </p>
      ) : (
        <ol className="space-y-3">
          {data.documents.map((document) => (
            <li key={document.id}>
              <SourceDocumentCard
                document={document}
                related={
                  document.amends_document_id
                    ? byId.get(document.amends_document_id)
                    : document.supersedes_document_id
                      ? byId.get(document.supersedes_document_id)
                      : undefined
                }
              />
            </li>
          ))}
        </ol>
      )}
      <p className="text-xs leading-5 text-muted-foreground">
        This catalog stores source metadata and links. It does not download
        filing contents or generate document summaries.
      </p>
    </div>
  );
}

export function SourceDocuments({ companyId }: { companyId: string }) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/source-documents`,
    isCompanySourceDocuments,
  );
  return (
    <section
      id="source-documents"
      aria-labelledby="source-documents-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="source-documents-title" className="text-xl font-semibold">
          Filings & source documents
        </h2>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
          Primary regulatory filings and issuer-published documents with
          reporting period, source identity, retrieval and amendment context.
        </p>
      </div>
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <SourceDocumentContent data={state.data} />
      )}
    </section>
  );
}
