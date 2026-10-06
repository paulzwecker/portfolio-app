"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError, useResearch } from "@/components/research-frame";
import {
  isCompanyEstimateMomentum,
  type CompanyEstimateMomentum,
  type EstimateMomentumPeriod,
} from "@/lib/domain-contracts";
import { date, percent, quantity } from "@/lib/display";

function day(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
}

function MomentumPeriod({ period }: { period: EstimateMomentumPeriod }) {
  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="text-sm">
            {period.metric === "REVENUE" ? "Revenue" : "EPS"} · {period.horizon}
          </CardTitle>
          <Badge variant="outline">FY end {day(period.period_end)}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Current estimate
          </p>
          <p className="mt-1 break-words text-lg font-semibold tabular-nums">
            {period.current_value === null
              ? "Unavailable"
              : `${period.currency ?? "Currency unknown"} ${quantity(period.current_value)}`}
          </p>
          <p className="text-[10px] text-muted-foreground">
            {period.current_snapshot_date
              ? `Snapshot ${day(period.current_snapshot_date)}`
              : "No current snapshot"}
            {period.metric === "EPS" ? " · per share" : ` · ${period.unit}`}
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            Analyst coverage: {period.analyst_count ?? "Not reported"}
          </p>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {period.windows.map((window) => (
            <div
              key={window.window}
              className="min-w-0 rounded-md bg-secondary/40 p-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold">{window.window}</span>
                <Badge
                  variant={
                    window.status === "AVAILABLE" ? "outline" : "secondary"
                  }
                  className="text-[9px]"
                >
                  {window.status.replaceAll("_", " ")}
                </Badge>
              </div>
              <p className="mt-2 text-sm font-semibold tabular-nums">
                {window.revision_fraction === null
                  ? "No comparison"
                  : percent(window.revision_fraction)}
              </p>
              <p className="text-[10px] leading-4 text-muted-foreground">
                {window.reference_snapshot_date
                  ? `vs ${day(window.reference_snapshot_date)}`
                  : "No same-source reference"}
                {window.component_score !== null &&
                  ` · component ${quantity(window.component_score)}`}
              </p>
              {window.reason && (
                <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
                  {window.reason}
                </p>
              )}
            </div>
          ))}
        </div>
        {period.quality_reason && (
          <p className="rounded-md border border-dashed p-2 text-xs leading-5 text-muted-foreground">
            {period.quality_reason}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function MomentumContent({ data }: { data: CompanyEstimateMomentum }) {
  const scoreLabel =
    data.confidence_adjusted_score === null
      ? "Unavailable"
      : quantity(data.confidence_adjusted_score);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={data.availability === "AVAILABLE" ? "default" : "secondary"}
        >
          {data.availability.replaceAll("_", " ")}
        </Badge>
        <Badge variant="outline">
          {data.direction?.replaceAll("_", " ") ?? "No direction"}
        </Badge>
        <Badge variant={data.freshness === "FRESH" ? "outline" : "secondary"}>
          {data.freshness.replaceAll("_", " ")}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {data.provider_id ?? "No source selected"}
          {data.latest_snapshot_date
            ? ` · latest ${day(data.latest_snapshot_date)}`
            : ""}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border p-3">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Confidence-adjusted signal
          </p>
          <p className="mt-1 text-xl font-semibold tabular-nums">
            {scoreLabel}
          </p>
          <p className="text-xs text-muted-foreground">
            Raw direction score{" "}
            {data.raw_score === null ? "unavailable" : quantity(data.raw_score)}
          </p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Estimate-history coverage
          </p>
          <p className="mt-1 text-xl font-semibold tabular-nums">
            {data.coverage_count} / {data.coverage_total}
          </p>
          <p className="text-xs text-muted-foreground">
            Confidence {percent(data.confidence)} · {data.confidence_band}
          </p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Data quality
          </p>
          <p className="mt-1 text-sm font-semibold">
            {data.data_quality.replaceAll("_", " ")}
          </p>
          <p className="text-xs text-muted-foreground">
            As of {day(data.as_of)}
            {data.known_at
              ? ` · known ${date(data.known_at)}`
              : " · latest recorded"}
          </p>
        </div>
      </div>

      {data.reason && (
        <p className="rounded-lg border border-dashed p-3 text-sm leading-5 text-muted-foreground">
          {data.reason}
        </p>
      )}

      {data.periods.length > 0 ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {data.periods.map((period) => (
            <MomentumPeriod
              key={`${period.metric}:${period.period_end}`}
              period={period}
            />
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          No usable forward annual Revenue/EPS estimate periods are available.
          Missing history is not assigned a neutral signal.
        </p>
      )}

      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-xs font-medium">
          Method and limitations · {data.methodology_version}
        </summary>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          The legacy signal combines Revenue/EPS at 70/30 and FY+1/FY+2 at
          60/40. Known 12M, 6M and 3M revision components use the legacy
          30/20/15 weights and 5% scaling, renormalized over available
          comparisons. Confidence is derived from coverage across 20 possible
          components. Legacy persistence and analyst up/down breadth are not
          calculated because the stored consensus snapshots do not contain those
          inputs. This signal is separate from price momentum, business
          Execution, valuation and scenario probabilities; it does not set
          Execution Pace.
        </p>
      </details>
    </div>
  );
}

export function EstimateMomentum({ companyId }: { companyId: string }) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/estimate-momentum`,
    isCompanyEstimateMomentum,
  );
  return (
    <section
      id="estimate-momentum"
      aria-labelledby="estimate-momentum-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="estimate-momentum-title" className="text-xl font-semibold">
          Estimate Momentum
        </h2>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
          Point-in-time Revenue and EPS revisions from the selected consensus
          provider. Direction, history coverage, confidence and freshness are
          shown separately.
        </p>
      </div>
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <MomentumContent data={state.data} />
      )}
    </section>
  );
}
