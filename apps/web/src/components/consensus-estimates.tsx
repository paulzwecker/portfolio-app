"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError, useResearch } from "@/components/research-frame";
import {
  isCompanyConsensusEstimates,
  type CompanyConsensusEstimates,
  type ConsensusEstimatePeriod,
  type ConsensusEstimateProvider,
} from "@/lib/domain-contracts";
import { date, quantity } from "@/lib/display";

const freshnessLabel: Record<string, string> = {
  FRESH: "Fresh",
  STALE: "Stale",
  DATA_CHECK: "Data check",
  NO_DATA: "No observations",
};

function snapshotLabel(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(
    new Date(`${value}T00:00:00Z`),
  );
}

function periodLabel(period: ConsensusEstimatePeriod) {
  if (period.period_end) {
    return `${period.period_type} · ${snapshotLabel(period.period_end)}`;
  }
  return `${period.forecast_period} · legacy horizon only`;
}

function ObservationCard({
  period,
  providerId,
}: {
  period: ConsensusEstimatePeriod;
  providerId: string;
}) {
  const current = period.current_observation;
  const label = period.metric === "REVENUE" ? "Revenue" : "EPS";
  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="text-sm">
            {label} · {periodLabel(period)}
          </CardTitle>
          <Badge
            variant={current?.data_quality === "PASS" ? "outline" : "secondary"}
          >
            {current?.data_quality === "PASS"
              ? "Verified fields"
              : "Data check"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {!current ? (
          <p className="text-sm text-muted-foreground">
            No estimate recorded for this period.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span className="text-2xl font-semibold tabular-nums">
                {period.currency ?? "Currency unknown"}{" "}
                {quantity(current.value)}
              </span>
              <span className="text-xs text-muted-foreground">
                {period.metric === "EPS"
                  ? "per share"
                  : period.unit.toLowerCase()}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>
                Range ·{" "}
                {current.low_value === null
                  ? "Unknown"
                  : quantity(current.low_value)}
                {" – "}
                {current.high_value === null
                  ? "Unknown"
                  : quantity(current.high_value)}
              </span>
              <span>
                Coverage ·{" "}
                {current.analyst_count === null
                  ? "Unknown"
                  : current.analyst_count}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Snapshot {snapshotLabel(current.snapshot_date)}
              {current.observed_at
                ? ` · observed ${date(current.observed_at)}`
                : " · source time unavailable"}
              {` · recorded ${date(current.recorded_at)}`}
            </p>
            {current.quality_reason && (
              <p className="rounded-md border border-dashed p-2 text-xs leading-5 text-muted-foreground">
                {current.quality_reason}
              </p>
            )}
            <details className="border-t pt-3">
              <summary className="cursor-pointer text-xs font-medium">
                Revision history · {period.history.length} snapshot
                {period.history.length === 1 ? "" : "s"}
              </summary>
              <ol className="mt-3 space-y-3">
                {period.history.map((item) => (
                  <li
                    key={item.id}
                    className="border-l-2 pl-3 text-xs leading-5"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="tabular-nums">
                        {period.currency ?? "Currency unknown"}{" "}
                        {quantity(item.value)}
                      </strong>
                      <Badge variant="secondary">
                        {item.revision_context.replaceAll("_", " ")}
                      </Badge>
                      <Badge variant="outline">
                        {item.data_quality.replaceAll("_", " ")}
                      </Badge>
                    </div>
                    <p className="text-muted-foreground">
                      Snapshot {snapshotLabel(item.snapshot_date)} ·{" "}
                      {item.analyst_count ?? "Unknown"} analysts
                      {item.supersedes_observation_id
                        ? " · supersedes an earlier source observation"
                        : ""}
                    </p>
                    {item.source_ref.startsWith("http") ? (
                      <a
                        className="break-all text-primary underline-offset-4 hover:underline"
                        href={item.source_ref}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Source record · {providerId}
                      </a>
                    ) : (
                      <p className="break-all text-muted-foreground">
                        Workbook reference · {item.source_ref.split("#").at(-1)}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </details>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ProviderSeries({
  provider,
  alternate = false,
}: {
  provider: ConsensusEstimateProvider;
  alternate?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={provider.selected ? "default" : "outline"}>
          {provider.selected ? "Selected source" : "Separate source"}
        </Badge>
        <Badge variant="secondary">{provider.role}</Badge>
        <Badge
          variant={provider.freshness === "FRESH" ? "outline" : "secondary"}
        >
          {freshnessLabel[provider.freshness]}
        </Badge>
        <span className="font-medium">
          {provider.provider_id} · {provider.provider_symbol}
        </span>
        <span className="text-muted-foreground">
          {provider.observation_count} observations
          {provider.latest_snapshot_date
            ? ` · latest ${snapshotLabel(provider.latest_snapshot_date)}`
            : ""}
        </span>
      </div>
      {provider.missing_metrics.length > 0 && (
        <p className="text-xs text-muted-foreground">
          No captured {provider.missing_metrics.join(" or ")} estimate
          {provider.missing_metrics.length === 1 ? "" : "s"} for this source.
        </p>
      )}
      {provider.periods.length ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {provider.periods.map((period) => (
            <ObservationCard
              key={`${period.metric}:${period.period_type}:${period.forecast_period}:${period.currency ?? "unknown"}`}
              period={period}
              providerId={provider.provider_id}
            />
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          This source has no captured estimate observations in the selected
          as-of view.
        </p>
      )}
      {provider.identity_evidence_source.startsWith("http") && (
        <a
          className="break-all text-xs text-primary underline-offset-4 hover:underline"
          href={provider.identity_evidence_source}
          target="_blank"
          rel="noreferrer"
        >
          Identity mapping evidence
        </a>
      )}
      {alternate && (
        <p className="text-xs text-muted-foreground">
          Kept separate from the selected consensus stream. No values are merged
          or used to fill its gaps.
        </p>
      )}
    </div>
  );
}

function ConsensusContent({ data }: { data: CompanyConsensusEstimates }) {
  const selected = data.providers.find((provider) => provider.selected);
  const alternates = data.providers.filter((provider) => !provider.selected);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            data.continuity_status.includes("SELECTED")
              ? "outline"
              : "secondary"
          }
        >
          {data.continuity_status.replaceAll("_", " ")}
        </Badge>
        {data.selected_provider_id && (
          <Badge variant="outline">{data.selected_provider_id}</Badge>
        )}
        <span className="text-xs text-muted-foreground">
          Estimates are provider snapshots, separate from native model
          assumptions.
        </span>
      </div>
      {data.continuity_status === "NO_MAPPING" && (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          No consensus provider identity is mapped. Estimates remain
          unavailable; no value is inferred from a model or another company.
        </p>
      )}
      {data.continuity_status === "AMBIGUOUS_FALLBACK" && (
        <p className="rounded-md border border-amber-300 p-4 text-sm text-muted-foreground">
          Multiple fallback sources share the same priority. No source is
          selected until precedence is reviewed.
        </p>
      )}
      {data.continuity_status === "PRIMARY_NO_DATA" && (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          A primary source is assigned but has no observations yet. Fallback
          observations remain separate and are not substituted.
        </p>
      )}
      {selected && <ProviderSeries provider={selected} />}
      {alternates.length > 0 && (
        <details className="rounded-lg border p-4">
          <summary className="cursor-pointer text-sm font-medium">
            Other provider histories · {alternates.length} separate source
            {alternates.length === 1 ? "" : "s"}
          </summary>
          <div className="mt-4 space-y-6">
            {alternates.map((provider) => (
              <ProviderSeries
                key={`${provider.provider_id}:${provider.provider_symbol}`}
                provider={provider}
                alternate
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

export function ConsensusEstimates({ companyId }: { companyId: string }) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/consensus-estimates`,
    isCompanyConsensusEstimates,
  );
  return (
    <section
      id="consensus-estimates"
      aria-labelledby="consensus-estimates-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="consensus-estimates-title" className="text-xl font-semibold">
          Consensus estimates
        </h2>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
          Point-in-time provider forecasts for forward revenue and EPS. Source
          continuity is explicit, revisions remain append-only, and estimates do
          not alter model assumptions.
        </p>
      </div>
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <ConsensusContent data={state.data} />
      )}
    </section>
  );
}
