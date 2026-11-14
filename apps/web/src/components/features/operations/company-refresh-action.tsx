"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { JobStatus } from "@/components/app/job-status";
import { RefreshAction } from "@/components/app/refresh-action";
import { Button } from "@/components/ui/button";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyRefreshOptions,
  isOperationalJobRequest,
  isOperationalJobRequestList,
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

export function latestCooldown(deadlines: string[]) {
  const invalid = deadlines.some((item) => Number.isNaN(Date.parse(item)));
  const until = deadlines.reduce<string | undefined>(
    (latest, item) =>
      !latest || Date.parse(item) > Date.parse(latest) ? item : latest,
    undefined,
  );
  return { invalid, until };
}

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
  const [requests, setRequests] = useState<OperationalJobRequest[]>([]);
  const [recoveredIds, setRecoveredIds] = useState<string[]>([]);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<CompanyJob | null>(null);
  const [cooldowns, setCooldowns] = useState<
    Partial<Record<CompanyJob, string>>
  >({});
  const [clock, setClock] = useState(0);
  const loadSequence = useRef(0);
  const previousActive = useRef(new Set<string>());
  const recoveredReceipts = useRef(new Map<string, OperationalJobRequest>());
  const active =
    historyFor === companyId &&
    requests.some(
      (item) => item.status === "QUEUED" || item.status === "RUNNING",
    );

  const recordJob = useCallback((data: OperationalJobRequest) => {
    // Invalidate any history response started before this submission completed.
    loadSequence.current += 1;
    setRequests((previous) => [
      data,
      ...previous.filter((item) => item.id !== data.id),
    ]);
    setClock(Date.now());
    setCooldowns((previous) => ({
      ...previous,
      [data.job_name]: data.cooldown_until,
    }));
    if (["QUEUED", "RUNNING"].includes(data.status))
      previousActive.current.add(data.id);
    else window.dispatchEvent(new Event("portfolio:data-refreshed"));
  }, []);

  const loadHistory = useCallback(
    async (signal: AbortSignal) => {
      const sequence = ++loadSequence.current;
      const controller = new AbortController();
      const cancel = () => controller.abort();
      signal.addEventListener("abort", cancel, { once: true });
      let timedOut = false;
      const timer = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, 10_000);
      try {
        const response = await fetch(
          `/api/research/companies/${companyId}/job-requests`,
          { cache: "no-store", signal: controller.signal },
        );
        const data: unknown = await response.json();
        if (signal.aborted || sequence !== loadSequence.current) return;
        if (
          !response.ok ||
          !isOperationalJobRequestList(data) ||
          data.some(
            (item) =>
              item.company_id !== companyId || item.scope_kind !== "COMPANY",
          )
        )
          throw new Error("Company refresh history could not be verified.");
        // An older active job can fall beyond the bounded list as soon as it
        // completes. Resolve its exact identity and outcome before dropping it.
        const missing = [...previousActive.current].filter(
          (id) => !data.some((item) => item.id === id),
        );
        const recovered = await Promise.all(
          missing.map(async (id) => {
            const response = await fetch(
              `/api/research/operations/job-requests/${id}`,
              {
                cache: "no-store",
                signal: controller.signal,
              },
            );
            const item: unknown = await response.json();
            if (
              !response.ok ||
              !isOperationalJobRequest(item) ||
              item.id !== id ||
              item.company_id !== companyId ||
              item.scope_kind !== "COMPANY"
            )
              throw new Error("Company refresh history could not be verified.");
            return item;
          }),
        );
        if (signal.aborted || sequence !== loadSequence.current) return;
        for (const item of data) recoveredReceipts.current.delete(item.id);
        for (const item of recovered)
          recoveredReceipts.current.set(item.id, item);
        while (recoveredReceipts.current.size > 30) {
          const oldest = recoveredReceipts.current.keys().next().value;
          if (oldest === undefined) break;
          recoveredReceipts.current.delete(oldest);
        }
        const combined = [...recoveredReceipts.current.values(), ...data];
        const completed = combined.some(
          (item) =>
            previousActive.current.has(item.id) &&
            !["QUEUED", "RUNNING"].includes(item.status),
        );
        previousActive.current = new Set(
          combined
            .filter((item) => ["QUEUED", "RUNNING"].includes(item.status))
            .map((item) => item.id),
        );
        setRequests(combined);
        setRecoveredIds([...recoveredReceipts.current.keys()]);
        setHistoryFor(companyId);
        setHistoryError(null);
        setClock(Date.now());
        if (completed)
          window.dispatchEvent(new Event("portfolio:data-refreshed"));
      } catch (failure) {
        if (!signal.aborted && sequence === loadSequence.current) {
          setHistoryFor(null);
          setHistoryError(
            timedOut
              ? "Company refresh history timed out."
              : failure instanceof Error
                ? failure.message
                : "Company refresh history is unavailable.",
          );
        }
      } finally {
        window.clearTimeout(timer);
        signal.removeEventListener("abort", cancel);
      }
    },
    [companyId],
  );

  useEffect(() => {
    const controller = new AbortController();
    previousActive.current = new Set();
    recoveredReceipts.current.clear();
    const timer = window.setTimeout(
      () => void loadHistory(controller.signal),
      0,
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
      loadSequence.current += 1;
    };
  }, [loadHistory]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let inFlight = false;
    const interval = window.setInterval(() => {
      if (inFlight) return;
      inFlight = true;
      void loadHistory(controller.signal).finally(() => {
        inFlight = false;
      });
    }, 3000);
    return () => {
      window.clearInterval(interval);
      controller.abort();
    };
  }, [active, loadHistory]);

  useEffect(() => {
    if (Object.keys(cooldowns).length === 0 && requests.length === 0) return;
    const interval = window.setInterval(() => setClock(Date.now()), 15_000);
    return () => window.clearInterval(interval);
  }, [cooldowns, requests.length]);

  const request = async (jobName: CompanyJob) => {
    if (
      !verified?.eligible_job_names.includes(jobName) ||
      verified.execution_mode === "DISABLED" ||
      historyFor !== companyId
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
          const deadlines = [
            cooldowns[name],
            ...requests
              .filter((item) => item.job_name === name)
              .map((item) => item.cooldown_until),
          ].filter((item): item is string => typeof item === "string");
          const { invalid: invalidDeadline, until } = latestCooldown(deadlines);
          const cooling =
            invalidDeadline || Boolean(until && Date.parse(until) > clock);
          return (
            <RefreshAction
              key={name}
              onClick={() => void request(name)}
              pending={submitting === name}
              disabled={Boolean(
                unavailable ||
                historyFor !== companyId ||
                active ||
                submitting ||
                cooling ||
                !verified?.eligible_job_names.includes(name),
              )}
              disabledReason={
                invalidDeadline
                  ? "Refresh cooldown could not be verified."
                  : cooling && until
                    ? `Available after ${dateTime(until)}`
                    : undefined
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
        {historyFor !== companyId &&
          !historyError &&
          " Checking refresh history…"}
      </p>
      {options.error && (
        <Button size="sm" variant="ghost" onClick={options.retry}>
          Retry refresh eligibility
        </Button>
      )}
      {historyFor === companyId && requests.length > 0 && (
        <div className="w-full max-w-md space-y-2">
          {requests
            .filter(
              (item, index) =>
                ["QUEUED", "RUNNING"].includes(item.status) ||
                recoveredIds.includes(item.id) ||
                index ===
                  requests.findIndex(
                    (candidate) =>
                      !["QUEUED", "RUNNING"].includes(candidate.status) &&
                      !recoveredIds.includes(candidate.id),
                  ),
            )
            .map((item) => (
              <JobStatus
                key={item.id}
                job={item}
                compact
                manualRunnerEnabled={verified?.execution_mode === "OPERATOR"}
              />
            ))}
        </div>
      )}
      {historyError && (
        <div className="max-w-md text-xs text-warning" role="alert">
          <p>
            {historyError} Refresh actions are unavailable until it can be
            checked.
          </p>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void loadHistory(new AbortController().signal)}
          >
            Retry refresh history
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="max-w-md break-words text-xs text-warning">
          {error}
        </p>
      )}
    </div>
  );
}
