"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { JobStatus } from "@/components/app/job-status";
import { RefreshAction } from "@/components/app/refresh-action";
import { Button } from "@/components/ui/button";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyRefreshOptions,
  isOperationalJobRequest,
  type CompanyRefreshOptions,
  type OperationalJobRequest,
} from "@/lib/domain-contracts";
import { dateTime } from "@/lib/display";

type CompanyJob = CompanyRefreshOptions["eligible_job_names"][number];
const labels: Record<CompanyJob, string> = {
  COMPANY_REFRESH: "Refresh this company",
  SEC_FUNDAMENTALS: "Refresh SEC fundamentals",
  SEC_FILINGS: "Refresh SEC filings",
};

export function CompanyRefreshAction({
  companyId,
  secOnly = false,
}: {
  companyId: string;
  secOnly?: boolean;
}) {
  const options = useResearch(
    `companies/${companyId}/refresh-options`,
    isCompanyRefreshOptions,
  );
  const descriptionId = useId();
  const verified =
    options.data?.company_id === companyId ? options.data : undefined;
  const [job, setJob] = useState<OperationalJobRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<CompanyJob | null>(null);
  const [cooldowns, setCooldowns] = useState<
    Partial<Record<CompanyJob, string>>
  >({});
  const [clock, setClock] = useState(0);
  const completedId = useRef<string | null>(null);
  const active = job?.status === "QUEUED" || job?.status === "RUNNING";
  const requestId = job?.id;

  const recordJob = useCallback((data: OperationalJobRequest) => {
    setJob(data);
    setClock(Date.now());
    setCooldowns((previous) => ({
      ...previous,
      [data.job_name]: data.cooldown_until,
    }));
    if (
      !["QUEUED", "RUNNING"].includes(data.status) &&
      completedId.current !== data.id
    ) {
      completedId.current = data.id;
      window.dispatchEvent(new Event("portfolio:data-refreshed"));
    }
  }, []);

  const jobName = job?.job_name;
  useEffect(() => {
    if (!requestId || !active || !jobName) return;
    const controller = new AbortController();
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch(
          `/api/research/operations/job-requests/${requestId}`,
          { cache: "no-store", signal: controller.signal },
        );
        const data: unknown = await response.json();
        if (controller.signal.aborted) return;
        if (
          !response.ok ||
          !isOperationalJobRequest(data) ||
          data.id !== requestId ||
          data.company_id !== companyId ||
          data.scope_kind !== "COMPANY" ||
          data.job_name !== jobName
        )
          throw new Error("Refresh status is unavailable.");
        recordJob(data);
        setError(null);
      } catch (failure) {
        if (!controller.signal.aborted)
          setError(
            failure instanceof Error
              ? failure.message
              : "Refresh status is unavailable.",
          );
      } finally {
        inFlight = false;
      }
    };
    const interval = window.setInterval(() => void poll(), 3000);
    return () => {
      window.clearInterval(interval);
      controller.abort();
    };
  }, [active, requestId, jobName, companyId, recordJob]);

  useEffect(() => {
    if (Object.keys(cooldowns).length === 0) return;
    const interval = window.setInterval(() => setClock(Date.now()), 15_000);
    return () => window.clearInterval(interval);
  }, [cooldowns]);

  const request = async (jobName: CompanyJob) => {
    if (
      !verified?.eligible_job_names.includes(jobName) ||
      verified.execution_mode === "DISABLED"
    )
      return;
    setSubmitting(jobName);
    setError(null);
    try {
      const response = await fetch("/api/research/operations/job-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_name: jobName,
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
      if (
        data.company_id !== companyId ||
        data.scope_kind !== "COMPANY" ||
        data.job_name !== jobName
      )
        throw new Error(
          "The refresh response did not match this company and operation.",
        );
      recordJob(data);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Company refresh could not be queued.",
      );
    } finally {
      setSubmitting(null);
    }
  };

  const jobs: CompanyJob[] =
    !secOnly && verified?.eligible_job_names.includes("COMPANY_REFRESH")
      ? ["COMPANY_REFRESH"]
      : ["SEC_FUNDAMENTALS", "SEC_FILINGS"];
  const unavailable = !verified
    ? "Refresh eligibility is unavailable."
    : verified.execution_mode === "DISABLED"
      ? "Manual and recurring operations are disabled."
      : verified.sec_unavailable_reason;

  return (
    <div
      role="group"
      aria-label="Company refresh requests"
      aria-describedby={descriptionId}
      className="flex min-w-0 flex-col items-start gap-2 sm:items-end"
    >
      <div className="flex max-w-full flex-wrap gap-2">
        {jobs.map((name) => {
          const until = cooldowns[name];
          const cooling = until && new Date(until).getTime() > clock;
          return (
            <RefreshAction
              key={name}
              onClick={() => void request(name)}
              pending={submitting === name}
              disabled={Boolean(
                unavailable ||
                active ||
                submitting ||
                cooling ||
                !verified?.eligible_job_names.includes(name),
              )}
              disabledReason={
                cooling ? `Available after ${dateTime(until)}` : undefined
              }
            >
              {labels[name]}
            </RefreshAction>
          );
        })}
      </div>
      <p
        id={descriptionId}
        className="max-w-md text-xs text-muted-foreground"
        role="status"
      >
        {options.error ??
          (unavailable ||
            (verified?.execution_mode === "OPERATOR"
              ? "Requests wait for an operator-run one-shot process."
              : "Requests run through the recurring operations worker."))}
        {verified?.sec_eligibility_basis === "VERIFIED_HOLDING" &&
          " SEC eligibility comes from verified holdings."}
      </p>
      {options.error && (
        <Button size="sm" variant="ghost" onClick={options.retry}>
          Retry refresh eligibility
        </Button>
      )}
      {job && (
        <JobStatus
          job={job}
          compact
          manualRunnerEnabled={verified?.execution_mode === "OPERATOR"}
        />
      )}
      {error && (
        <p role="alert" className="max-w-md break-words text-xs text-warning">
          {error}
        </p>
      )}
    </div>
  );
}
