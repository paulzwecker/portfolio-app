"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  { name: "SHEETS_DISCOVERY", label: "Sheets proposals and acknowledgments" },
  { name: "RESEARCH_REFRESH", label: "Research triggers and queue" },
  { name: "AGENT_WORK_FEED", label: "Publish agent work feed" },
];

export function ManualRefreshPanel({
  workerEnabled = true,
}: {
  workerEnabled?: boolean;
}) {
  const [requests, setRequests] = useState<OperationalJobRequest[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [queueing, setQueueing] = useState<OperationalJobName | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [clockNow, setClockNow] = useState(0);

  const load = useCallback(async () => {
    try {
      const response = await fetch(
        "/api/research/operations/job-requests?limit=30",
        {
          cache: "no-store",
        },
      );
      const data: unknown = await response.json();
      if (!response.ok || !isOperationalJobRequestList(data))
        throw new Error("Manual job history is unavailable.");
      setRequests(data);
      setLoadError(null);
    } catch (error) {
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
    const interval = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(interval);
  }, [active, load]);

  const cooldownByJob = useMemo(() => {
    const latest = new Map<OperationalJobName, OperationalJobRequest>();
    for (const request of requests) {
      if (!latest.has(request.job_name)) latest.set(request.job_name, request);
    }
    return latest;
  }, [requests]);

  const queue = async (jobName: OperationalJobName) => {
    setQueueing(jobName);
    setQueueError(null);
    setNotice(null);
    try {
      const response = await fetch("/api/research/operations/job-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_name: jobName,
          scope_kind: "ACTIVE_UNIVERSE",
        }),
      });
      const data: unknown = await response.json();
      if (!response.ok || !isOperationalJobRequest(data)) {
        const detail =
          typeof data === "object" && data !== null && "detail" in data
            ? String(data.detail)
            : "The refresh request could not be queued.";
        throw new Error(detail);
      }
      setNotice(
        data.deduplicated
          ? "A matching request is already queued or within its cooldown; its status is shown below."
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
      description="Queue bounded work in the existing background workers. Requests are deduplicated during a cooldown and retain step-level outcomes."
      id="manual-refresh"
    >
      <div className="space-y-4">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {refreshActions.map((action) => {
            const recent = cooldownByJob.get(action.name);
            const cooling =
              recent && Date.parse(recent.cooldown_until) > clockNow;
            const running =
              recent && ["QUEUED", "RUNNING"].includes(recent.status);
            const disabledReason = !workerEnabled
              ? "The background operations worker is disabled."
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
                  disabled={!workerEnabled || Boolean(cooling || running)}
                  disabledReason={disabledReason}
                >
                  {action.label}
                </RefreshAction>
              </div>
            );
          })}
        </div>
        {!workerEnabled && (
          <p
            role="status"
            className="rounded-md border border-warning/40 p-3 text-sm"
          >
            Manual refresh is paused because the background operations worker is
            disabled. Enable it with{" "}
            <code>RECURRING_OPERATIONS_ENABLED=true</code>
            and restart the worker.
          </p>
        )}
        <Card className="border-primary/20 bg-primary/[0.025] shadow-none">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="font-medium">Refresh All · active universe</p>
              <p className="mt-1 text-sm leading-5 text-muted-foreground">
                Updates prices, FX, SEC facts and filings; checks proposal and
                acknowledgment inboxes; refreshes research work; then publishes
                the current agent work feed to the configured workbook. It does
                not accept proposals, change models, holdings or targets,
                recompute decisions or execute trades.
              </p>
            </div>
            <RefreshAction
              variant="default"
              onClick={() => void queue("REFRESH_ALL")}
              pending={queueing === "REFRESH_ALL"}
              disabled={
                !workerEnabled || refreshAllRunning || refreshAllCooling
              }
              disabledReason={
                !workerEnabled
                  ? "The background operations worker is disabled."
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
                <JobStatus job={request} />
                {request.retry_available && (
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
