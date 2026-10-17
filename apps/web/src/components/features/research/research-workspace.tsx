"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/app/page-header";
import { StatusIndicator } from "@/components/app/status-indicator";
import { AttentionCenter } from "@/components/attention-center";
import { CandidatePipelinePanel } from "@/components/features/research/candidate-pipeline-panel";
import { GoogleSheetsAgentWorkFeed as AgentWorkFeed } from "@/components/features/research/agent-work-feed";
import { PortfolioStatePublication } from "@/components/features/research/portfolio-state-publication";
import { ProposalReviewPanel } from "@/components/features/research/proposal-review-panel";
import { ResearchQueuePanel } from "@/components/features/research/research-queue-panel";
import {
  isCandidatePipelineQueue,
  isGoogleSheetsResearchCandidate,
  isGoogleSheetsRiskCandidate,
  isGoogleSheetsSyncCandidate,
  isResearchQueue,
  isResearchTriggerReadResult,
} from "@/lib/domain-contracts";
import { useResearch } from "@/hooks/use-research";

export type ResearchView = "pipeline" | "queue" | "reviews" | "changes";

const views: [ResearchView, string][] = [
  ["pipeline", "Candidate Pipeline"],
  ["queue", "Review Queue"],
  ["reviews", "Agent proposals"],
  ["changes", "Change feed"],
];

function isModelCandidates(value: unknown) {
  return Array.isArray(value) && value.every(isGoogleSheetsSyncCandidate);
}
function isResearchCandidates(value: unknown) {
  return Array.isArray(value) && value.every(isGoogleSheetsResearchCandidate);
}
function isRiskCandidates(value: unknown) {
  return Array.isArray(value) && value.every(isGoogleSheetsRiskCandidate);
}
function asCount(value: number | undefined) {
  return value === undefined ? "Unavailable" : value;
}

export function ResearchWorkspace({
  initialView,
}: {
  initialView: ResearchView;
}) {
  const candidates = useResearch(
    "candidate-pipeline",
    isCandidatePipelineQueue,
  );
  const queue = useResearch("research-queue", isResearchQueue);
  const triggers = useResearch(
    "research-triggers?processing_state=OPEN&limit=100",
    isResearchTriggerReadResult,
  );
  const modelProposals = useResearch(
    "google-sheets-sync/candidates",
    isModelCandidates,
  );
  const researchProposals = useResearch(
    "google-sheets-research-sync/candidates",
    isResearchCandidates,
  );
  const riskProposals = useResearch(
    "google-sheets-risk-sync/candidates",
    isRiskCandidates,
  );

  const openProposalCount = [
    modelProposals.data,
    researchProposals.data,
    riskProposals.data,
  ].reduce(
    (count, rows) =>
      count +
      (rows ?? []).filter(
        (row) => !["ACCEPTED", "REJECTED"].includes(row.status),
      ).length,
    0,
  );
  const proposalDataLoaded = Boolean(
    modelProposals.data && researchProposals.data && riskProposals.data,
  );
  const retryProposals = () => {
    modelProposals.retry();
    researchProposals.retry();
    riskProposals.retry();
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Research"
        title="Research & Review"
        description="Find the next research task, understand the evidence behind it, and review external proposals without conflating delivery, completion, or approval."
        actions={
          <Link
            href="/universe"
            className="inline-flex min-h-10 items-center rounded-md border px-3 text-sm font-medium hover:bg-muted"
          >
            Open Universe
          </Link>
        }
      />

      <section
        aria-label="Research workload at a glance"
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        <GlanceCard
          label="Candidate companies"
          value={asCount(candidates.data?.length)}
          note={
            candidates.error
              ? "Pipeline unavailable"
              : "Explicit Candidate lifecycle"
          }
          status={
            candidates.error
              ? "UNAVAILABLE"
              : candidates.data
                ? "AVAILABLE"
                : "LOADING"
          }
        />
        <GlanceCard
          label="Open research reviews"
          value={asCount(queue.data?.counts.open)}
          note={
            queue.error
              ? "Queue unavailable"
              : "Cross-lifecycle source conditions"
          }
          status={
            queue.error ? "UNAVAILABLE" : queue.data ? "AVAILABLE" : "LOADING"
          }
        />
        <GlanceCard
          label="Agent proposals"
          value={proposalDataLoaded ? openProposalCount : "Unavailable"}
          note={
            proposalDataLoaded
              ? "Awaiting explicit reviewer action"
              : "Inbox status unavailable"
          }
          status={
            proposalDataLoaded
              ? openProposalCount
                ? "PENDING"
                : "COMPLETE"
              : "UNAVAILABLE"
          }
        />
        <GlanceCard
          label="Open evidence triggers"
          value={triggers.data ? triggers.data.triggers.length : "Unavailable"}
          note={
            triggers.error
              ? "Trigger feed unavailable"
              : "Captured source events"
          }
          status={
            triggers.error
              ? "UNAVAILABLE"
              : triggers.data
                ? "AVAILABLE"
                : "LOADING"
          }
        />
      </section>

      <nav
        aria-label="Research views"
        className="flex flex-wrap gap-2 border-b pb-3"
      >
        {views.map(([value, label]) => (
          <Link
            key={value}
            href={"/research?view=" + value}
            aria-current={initialView === value ? "page" : undefined}
            className={
              "rounded-md px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
              (initialView === value
                ? "bg-primary font-medium text-primary-foreground"
                : "border text-foreground hover:bg-muted")
            }
          >
            {label}
            {value === "queue" && queue.data && (
              <Badge variant="outline" className="ml-2">
                {queue.data.counts.open}
              </Badge>
            )}
            {value === "reviews" && proposalDataLoaded && (
              <Badge variant="outline" className="ml-2">
                {openProposalCount}
              </Badge>
            )}
          </Link>
        ))}
      </nav>

      {initialView === "pipeline" && (
        <CandidatePipelinePanel
          candidates={candidates.data}
          loading={!candidates.data && !candidates.error}
          error={candidates.error}
          retry={candidates.retry}
        />
      )}
      {initialView === "queue" && (
        <>
          <ResearchQueuePanel
            queue={queue.data}
            loading={!queue.data && !queue.error}
            error={queue.error}
            retry={queue.retry}
            triggers={triggers.data}
            triggerLoading={!triggers.data && !triggers.error}
            triggerError={triggers.error}
            retryTriggers={triggers.retry}
          />
          <section
            aria-label="External research agent handoff"
            id="agent-work-feed"
          >
            <div className="grid gap-4 xl:grid-cols-2">
              <AgentWorkFeed />
              <PortfolioStatePublication />
            </div>
          </section>
        </>
      )}
      {initialView === "reviews" && (
        <>
          {(!modelProposals.data ||
            !researchProposals.data ||
            !riskProposals.data) && (
            <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              Some proposal inbox data is unavailable. Available domains remain
              reviewable; missing inboxes are not treated as empty.
              <Button
                variant="outline"
                className="ml-2"
                onClick={retryProposals}
              >
                Retry inboxes
              </Button>
            </div>
          )}
          <ProposalReviewPanel
            modelCandidates={modelProposals.data}
            researchCandidates={researchProposals.data}
            riskCandidates={riskProposals.data}
            retry={retryProposals}
          />
        </>
      )}
      {initialView === "changes" && (
        <section
          aria-labelledby="research-changes-heading"
          className="space-y-3"
        >
          <div>
            <h2 id="research-changes-heading" className="text-lg font-semibold">
              Research change feed
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Material source changes are separate from queue tasks and proposal
              decisions.
            </p>
          </div>
          <AttentionCenter />
        </section>
      )}
    </div>
  );
}

function GlanceCard({
  label,
  value,
  note,
  status,
}: {
  label: string;
  value: string | number;
  note: string;
  status: string;
}) {
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">{note}</span>
          <StatusIndicator status={status} />
        </div>
      </CardContent>
    </Card>
  );
}
