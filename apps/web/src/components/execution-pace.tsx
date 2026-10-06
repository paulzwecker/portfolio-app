"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError, useResearch } from "@/components/research-frame";
import {
  isCompanyExecutionPace,
  isExecutionPaceRun,
  type CompanyExecutionPace,
  type ExecutionPaceHistoryEntry,
} from "@/lib/domain-contracts";
import { date, percent, quantity } from "@/lib/display";

export function executionPaceLabel(value: string | null | undefined) {
  if (!value) return "Unavailable";
  const paceLabels: Record<string, string> = {
    SMALL_LADDER: "SMALL / LADDER",
    SLOW_LIMIT: "SLOW / LIMIT",
    WAIT_LIMIT: "WAIT / LIMIT",
  };
  return paceLabels[value] ?? value.replaceAll("_", " ");
}

function percentValue(value: string | null, missing = "Unavailable") {
  return value === null ? missing : percent(value);
}

function tone(status: string | undefined) {
  return status === "AVAILABLE" ? "default" : "secondary";
}

export function ExecutionPaceCompact({
  entry,
}: {
  entry: ExecutionPaceHistoryEntry | null | undefined;
}) {
  if (!entry) {
    return (
      <div className="mt-2 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        No Execution Pace run recorded. This is unavailable, not a neutral
        signal.
      </div>
    );
  }
  const { run, decision } = entry;
  const inputs = decision.input_snapshot;
  return (
    <div className="mt-2 rounded-md border bg-secondary/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge variant={tone(decision.decision_status)}>
          {decision.pace
            ? executionPaceLabel(decision.pace)
            : executionPaceLabel(decision.decision_status)}
        </Badge>
        <span className="text-[10px] text-muted-foreground">
          As of {date(run.as_of)}
        </span>
      </div>
      <p className="mt-2 text-xs leading-5">{decision.reason}</p>
      <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
        Recorded {date(run.recorded_at)} by {run.actor}. {run.reason}
      </p>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-[10px] sm:grid-cols-3 xl:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Current → target</dt>
          <dd className="mt-0.5 font-medium tabular-nums">
            {percentValue(inputs.current_weight)} →{" "}
            {percentValue(inputs.target_weight, "No target")}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Expected IRR / hurdle</dt>
          <dd className="mt-0.5 font-medium tabular-nums">
            {percentValue(inputs.expected_irr)} / {percentValue(inputs.hurdle)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Valuation / upside</dt>
          <dd className="mt-0.5 font-medium">
            {executionPaceLabel(inputs.valuation_zone)} /{" "}
            {percentValue(inputs.weighted_upside)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Exact-listing quote</dt>
          <dd className="mt-0.5 font-medium">
            {quantity(inputs.price)} {inputs.price_currency ?? ""} |{" "}
            {executionPaceLabel(inputs.price_freshness)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Price regime</dt>
          <dd className="mt-0.5 font-medium">
            {executionPaceLabel(inputs.price_regime)} |{" "}
            {executionPaceLabel(inputs.price_regime_freshness)} |{" "}
            {executionPaceLabel(inputs.price_regime_quality)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Estimate Momentum</dt>
          <dd className="mt-0.5 font-medium">
            {inputs.estimate_momentum_direction
              ? executionPaceLabel(inputs.estimate_momentum_direction)
              : executionPaceLabel(inputs.estimate_momentum_availability)}{" "}
            | {executionPaceLabel(inputs.estimate_momentum_freshness)} |{" "}
            {executionPaceLabel(inputs.estimate_momentum_quality)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Model output / allocation</dt>
          <dd className="mt-0.5 font-medium">
            {executionPaceLabel(inputs.model_output_quality)} |{" "}
            {executionPaceLabel(inputs.allocation_status)}
          </dd>
        </div>
      </dl>
      <details className="mt-3 border-t pt-2">
        <summary className="cursor-pointer text-[10px] font-medium">
          Input provenance and data-quality notes
        </summary>
        <dl className="mt-2 grid gap-2 text-[10px] sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Model source</dt>
            <dd className="mt-0.5 break-all">
              {inputs.model_key ?? "No model"} |{" "}
              {executionPaceLabel(inputs.model_source_kind)} |{" "}
              {inputs.model_currency ?? "Currency unknown"}
            </dd>
            <dd className="mt-0.5 break-all text-muted-foreground">
              Revision {decision.model_revision_id ?? "unavailable"} | source{" "}
              {inputs.model_source_id ?? "unavailable"} | effective{" "}
              {inputs.model_effective_at
                ? date(inputs.model_effective_at)
                : "unknown"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Market and regime source</dt>
            <dd className="mt-0.5 break-all">
              {inputs.valuation_ticker ?? "Listing unknown"}{" "}
              {inputs.valuation_venue ?? ""} |{" "}
              {inputs.price_provider ?? "Provider unknown"}
            </dd>
            <dd className="mt-0.5 break-all text-muted-foreground">
              Price observation {decision.price_observation_id ?? "unavailable"}{" "}
              | date{" "}
              {inputs.price_market_date
                ? date(inputs.price_market_date)
                : "unknown"}{" "}
              | regime ref {inputs.price_regime_source_ref ?? "unavailable"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Estimate source</dt>
            <dd className="mt-0.5 break-all">
              {inputs.estimate_provider_id ?? "No selected provider"} | latest{" "}
              {inputs.estimate_latest_snapshot_date ?? "unknown"}
            </dd>
            {inputs.estimate_momentum_reason && (
              <dd className="mt-0.5 text-muted-foreground">
                {inputs.estimate_momentum_reason}
              </dd>
            )}
          </div>
          <div>
            <dt className="text-muted-foreground">Allocation source IDs</dt>
            <dd className="mt-0.5 break-all">
              Target {decision.target_revision_id ?? "unavailable"} | holdings{" "}
              {decision.holding_snapshot_id ?? "unavailable"}
            </dd>
          </div>
        </dl>
        {inputs.context_notes.length > 0 && (
          <ul className="mt-2 list-disc space-y-1 pl-4 text-[10px] text-muted-foreground">
            {inputs.context_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}

export function ExecutionPacePanel({ companyId }: { companyId: string }) {
  const state = useResearch<CompanyExecutionPace>(
    `companies/${encodeURIComponent(companyId)}/execution-pace`,
    isCompanyExecutionPace,
  );
  const [reason, setReason] = useState("Periodic portfolio execution review.");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function recordRun() {
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/research/execution-pace-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor: "LOCAL_USER",
          reason: reason.trim(),
          source: "web-company-explorer",
        }),
      });
      const result: unknown = await response.json();
      if (!response.ok || !isExecutionPaceRun(result)) {
        throw new Error(
          "Execution Pace could not be recorded. Check the current portfolio and input coverage, then retry.",
        );
      }
      state.retry();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Execution Pace could not be recorded.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <section
      id="execution-pace"
      aria-labelledby="execution-pace-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="execution-pace-title" className="text-xl font-semibold">
          Execution Pace
        </h2>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
          How quickly to move toward the accepted target given current
          valuation, expected return, estimate revisions and price context. This
          is a portfolio timing decision, separate from the 1–5 business
          Execution score. It never changes targets, holdings, lifecycle or
          model state.
        </p>
      </div>
      {!state.data ? (
        <PendingOrError error={state.error} retry={state.retry} />
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,1fr)]">
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-sm">Latest decision</CardTitle>
                {state.data.current && (
                  <Badge
                    variant={tone(state.data.current.decision.decision_status)}
                  >
                    {executionPaceLabel(
                      state.data.current.decision.pace ??
                        state.data.current.decision.decision_status,
                    )}
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {state.data.current ? (
                <ExecutionPaceCompact entry={state.data.current} />
              ) : (
                <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                  No decision has been recorded. Missing history is not a
                  neutral pace.
                </p>
              )}
              <details className="mt-4 border-t pt-3">
                <summary className="cursor-pointer text-xs font-medium">
                  Decision history ({state.data.history.length})
                </summary>
                {state.data.history.length === 0 ? (
                  <p className="mt-3 text-xs text-muted-foreground">
                    No historical decisions are available.
                  </p>
                ) : (
                  <ol className="mt-3 space-y-3">
                    {state.data.history.map((entry) => (
                      <li key={entry.decision.id}>
                        <ExecutionPaceCompact entry={entry} />
                      </li>
                    ))}
                  </ol>
                )}
              </details>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Record a new run</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs leading-5 text-muted-foreground">
                Records an immutable portfolio-wide snapshot. Every decision
                keeps the exact source IDs and input values used at that time.
              </p>
              <label className="mt-4 block text-xs font-medium">
                Review rationale
                <textarea
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  maxLength={1000}
                  rows={3}
                  className="mt-2 block min-h-20 w-full rounded-md border bg-background px-3 py-2 text-sm"
                />
              </label>
              <Button
                type="button"
                onClick={recordRun}
                disabled={pending || !reason.trim()}
                className="mt-3 w-full sm:w-auto"
              >
                {pending ? "Recording snapshot…" : "Record Execution Pace"}
              </Button>
              {error && (
                <p role="alert" className="mt-3 text-xs text-destructive">
                  {error}
                </p>
              )}
              {state.data.current && (
                <p className="mt-3 text-[10px] text-muted-foreground">
                  Latest run recorded {date(state.data.current.run.recorded_at)}
                  . Expected IRR{" "}
                  {quantity(
                    state.data.current.decision.input_snapshot.expected_irr,
                  )}
                  ; regime{" "}
                  {executionPaceLabel(
                    state.data.current.decision.input_snapshot.price_regime,
                  )}
                  .
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </section>
  );
}
