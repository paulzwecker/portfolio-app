"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { JobStatus } from "@/components/app/job-status";
import { RefreshAction } from "@/components/app/refresh-action";
import { PageSection } from "@/components/app/page-section";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  isOperationalJobRequest,
  isOperationalJobRequestList,
  type OperationalJobName,
  type OperationalJobRequest,
} from "@/lib/domain-contracts";
import { dateTime, statusLabel } from "@/lib/display";

const refreshActions: { name: OperationalJobName; label: string }[] = [
  { name: "MARKET_AND_FX", label: "Market prices and FX" },
  { name: "SEC_FUNDAMENTALS", label: "SEC reported fundamentals" },
  { name: "SEC_FILINGS", label: "SEC filing metadata" },
  { name: "WORKBOOK_SYNC", label: "Stage portfolio workbook sync" },
  { name: "SHEETS_DISCOVERY", label: "Sheets proposals and acknowledgments" },
  { name: "RESEARCH_REFRESH", label: "Research triggers and queue" },
  {
    name: "DECISION_RECOMPUTE",
    label: "Recompute rankings and Execution Pace",
  },
];

const secJobs = ["SEC_FILINGS", "SEC_FUNDAMENTALS"] as const;

export async function requestUniverseRefresh(jobName: OperationalJobName) {
  const response = await fetch("/api/research/operations/job-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_name: jobName, scope_kind: "ACTIVE_UNIVERSE" }),
  });
  const data: unknown = await response.json();
  if (!response.ok || !isOperationalJobRequest(data)) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data
        ? String(data.detail)
        : "The refresh request could not be queued.";
    throw new Error(detail);
  }
  if (
    data.job_name !== jobName ||
    data.scope_kind !== "ACTIVE_UNIVERSE" ||
    data.company_id !== null
  )
    throw new Error("The refresh receipt did not match the requested scope.");
  return data;
}

/** Two existing durable requests; retain the first receipt if the second fails. */
export async function requestEligibleSecRefresh(
  record: (request: OperationalJobRequest) => void,
) {
  for (const name of secJobs) {
    try {
      record(await requestUniverseRefresh(name));
    } catch (failure) {
      const detail =
        failure instanceof Error ? failure.message : "Request unavailable.";
      throw new Error(
        name === "SEC_FILINGS"
          ? `SEC filings could not be confirmed; fundamentals were not requested. ${detail}`
          : `SEC fundamentals could not be confirmed. The filings receipt remains below. ${detail}`,
      );
    }
  }
}

export function hasCompletedRefresh(
  previousActive: ReadonlySet<string>,
  requests: OperationalJobRequest[],
) {
  return requests.some(
    (request) =>
      previousActive.has(request.id) &&
      !["QUEUED", "RUNNING"].includes(request.status),
  );
}

export function ManualRefreshPanel({
  workerEnabled = true,
  manualRunnerEnabled = false,
  workbookSyncEnabled = false,
  workbookSourceConfigured = false,
  workbookCredentialsAvailable = false,
}: {
  workerEnabled?: boolean;
  manualRunnerEnabled?: boolean;
  workbookSyncEnabled?: boolean;
  workbookSourceConfigured?: boolean;
  workbookCredentialsAvailable?: boolean;
}) {
  const [requests, setRequests] = useState<OperationalJobRequest[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [queueing, setQueueing] = useState<OperationalJobName | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [clockNow, setClockNow] = useState(0);
  const [queueingSec, setQueueingSec] = useState(false);
  const previousActive = useRef(new Set<string>());
  const loadSequence = useRef(0);

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    try {
      const response = await fetch(
        "/api/research/operations/job-requests?limit=30",
        {
          cache: "no-store",
        },
      );
      const data: unknown = await response.json();
      if (sequence !== loadSequence.current) return;
      if (!response.ok || !isOperationalJobRequestList(data))
        throw new Error("Manual job history is unavailable.");
      const completed = hasCompletedRefresh(previousActive.current, data);
      previousActive.current = new Set(
        data
          .filter((item) => ["QUEUED", "RUNNING"].includes(item.status))
          .map((item) => item.id),
      );
      setRequests(data);
      setLoadError(null);
      if (completed)
        window.dispatchEvent(new Event("portfolio:data-refreshed"));
    } catch (error) {
      if (sequence !== loadSequence.current) return;
      setLoadError(
        error instanceof Error
          ? error.message
          : "Manual job history is unavailable.",
      );
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (requests.length === 0) return;
    const initial = window.setTimeout(() => setClockNow(Date.now()), 0);
    const interval = window.setInterval(() => setClockNow(Date.now()), 15_000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
  }, [requests.length]);

  const active = requests.some(
    (request) => request.status === "QUEUED" || request.status === "RUNNING",
  );
  useEffect(() => {
    if (!active) return;
    let inFlight = false;
    const interval = window.setInterval(() => {
      if (inFlight) return;
      inFlight = true;
      void load().finally(() => {
        inFlight = false;
      });
    }, 3000);
    return () => window.clearInterval(interval);
  }, [active, load]);

  const cooldownByJob = useMemo(() => {
    const latest = new Map<OperationalJobName, OperationalJobRequest>();
    for (const request of requests) {
      if (!latest.has(request.job_name)) latest.set(request.job_name, request);
    }
    return latest;
  }, [requests]);

  const recordRequest = useCallback((data: OperationalJobRequest) => {
    loadSequence.current += 1;
    setRequests((previous) => [
      data,
      ...previous.filter((item) => item.id !== data.id),
    ]);
    if (["QUEUED", "RUNNING"].includes(data.status))
      previousActive.current.add(data.id);
    else window.dispatchEvent(new Event("portfolio:data-refreshed"));
    setClockNow(Date.now());
  }, []);

  const queueSec = async () => {
    setQueueingSec(true);
    setQueueError(null);
    setNotice(null);
    try {
      await requestEligibleSecRefresh(recordRequest);
      setNotice(
        "SEC filings and fundamentals requests are recorded below. Existing requests are reused during their active period or cooldown.",
      );
    } catch (failure) {
      setQueueError(
        failure instanceof Error ? failure.message : "SEC refresh unavailable.",
      );
    } finally {
      setQueueingSec(false);
      void load();
    }
  };

  const queue = async (jobName: OperationalJobName) => {
    setQueueing(jobName);
    setQueueError(null);
    setNotice(null);
    try {
      const data = await requestUniverseRefresh(jobName);
      recordRequest(data);
      setNotice(
        data.deduplicated
          ? "A matching request is already queued or within its cooldown; its status is shown below."
          : manualRunnerEnabled && !workerEnabled
            ? "Request queued for an explicitly invoked one-shot operator process."
            : "Refresh request queued for the background operations worker.",
      );
      await load();
    } catch (error) {
      setQueueError(
        error instanceof Error
          ? error.message
          : "The refresh request could not be queued.",
      );
    } finally {
      setQueueing(null);
    }
  };

  const retry = async (request: OperationalJobRequest) => {
    setQueueError(null);
    setNotice(null);
    try {
      const response = await fetch(
        `/api/research/operations/job-requests/${request.id}/retry`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        },
      );
      const data: unknown = await response.json();
      if (!response.ok || !isOperationalJobRequest(data))
        throw new Error("This request is not currently safe to retry.");
      setNotice("A retry was queued. The original attempt remains in history.");
      await load();
    } catch (error) {
      setQueueError(
        error instanceof Error ? error.message : "Retry could not be queued.",
      );
    }
  };

  const refreshAllRequest = cooldownByJob.get("REFRESH_ALL");
  const refreshAllRunning = Boolean(
    refreshAllRequest &&
    ["QUEUED", "RUNNING"].includes(refreshAllRequest.status),
  );
  const refreshAllCooling = Boolean(
    refreshAllRequest &&
    Date.parse(refreshAllRequest.cooldown_until) > clockNow,
  );
  const refreshAllDisabledReason = refreshAllRunning
    ? "Refresh All is already queued or running."
    : refreshAllCooling && refreshAllRequest
      ? `Available again after ${dateTime(refreshAllRequest.cooldown_until)}.`
      : undefined;

  return (
    <PageSection
      title="Manual refresh"
      description="Queue bounded, idempotent work in the existing operations pipeline. Requests are deduplicated during a cooldown and retain step-level outcomes."
      id="manual-refresh"
    >
      <div className="space-y-4">
        <Card className="border-primary/20 bg-primary/[0.025] shadow-none">
          <CardContent className="space-y-3 p-4">
            <div>
              <h3 className="font-medium">Refresh eligible SEC data</h3>
              <p className="mt-1 text-sm leading-5 text-muted-foreground">
                Update reported fundamentals and filing history for held and
                Watchlist companies with reviewed issuer mappings. Each domain
                is limited to 30 issuers; filings can retrieve up to 30 recent
                submissions and five historical files per attempt. Missing
                mappings and partial coverage remain visible in the results.
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Creates two durable requests: filings, then fundamentals.
                Provider transport retries keep their existing limits. No market
                prices, FX, analyst estimates, Sheets or investment decisions
                are included.
              </p>
            </div>
            <RefreshAction
              variant="default"
              onClick={() => void queueSec()}
              pending={queueingSec}
              disabled={
                !(workerEnabled || manualRunnerEnabled) || Boolean(queueing)
              }
              disabledReason={
                !(workerEnabled || manualRunnerEnabled)
                  ? "Manual operations are disabled in this environment."
                  : undefined
              }
            >
              Refresh eligible SEC data
            </RefreshAction>
          </CardContent>
        </Card>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {refreshActions.map((action) => {
            const recent = cooldownByJob.get(action.name);
            const cooling =
              recent && Date.parse(recent.cooldown_until) > clockNow;
            const running =
              recent && ["QUEUED", "RUNNING"].includes(recent.status);
            const disabledReason = !(workerEnabled || manualRunnerEnabled)
              ? "Manual operations are disabled in this environment."
              : action.name === "WORKBOOK_SYNC" && !workbookSyncEnabled
                ? "Workbook synchronization is disabled in this environment."
                : action.name === "WORKBOOK_SYNC" && !workbookSourceConfigured
                  ? "Configure the approved portfolio workbook ID and read-only Google service account."
                  : action.name === "WORKBOOK_SYNC" &&
                      !workbookCredentialsAvailable
                    ? "Configure the external read-only Google service-account file."
                    : running
                      ? "A matching refresh is already queued or running."
                      : cooling && recent
                        ? `Available again after ${dateTime(recent.cooldown_until)}.`
                        : undefined;
            return (
              <div key={action.name} className="min-w-0">
                <RefreshAction
                  onClick={() => void queue(action.name)}
                  pending={queueing === action.name}
                  disabled={Boolean(disabledReason) || queueingSec}
                  disabledReason={disabledReason}
                >
                  {action.label}
                </RefreshAction>
              </div>
            );
          })}
        </div>
        {!workerEnabled && !manualRunnerEnabled && (
          <p
            role="status"
            className="rounded-md border border-warning/40 p-3 text-sm"
          >
            Manual refresh is paused because both the recurring worker and the
            one-shot operator runner are disabled. Keep recurring work off
            unless a schedule is approved; an authorized operator can instead
            enable <code>MANUAL_OPERATIONS_ENABLED=true</code> and run one
            queued request with the documented one-shot command.
          </p>
        )}
        {!workerEnabled && manualRunnerEnabled && (
          <p role="status" className="rounded-md border p-3 text-sm">
            Requests are queued for an explicitly invoked one-shot operator
            runner. They are not processed on a schedule. Workbook sync only
            freezes and previews a source revision; applying workbook-owned
            state is a separate reviewed operation.
          </p>
        )}
        <Card className="border-primary/20 bg-primary/[0.025] shadow-none">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="font-medium">Refresh All · active universe</p>
              <p className="mt-1 text-sm leading-5 text-muted-foreground">
                Updates prices, FX, SEC facts and filings; checks proposal and
                acknowledgment inboxes; and refreshes research work. It does not
                synchronize portfolio workbook data, publish to Sheets, accept
                proposals, recalculate decisions, change holdings or targets, or
                execute trades.
              </p>
            </div>
            <RefreshAction
              variant="default"
              onClick={() => void queue("REFRESH_ALL")}
              pending={queueing === "REFRESH_ALL"}
              disabled={
                !(workerEnabled || manualRunnerEnabled) ||
                queueingSec ||
                refreshAllRunning ||
                refreshAllCooling
              }
              disabledReason={
                !(workerEnabled || manualRunnerEnabled)
                  ? "Manual operations are disabled in this environment."
                  : refreshAllDisabledReason
              }
            >
              Refresh All
            </RefreshAction>
          </CardContent>
        </Card>

        {notice && (
          <p role="status" className="rounded-md border p-3 text-sm">
            {notice}
          </p>
        )}
        {queueError && (
          <p
            role="alert"
            className="rounded-md border border-warning/40 p-3 text-sm"
          >
            {queueError}
          </p>
        )}
        {loadError && (
          <p
            role="status"
            className="rounded-md border border-warning/40 p-3 text-sm"
          >
            {loadError}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-medium">Recent requests</span>
            {active && (
              <StatusIndicator status="RUNNING" label="Worker processing" />
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={() => void load()}>
            Refresh job status
          </Button>
        </div>
        {requests.length ? (
          <ol className="grid gap-3 lg:grid-cols-2">
            {requests.slice(0, 8).map((request) => (
              <li key={request.id} className="min-w-0">
                <JobStatus
                  job={request}
                  manualRunnerEnabled={manualRunnerEnabled}
                />
                {request.retry_available &&
                  (workerEnabled || manualRunnerEnabled) && (
                    <div className="mt-2 flex justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void retry(request)}
                      >
                        Retry {statusLabel(request.job_name)}
                      </Button>
                    </div>
                  )}
              </li>
            ))}
          </ol>
        ) : !loadError ? (
          <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            No manual refresh requests have been recorded.
          </p>
        ) : null}
      </div>
    </PageSection>
  );
}
