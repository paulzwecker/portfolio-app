"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ArrowRight,
  ExternalLink,
  FileCheck2,
  FileQuestion,
  ShieldAlert,
} from "lucide-react";
import { DetailDrawer } from "@/components/app/detail-drawer";
import { EmptyState } from "@/components/app/empty-state";
import { MetricCard } from "@/components/app/metric-card";
import { PageSection } from "@/components/app/page-section";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyInvestmentThesis,
  isCompanyResearch,
  isCompanyRiskAssessments,
  isCompanySourceDocuments,
  isResearchQueue,
  isResearchTriggerReadResult,
  type CompanyInvestmentThesis,
  type CompanyResearch,
  type CompanyRiskAssessments,
  type CompanySourceDocuments,
  type InvestmentThesisClaim,
  type ResearchEvidence,
  type ResearchQueue,
  type ResearchQueueTask,
  type ResearchRevision,
  type ResearchTriggerRead,
  type RiskAssessmentFinding,
  type RiskAssessmentRevision,
  type SourceDocument,
} from "@/lib/domain-contracts";
import { dateOnly, dateTime, statusLabel } from "@/lib/display";

export type EvidenceCategory =
  "ALL" | "FILINGS" | "RESEARCH" | "RISKS" | "TRIGGERS";
export type EvidenceRecency = "ALL" | "30" | "90";

type ActivityDetail =
  | { kind: "DOCUMENT"; document: SourceDocument }
  | { kind: "RESEARCH"; revision: ResearchRevision }
  | {
      kind: "RISK";
      revision: RiskAssessmentRevision;
      finding: RiskAssessmentFinding | null;
    }
  | { kind: "TRIGGER"; trigger: ResearchTriggerRead };

export type ResearchActivityItem = {
  id: string;
  category: Exclude<EvidenceCategory, "ALL">;
  title: string;
  summary: string;
  effectiveAt: string | null;
  recordedAt: string | null;
  sourceLabel: string;
  sourceUrl: string | null;
  status: string | null;
  detail: ActivityDetail;
};

const categoryLabels: Record<Exclude<EvidenceCategory, "ALL">, string> = {
  FILINGS: "Reported sources",
  RESEARCH: "Research interpretations",
  RISKS: "Accepted risks",
  TRIGGERS: "Evidence triggers",
};

function effectiveActivityDate(
  item: Pick<ResearchActivityItem, "effectiveAt" | "recordedAt">,
) {
  return item.effectiveAt ?? item.recordedAt;
}

export function researchActivityIsRecent(
  item: Pick<ResearchActivityItem, "effectiveAt" | "recordedAt">,
  days: number | null,
  now = new Date(),
) {
  if (days === null) return true;
  const value = effectiveActivityDate(item);
  if (!value) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return false;
  const age = now.getTime() - parsed.getTime();
  return age <= days * 24 * 60 * 60 * 1000;
}

export function filterResearchActivity(
  items: ResearchActivityItem[],
  category: EvidenceCategory,
  recency: EvidenceRecency,
  now = new Date(),
) {
  const days = recency === "ALL" ? null : Number(recency);
  return items
    .filter((item) => category === "ALL" || item.category === category)
    .filter((item) => researchActivityIsRecent(item, days, now))
    .sort((left, right) => {
      const leftDate = effectiveActivityDate(left);
      const rightDate = effectiveActivityDate(right);
      if (!leftDate && !rightDate) return left.title.localeCompare(right.title);
      if (!leftDate) return 1;
      if (!rightDate) return -1;
      return rightDate.localeCompare(leftDate);
    });
}

function uniqueRevisions(revisions: ResearchRevision[]) {
  const seen = new Set<string>();
  return revisions.filter((revision) => {
    if (seen.has(revision.id)) return false;
    seen.add(revision.id);
    return true;
  });
}

export function buildResearchActivity(input: {
  documents: SourceDocument[];
  researchRevisions: ResearchRevision[];
  riskRevisions: RiskAssessmentRevision[];
  triggers: ResearchTriggerRead[];
}): ResearchActivityItem[] {
  const activity: ResearchActivityItem[] = input.documents.map((document) => ({
    id: `document:${document.id}`,
    category: "FILINGS",
    title: document.title,
    summary: `${statusLabel(document.document_type)} · ${document.source_name}`,
    effectiveAt: document.filed_at ?? document.published_at,
    recordedAt: document.recorded_at,
    sourceLabel: "Reported source",
    sourceUrl: document.canonical_url,
    status: document.data_quality,
    detail: { kind: "DOCUMENT", document },
  }));

  uniqueRevisions(input.researchRevisions).forEach((revision) => {
    activity.push({
      id: `research:${revision.id}`,
      category: "RESEARCH",
      title: `Research revision ${revision.revision_number} · ${revision.stream_key}`,
      summary: revision.rationale,
      effectiveAt: revision.observed_at,
      recordedAt: revision.recorded_at,
      sourceLabel: "Research interpretation",
      sourceUrl: revision.source_reference.startsWith("https://")
        ? revision.source_reference
        : null,
      status: revision.status,
      detail: { kind: "RESEARCH", revision },
    });
  });

  input.riskRevisions.forEach((revision) => {
    if (revision.findings.length === 0) {
      activity.push({
        id: `risk:${revision.id}`,
        category: "RISKS",
        title: `Accepted risk assessment · revision ${revision.revision_number}`,
        summary: revision.summary,
        effectiveAt: revision.accepted_at,
        recordedAt: revision.recorded_at,
        sourceLabel: "Accepted qualitative risk",
        sourceUrl: revision.source_reference.startsWith("https://")
          ? revision.source_reference
          : null,
        status: revision.baseline_status_at_accept,
        detail: { kind: "RISK", revision, finding: null },
      });
    } else {
      revision.findings.forEach((finding) => {
        const source = finding.evidence.find(
          (evidence) => evidence.source_document_url ?? evidence.source_url,
        );
        activity.push({
          id: `risk:${revision.id}:${finding.id}`,
          category: "RISKS",
          // Keep the activity stream compact. The full finding title and
          // description remain available in the evidence drawer and risk
          // section below, so the stream does not repeat an entire risk card.
          title: `Risk assessment · revision ${revision.revision_number}`,
          summary: `${statusLabel(finding.category)} · ${statusLabel(finding.change_direction)} · ${revision.summary}`,
          effectiveAt: revision.accepted_at,
          recordedAt: revision.recorded_at,
          sourceLabel: "Accepted qualitative risk",
          sourceUrl: source?.source_document_url ?? source?.source_url ?? null,
          status: finding.change_direction,
          detail: { kind: "RISK", revision, finding },
        });
      });
    }
  });

  input.triggers.forEach((trigger) => {
    activity.push({
      id: `trigger:${trigger.id}`,
      category: "TRIGGERS",
      title: trigger.title,
      summary: trigger.reason,
      effectiveAt:
        trigger.effective_at ??
        trigger.source_observed_at ??
        trigger.detected_at,
      recordedAt: trigger.source_recorded_at,
      sourceLabel: "Deterministic evidence trigger",
      sourceUrl: trigger.source_reference,
      status: trigger.processing_state,
      detail: { kind: "TRIGGER", trigger },
    });
  });

  return activity;
}

function dateLabel(value: string | null | undefined) {
  if (!value) return "Date unavailable";
  return value.length <= 10 ? dateOnly(value) : dateTime(value);
}

function SourceDocumentDetail({ document }: { document: SourceDocument }) {
  return (
    <div className="space-y-5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusIndicator status={document.document_type} />
        <StatusIndicator status={document.data_quality} />
        {document.is_amendment && <Badge variant="secondary">Amendment</Badge>}
      </div>
      <p className="text-base font-medium">{document.title}</p>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">Source</dt>
          <dd className="mt-1">{document.source_name}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Provider</dt>
          <dd className="mt-1">{document.provider_id}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Published / filed</dt>
          <dd className="mt-1">
            {dateLabel(document.filed_at ?? document.published_at)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Reporting period</dt>
          <dd className="mt-1">
            {document.reporting_period ?? dateLabel(document.period_end)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Recorded</dt>
          <dd className="mt-1">{dateLabel(document.recorded_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">External identifier</dt>
          <dd className="mt-1 break-all">{document.external_identifier}</dd>
        </div>
      </dl>
      {(document.amends_document_id || document.supersedes_document_id) && (
        <div className="rounded-md border border-warning/35 bg-warning/5 p-3 text-xs leading-5">
          {document.amends_document_id
            ? `Amends source document ${document.amends_document_id}.`
            : `Supersedes source document ${document.supersedes_document_id}.`}
        </div>
      )}
      {document.quality_reason && (
        <p className="rounded-md border border-dashed p-3 text-xs leading-5 text-muted-foreground">
          {document.quality_reason}
        </p>
      )}
      <SourceReference
        label="Open original source"
        href={document.canonical_url}
        reference={document.external_identifier}
      />
    </div>
  );
}

function ResearchRevisionDetail({ revision }: { revision: ResearchRevision }) {
  return (
    <div className="space-y-5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusIndicator status="RESEARCH INTERPRETATION" />
        <StatusIndicator status={revision.status} />
        <Badge variant="outline">Revision {revision.revision_number}</Badge>
      </div>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">Author</dt>
          <dd className="mt-1">{revision.author_id}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Source</dt>
          <dd className="mt-1">{revision.source_id}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Observed</dt>
          <dd className="mt-1">{dateTime(revision.observed_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Recorded</dt>
          <dd className="mt-1">{dateTime(revision.recorded_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Contract</dt>
          <dd className="mt-1">{revision.contract_version}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">External revision</dt>
          <dd className="mt-1 break-all">{revision.external_revision_id}</dd>
        </div>
      </dl>
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Rationale
        </h3>
        <p className="mt-2 leading-6">{revision.rationale}</p>
      </div>
      {revision.uncertainty && (
        <div className="rounded-md border border-warning/35 bg-warning/5 p-3 leading-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-warning">
            Uncertainty
          </p>
          <p className="mt-1">{revision.uncertainty}</p>
        </div>
      )}
      <div className="grid gap-2 text-xs sm:grid-cols-2">
        <span>{revision.forecasts.length} forecast observations</span>
        <span>{revision.assessments.length} qualitative assessments</span>
        <span>{revision.evidence.length} linked evidence items</span>
        <span>Fingerprint · {revision.content_fingerprint.slice(0, 16)}…</span>
      </div>
      <SourceReference
        label="Open research source"
        href={
          revision.source_reference.startsWith("https://")
            ? revision.source_reference
            : null
        }
        reference={
          revision.source_reference.startsWith("https://")
            ? null
            : revision.source_reference
        }
      />
    </div>
  );
}

function RiskDetail({
  revision,
  finding,
}: {
  revision: RiskAssessmentRevision;
  finding: RiskAssessmentFinding | null;
}) {
  return (
    <div className="space-y-5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusIndicator status="ACCEPTED QUALITATIVE RISK" />
        <StatusIndicator status={revision.baseline_status_at_accept} />
        {finding && <StatusIndicator status={finding.severity} />}
      </div>
      <div>
        <p className="text-base font-medium">
          {finding?.title ?? revision.summary}
        </p>
        <p className="mt-2 leading-6 text-muted-foreground">
          {finding?.description ?? revision.rationale}
        </p>
      </div>
      {finding && (
        <dl className="grid gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">Category</dt>
            <dd className="mt-1">{statusLabel(finding.category)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Confidence</dt>
            <dd className="mt-1">{statusLabel(finding.confidence)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Change</dt>
            <dd className="mt-1">{statusLabel(finding.change_direction)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Finding status</dt>
            <dd className="mt-1">{statusLabel(finding.status)}</dd>
          </div>
        </dl>
      )}
      <dl className="grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">Accepted</dt>
          <dd className="mt-1">{dateTime(revision.accepted_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Portfolio baseline</dt>
          <dd className="mt-1">
            {statusLabel(revision.baseline_status_at_accept)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Valuation context</dt>
          <dd className="mt-1">{dateTime(revision.valuation_as_of)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Reviewer</dt>
          <dd className="mt-1">{revision.reviewer}</dd>
        </div>
      </dl>
      {revision.baseline_status_at_accept !== "CURRENT" && (
        <p className="rounded-md border border-warning/35 bg-warning/5 p-3 text-xs leading-5">
          This assessment was accepted against a{" "}
          {statusLabel(revision.baseline_status_at_accept).toLowerCase()}{" "}
          baseline. It remains historical evidence and does not update current
          exposure or the numeric Risk score.
        </p>
      )}
      {finding?.rationale && (
        <p className="text-xs leading-5 text-muted-foreground">
          {finding.rationale}
        </p>
      )}
      {finding && finding.evidence.length > 0 && (
        <div className="space-y-2 border-t pt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Evidence
          </h3>
          {finding.evidence.map((evidence) => (
            <SourceReference
              key={evidence.id}
              label={evidence.source_name}
              reference={
                evidence.external_identifier ?? evidence.source_document_title
              }
              href={evidence.source_document_url ?? evidence.source_url}
            />
          ))}
        </div>
      )}
      <SourceReference
        label="Open assessment source"
        reference={revision.source_id}
        href={
          revision.source_reference.startsWith("https://")
            ? revision.source_reference
            : null
        }
      />
    </div>
  );
}

function TriggerDetail({ trigger }: { trigger: ResearchTriggerRead }) {
  return (
    <div className="space-y-5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusIndicator status="DETERMINISTIC EVIDENCE TRIGGER" />
        <StatusIndicator status={trigger.processing_state} />
        <Badge variant="outline">Version {trigger.version}</Badge>
      </div>
      <p className="text-base font-medium">{trigger.title}</p>
      <p className="leading-6 text-muted-foreground">{trigger.reason}</p>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">Trigger type</dt>
          <dd className="mt-1">{statusLabel(trigger.trigger_type)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Source domain</dt>
          <dd className="mt-1">{trigger.source_domain}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Effective</dt>
          <dd className="mt-1">{dateLabel(trigger.effective_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Detected</dt>
          <dd className="mt-1">{dateTime(trigger.detected_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Source recorded</dt>
          <dd className="mt-1">{dateTime(trigger.source_recorded_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Source record</dt>
          <dd className="mt-1 break-all">{trigger.source_record_id}</dd>
        </div>
      </dl>
      <SourceReference
        label="Open trigger source"
        href={trigger.source_reference}
      />
    </div>
  );
}

function ActivityDrawer({
  item,
  onOpenChange,
}: {
  item: ResearchActivityItem | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <DetailDrawer
      open={item !== null}
      onOpenChange={onOpenChange}
      title={item?.title ?? "Evidence details"}
      description={
        item
          ? `${item.sourceLabel} · ${categoryLabels[item.category]}`
          : undefined
      }
    >
      {item?.detail.kind === "DOCUMENT" && (
        <SourceDocumentDetail document={item.detail.document} />
      )}
      {item?.detail.kind === "RESEARCH" && (
        <ResearchRevisionDetail revision={item.detail.revision} />
      )}
      {item?.detail.kind === "RISK" && (
        <RiskDetail
          revision={item.detail.revision}
          finding={item.detail.finding}
        />
      )}
      {item?.detail.kind === "TRIGGER" && (
        <TriggerDetail trigger={item.detail.trigger} />
      )}
    </DetailDrawer>
  );
}

function ResearchEvidenceCard({
  evidence,
  onInspect,
}: {
  evidence: ResearchEvidence;
  onInspect: (evidence: ResearchEvidence) => void;
}) {
  return (
    <li className="rounded-md border bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusIndicator status="SOURCE EVIDENCE" />
        <span className="font-medium">{evidence.source_name}</span>
        {evidence.published_at && (
          <span className="text-xs text-muted-foreground">
            Published {dateOnly(evidence.published_at)}
          </span>
        )}
      </div>
      {evidence.excerpt && (
        <blockquote className="mt-2 border-l-2 pl-3 text-xs leading-5 text-muted-foreground">
          {evidence.excerpt}
        </blockquote>
      )}
      {evidence.note && (
        <p className="mt-2 text-xs leading-5">{evidence.note}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
        <SourceReference
          label={evidence.source_document_title ?? evidence.source_name}
          reference={evidence.external_identifier}
          href={evidence.source_url}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onInspect(evidence)}
        >
          Inspect evidence
        </Button>
      </div>
    </li>
  );
}

function EvidenceDrawer({
  evidence,
  onOpenChange,
}: {
  evidence: ResearchEvidence | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <DetailDrawer
      open={evidence !== null}
      onOpenChange={onOpenChange}
      title={evidence ? `${evidence.source_name} evidence` : "Evidence details"}
      description="Source and publication context for the selected research evidence."
    >
      {evidence && (
        <div className="space-y-5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <StatusIndicator status="SOURCE EVIDENCE" />
            <span className="text-xs text-muted-foreground">
              Used by an accepted research interpretation
            </span>
          </div>
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted-foreground">Published</dt>
              <dd className="mt-1">{dateLabel(evidence.published_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">
                External identifier
              </dt>
              <dd className="mt-1 break-all">
                {evidence.external_identifier ?? "Not recorded"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Source document</dt>
              <dd className="mt-1 break-all">
                {evidence.source_document_id ?? "Not linked"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Source URL</dt>
              <dd className="mt-1 break-all">
                {evidence.source_url ?? "Not recorded"}
              </dd>
            </div>
          </dl>
          {evidence.excerpt && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Excerpt
              </h3>
              <blockquote className="mt-2 border-l-2 pl-3 leading-6">
                {evidence.excerpt}
              </blockquote>
            </div>
          )}
          {evidence.note && <p className="leading-6">{evidence.note}</p>}
          <SourceReference
            label="Open source evidence"
            href={evidence.source_url}
            reference={evidence.external_identifier}
          />
        </div>
      )}
    </DetailDrawer>
  );
}

function ClaimEvidenceDrawer({
  claim,
  onOpenChange,
}: {
  claim: InvestmentThesisClaim | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <DetailDrawer
      open={claim !== null}
      onOpenChange={onOpenChange}
      title={claim ? "Thesis claim evidence" : "Claim evidence"}
      description="Supporting, contradicting and contextual sources remain linked to the accepted thesis claim."
    >
      {claim && (
        <div className="space-y-5 text-sm">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusIndicator status={claim.claim_type} />
              <StatusIndicator status={claim.status} />
              <StatusIndicator
                status={claim.confidence}
                label={`${statusLabel(claim.confidence)} confidence`}
              />
            </div>
            <p className="mt-3 text-base font-medium">{claim.statement}</p>
            {claim.uncertainty && (
              <p className="mt-2 text-sm text-muted-foreground">
                {claim.uncertainty}
              </p>
            )}
          </div>
          {claim.evidence.length === 0 ? (
            <EmptyState
              title="No linked evidence"
              description="This claim is recorded without a source relationship in the accepted thesis revision."
            />
          ) : (
            <ul className="space-y-3">
              {claim.evidence.map((evidence) => (
                <li key={evidence.id} className="rounded-md border p-3">
                  <StatusIndicator status={evidence.relationship} />
                  <p className="mt-2 font-medium">{evidence.source_name}</p>
                  {evidence.excerpt && (
                    <blockquote className="mt-2 border-l-2 pl-3 text-xs leading-5 text-muted-foreground">
                      {evidence.excerpt}
                    </blockquote>
                  )}
                  {evidence.note && (
                    <p className="mt-2 text-xs leading-5">{evidence.note}</p>
                  )}
                  <SourceReference
                    className="mt-2"
                    label={
                      evidence.source_document_title ?? evidence.source_name
                    }
                    reference={
                      evidence.external_identifier ??
                      evidence.source_document_type
                    }
                    href={evidence.source_document_url ?? evidence.source_url}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </DetailDrawer>
  );
}

function InlineState({
  error,
  retry,
  label,
}: {
  error?: string;
  retry: () => void;
  label: string;
}) {
  return error ? (
    <div
      role="alert"
      className="rounded-md border border-destructive/35 bg-destructive/5 p-3 text-sm"
    >
      <p>{label} unavailable.</p>
      <Button variant="outline" size="sm" className="mt-2" onClick={retry}>
        Retry
      </Button>
    </div>
  ) : (
    <p
      role="status"
      className="rounded-md border border-dashed p-3 text-sm text-muted-foreground"
    >
      Loading {label.toLowerCase()}…
    </p>
  );
}

function ActivitySummary({
  source,
  research,
  risks,
  openReviewCount,
}: {
  source: CompanySourceDocuments | undefined;
  research: CompanyResearch | undefined;
  risks: CompanyRiskAssessments | undefined;
  openReviewCount: number | null;
}) {
  const latestSource = source?.documents
    .map((document) => document.filed_at ?? document.published_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
  const revisionCount = research
    ? research.streams.reduce(
        (total, stream) => total + uniqueRevisions(stream.history).length,
        0,
      )
    : null;
  const acceptedRiskFindings = risks
    ? risks.current.reduce(
        (total, revision) => total + revision.findings.length,
        0,
      )
    : null;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="Latest primary source"
        value={
          latestSource
            ? dateOnly(latestSource)
            : source
              ? "No dated source"
              : "Loading"
        }
        note={
          source
            ? `${source.source_count} source records · ${statusLabel(source.sec_identity_status)} identity`
            : "Source catalog status"
        }
      />
      <MetricCard
        label="Research revisions"
        value={revisionCount === null ? "Loading" : revisionCount}
        note="Accepted interpretation history"
      />
      <MetricCard
        label="Accepted risk findings"
        value={acceptedRiskFindings === null ? "Loading" : acceptedRiskFindings}
        note="Qualitative only · never a numeric Risk score"
      />
      <MetricCard
        label="Research requiring review"
        value={openReviewCount === null ? "Loading" : openReviewCount}
        note="Queue, triggers and unresolved thesis questions"
        tone={openReviewCount ? "warning" : "default"}
      />
    </div>
  );
}

function ActivityList({
  items,
  total,
  onInspect,
}: {
  items: ResearchActivityItem[];
  total: number;
  onInspect: (item: ResearchActivityItem) => void;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No evidence matches these filters"
        description="A missing or undated source is not treated as a neutral event. Broaden the category or recency filter to inspect the remaining canonical records."
        icon={<FileQuestion aria-hidden="true" className="size-4" />}
      />
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>
          Showing {items.length} of {total} matching records
        </span>
        <span>Sorted by effective or recorded time</span>
      </div>
      <ol className="space-y-2" aria-label="Prioritized research activity">
        {items.map((item) => (
          <li key={item.id} className="rounded-lg border bg-card p-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusIndicator
                    status={item.category}
                    label={categoryLabels[item.category]}
                  />
                  {item.status && <StatusIndicator status={item.status} />}
                  <span className="text-xs text-muted-foreground">
                    {dateLabel(effectiveActivityDate(item))}
                  </span>
                </div>
                <h3 className="mt-2 text-sm font-semibold">{item.title}</h3>
                <p className="mt-1 line-clamp-2 text-sm leading-5 text-muted-foreground">
                  {item.summary}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {item.sourceLabel}
                  {item.recordedAt
                    ? ` · recorded ${dateLabel(item.recordedAt)}`
                    : ""}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="shrink-0"
                onClick={() => onInspect(item)}
              >
                Inspect evidence
              </Button>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function SourceDocumentsSection({
  state,
  recency,
  onInspect,
}: {
  state: ReturnType<typeof useResearch<CompanySourceDocuments>>;
  recency: EvidenceRecency;
  onInspect: (item: ResearchActivityItem) => void;
}) {
  if (!state.data)
    return (
      <InlineState
        error={state.error}
        retry={state.retry}
        label="source documents"
      />
    );
  const days = recency === "ALL" ? null : Number(recency);
  const documents = state.data.documents.filter((document) =>
    researchActivityIsRecent(
      {
        effectiveAt: document.filed_at ?? document.published_at,
        recordedAt: document.recorded_at,
      },
      days,
    ),
  );
  const byId = new Map(
    state.data.documents.map((document) => [document.id, document]),
  );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            state.data.sec_identity_status === "MAPPED"
              ? "outline"
              : "secondary"
          }
        >
          SEC identity · {state.data.sec_identity_status.toLowerCase()}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {state.data.source_count} source{" "}
          {state.data.source_count === 1 ? "document" : "documents"}
          {state.data.as_of ? ` · as of ${dateOnly(state.data.as_of)}` : ""}
        </span>
      </div>
      {documents.length === 0 ? (
        <EmptyState
          title={
            state.data.documents.length === 0
              ? "No source documents captured"
              : "No source documents match this recency filter"
          }
          description={
            state.data.documents.length === 0
              ? state.data.sec_identity_status === "MAPPED"
                ? "No supported filing or issuer-source metadata has been captured yet."
                : "Source documents require an explicitly reviewed issuer identity; no mapping is inferred from ticker or company name."
              : "Broaden the evidence recency filter to inspect older filings."
          }
        />
      ) : (
        <ol className="space-y-3">
          {documents.slice(0, 8).map((document) => {
            const related = document.amends_document_id
              ? byId.get(document.amends_document_id)
              : document.supersedes_document_id
                ? byId.get(document.supersedes_document_id)
                : undefined;
            const activity: ResearchActivityItem = {
              id: `document:${document.id}`,
              category: "FILINGS",
              title: document.title,
              summary: `${statusLabel(document.document_type)} · ${document.source_name}`,
              effectiveAt: document.filed_at ?? document.published_at,
              recordedAt: document.recorded_at,
              sourceLabel: "Reported source",
              sourceUrl: document.canonical_url,
              status: document.data_quality,
              detail: { kind: "DOCUMENT", document },
            };
            return (
              <li key={document.id} className="rounded-lg border bg-card p-4">
                <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">
                        {statusLabel(document.document_type)}
                      </Badge>
                      {document.source_form && (
                        <Badge variant="secondary">
                          Form {document.source_form}
                        </Badge>
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
                      <span>
                        {document.filed_at
                          ? `Filed ${dateOnly(document.filed_at)}`
                          : `Published ${dateLabel(document.published_at)}`}
                      </span>
                      <span>
                        Period · {dateLabel(document.period_end)}
                        {document.fiscal_period
                          ? ` · ${document.fiscal_period}`
                          : ""}
                      </span>
                    </div>
                    {(document.amends_document_id ||
                      document.supersedes_document_id) && (
                      <p className="text-xs text-muted-foreground">
                        {document.amends_document_id ? "Amends" : "Supersedes"}{" "}
                        ·{" "}
                        {related?.title ??
                          "Related source is outside this view"}
                      </p>
                    )}
                    {document.quality_reason && (
                      <p className="rounded-md border border-dashed p-2 text-xs leading-5 text-muted-foreground">
                        {document.quality_reason}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {document.retrieved_at
                        ? `Metadata retrieved ${dateLabel(document.retrieved_at)}`
                        : "Reference registered without downloading the source document"}
                      {` · recorded ${dateLabel(document.recorded_at)}`}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2 sm:flex-col sm:items-stretch">
                    <a
                      className="inline-flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-xs font-medium text-primary hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      href={document.canonical_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open source{" "}
                      <ExternalLink aria-hidden="true" className="size-3.5" />
                    </a>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => onInspect(activity)}
                    >
                      Inspect metadata
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {documents.length > 8 && (
        <p className="text-xs text-muted-foreground">
          Showing the 8 most recent records. Use the activity filters for a
          compact cross-domain view.
        </p>
      )}
      <p className="text-xs leading-5 text-muted-foreground">
        This catalog stores source metadata and links. It does not download
        filing contents or generate document summaries.
      </p>
    </div>
  );
}

function ResearchEvidenceSection({
  data,
  onInspect,
}: {
  data: CompanyResearch | undefined;
  onInspect: (evidence: ResearchEvidence) => void;
}) {
  const evidence = useMemo(() => {
    if (!data) return [];
    const seen = new Set<string>();
    return data.streams
      .flatMap((stream) => uniqueRevisions(stream.history))
      .flatMap((revision) => revision.evidence)
      .filter((item) => {
        if (seen.has(item.id)) return false;
        seen.add(item.id);
        return true;
      });
  }, [data]);
  if (!data)
    return (
      <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
        Research evidence is unavailable until the accepted research archive
        loads.
      </p>
    );
  return evidence.length === 0 ? (
    <EmptyState
      title="No linked research evidence"
      description="Accepted research revisions are present only when their source evidence is recorded. This does not imply that the company's claims are validated."
    />
  ) : (
    <ul className="space-y-2">
      {evidence.slice(0, 8).map((item) => (
        <ResearchEvidenceCard
          key={item.id}
          evidence={item}
          onInspect={onInspect}
        />
      ))}
    </ul>
  );
}

function AcceptedRiskSection({
  state,
  onInspect,
}: {
  state: ReturnType<typeof useResearch<CompanyRiskAssessments>>;
  onInspect: (item: ResearchActivityItem) => void;
}) {
  if (!state.data)
    return (
      <InlineState
        error={state.error}
        retry={state.retry}
        label="accepted risk assessments"
      />
    );
  const data = state.data;
  if (data.current.length === 0)
    return (
      <EmptyState
        title="No accepted company risk assessments"
        description="Qualitative risk review has not been accepted for this company. The numeric Risk score and deterministic exposure calculations remain separate."
        icon={<ShieldAlert aria-hidden="true" className="size-4" />}
      />
    );
  return (
    <div className="space-y-3">
      {data.current.map((revision) => (
        <Card key={revision.id} className="shadow-none">
          <CardHeader className="pb-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <CardTitle className="text-sm">
                  Revision {revision.revision_number} · {revision.summary}
                </CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  Accepted {dateTime(revision.accepted_at)} ·{" "}
                  {revision.reviewer} · {revision.findings.length} finding
                  {revision.findings.length === 1 ? "" : "s"}
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <StatusIndicator
                  status="ACCEPTED"
                  label="Current accepted assessment"
                />
                <StatusIndicator status={revision.coverage_status} />
                <StatusIndicator
                  status={revision.baseline_status_at_accept}
                  label={
                    revision.baseline_status_at_accept === "CURRENT"
                      ? "Current baseline"
                      : statusLabel(revision.baseline_status_at_accept)
                  }
                />
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm leading-6 text-muted-foreground">
              {revision.rationale}
            </p>
            {revision.baseline_status_at_accept !== "CURRENT" && (
              <p className="rounded-md border border-warning/35 bg-warning/5 p-2 text-xs leading-5">
                Accepted against a{" "}
                {statusLabel(revision.baseline_status_at_accept).toLowerCase()}{" "}
                portfolio baseline
                {revision.baseline_stale_acknowledged
                  ? "; the reviewer acknowledged the stale baseline."
                  : "."}
              </p>
            )}
            {revision.findings.length > 0 ? (
              <ul className="grid gap-2 sm:grid-cols-2">
                {revision.findings.map((finding) => {
                  const activity: ResearchActivityItem = {
                    id: `risk:${revision.id}:${finding.id}`,
                    category: "RISKS",
                    title: finding.title,
                    summary: finding.description,
                    effectiveAt: revision.accepted_at,
                    recordedAt: revision.recorded_at,
                    sourceLabel: "Accepted qualitative risk",
                    sourceUrl:
                      finding.evidence[0]?.source_document_url ??
                      finding.evidence[0]?.source_url ??
                      null,
                    status: finding.change_direction,
                    detail: { kind: "RISK", revision, finding },
                  };
                  return (
                    <li key={finding.id} className="rounded-md border p-3">
                      <div className="flex flex-wrap gap-1.5">
                        <StatusIndicator status={finding.severity} />
                        <StatusIndicator status={finding.change_direction} />
                        <StatusIndicator status={finding.confidence} />
                      </div>
                      <h3 className="mt-2 text-sm font-semibold">
                        {finding.title}
                      </h3>
                      <p className="mt-1 text-xs leading-5">
                        {finding.description}
                      </p>
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        {statusLabel(finding.category)} ·{" "}
                        {statusLabel(finding.status)} ·{" "}
                        {statusLabel(finding.confidence)} confidence
                      </p>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="mt-2 h-7 px-2 text-xs"
                        onClick={() => onInspect(activity)}
                      >
                        Inspect risk evidence
                      </Button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No structured risk findings were recorded in this revision.
              </p>
            )}
            {data.history.filter(
              (item) =>
                item.stream_key === revision.stream_key &&
                item.id !== revision.id,
            ).length > 0 && (
              <details className="rounded-md border p-3">
                <summary className="cursor-pointer text-sm font-medium">
                  Prior accepted risk revisions
                </summary>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  Historical revisions remain available in the assessment source
                  and are not rewritten when the portfolio baseline changes.
                </p>
              </details>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ResearchNextSection({
  companyId,
  companyName,
  queue,
  queueError,
  queueRetry,
  triggers,
  triggerError,
  triggerRetry,
  thesis,
}: {
  companyId: string;
  companyName: string;
  queue: ResearchQueue | undefined;
  queueError?: string;
  queueRetry: () => void;
  triggers: ResearchTriggerRead[] | undefined;
  triggerError?: string;
  triggerRetry: () => void;
  thesis: CompanyInvestmentThesis | undefined;
}) {
  const tasks =
    queue?.tasks.filter(
      (task) => task.company.id === companyId && task.status === "OPEN",
    ) ?? [];
  const openTriggers = (triggers ?? []).filter(
    (trigger) =>
      trigger.company.id === companyId && trigger.processing_state === "OPEN",
  );
  const questions =
    thesis?.streams
      .flatMap((stream) => stream.current_revision.claims)
      .filter(
        (claim) =>
          claim.claim_type === "UNRESOLVED_QUESTION" &&
          claim.status !== "RESOLVED",
      ) ?? [];
  const total = tasks.length + openTriggers.length + questions.length;
  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-muted/20 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-semibold">
              Accepted risks stay separate from pending work
            </p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">
              New risk or model proposals require the existing review flow. This
              page never accepts research, changes scores or turns a qualitative
              finding into a trade.
            </p>
          </div>
          <Link
            href="/model-sync"
            className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-primary hover:underline"
          >
            Open proposal review{" "}
            <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
        </div>
      </div>
      {queueError && (
        <InlineState
          error={queueError}
          retry={queueRetry}
          label="research queue"
        />
      )}
      {triggerError && (
        <InlineState
          error={triggerError}
          retry={triggerRetry}
          label="evidence triggers"
        />
      )}
      {!queueError &&
      !triggerError &&
      queue === undefined &&
      triggers === undefined ? (
        <InlineState
          retry={() => {
            queueRetry();
            triggerRetry();
          }}
          label="research next actions"
        />
      ) : total === 0 && queue && triggers ? (
        <EmptyState
          title="No open research items"
          description="No queue task, open evidence trigger or unresolved thesis question is currently recorded. This is not a claim that research is complete."
          icon={<FileCheck2 aria-hidden="true" className="size-4" />}
        />
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            {total} open research item{total === 1 ? "" : "s"} linked to{" "}
            {companyName}.
          </p>
          {tasks.map((task) => (
            <QueueTaskSummary key={task.task_id} task={task} />
          ))}
          {openTriggers.map((trigger) => (
            <TriggerSummary key={trigger.id} trigger={trigger} />
          ))}
          {questions.map((claim) => (
            <QuestionSummary
              key={claim.id}
              claim={claim}
              companyId={companyId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function QueueTaskSummary({ task }: { task: ResearchQueueTask }) {
  return (
    <Card className="shadow-none">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusIndicator status="OPEN" />
            <Badge variant="secondary">{statusLabel(task.task_type)}</Badge>
            <span className="text-xs text-muted-foreground">
              {statusLabel(task.owner_workflow)}
            </span>
          </div>
          <h3 className="mt-2 text-sm font-semibold">{task.title}</h3>
          <p className="mt-1 text-sm leading-5 text-muted-foreground">
            {task.reason}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            {task.judgment_required
              ? "Analyst judgment required"
              : "Deterministic review condition"}
            {task.due_at ? ` · due ${dateLabel(task.due_at)}` : ""}
          </p>
        </div>
        <Link
          href={`/research-queue?search=${encodeURIComponent(task.company.name)}`}
          className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-primary hover:underline"
        >
          Open review queue <ArrowRight aria-hidden="true" className="size-4" />
        </Link>
      </CardContent>
    </Card>
  );
}

function TriggerSummary({ trigger }: { trigger: ResearchTriggerRead }) {
  return (
    <Card className="shadow-none">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusIndicator status="OPEN" />
            <Badge variant="outline">{statusLabel(trigger.trigger_type)}</Badge>
            <span className="text-xs text-muted-foreground">
              {dateLabel(
                effectiveActivityDate({
                  effectiveAt:
                    trigger.effective_at ??
                    trigger.source_observed_at ??
                    trigger.detected_at,
                  recordedAt: trigger.source_recorded_at,
                }),
              )}
            </span>
          </div>
          <h3 className="mt-2 text-sm font-semibold">{trigger.title}</h3>
          <p className="mt-1 text-sm leading-5 text-muted-foreground">
            {trigger.reason}
          </p>
        </div>
        {trigger.source_reference ? (
          <SourceReference
            label="Open trigger source"
            href={trigger.source_reference}
          />
        ) : (
          <span className="text-xs text-muted-foreground">
            Source reference unavailable
          </span>
        )}
      </CardContent>
    </Card>
  );
}

function QuestionSummary({
  claim,
  companyId,
}: {
  claim: InvestmentThesisClaim;
  companyId: string;
}) {
  return (
    <Card className="shadow-none">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusIndicator status="UNRESOLVED QUESTION" />
            <StatusIndicator
              status={claim.confidence}
              label={`${statusLabel(claim.confidence)} confidence`}
            />
          </div>
          <h3 className="mt-2 text-sm font-semibold">{claim.statement}</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            The accepted thesis keeps this question open for evidence review.
          </p>
        </div>
        <Link
          href={`/company/${encodeURIComponent(companyId)}?view=thesis`}
          className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-primary hover:underline"
        >
          Review thesis <ArrowRight aria-hidden="true" className="size-4" />
        </Link>
      </CardContent>
    </Card>
  );
}

function ThesisContext({
  companyId,
  thesis,
  onInspect,
}: {
  companyId: string;
  thesis: CompanyInvestmentThesis | undefined;
  onInspect: (claim: InvestmentThesisClaim) => void;
}) {
  const current = thesis?.streams[0]?.current_revision;
  const claims =
    thesis?.streams.flatMap((stream) => stream.current_revision.claims) ?? [];
  if (!thesis)
    return (
      <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
        Thesis context is unavailable until the accepted thesis archive loads.
      </p>
    );
  if (!current)
    return (
      <EmptyState
        title="No accepted thesis"
        description="Claims and evidence relationships have not been accepted for this company."
      />
    );
  return (
    <div className="space-y-4">
      <Card className="shadow-none">
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusIndicator status="ACCEPTED THESIS" />
            <Badge variant="outline">Revision {current.revision_number}</Badge>
            <span className="text-xs text-muted-foreground">
              Observed {dateTime(current.observed_at)}
            </span>
          </div>
          <p className="text-base font-medium">
            {current.thesis_statement ?? "Thesis statement unavailable"}
          </p>
          <p className="text-sm leading-5 text-muted-foreground">
            Evidence relationships below keep reported facts and interpretation
            distinct.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {claims.slice(0, 6).map((claim) => {
              const supporting = claim.evidence.filter(
                (item) => item.relationship === "SUPPORTS",
              ).length;
              const contradicting = claim.evidence.filter(
                (item) => item.relationship === "CONTRADICTS",
              ).length;
              return (
                <button
                  key={claim.id}
                  type="button"
                  className="rounded-md border p-3 text-left hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => onInspect(claim)}
                >
                  <div className="flex flex-wrap gap-1.5">
                    <StatusIndicator status={claim.claim_type} />
                    <StatusIndicator status={claim.status} />
                  </div>
                  <p className="mt-2 text-sm font-medium">{claim.statement}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {supporting} supporting · {contradicting} contradicting ·{" "}
                    {claim.evidence.length} linked
                  </p>
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-3 border-t pt-3">
            <Link
              href={`/company/${encodeURIComponent(companyId)}?view=thesis`}
              className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
              Open full thesis{" "}
              <ArrowRight aria-hidden="true" className="size-4" />
            </Link>
            <Link
              href={`/company/${encodeURIComponent(companyId)}?view=financials`}
              className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
              Review financials{" "}
              <ArrowRight aria-hidden="true" className="size-4" />
            </Link>
            <Link
              href={`/company/${encodeURIComponent(companyId)}?view=valuation`}
              className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
              Review valuation{" "}
              <ArrowRight aria-hidden="true" className="size-4" />
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function CompanyResearchEvidenceWorkspace({
  companyId,
  companyName,
}: {
  companyId: string;
  companyName: string;
}) {
  const sourceState = useResearch(
    `companies/${encodeURIComponent(companyId)}/source-documents`,
    isCompanySourceDocuments,
  );
  const riskState = useResearch(
    `companies/${encodeURIComponent(companyId)}/risk-assessments`,
    isCompanyRiskAssessments,
  );
  const researchState = useResearch(
    `companies/${encodeURIComponent(companyId)}/research`,
    isCompanyResearch,
  );
  const thesisState = useResearch(
    `companies/${encodeURIComponent(companyId)}/thesis`,
    isCompanyInvestmentThesis,
  );
  const queueState = useResearch(
    `research-queue?search=${encodeURIComponent(companyName)}`,
    isResearchQueue,
  );
  const triggerState = useResearch(
    `research-triggers?company_id=${encodeURIComponent(companyId)}&processing_state=OPEN&limit=50`,
    isResearchTriggerReadResult,
  );
  const [category, setCategory] = useState<EvidenceCategory>("ALL");
  const [recency, setRecency] = useState<EvidenceRecency>("ALL");
  const [selectedActivity, setSelectedActivity] =
    useState<ResearchActivityItem | null>(null);
  const [selectedEvidence, setSelectedEvidence] =
    useState<ResearchEvidence | null>(null);
  const [selectedClaim, setSelectedClaim] =
    useState<InvestmentThesisClaim | null>(null);

  const researchRevisions = useMemo(
    () => researchState.data?.streams.flatMap((stream) => stream.history) ?? [],
    [researchState.data],
  );
  const activity = buildResearchActivity({
    documents: sourceState.data?.documents ?? [],
    researchRevisions,
    riskRevisions: riskState.data?.current ?? [],
    triggers:
      triggerState.data?.triggers.filter(
        (trigger) => trigger.company.id === companyId,
      ) ?? [],
  });
  const filteredActivity = useMemo(
    () => filterResearchActivity(activity, category, recency),
    [activity, category, recency],
  );
  const queueTasks =
    queueState.data?.tasks.filter(
      (task) => task.company.id === companyId && task.status === "OPEN",
    ) ?? [];
  const openTriggers =
    triggerState.data?.triggers.filter(
      (trigger) =>
        trigger.company.id === companyId && trigger.processing_state === "OPEN",
    ) ?? [];
  const unresolvedQuestions =
    thesisState.data?.streams
      .flatMap((stream) => stream.current_revision.claims)
      .filter(
        (claim) =>
          claim.claim_type === "UNRESOLVED_QUESTION" &&
          claim.status !== "RESOLVED",
      ) ?? [];
  const openReviewCount =
    queueState.data && triggerState.data && thesisState.data
      ? queueTasks.length + openTriggers.length + unresolvedQuestions.length
      : null;

  return (
    <div className="space-y-8">
      <PageSection
        title="Research & evidence"
        description="Prioritized source events, accepted interpretations and review work for this company. Facts, judgments and pending proposals remain separate."
        id="research-evidence"
      >
        <div className="space-y-5">
          <ActivitySummary
            source={sourceState.data}
            research={researchState.data}
            risks={riskState.data}
            openReviewCount={openReviewCount}
          />
          <div className="rounded-lg border bg-card p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-sm font-semibold">What changed</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Start with material source activity, then open the underlying
                  evidence or review context.
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium">
                  Evidence category
                  <select
                    aria-label="Evidence category"
                    className="h-10 rounded-md border bg-background px-3 text-sm"
                    value={category}
                    onChange={(event) =>
                      setCategory(event.target.value as EvidenceCategory)
                    }
                  >
                    <option value="ALL">All evidence</option>
                    <option value="FILINGS">Reported sources</option>
                    <option value="RESEARCH">Research interpretations</option>
                    <option value="RISKS">Accepted risks</option>
                    <option value="TRIGGERS">Evidence triggers</option>
                  </select>
                </label>
                <label className="grid gap-1 text-xs font-medium">
                  Recency
                  <select
                    aria-label="Evidence recency"
                    className="h-10 rounded-md border bg-background px-3 text-sm"
                    value={recency}
                    onChange={(event) =>
                      setRecency(event.target.value as EvidenceRecency)
                    }
                  >
                    <option value="ALL">All available dates</option>
                    <option value="30">Last 30 days</option>
                    <option value="90">Last 90 days</option>
                  </select>
                </label>
              </div>
            </div>
          </div>
          {(sourceState.error ||
            researchState.error ||
            riskState.error ||
            triggerState.error ||
            queueState.error ||
            thesisState.error) && (
            <p
              className="rounded-md border border-warning/35 bg-warning/5 p-3 text-sm"
              role="status"
            >
              Some evidence streams are unavailable. Missing source data remains
              explicit and does not become an empty or neutral investment
              conclusion.
            </p>
          )}
          <ActivityList
            items={filteredActivity.slice(0, 10)}
            total={filteredActivity.length}
            onInspect={setSelectedActivity}
          />
        </div>
      </PageSection>

      <PageSection
        title="Filings & source documents"
        description="Reported source metadata and primary links, with filing dates, amendments and retrieval provenance."
        id="source-documents"
      >
        <SourceDocumentsSection
          state={sourceState}
          recency={recency}
          onInspect={setSelectedActivity}
        />
      </PageSection>

      <PageSection
        title="Research interpretations & source evidence"
        description="Published research revisions and their source links. These are interpretations and forecasts, not third-party consensus or accepted model assumptions."
        id="research-interpretations"
      >
        <div className="space-y-4">
          {!researchState.data ? (
            <InlineState
              error={researchState.error}
              retry={researchState.retry}
              label="research archive"
            />
          ) : researchState.data.streams.length === 0 ? (
            <EmptyState
              title="No accepted research revisions"
              description="No agent-authored research forecast or assessment has been accepted for this company."
            />
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {researchState.data.streams.map((stream) => {
                const revisions = uniqueRevisions(stream.history);
                const current = stream.current_revision;
                const streamResearch: CompanyResearch = {
                  company_id: researchState.data!.company_id,
                  as_of: researchState.data!.as_of ?? null,
                  known_at: researchState.data!.known_at ?? null,
                  streams: [stream],
                };
                return (
                  <Card key={stream.stream_key} className="shadow-none">
                    <CardHeader className="pb-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <CardTitle className="text-sm">
                          {stream.stream_key}
                        </CardTitle>
                        <Badge variant="outline">
                          {revisions.length} revision
                          {revisions.length === 1 ? "" : "s"}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Current revision {current.revision_number} ·{" "}
                        {dateTime(current.observed_at)}
                      </p>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <p className="text-sm leading-5">{current.rationale}</p>
                      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>
                          {current.forecasts.length} forecast
                          {current.forecasts.length === 1 ? "" : "s"}
                        </span>
                        <span>
                          {current.assessments.length} assessment
                          {current.assessments.length === 1 ? "" : "s"}
                        </span>
                        <span>
                          {current.evidence.length} evidence link
                          {current.evidence.length === 1 ? "" : "s"}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            setSelectedActivity({
                              id: `research:${current.id}`,
                              category: "RESEARCH",
                              title: `Research revision ${current.revision_number} · ${stream.stream_key}`,
                              summary: current.rationale,
                              effectiveAt: current.observed_at,
                              recordedAt: current.recorded_at,
                              sourceLabel: "Research interpretation",
                              sourceUrl: current.source_reference.startsWith(
                                "https://",
                              )
                                ? current.source_reference
                                : null,
                              status: current.status,
                              detail: { kind: "RESEARCH", revision: current },
                            })
                          }
                        >
                          Inspect current revision
                        </Button>
                        <Link
                          href={`/company/${encodeURIComponent(companyId)}?view=financials`}
                          className="inline-flex items-center gap-1 px-2 text-sm font-medium text-primary hover:underline"
                        >
                          Financial context{" "}
                          <ArrowRight aria-hidden="true" className="size-4" />
                        </Link>
                      </div>
                      <ResearchEvidenceSection
                        data={streamResearch}
                        onInspect={setSelectedEvidence}
                      />
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </PageSection>

      <PageSection
        title="Accepted qualitative risk assessments"
        description="Source-linked judgments remain distinct from the numeric Risk score and deterministic portfolio exposure. Baseline age and reviewer context stay visible."
        id="risk-assessments"
      >
        <AcceptedRiskSection
          state={riskState}
          onInspect={setSelectedActivity}
        />
      </PageSection>

      <PageSection
        title="Research next"
        description="Open evidence triggers, queue work and unresolved thesis questions. Completion uses the existing review workflow and never accepts a proposal automatically."
        id="research-next"
      >
        <ResearchNextSection
          companyId={companyId}
          companyName={companyName}
          queue={queueState.data}
          queueError={queueState.error}
          queueRetry={queueState.retry}
          triggers={triggerState.data?.triggers}
          triggerError={triggerState.error}
          triggerRetry={triggerState.retry}
          thesis={thesisState.data}
        />
      </PageSection>

      <PageSection
        title="Thesis and model context"
        description="Follow evidence relationships into the accepted thesis, financial statements or valuation model without losing the company context."
        id="research-context"
      >
        <ThesisContext
          companyId={companyId}
          thesis={thesisState.data}
          onInspect={setSelectedClaim}
        />
      </PageSection>

      <ActivityDrawer
        item={selectedActivity}
        onOpenChange={(open) => {
          if (!open) setSelectedActivity(null);
        }}
      />
      <EvidenceDrawer
        evidence={selectedEvidence}
        onOpenChange={(open) => {
          if (!open) setSelectedEvidence(null);
        }}
      />
      <ClaimEvidenceDrawer
        claim={selectedClaim}
        onOpenChange={(open) => {
          if (!open) setSelectedClaim(null);
        }}
      />
    </div>
  );
}
