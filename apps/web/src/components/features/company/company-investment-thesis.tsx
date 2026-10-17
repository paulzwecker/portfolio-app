"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRight, FileQuestion, History, ShieldAlert } from "lucide-react";
import { DetailDrawer } from "@/components/app/detail-drawer";
import { EmptyState, PendingOrError } from "@/components/app/empty-state";
import { PageSection } from "@/components/app/page-section";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyInvestmentThesis,
  isResearchQueue,
  type InvestmentThesisClaim,
  type InvestmentThesisEvidence,
  type InvestmentThesisRevision,
  type InvestmentThesisStream,
  type ResearchQueueTask,
} from "@/lib/domain-contracts";
import {
  dateOnly,
  dateTime,
  formatCurrency,
  quantity,
  statusLabel,
} from "@/lib/display";

const claimTypeLabels: Record<string, string> = {
  COMPETITIVE_ADVANTAGE: "Competitive advantage",
  DURABILITY: "Durability",
  GROWTH_DRIVER: "Growth driver",
  PRINCIPAL_RISK: "Principal risk",
  THESIS_BREAKER: "Thesis breaker",
  CATALYST: "Catalyst",
  IMPORTANT_DEVELOPMENT: "Important development",
  UNRESOLVED_QUESTION: "Unresolved question",
};

const claimGroupLabels: Record<string, string> = {
  COMPETITIVE_ADVANTAGE: "Advantage & durability",
  DURABILITY: "Advantage & durability",
  GROWTH_DRIVER: "Growth & reinvestment",
  PRINCIPAL_RISK: "Risks & thesis breakers",
  THESIS_BREAKER: "Risks & thesis breakers",
  CATALYST: "Catalysts",
  IMPORTANT_DEVELOPMENT: "Developments",
  UNRESOLVED_QUESTION: "Open questions",
};

export function reportedFactPeriodLabel(
  fiscalYear: number | null,
  fiscalPeriod: string | null,
) {
  if (fiscalYear === null)
    return fiscalPeriod?.replaceAll("_", " ") ?? "Period unavailable";
  if (!fiscalPeriod || fiscalPeriod === "FY") return `FY${fiscalYear}`;
  return `FY${fiscalYear} · ${fiscalPeriod}`;
}

export function thesisClaimTypeLabel(claimType: string) {
  return claimTypeLabels[claimType] ?? statusLabel(claimType);
}

export function thesisClaimGroupLabel(claimType: string) {
  return claimGroupLabels[claimType] ?? "Other claims";
}

export function thesisEvidenceCounts(claim: InvestmentThesisClaim) {
  return {
    supporting: claim.evidence.filter(
      (item) => item.relationship === "SUPPORTS",
    ).length,
    contradicting: claim.evidence.filter(
      (item) => item.relationship === "CONTRADICTS",
    ).length,
    context: claim.evidence.filter((item) => item.relationship === "CONTEXT")
      .length,
  };
}

type RevisionDelta = {
  added: InvestmentThesisClaim[];
  removed: InvestmentThesisClaim[];
  changed: InvestmentThesisClaim[];
  evidenceChanged: InvestmentThesisClaim[];
  unchanged: number;
};

function evidenceSignature(claim: InvestmentThesisClaim) {
  return claim.evidence
    .map((evidence) =>
      [
        evidence.id,
        evidence.relationship,
        evidence.source_document_id,
        evidence.reported_fundamental_observation_id,
        evidence.external_identifier,
        evidence.source_url,
        evidence.published_at,
        evidence.excerpt,
        evidence.note,
      ]
        .map((value) => value ?? "")
        .join("|"),
    )
    .sort()
    .join("\n");
}

export function compareThesisRevisions(
  current: InvestmentThesisRevision,
  prior: InvestmentThesisRevision,
): RevisionDelta {
  const currentByKey = new Map(
    current.claims.map((claim) => [claim.claim_key, claim]),
  );
  const priorByKey = new Map(
    prior.claims.map((claim) => [claim.claim_key, claim]),
  );
  const added = current.claims.filter(
    (claim) => !priorByKey.has(claim.claim_key),
  );
  const removed = prior.claims.filter(
    (claim) => !currentByKey.has(claim.claim_key),
  );
  const changed: InvestmentThesisClaim[] = [];
  const evidenceChanged: InvestmentThesisClaim[] = [];
  let unchanged = 0;

  current.claims.forEach((claim) => {
    const previous = priorByKey.get(claim.claim_key);
    if (!previous || added.some((item) => item.claim_key === claim.claim_key))
      return;
    const same =
      previous.statement === claim.statement &&
      previous.status === claim.status &&
      previous.confidence === claim.confidence &&
      previous.uncertainty === claim.uncertainty;
    const sameEvidence =
      evidenceSignature(previous) === evidenceSignature(claim);
    if (!same) changed.push(claim);
    if (!sameEvidence) evidenceChanged.push(claim);
    if (same && sameEvidence) unchanged += 1;
  });
  return { added, removed, changed, evidenceChanged, unchanged };
}

function claimSummary(claim: InvestmentThesisClaim) {
  const counts = thesisEvidenceCounts(claim);
  const evidence = [
    counts.supporting ? `${counts.supporting} supporting` : null,
    counts.contradicting ? `${counts.contradicting} contradicting` : null,
    counts.context ? `${counts.context} contextual` : null,
  ].filter(Boolean);
  return evidence.length > 0 ? evidence.join(" · ") : "No linked evidence";
}

function ThesisEvidenceItem({
  evidence,
  onInspect,
}: {
  evidence: InvestmentThesisEvidence;
  onInspect: (evidence: InvestmentThesisEvidence) => void;
}) {
  return (
    <li className="rounded-md border bg-card p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusIndicator status={evidence.relationship} />
        <span className="font-medium">{evidence.source_name}</span>
        {evidence.published_at && (
          <time
            dateTime={evidence.published_at}
            className="text-xs text-muted-foreground"
          >
            Published {dateOnly(evidence.published_at)}
          </time>
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
      {evidence.reported_fundamental && (
        <p className="mt-2 text-xs tabular-nums">
          Linked reported fact ·{" "}
          {evidence.reported_fundamental.metric.replaceAll("_", " ")} ·{" "}
          {evidence.reported_fundamental.unit === "currency"
            ? formatCurrency(
                evidence.reported_fundamental.value,
                evidence.reported_fundamental.currency,
                2,
              )
            : `${quantity(evidence.reported_fundamental.value)} ${evidence.reported_fundamental.currency ?? evidence.reported_fundamental.unit}`}{" "}
          ·{" "}
          {reportedFactPeriodLabel(
            evidence.reported_fundamental.fiscal_year,
            evidence.reported_fundamental.fiscal_period,
          )}
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
        <SourceReference
          className="max-w-full"
          label={evidence.source_document_title ?? evidence.source_name}
          href={evidence.source_document_url ?? evidence.source_url}
          reference={
            evidence.external_identifier ?? evidence.source_document_type
          }
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
      {evidence.reported_fundamental_observation_id && (
        <p className="mt-1 break-all text-[10px] text-muted-foreground">
          Reported-fact observation{" "}
          {evidence.reported_fundamental_observation_id}
        </p>
      )}
      {evidence.source_document_id && (
        <p className="mt-1 break-all text-[10px] text-muted-foreground">
          Source document {evidence.source_document_id}
        </p>
      )}
    </li>
  );
}

function EvidenceDrawer({
  evidence,
  onOpenChange,
}: {
  evidence: InvestmentThesisEvidence | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <DetailDrawer
      open={evidence !== null}
      onOpenChange={onOpenChange}
      title={evidence ? `${evidence.source_name} evidence` : "Evidence details"}
      description="Source and observation provenance for the selected thesis evidence."
    >
      {evidence && (
        <div className="space-y-5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <StatusIndicator status={evidence.relationship} />
            {evidence.source_document_type && (
              <StatusIndicator
                status={evidence.source_document_type}
                label={statusLabel(evidence.source_document_type)}
              />
            )}
          </div>
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted-foreground">Published</dt>
              <dd className="mt-1">
                {evidence.published_at
                  ? dateOnly(evidence.published_at)
                  : "Date unavailable"}
              </dd>
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
              <dt className="text-xs text-muted-foreground">Reported fact</dt>
              <dd className="mt-1 break-all">
                {evidence.reported_fundamental_observation_id ?? "Not linked"}
              </dd>
            </div>
          </dl>
          {evidence.reported_fundamental && (
            <div className="rounded-md border bg-muted/20 p-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Linked reported fact
              </h3>
              <dl className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">Period</dt>
                  <dd className="mt-1">
                    {reportedFactPeriodLabel(
                      evidence.reported_fundamental.fiscal_year,
                      evidence.reported_fundamental.fiscal_period,
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Value</dt>
                  <dd className="mt-1 tabular-nums">
                    {evidence.reported_fundamental.unit === "currency"
                      ? formatCurrency(
                          evidence.reported_fundamental.value,
                          evidence.reported_fundamental.currency,
                          2,
                        )
                      : `${quantity(evidence.reported_fundamental.value)} ${evidence.reported_fundamental.unit}`}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Observed</dt>
                  <dd className="mt-1">
                    {dateTime(evidence.reported_fundamental.observed_at)}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Recorded</dt>
                  <dd className="mt-1">
                    {dateTime(evidence.reported_fundamental.recorded_at)}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Provider</dt>
                  <dd className="mt-1">
                    {evidence.reported_fundamental.provider_id}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Data quality</dt>
                  <dd className="mt-1">
                    {statusLabel(evidence.reported_fundamental.data_quality)}
                  </dd>
                </div>
              </dl>
            </div>
          )}
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
          {evidence.note && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Research note
              </h3>
              <p className="mt-2 leading-6">{evidence.note}</p>
            </div>
          )}
          <SourceReference
            label={evidence.source_document_title ?? evidence.source_name}
            href={evidence.source_document_url ?? evidence.source_url}
            reference={
              evidence.external_identifier ?? evidence.source_document_type
            }
          />
        </div>
      )}
    </DetailDrawer>
  );
}

function InvestmentCaseSummary({
  companyId,
  revision,
}: {
  companyId: string;
  revision: InvestmentThesisRevision;
}) {
  const groups = useMemo(() => {
    const grouped = new Map<string, InvestmentThesisClaim[]>();
    revision.claims.forEach((claim) => {
      const key = thesisClaimGroupLabel(claim.claim_type);
      const claims = grouped.get(key) ?? [];
      claims.push(claim);
      grouped.set(key, claims);
    });
    return grouped;
  }, [revision.claims]);

  const cards = [
    ["Advantage & durability", groups.get("Advantage & durability")],
    ["Growth & reinvestment", groups.get("Growth & reinvestment")],
    ["Risks & thesis breakers", groups.get("Risks & thesis breakers")],
    ["Unresolved questions", groups.get("Open questions")],
  ] as const;

  return (
    <Card className="shadow-none">
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Investment case at a glance
            </p>
            <CardTitle className="mt-1 text-xl">
              {revision.thesis_statement}
            </CardTitle>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusIndicator status={revision.status} label="Accepted thesis" />
            <StatusIndicator
              status={revision.confidence}
              label={`${statusLabel(revision.confidence)} confidence`}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>Revision {revision.revision_number}</span>
          <span>Observed {dateTime(revision.observed_at)}</span>
          <span>Recorded {dateTime(revision.recorded_at)}</span>
          <span>Source · {revision.source_id}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="max-w-4xl text-sm leading-6 text-muted-foreground">
          {revision.rationale}
        </p>
        {revision.uncertainty && (
          <div className="rounded-md border border-warning/30 bg-warning/5 p-3 text-sm">
            <div className="flex items-center gap-2 font-medium">
              <ShieldAlert aria-hidden="true" className="size-4" /> What could
              change the view
            </div>
            <p className="mt-1 leading-5 text-muted-foreground">
              {revision.uncertainty}
            </p>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          {cards.map(([label, claims]) => (
            <div key={label} className="rounded-md border bg-muted/20 p-3">
              <h3 className="text-sm font-semibold">{label}</h3>
              {claims && claims.length > 0 ? (
                <ul className="mt-2 space-y-2">
                  {claims.slice(0, 2).map((claim) => (
                    <li key={claim.id} className="text-sm leading-5">
                      <span className="font-medium">{claim.statement}</span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {statusLabel(claim.status)} ·{" "}
                        {statusLabel(claim.confidence)} confidence ·{" "}
                        {claimSummary(claim)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  No structured claim recorded.
                </p>
              )}
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 border-t pt-3">
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
  );
}

function ClaimExplorer({ claims }: { claims: InvestmentThesisClaim[] }) {
  const [selectedKey, setSelectedKey] = useState(claims[0]?.claim_key ?? "");
  const [selectedEvidence, setSelectedEvidence] =
    useState<InvestmentThesisEvidence | null>(null);

  const selected =
    claims.find((claim) => claim.claim_key === selectedKey) ??
    claims[0] ??
    null;
  if (claims.length === 0) {
    return (
      <EmptyState
        title="No structured claims"
        description="This accepted revision contains a thesis statement but no keyed claims or linked evidence."
        icon={<FileQuestion aria-hidden="true" className="size-4" />}
      />
    );
  }

  const groupedClaims = claims.reduce<Record<string, InvestmentThesisClaim[]>>(
    (groups, claim) => {
      const group = thesisClaimGroupLabel(claim.claim_type);
      groups[group] = [...(groups[group] ?? []), claim];
      return groups;
    },
    {},
  );

  return (
    <>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.4fr)]">
        <div className="space-y-3" aria-label="Thesis claims">
          {Object.entries(groupedClaims).map(([group, groupClaims]) => (
            <div key={group} className="space-y-1">
              <p className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group}
              </p>
              {groupClaims.map((claim) => (
                <button
                  key={claim.id}
                  type="button"
                  aria-pressed={claim.claim_key === selected?.claim_key}
                  onClick={() => setSelectedKey(claim.claim_key)}
                  className={`block w-full rounded-md border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${claim.claim_key === selected?.claim_key ? "border-primary bg-primary/5" : "bg-card hover:bg-muted/40"}`}
                >
                  <span className="flex flex-wrap items-center gap-2">
                    <StatusIndicator
                      status={claim.status}
                      label={thesisClaimTypeLabel(claim.claim_type)}
                    />
                    <span className="text-xs text-muted-foreground">
                      {statusLabel(claim.confidence)}
                    </span>
                  </span>
                  <span className="mt-2 block text-sm leading-5">
                    {claim.statement}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {claimSummary(claim)}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
        <div
          className="min-w-0 rounded-lg border bg-card p-4"
          aria-live="polite"
        >
          {selected ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Selected claim
                  </p>
                  <h3 className="mt-1 text-lg font-semibold">
                    {selected.statement}
                  </h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusIndicator status={selected.status} />
                  <StatusIndicator
                    status={selected.confidence}
                    label={`${statusLabel(selected.confidence)} confidence`}
                  />
                </div>
              </div>
              {selected.uncertainty && (
                <p className="rounded-md bg-muted/40 p-3 text-sm leading-5 text-muted-foreground">
                  Uncertainty · {selected.uncertainty}
                </p>
              )}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Evidence
                </h4>
                {selected.evidence.length > 0 ? (
                  <div className="mt-2 space-y-2">
                    {selected.evidence.map((evidence) => (
                      <ThesisEvidenceItem
                        key={evidence.id}
                        evidence={evidence}
                        onInspect={setSelectedEvidence}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">
                    No supporting, contradicting or contextual evidence is
                    linked.
                  </p>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Claim key · {selected.claim_key}
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Select a claim to inspect its evidence.
            </p>
          )}
        </div>
      </div>
      <EvidenceDrawer
        evidence={selectedEvidence}
        onOpenChange={(open) => !open && setSelectedEvidence(null)}
      />
    </>
  );
}

function RevisionHistory({ stream }: { stream: InvestmentThesisStream }) {
  const prior = stream.history.filter(
    (revision) => revision.id !== stream.current_revision.id,
  );
  if (prior.length === 0) return null;
  return (
    <details className="rounded-lg border bg-card p-4">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium">
        <History aria-hidden="true" className="size-4" />
        Prior thesis revisions · {prior.length}
      </summary>
      <div className="mt-4 space-y-3">
        {prior.map((revision) => {
          const delta = compareThesisRevisions(
            stream.current_revision,
            revision,
          );
          return (
            <Card key={revision.id} className="shadow-none">
              <CardHeader className="pb-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-sm">
                    Revision {revision.revision_number} ·{" "}
                    {dateTime(revision.recorded_at)}
                  </CardTitle>
                  <div className="flex flex-wrap gap-2">
                    <StatusIndicator status={revision.status} />
                    <StatusIndicator status={revision.confidence} />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {revision.thesis_statement && (
                  <p className="leading-6">{revision.thesis_statement}</p>
                )}
                <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-4">
                  <span>{delta.added.length} added</span>
                  <span>{delta.changed.length} changed</span>
                  <span>{delta.evidenceChanged.length} evidence updated</span>
                  <span>
                    {delta.removed.length} removed · {delta.unchanged} unchanged
                  </span>
                </div>
                {(delta.added.length > 0 ||
                  delta.changed.length > 0 ||
                  delta.evidenceChanged.length > 0 ||
                  delta.removed.length > 0) && (
                  <ul className="space-y-1 border-t pt-3 text-xs">
                    {delta.added.map((claim) => (
                      <li key={`added-${claim.id}`}>
                        <StatusIndicator
                          status="AVAILABLE"
                          label="Added"
                          className="mr-2"
                        />
                        {claim.statement}
                      </li>
                    ))}
                    {delta.changed.map((claim) => (
                      <li key={`changed-${claim.id}`}>
                        <StatusIndicator
                          status="REVIEW"
                          label="Changed"
                          className="mr-2"
                        />
                        {claim.statement}
                      </li>
                    ))}
                    {delta.evidenceChanged.map((claim) => (
                      <li key={`evidence-${claim.id}`}>
                        <StatusIndicator
                          status="INFO"
                          label="Evidence updated"
                          className="mr-2"
                        />
                        {claim.statement}
                      </li>
                    ))}
                    {delta.removed.map((claim) => (
                      <li key={`removed-${claim.id}`}>
                        <StatusIndicator
                          status="INVALID"
                          label="Removed"
                          className="mr-2"
                        />
                        {claim.statement}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    {revision.author_id} · {revision.source_id}
                  </span>
                  <span>Observed {dateTime(revision.observed_at)}</span>
                </div>
                <SourceReference
                  label={revision.source_id}
                  href={
                    revision.source_reference.startsWith("http")
                      ? revision.source_reference
                      : null
                  }
                  reference={revision.source_reference}
                />
              </CardContent>
            </Card>
          );
        })}
      </div>
    </details>
  );
}

function ResearchFollowUp({
  companyId,
  companyName,
  queue,
}: {
  companyId: string;
  companyName: string;
  queue: { data?: { tasks: ResearchQueueTask[] }; error?: string };
}) {
  const tasks =
    queue.data?.tasks.filter(
      (task) => task.company.id === companyId && task.status === "OPEN",
    ) ?? [];
  return (
    <PageSection
      title="Research next"
      description="Open review conditions point to the next evidence or question. Completing a queue item never accepts a thesis or changes investment state."
    >
      {!queue.data && !queue.error ? (
        <p
          role="status"
          className="rounded-md border border-dashed p-4 text-sm text-muted-foreground"
        >
          Loading research queue…
        </p>
      ) : queue.error ? (
        <EmptyState
          title="Research queue unavailable"
          description={queue.error}
        />
      ) : tasks.length === 0 ? (
        <EmptyState
          title="No open research item linked"
          description="This is not a claim that the thesis is complete; no current queue condition is associated with this company."
          icon={<FileQuestion aria-hidden="true" className="size-4" />}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {tasks.map((task) => (
            <Card key={task.task_id} className="shadow-none">
              <CardContent className="space-y-3 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusIndicator status={task.task_type} />
                  <StatusIndicator status={task.status} />
                </div>
                <h3 className="font-semibold">{task.title}</h3>
                <p className="text-sm leading-5 text-muted-foreground">
                  {task.reason}
                </p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>{statusLabel(task.owner_workflow)}</span>
                  <span>
                    {task.judgment_required
                      ? "Analyst judgment required"
                      : "Deterministic review"}
                  </span>
                  {task.source_published_at && (
                    <span>
                      Source published {dateOnly(task.source_published_at)}
                    </span>
                  )}
                  {task.source_recorded_at && (
                    <span>Recorded {dateTime(task.source_recorded_at)}</span>
                  )}
                </div>
                <Link
                  href={`/research-queue?search=${encodeURIComponent(companyName)}`}
                  className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                >
                  Open research queue{" "}
                  <ArrowRight aria-hidden="true" className="size-4" />
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </PageSection>
  );
}

function ThesisStream({
  companyId,
  stream,
}: {
  companyId: string;
  stream: InvestmentThesisStream;
}) {
  const revision = stream.current_revision;
  if (revision.status === "WITHDRAWN") {
    return (
      <EmptyState
        title="Thesis withdrawn"
        description={`The latest accepted revision was withdrawn on ${dateTime(revision.recorded_at)}. Earlier revisions remain available in the audit history.`}
      />
    );
  }
  return (
    <div className="space-y-5">
      <InvestmentCaseSummary companyId={companyId} revision={revision} />
      <PageSection
        title="Claims & evidence"
        description="Select a claim to inspect supporting, contradicting and contextual evidence. Linked facts retain their own source and reporting dates."
      >
        <ClaimExplorer claims={revision.claims} />
      </PageSection>
      <RevisionHistory stream={stream} />
    </div>
  );
}

export function CompanyInvestmentThesis({
  companyId,
  companyName = "company",
}: {
  companyId: string;
  companyName?: string;
}) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/thesis`,
    isCompanyInvestmentThesis,
  );
  const queue = useResearch("research-queue", isResearchQueue);

  return (
    <section id="investment-thesis" className="scroll-mt-5">
      <PageSection
        title="Investment thesis"
        description="Why this business may compound over the long term, what supports that view and what could invalidate it. Accepted opinions remain separate from reported facts, scores and model assumptions."
      >
        {!state.data ? (
          <PendingOrError {...state} />
        ) : state.data.streams.length === 0 ? (
          <div className="space-y-5">
            <EmptyState
              title="No accepted thesis revision"
              description="The application has no source-linked investment case for this company yet. This is an explicit missing state, not a neutral assessment."
              icon={<FileQuestion aria-hidden="true" className="size-4" />}
            />
            <ResearchFollowUp
              companyId={companyId}
              companyName={companyName}
              queue={queue}
            />
          </div>
        ) : (
          <div className="space-y-8">
            {state.data.streams.map((stream) => (
              <div key={stream.stream_key} className="space-y-3">
                {state.data!.streams.length > 1 && (
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {stream.stream_key}
                  </p>
                )}
                <ThesisStream companyId={companyId} stream={stream} />
              </div>
            ))}
            <ResearchFollowUp
              companyId={companyId}
              companyName={companyName}
              queue={queue}
            />
          </div>
        )}
      </PageSection>
    </section>
  );
}
