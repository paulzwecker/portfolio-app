"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { JobStatus } from "@/components/app/job-status";
import { RefreshAction } from "@/components/app/refresh-action";
import {
  isOperationalJobRequest,
  type OperationalJobRequest,
} from "@/lib/domain-contracts";

export function CompanyRefreshAction({ companyId }: { companyId: string }) {
  const [job, setJob] = useState<OperationalJobRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const completedId = useRef<string | null>(null);
  const active = job?.status === "QUEUED" || job?.status === "RUNNING";
  const requestId = job?.id;

  const refreshStatus = useCallback(async (requestId: string) => {
    try {
      const response = await fetch(
        `/api/research/operations/job-requests/${requestId}`,
        { cache: "no-store" },
      );
      const data: unknown = await response.json();
      if (!response.ok || !isOperationalJobRequest(data))
        throw new Error("Refresh status is unavailable.");
      setJob(data);
      setError(null);
      if (
        ["SUCCEEDED", "PARTIAL"].includes(data.status) &&
        completedId.current !== data.id
      ) {
        completedId.current = data.id;
        window.dispatchEvent(new Event("portfolio:data-refreshed"));
      }
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Refresh status is unavailable.",
      );
    }
  }, []);

  useEffect(() => {
    if (!requestId || !active) return;
    const interval = window.setInterval(
      () => void refreshStatus(requestId),
      3000,
    );
    return () => window.clearInterval(interval);
  }, [active, requestId, refreshStatus]);

  const request = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/research/operations/job-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_name: "COMPANY_REFRESH",
          scope_kind: "COMPANY",
          company_id: companyId,
        }),
      });
      const data: unknown = await response.json();
      if (!response.ok || !isOperationalJobRequest(data))
        throw new Error(
          typeof data === "object" && data !== null && "detail" in data
            ? String(data.detail)
            : "Company refresh could not be queued.",
        );
      completedId.current = null;
      setJob(data);
      if (["SUCCEEDED", "PARTIAL"].includes(data.status))
        await refreshStatus(data.id);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Company refresh could not be queued.",
      );
    } finally {
      setSubmitting(false);
    }
  }, [companyId, refreshStatus]);

  return (
    <div className="flex min-w-0 flex-col items-start gap-2 sm:items-end">
      <RefreshAction
        onClick={() => void request()}
        pending={submitting}
        disabled={Boolean(active || submitting)}
      >
        Refresh this company
      </RefreshAction>
      {job && <JobStatus job={job} compact />}
      {error && (
        <p role="alert" className="max-w-md break-words text-xs text-warning">
          {error}
        </p>
      )}
    </div>
  );
}
