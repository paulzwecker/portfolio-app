"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { EmptyState, PendingOrError } from "@/components/app/empty-state";
import { MetricCard } from "@/components/app/metric-card";
import { PageHeader } from "@/components/app/page-header";
import { PageSection } from "@/components/app/page-section";
import {
  ResponsiveDataTable,
  type ResponsiveColumn,
} from "@/components/app/responsive-data-table";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ManualRefreshPanel } from "@/components/features/operations/manual-refresh-panel";
import { useResearch } from "@/hooks/use-research";
import {
  isGoogleSheetsResearchCandidate,
  isGoogleSheetsResearchSyncStatus,
  isGoogleSheetsRiskCandidate,
  isGoogleSheetsRiskSyncStatus,
  isGoogleSheetsSyncCandidate,
  isGoogleSheetsSyncStatus,
  isRecurringOperationsStatus,
  isResearchAgentWorkEvent,
  type GoogleSheetsResearchCandidate,
  type GoogleSheetsRiskCandidate,
  type GoogleSheetsSyncCandidate,
  type RecurringOperationJob,
  type ResearchAgentWorkEvent,
} from "@/lib/domain-contracts";
import { dateTime, statusLabel } from "@/lib/display";

const jobLabels: Record<RecurringOperationJob["job_name"], string> = {
  SEC_FUNDAMENTALS: "SEC reported fundamentals",
  SEC_FILINGS: "SEC filings",
  FMP_CONSENSUS: "Consensus estimates",
  SHEETS_DISCOVERY: "Google Sheets proposal discovery",
  RESEARCH_TRIGGER_SCAN: "Research trigger scan",
  AGENT_WORK_FEED: "Agent work-feed publication",
  DECISION_RECOMPUTE: "Decision recomputation",
};

const isGoogleSheetsSyncCandidates = (
  value: unknown,
): value is GoogleSheetsSyncCandidate[] =>
  Array.isArray(value) && value.every(isGoogleSheetsSyncCandidate);
const isGoogleSheetsResearchCandidates = (
  value: unknown,
): value is GoogleSheetsResearchCandidate[] =>
  Array.isArray(value) && value.every(isGoogleSheetsResearchCandidate);
const isGoogleSheetsRiskCandidates = (
  value: unknown,
): value is GoogleSheetsRiskCandidate[] =>
  Array.isArray(value) && value.every(isGoogleSheetsRiskCandidate);
const isRecentAgentEvents = (
  value: unknown,
): value is ResearchAgentWorkEvent[] =>
  Array.isArray(value) && value.every(isResearchAgentWorkEvent);

type CandidateState = { status: string; issue: string | null };
type SyncRunState = {
  status: string;
  started_at: string;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  issue_count: number;
  candidate_count: number;
  new_count: number;
  unchanged_count: number;
};

type IntegrationSummary = {
  title: string;
  inbox: string;
  spreadsheetId?: string | null;
  spreadsheetUrl?: string | null;
  pollingSeconds?: number;
  configured?: boolean;
  credentialsAvailable?: boolean;
  lastRun?: SyncRunState | null;
  candidates?: CandidateState[];
  statusError?: string;
  candidatesError?: string;
};

export function OperationsOverview() {
  const recurring = useResearch(
    "recurring-operations/status",
    isRecurringOperationsStatus,
  );
  const modelSync = useResearch(
    "google-sheets-sync/status",
    isGoogleSheetsSyncStatus,
  );
  const modelCandidates = useResearch(
    "google-sheets-sync/candidates",
    isGoogleSheetsSyncCandidates,
  );
  const researchSync = useResearch(
    "google-sheets-research-sync/status",
    isGoogleSheetsResearchSyncStatus,
  );
  const researchCandidates = useResearch(
    "google-sheets-research-sync/candidates",
    isGoogleSheetsResearchCandidates,
  );
  const riskSync = useResearch(
    "google-sheets-risk-sync/status",
    isGoogleSheetsRiskSyncStatus,
  );
  const riskCandidates = useResearch(
    "google-sheets-risk-sync/candidates",
    isGoogleSheetsRiskCandidates,
  );
  const agentEvents = useResearch(
    "research-agent-operations/events?limit=12",
    isRecentAgentEvents,
  );

  const retryAll = () => {
    recurring.retry();
    modelSync.retry();
    modelCandidates.retry();
    researchSync.retry();
    researchCandidates.retry();
    riskSync.retry();
    riskCandidates.retry();
    agentEvents.retry();
  };

  const header = (
    <PageHeader
      eyebrow="Operations"
      title="Data and integration status"
      description="Review worker health and data connections, then queue bounded refreshes through the existing background workers. Refreshing never accepts an investment proposal or changes portfolio decisions."
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={retryAll}>
            <RefreshCw aria-hidden="true" />
            Refresh status
          </Button>
          <Button asChild>
            <Link href="/research?view=reviews">Open research reviews</Link>
          </Button>
        </div>
      }
    />
  );

  if (!recurring.data)
    return (
      <div className="space-y-6">
        {header}
        <PendingOrError error={recurring.error} retry={retryAll} />
      </div>
    );

  const data = recurring.data;
  const jobs = data.jobs;
  const problemJobs = jobs.filter((job) =>
    ["PARTIAL", "BLOCKED", "FAILED"].includes(job.status),
  );
  const integrationCards: IntegrationSummary[] = [
    {
      title: "Model proposals",
      inbox: modelSync.data?.sync_tab ?? "Model Sync Inbox",
      spreadsheetId: modelSync.data?.spreadsheet_id,
      spreadsheetUrl: modelSync.data?.spreadsheet_url,
      pollingSeconds: modelSync.data?.polling_interval_seconds,
      configured: modelSync.data?.configured,
      credentialsAvailable: modelSync.data?.credentials_available,
      lastRun: modelSync.data?.last_run,
      candidates: modelCandidates.data?.map(({ status, issue }) => ({
        status,
        issue,
      })),
      statusError: modelSync.error,
      candidatesError: modelCandidates.error,
    },
    {
      title: "Research and thesis proposals",
      inbox:
        researchSync.data?.research_inbox_tab ?? "Research / thesis inboxes",
      spreadsheetId: researchSync.data?.spreadsheet_id,
      spreadsheetUrl: researchSync.data?.spreadsheet_url,
      configured: researchSync.data?.configured,
      credentialsAvailable: researchSync.data?.credentials_available,
      lastRun: researchSync.data?.last_run,
      candidates: researchCandidates.data?.map(({ status, issue }) => ({
        status,
        issue,
      })),
      statusError: researchSync.error,
      candidatesError: researchCandidates.error,
    },
    {
      title: "Risk assessments",
      inbox: riskSync.data?.inbox_tab ?? "Risk Assessment Inbox",
      spreadsheetId: riskSync.data?.spreadsheet_id,
      spreadsheetUrl: riskSync.data?.spreadsheet_url,
      configured: riskSync.data?.configured,
      credentialsAvailable: riskSync.data?.credentials_available,
      lastRun: riskSync.data?.last_run,
      candidates: riskCandidates.data?.map(({ status, issue }) => ({
        status,
        issue,
      })),
      statusError: riskSync.error,
      candidatesError: riskCandidates.error,
    },
  ];
  const openCandidates = integrationCards.flatMap(
    (item) =>
      item.candidates?.filter(
        (candidate) =>
          !["ACCEPTED", "REJECTED", "NO_CHANGES"].includes(candidate.status),
      ) ?? [],
  );
  const candidateCountsAvailable = integrationCards.every(
    (item) => item.candidates !== undefined,
  );
  const jobColumns: ResponsiveColumn<RecurringOperationJob>[] = [
    {
      id: "job",
      header: "Job",
      render: (job) => jobLabels[job.job_name],
    },
    {
      id: "status",
      header: "Status",
      render: (job) => <StatusIndicator status={job.status} />,
    },
    {
      id: "last-attempt",
      header: "Last attempt",
      render: (job) => dateTime(job.last_attempt_at),
    },
    {
      id: "last-success",
      header: "Last success",
      render: (job) => dateTime(job.last_successful_at),
    },
    {
      id: "next-attempt",
      header: "Next attempt",
      render: (job) => dateTime(job.next_attempt_at),
    },
    {
      id: "issue",
      header: "Issue",
      render: (job) =>
        job.failure_message ?? job.failure_code ?? "None reported",
    },
    {
      id: "details",
      header: "Run details",
      render: (job) =>
        Object.keys(job.result).length ? (
          <details className="max-w-64">
            <summary className="cursor-pointer text-xs font-medium">
              Inspect recorded result
            </summary>
            <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-2 text-xs">
              {JSON.stringify(job.result, null, 2)}
            </pre>
          </details>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <div className="space-y-8">
      {header}

      <ManualRefreshPanel workerEnabled={data.enabled} />

      <section
        aria-label="Operational summary"
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        <MetricCard
          label="Recurring worker"
          value={
            <StatusIndicator
              status={data.enabled ? data.worker_state : "DISABLED"}
            />
          }
          note={`Last heartbeat · ${dateTime(data.worker_last_seen_at)}`}
        />
        <MetricCard
          label="Market data"
          value={<StatusIndicator status={data.market_data.state} />}
          note={`Last success · ${dateTime(data.market_data.last_successful_update)}`}
        />
        <MetricCard
          label="Open proposals"
          value={
            candidateCountsAvailable
              ? String(openCandidates.length)
              : "Unavailable"
          }
          note={
            candidateCountsAvailable
              ? "Open records in the returned lists (up to 100 per integration)"
              : "One or more candidate feeds could not be read"
          }
        />
        <MetricCard
          label="Recent agent receipts"
          value={
            agentEvents.data
              ? String(agentEvents.data.length)
              : agentEvents.error
                ? "Unavailable"
                : "Loading"
          }
          note="Latest delivery and acknowledgment records"
        />
      </section>

      <PageSection
        title="Worker and market data"
        description="Worker heartbeat and market-data freshness are independent checks. Configured credentials do not prove that a provider request succeeded."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="shadow-none">
            <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
              <CardTitle className="text-base">Recurring worker</CardTitle>
              <StatusIndicator
                status={data.enabled ? data.worker_state : "DISABLED"}
              />
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <StatusField
                  label="Started"
                  value={dateTime(data.worker_started_at)}
                />
                <StatusField
                  label="Last heartbeat"
                  value={dateTime(data.worker_last_seen_at)}
                />
                <StatusField
                  label="SEC user agent"
                  value={
                    data.sec_user_agent_configured
                      ? "Configured"
                      : "Not configured"
                  }
                />
                <StatusField
                  label="Sheets configuration"
                  value={
                    !data.google_sheets_configured
                      ? "Not configured"
                      : data.google_sheets_credentials_available
                        ? "Credentials available"
                        : "Credentials unavailable"
                  }
                />
                <StatusField
                  label="Sheets polling interval"
                  value={
                    data.google_sheets_configured
                      ? `${data.google_sheets_poll_seconds} seconds`
                      : "Not configured"
                  }
                />
                <StatusField
                  label="FMP consensus ingestion"
                  value={
                    data.fmp_consensus_ingestion_enabled
                      ? "Enabled"
                      : "Disabled"
                  }
                />
              </dl>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
              <CardTitle className="text-base">Market data refresh</CardTitle>
              <StatusIndicator status={data.market_data.state} />
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <StatusField
                  label="Last successful update"
                  value={dateTime(data.market_data.last_successful_update)}
                />
                <StatusField
                  label="Last attempt"
                  value={dateTime(data.market_data.last_attempt_at)}
                />
                <StatusField
                  label="Market run"
                  value={data.market_data.market_run_id ?? "Not recorded"}
                />
                <StatusField
                  label="FX run"
                  value={data.market_data.fx_run_id ?? "Not recorded"}
                />
              </dl>
              {data.market_data.message && (
                <p className="mt-4 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
                  {data.market_data.message}
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </PageSection>

      <PageSection
        title="Recurring jobs"
        description="Latest attempt, successful completion and next scheduled attempt. Expand a result to inspect the structured report saved by the worker."
      >
        <ResponsiveDataTable
          caption="Recurring data and research jobs"
          columns={jobColumns}
          rows={jobs}
          getRowKey={(job) => job.job_name}
        />
        <p className="text-xs text-muted-foreground">
          This is the latest recorded state, not a guarantee that every company
          has complete or current data.
        </p>
      </PageSection>

      <PageSection
        title="Workbook synchronization and proposal intake"
        description="Connection configuration, latest polling result and candidate review states. Publication discovery does not accept a proposal."
        actions={
          <Button asChild variant="outline">
            <Link href="/research?view=reviews">Review proposals</Link>
          </Button>
        }
      >
        <div className="grid gap-4 xl:grid-cols-3">
          {integrationCards.map((integration) => (
            <IntegrationCard
              key={integration.title}
              integration={integration}
            />
          ))}
        </div>
      </PageSection>

      <PageSection
        title="Agent delivery and acknowledgments"
        description="Delivery receipts and agent status updates are operational records; they do not imply that research or a proposal has been accepted."
        actions={
          <Button asChild variant="outline">
            <Link href="/research?view=changes">Open research changes</Link>
          </Button>
        }
      >
        {agentEvents.error ? (
          <InlineUnavailable message="Agent event history is unavailable. Check the API and worker connection, then refresh." />
        ) : agentEvents.data?.length ? (
          <ol
            aria-label="Recent agent delivery and acknowledgment events"
            className="space-y-3"
          >
            {agentEvents.data.map((event) => (
              <AgentEventRow key={event.id} event={event} />
            ))}
          </ol>
        ) : agentEvents.data ? (
          <EmptyState
            title="No agent receipts recorded"
            description="The event endpoint returned no recent deliveries or acknowledgments. This does not indicate that there is no research work waiting."
          />
        ) : (
          <div
            role="status"
            className="rounded-md border p-4 text-sm text-muted-foreground"
          >
            Loading agent event history…
          </div>
        )}
      </PageSection>

      <PageSection
        title="Coverage and blockers"
        description="Operational failures are summarized here. Company-level factual coverage remains visible in the Universe and Company Explorer."
      >
        {problemJobs.length ? (
          <div className="space-y-3">
            {problemJobs.map((job) => (
              <div
                key={job.job_name}
                className="flex flex-wrap items-start justify-between gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0">
                  <p className="font-medium">{jobLabels[job.job_name]}</p>
                  <p className="mt-1 break-words text-sm text-muted-foreground">
                    {job.failure_message ??
                      job.failure_code ??
                      "The latest run reported partial or blocked work."}
                  </p>
                </div>
                <StatusIndicator status={job.status} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No recurring job failures reported"
            description="The latest job records contain no PARTIAL, BLOCKED or FAILED state. This does not confirm full company-level coverage."
          />
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link href="/universe">Inspect company coverage</Link>
          </Button>
        </div>
        {(modelSync.error ||
          researchSync.error ||
          riskSync.error ||
          modelCandidates.error ||
          researchCandidates.error ||
          riskCandidates.error) && (
          <p
            role="status"
            className="mt-3 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm"
          >
            One or more workbook status or candidate feeds could not be
            verified. The individual integration panels retain the unavailable
            state.
          </p>
        )}
      </PageSection>
    </div>
  );
}

function IntegrationCard({ integration }: { integration: IntegrationSummary }) {
  const counts = countCandidates(integration.candidates);
  const connectionStatus =
    integration.configured === undefined
      ? "UNAVAILABLE"
      : !integration.configured
        ? "NOT_CONFIGURED"
        : integration.credentialsAvailable
          ? "CONFIGURED"
          : "BLOCKED";
  return (
    <Card className="shadow-none">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="min-w-0">
          <CardTitle className="text-base">{integration.title}</CardTitle>
          <p className="mt-1 break-words text-xs text-muted-foreground">
            {integration.inbox}
          </p>
        </div>
        <StatusIndicator status={connectionStatus} />
      </CardHeader>
      <CardContent className="space-y-4">
        {integration.statusError ? (
          <InlineUnavailable message="Connection status unavailable." />
        ) : (
          <p className="text-xs text-muted-foreground">
            {integration.configured
              ? integration.credentialsAvailable
                ? "Configuration and credentials are present; the last run below shows actual connection status."
                : "Configuration exists, but credentials are unavailable."
              : integration.configured === false
                ? "This integration is not configured."
                : "Status is still loading."}
          </p>
        )}
        {integration.spreadsheetId && (
          <StatusField
            label="Spreadsheet ID"
            value={integration.spreadsheetId}
          />
        )}
        {integration.pollingSeconds !== undefined && (
          <StatusField
            label="Polling interval"
            value={`${integration.pollingSeconds} seconds`}
          />
        )}
        {integration.spreadsheetUrl && (
          <Link
            href={integration.spreadsheetUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-8 items-center text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
          >
            Open configured workbook
            <span className="sr-only"> for {integration.title}</span>
          </Link>
        )}
        {integration.lastRun ? (
          <div className="rounded-md border bg-muted/20 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-medium">Latest check</span>
              <StatusIndicator status={integration.lastRun.status} />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <StatusField
                label="Started"
                value={dateTime(integration.lastRun.started_at)}
              />
              <StatusField
                label="Completed"
                value={dateTime(integration.lastRun.completed_at)}
              />
              <StatusField
                label="Candidates"
                value={String(integration.lastRun.candidate_count)}
              />
              <StatusField
                label="Run issues"
                value={String(integration.lastRun.issue_count)}
              />
            </dl>
            {(integration.lastRun.error_message ||
              integration.lastRun.error_code) && (
              <p className="mt-3 break-words text-xs text-warning">
                {integration.lastRun.error_message ??
                  integration.lastRun.error_code}
              </p>
            )}
          </div>
        ) : integration.statusError ? null : (
          <div className="rounded-md border p-3 text-xs text-muted-foreground">
            No synchronization run has been recorded.
          </div>
        )}
        {integration.candidatesError ? (
          <InlineUnavailable message="Candidate review counts unavailable." />
        ) : counts ? (
          <dl className="grid grid-cols-3 gap-2 text-xs">
            <StatusField label="Open" value={String(counts.open)} />
            <StatusField label="Conflicts" value={String(counts.conflicts)} />
            <StatusField label="Invalid" value={String(counts.invalid)} />
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">
            Loading candidate review states…
          </p>
        )}
        {counts?.issues.length ? (
          <ul className="space-y-1 rounded-md border border-warning/40 bg-warning/5 p-3 text-xs">
            {counts.issues.slice(0, 3).map((issue, index) => (
              <li key={`${issue.status}-${index}`} className="break-words">
                <span className="font-medium">
                  {statusLabel(issue.status)}:
                </span>{" "}
                {issue.issue ?? "No issue detail supplied."}
              </li>
            ))}
          </ul>
        ) : null}
        <Button asChild variant="outline" className="w-full">
          <Link href="/research?view=reviews">Open proposal review</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function countCandidates(candidates: CandidateState[] | undefined) {
  if (!candidates) return null;
  const conflicts = candidates.filter((candidate) =>
    ["CONFLICT", "STALE_BASELINE"].includes(candidate.status),
  );
  const invalid = candidates.filter(
    (candidate) => candidate.status === "INVALID",
  );
  const open = candidates.filter(
    (candidate) =>
      !["ACCEPTED", "REJECTED", "NO_CHANGES"].includes(candidate.status),
  );
  return {
    open: open.length,
    conflicts: conflicts.length,
    invalid: invalid.length,
    issues: [...conflicts, ...invalid],
  };
}

function AgentEventRow({ event }: { event: ResearchAgentWorkEvent }) {
  return (
    <li className="rounded-lg border p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{statusLabel(event.event_type)}</p>
          <p className="mt-1 break-words text-sm text-muted-foreground">
            {statusLabel(event.agent_role)} · {statusLabel(event.work_type)} ·{" "}
            {event.channel === "GOOGLE_SHEETS" ? "Google Sheets" : "API"}
          </p>
        </div>
        <StatusIndicator status={event.event_type} />
      </div>
      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <StatusField label="Recorded" value={dateTime(event.recorded_at)} />
        <StatusField label="Work key" value={event.work_key} />
        {event.proposal_domain && (
          <StatusField
            label="Proposal domain"
            value={statusLabel(event.proposal_domain)}
          />
        )}
        {event.blocker_code && (
          <StatusField
            label="Blocker"
            value={statusLabel(event.blocker_code)}
          />
        )}
      </dl>
      {event.reason && (
        <p className="mt-2 break-words text-sm">{event.reason}</p>
      )}
      {event.proposal_candidate_id && (
        <p className="mt-2 break-all text-xs text-muted-foreground">
          Candidate reference · {event.proposal_candidate_id}
        </p>
      )}
    </li>
  );
}

function InlineUnavailable({ message }: { message: string }) {
  return (
    <p
      role="status"
      className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs"
    >
      {message}
    </p>
  );
}

function StatusField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-medium">{value}</dd>
    </div>
  );
}
