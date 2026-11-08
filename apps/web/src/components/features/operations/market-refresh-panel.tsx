"use client";

import { useEffect, useRef, useState } from "react";
import { DetailDrawer } from "@/components/app/detail-drawer";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  MarketRefreshRun,
  MarketRefreshStatus,
} from "@/lib/domain-contracts";
import { dateTime } from "@/lib/display";

const domainLabels: Record<MarketRefreshRun["domain"], string> = {
  MARKET_DATA: "Prices",
  FX: "FX",
  CORPORATE_ACTIONS: "Corporate actions",
};
const retryLabels: Record<MarketRefreshRun["retry_state"], string> = {
  RUNNING: "An attempt is running.",
  COOLDOWN: "Waiting for the retry cooldown.",
  ELIGIBLE: "Eligible for the next authorized cloud cycle.",
  EXHAUSTED: "Attempt limit reached. Operator review required.",
  REVIEW_REQUIRED: "A fresh scope check or operator review is required.",
  NONE: "No retry is pending.",
};

export function ProviderQualityWarnings({
  report,
}: {
  report: MarketRefreshRun["report"];
}) {
  const domain = report.domain_report;
  if (!domain || typeof domain !== "object" || Array.isArray(domain))
    return null;
  const warnings = (domain as Record<string, unknown>).normalization_warnings;
  if (!Array.isArray(warnings) || warnings.length === 0) return null;
  const descriptions: Record<string, string> = {
    PRICE_ROWS_WITHOUT_CLOSE:
      "Some returned price rows lacked a usable timestamp or positive close and were excluded.",
    FX_ROWS_WITHOUT_CLOSE:
      "Some returned FX rows lacked a usable timestamp or positive close and were excluded.",
    DUPLICATE_SESSION_BARS_COLLAPSED:
      "Duplicate price bars were collapsed; volume may be unavailable.",
  };
  return (
    <section
      aria-label="Provider quality warnings"
      className="space-y-2 rounded-md border border-warning/35 bg-warning/10 p-3 text-sm"
    >
      <h3 className="font-semibold">Provider quality warnings</h3>
      <p>
        Review the recorded diagnostics. These warnings do not establish
        expected-session coverage.
      </p>
      <ul className="list-inside list-disc space-y-1">
        {warnings.map((warning, index) => {
          const item =
            warning && typeof warning === "object" && !Array.isArray(warning)
              ? (warning as Record<string, unknown>)
              : {};
          const code = typeof item.code === "string" ? item.code : "";
          return (
            <li key={index}>
              {descriptions[code] ??
                "A provider normalization warning requires review."}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function MarketRefreshPanel({
  status,
}: {
  status: MarketRefreshStatus;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const runs = status.runs ?? [];
  const selected = runs.find((run) => run.run_id === selectedId);
  useEffect(() => {
    if (window.location.hash === "#market-data-refresh") {
      panelRef.current?.focus({ preventScroll: true });
      panelRef.current?.scrollIntoView({ block: "start" });
    }
  }, []);
  return (
    <Card
      ref={panelRef}
      id="market-data-refresh"
      role="region"
      aria-labelledby="market-data-refresh-heading"
      tabIndex={-1}
      className="min-w-0 scroll-mt-6 shadow-none"
    >
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <CardTitle id="market-data-refresh-heading" className="text-base">
          Market data refresh
        </CardTitle>
        <StatusIndicator status={status.state} />
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">
              Latest price or FX success
            </dt>
            <dd className="mt-1">
              {status.last_successful_update
                ? dateTime(status.last_successful_update)
                : "No successful update recorded"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              Last check or attempt
            </dt>
            <dd className="mt-1">
              {status.last_attempt_at
                ? dateTime(status.last_attempt_at)
                : "No attempt recorded"}
            </dd>
          </div>
        </dl>
        {status.message && (
          <p className="break-words rounded-md border border-warning/35 bg-warning/10 p-3 text-sm">
            {status.message}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          Prices and FX determine the refresh summary. Corporate-action evidence
          has its own quality state. Retry eligibility requires an authorized
          worker cycle.
        </p>
        {runs.length === 0 ? (
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>Detailed refresh runs are unavailable.</p>
            <p className="break-all text-xs">
              Market run · {status.market_run_id ?? "Not recorded"}
            </p>
            <p className="break-all text-xs">
              FX run · {status.fx_run_id ?? "Not recorded"}
            </p>
          </div>
        ) : (
          <ul aria-label="Market refresh runs" className="space-y-3">
            {runs.map((run) => (
              <li
                key={run.run_id}
                className="min-w-0 space-y-2 rounded-md border p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium">
                    {domainLabels[run.domain]}
                  </span>
                  <StatusIndicator status={run.status} />
                </div>
                <p className="text-xs text-muted-foreground">
                  {run.request_scope.scope === "cloud_market_preflight"
                    ? "Scope check"
                    : `Attempts ${run.attempt_count} of ${run.max_attempts}`}
                  {" · "}
                  {retryLabels[run.retry_state]}
                </p>
                {run.retry_eligible_at && (
                  <p className="text-xs text-muted-foreground">
                    Eligible after {dateTime(run.retry_eligible_at)}
                  </p>
                )}
                {run.failure_code && (
                  <p className="break-words text-xs">{run.failure_code}</p>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedId(run.run_id)}
                >
                  Inspect {domainLabels[run.domain]} refresh
                </Button>
              </li>
            ))}
          </ul>
        )}
        <DetailDrawer
          open={Boolean(selected)}
          onOpenChange={(open) => {
            if (!open) setSelectedId(null);
          }}
          title={
            selected
              ? `${domainLabels[selected.domain]} refresh details`
              : "Refresh details"
          }
          description="Recorded scope, attempt outcomes and diagnostics. This view performs read-only inspection."
        >
          {selected && (
            <div className="min-w-0 space-y-5 text-sm">
              <StatusIndicator status={selected.status} />
              <p className="break-all font-mono text-xs">
                Run {selected.run_id}
              </p>
              <p>{retryLabels[selected.retry_state]}</p>
              <dl className="space-y-1 text-xs">
                <dt className="text-muted-foreground">
                  Last recorded success for this domain
                </dt>
                <dd>
                  {selected.last_successful_at
                    ? dateTime(selected.last_successful_at)
                    : "No successful update recorded"}
                </dd>
              </dl>
              {selected.failure_message && (
                <p className="break-words">{selected.failure_message}</p>
              )}
              <ProviderQualityWarnings report={selected.report} />
              <section aria-label="Recorded attempts" className="space-y-2">
                <h3 className="font-semibold">Attempt history</h3>
                {selected.attempts.length === 0 && (
                  <p>No completed attempt is recorded.</p>
                )}
                {selected.attempts.map((attempt) => (
                  <div
                    key={attempt.attempt_number}
                    className="space-y-1 rounded-md border p-3"
                  >
                    <p className="flex flex-wrap items-center justify-between gap-2">
                      <span>Attempt {attempt.attempt_number}</span>
                      <StatusIndicator status={attempt.status} />
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {dateTime(attempt.started_at)} →{" "}
                      {dateTime(attempt.finished_at)}
                    </p>
                    {(attempt.failure_message || attempt.failure_code) && (
                      <p className="break-words text-xs">
                        {attempt.failure_message ?? attempt.failure_code}
                      </p>
                    )}
                  </div>
                ))}
              </section>
              <section className="space-y-2">
                <h3 className="font-semibold">Frozen request scope</h3>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">
                  {JSON.stringify(selected.request_scope, null, 2)}
                </pre>
              </section>
              <section className="space-y-2">
                <h3 className="font-semibold">Recorded diagnostic report</h3>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">
                  {JSON.stringify(selected.report, null, 2)}
                </pre>
              </section>
            </div>
          )}
        </DetailDrawer>
      </CardContent>
    </Card>
  );
}
