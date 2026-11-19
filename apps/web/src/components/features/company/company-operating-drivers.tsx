"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError } from "@/components/app/empty-state";
import { useResearch } from "@/hooks/use-research";
import { ObservationProposalReview } from "@/components/features/company/company-observation-review";
import {
  isCompanyAgentContext,
  type CompanyAgentContext,
} from "@/lib/domain-contracts";

type Actual = CompanyAgentContext["metric_observations"][number];
type Guidance = CompanyAgentContext["guidance_observations"][number];
type Driver =
  CompanyAgentContext["native_models"][number]["driver_projections"][number];
type Metric = CompanyAgentContext["metric_definitions"][number];

type PeriodGroup = {
  key: string;
  periodStart: string;
  periodEnd: string;
  periodType: string;
  scope: string;
  actuals: Actual[];
  guidance: Guidance[];
  drivers: Array<{ value: Driver; modelName: string; revisionNumber: number }>;
};

export function comparableOperatingValues(
  actual: Actual,
  reference: Guidance | Driver,
): boolean {
  return (
    actual.is_current &&
    ["VERIFIED", "RESTATED"].includes(actual.quality_status) &&
    actual.value_qualifier === "EQ" &&
    actual.period_type === reference.period_type &&
    actual.period_start === reference.period_start &&
    actual.period_end === reference.period_end &&
    actual.unit === reference.unit &&
    actual.scale === reference.scale &&
    actual.currency === reference.currency &&
    JSON.stringify(actual.scope_json) === JSON.stringify(reference.scope_json)
  );
}

/** Never convert unlike units, currencies, fiscal windows or qualified actuals. */
export function actualVsGuidance(
  actual: Actual,
  guidance: Guidance,
): "ABOVE" | "WITHIN" | "BELOW" | null {
  if (
    !comparableOperatingValues(actual, guidance) ||
    guidance.value_qualifier !== "RANGE"
  )
    return null;
  const actualValue = Number(actual.value);
  const lower =
    guidance.lower_value === null ? null : Number(guidance.lower_value);
  const upper =
    guidance.upper_value === null ? null : Number(guidance.upper_value);
  if (
    ![actualValue, lower, upper].every(
      (value) => value === null || Number.isFinite(value),
    )
  )
    return null;
  if (lower !== null && actualValue < lower) return "BELOW";
  if (upper !== null && actualValue > upper) return "ABOVE";
  return lower !== null && upper !== null ? "WITHIN" : null;
}

export function actualVsDriver(
  actual: Actual,
  driver: Driver,
): "ABOVE" | "ON" | "BELOW" | null {
  if (
    !comparableOperatingValues(actual, driver) ||
    driver.value_qualifier !== "EQ"
  )
    return null;
  const observed = Number(actual.value);
  const projected = Number(driver.value);
  if (!Number.isFinite(observed) || !Number.isFinite(projected)) return null;
  return observed > projected ? "ABOVE" : observed < projected ? "BELOW" : "ON";
}

function formatDecimal(raw: string | null) {
  if (raw === null) return "Not published";
  const parts = raw.split(".");
  const integer = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return parts.length > 1 ? `${integer}.${parts[1]}` : integer;
}

function measure(
  value: string | null,
  scale: string,
  unit: string,
  currency: string | null,
  qualifier: string,
) {
  if (value === null) return "Not published";
  return `${qualifier === "EQ" ? "" : `${qualifier} `}${formatDecimal(value)} × ${formatDecimal(scale)} ${currency ?? unit}`;
}

function href(reference: string | null) {
  return reference && /^https:\/\//i.test(reference) ? reference : null;
}

function Source({ url, label }: { url: string | null; label: string }) {
  const link = href(url);
  return link ? (
    <a
      className="text-xs text-primary underline-offset-2 hover:underline"
      target="_blank"
      rel="noopener noreferrer"
      href={link}
    >
      {label}
    </a>
  ) : (
    <span className="text-xs text-muted-foreground">Source unavailable</span>
  );
}

function periodKey(
  periodType: string,
  start: string,
  end: string,
  scope: Record<string, unknown>,
) {
  return [
    periodType,
    start,
    end,
    JSON.stringify(Object.entries(scope).sort()),
  ].join("|");
}

export function operatingMetricPeriods(
  context: CompanyAgentContext,
  metricId: string,
): PeriodGroup[] {
  const byPeriod = new Map<string, PeriodGroup>();
  const get = (
    periodType: string,
    start: string,
    end: string,
    scopeJson: Record<string, unknown>,
  ) => {
    const key = periodKey(periodType, start, end, scopeJson);
    let group = byPeriod.get(key);
    if (!group) {
      group = {
        key,
        periodType,
        periodStart: start,
        periodEnd: end,
        scope: Object.keys(scopeJson).length
          ? Object.entries(scopeJson)
              .sort()
              .map(([k, v]) => `${k}: ${String(v)}`)
              .join(", ")
          : "Company",
        actuals: [],
        guidance: [],
        drivers: [],
      };
      byPeriod.set(key, group);
    }
    return group;
  };
  for (const actual of context.metric_observations) {
    if (actual.metric_id !== metricId || !actual.is_current) continue;
    get(
      actual.period_type,
      actual.period_start,
      actual.period_end,
      actual.scope_json,
    ).actuals.push(actual);
  }
  for (const guidance of context.guidance_observations) {
    if (guidance.metric_id !== metricId || !guidance.is_current) continue;
    get(
      guidance.period_type,
      guidance.period_start,
      guidance.period_end,
      guidance.scope_json,
    ).guidance.push(guidance);
  }
  for (const model of context.native_models) {
    for (const driver of model.driver_projections) {
      if (driver.metric_id !== metricId) continue;
      get(
        driver.period_type,
        driver.period_start,
        driver.period_end,
        driver.scope_json,
      ).drivers.push({
        value: driver,
        modelName: model.model_name,
        revisionNumber: model.accepted_revision.revision_number,
      });
    }
  }
  return [...byPeriod.values()].sort(
    (a, b) =>
      b.periodEnd.localeCompare(a.periodEnd) ||
      b.periodStart.localeCompare(a.periodStart),
  );
}

function ActualCell({ values }: { values: Actual[] }) {
  if (!values.length)
    return <span className="text-muted-foreground">No accepted actual</span>;
  return (
    <div className="space-y-2">
      {values.map((value) => (
        <div key={value.id} className="space-y-1">
          <div className="font-medium">
            {measure(
              value.value,
              value.scale,
              value.unit,
              value.currency,
              value.value_qualifier,
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {value.quality_status} · {value.basis}
          </div>
          <Source url={value.source_reference} label="Issuer evidence" />
        </div>
      ))}
    </div>
  );
}

function GuidanceCell({
  values,
  actuals,
}: {
  values: Guidance[];
  actuals: Actual[];
}) {
  if (!values.length)
    return (
      <span className="text-muted-foreground">No management guidance</span>
    );
  return (
    <div className="space-y-2">
      {values.map((value) => {
        const alignment = actuals
          .map((actual) => actualVsGuidance(actual, value))
          .find(Boolean);
        return (
          <div key={value.id} className="space-y-1">
            <div className="font-medium">
              {measure(
                value.lower_value,
                value.scale,
                value.unit,
                value.currency,
                value.value_qualifier,
              )}
              {" – "}
              {formatDecimal(value.upper_value)}
            </div>
            <div className="text-xs text-muted-foreground">
              {value.status} · company-issued range
            </div>
            {alignment && (
              <span className="text-xs font-medium">
                Actual {alignment.toLowerCase()} guidance range
              </span>
            )}
            <Source
              url={value.source_reference}
              label="Management disclosure"
            />
          </div>
        );
      })}
    </div>
  );
}

function DriverCell({
  drivers,
  actuals,
}: {
  drivers: PeriodGroup["drivers"];
  actuals: Actual[];
}) {
  if (!drivers.length)
    return (
      <span className="text-muted-foreground">No accepted driver path</span>
    );
  return (
    <div className="space-y-2">
      {drivers.map(({ value, modelName, revisionNumber }) => {
        const alignment = actuals
          .map((actual) => actualVsDriver(actual, value))
          .find(Boolean);
        return (
          <div key={value.id} className="space-y-1">
            <div className="font-medium">
              {value.scenario} ·{" "}
              {measure(
                value.value,
                value.scale,
                value.unit,
                value.currency,
                value.value_qualifier,
              )}
            </div>
            <div className="text-xs text-muted-foreground">
              {modelName} · accepted revision {revisionNumber} · year{" "}
              {value.forecast_year}
            </div>
            {alignment && (
              <div className="text-xs font-medium">
                Actual {alignment.toLowerCase()} {value.scenario.toLowerCase()}{" "}
                case
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              {value.rationale}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Coverage({
  status,
  label,
}: {
  status: CompanyAgentContext["metrics_status"];
  label: string;
}) {
  return (
    <span className="rounded-md border px-2 py-1 text-xs">
      {label}: {status.status.toLowerCase().replaceAll("_", " ")}
      {status.truncated ? " · limited history" : ""}
    </span>
  );
}

export function OperatingDriversPanel({
  context,
}: {
  context: CompanyAgentContext;
}) {
  const [selectedMetric, setSelectedMetric] = useState("ALL");
  const metrics = useMemo(() => {
    const found = new Map<string, Metric>();
    for (const definition of context.metric_definitions)
      found.set(definition.metric_id, definition);
    return [...found.values()].sort((a, b) =>
      a.display_name.localeCompare(b.display_name),
    );
  }, [context.metric_definitions]);
  const displayed =
    selectedMetric === "ALL"
      ? metrics
      : metrics.filter((metric) => metric.metric_id === selectedMetric);
  const currentActuals = context.metric_observations.filter(
    (value) => value.is_current,
  ).length;
  const currentGuidance = context.guidance_observations.filter(
    (value) => value.is_current,
  ).length;
  const acceptedDrivers = context.native_models.reduce(
    (sum, item) => sum + item.driver_projections.length,
    0,
  );
  const missingDefinitions = [
    ...context.metric_observations,
    ...context.guidance_observations,
  ].some(
    (item) => !metrics.some((metric) => metric.metric_id === item.metric_id),
  );
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">
            Operating KPIs & model drivers
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Accepted company-specific actuals, management guidance, and
            explicitly published model scenarios. Financial-statement
            revenue/EPS estimates remain separate below.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Metric</span>
          <select
            aria-label="Select operating metric"
            className="max-w-56 rounded-md border bg-background px-3 py-2"
            value={selectedMetric}
            onChange={(event) => setSelectedMetric(event.target.value)}
          >
            <option value="ALL">All operating metrics</option>
            {metrics.map((metric) => (
              <option key={metric.id} value={metric.metric_id}>
                {metric.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Coverage label="KPI history" status={context.metrics_status} />
        <Coverage label="Guidance" status={context.guidance_status} />
        <Coverage label="Native models" status={context.native_models_status} />
        <Coverage label="Consensus" status={context.consensus_status} />
        <span className="text-xs text-muted-foreground">
          {currentActuals} actuals · {currentGuidance} guidance entries ·{" "}
          {acceptedDrivers} driver points
        </span>
      </div>
      {(context.metrics_status.truncated ||
        context.guidance_status.truncated ||
        context.native_models_status.truncated ||
        missingDefinitions) && (
        <p role="status" className="rounded-md border p-3 text-sm">
          Partial coverage or missing metric definitions. A missing row is not
          evidence of a missing company disclosure. Consult the detailed history
          before making a decision.
        </p>
      )}
      {displayed.length === 0 && (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            No accepted operating metric definitions are available for this
            company. No operating forecasts are inferred from revenue or
            earnings.
          </CardContent>
        </Card>
      )}
      {displayed.map((metric) => {
        const periods = operatingMetricPeriods(context, metric.metric_id);
        return (
          <Card key={metric.id}>
            <CardHeader>
              <CardTitle className="text-base">{metric.display_name}</CardTitle>
              <p className="text-xs text-muted-foreground">
                {metric.metric_id} · {metric.description} ·{" "}
                {metric.canonical_unit} ×{" "}
                {formatDecimal(metric.canonical_scale)}
              </p>
            </CardHeader>
            <CardContent>
              {periods.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No accepted actual, guidance or model-driver observations for
                  this metric.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[700px] text-left text-sm">
                    <thead>
                      <tr className="border-b text-xs text-muted-foreground">
                        <th className="p-2 font-medium">Economic period</th>
                        <th className="p-2 font-medium">Accepted actual</th>
                        <th className="p-2 font-medium">Management guidance</th>
                        <th className="p-2 font-medium">
                          Accepted model assumptions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {periods.map((period) => (
                        <tr key={period.key} className="align-top">
                          <td className="p-2">
                            <div className="font-medium">
                              {period.periodEnd}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {period.periodType} · {period.periodStart} ·{" "}
                              {period.scope}
                            </div>
                          </td>
                          <td className="p-2">
                            <ActualCell values={period.actuals} />
                          </td>
                          <td className="p-2">
                            <GuidanceCell
                              values={period.guidance}
                              actuals={period.actuals}
                            />
                          </td>
                          <td className="p-2">
                            <DriverCell
                              drivers={period.drivers}
                              actuals={period.actuals}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Selected analyst consensus — financial metrics only
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Provider: {context.consensus_provider_id ?? "Not selected"} ·{" "}
            {context.consensus_continuity_status}. Revenue and EPS estimates are
            not interchangeable with company operating KPIs.
          </p>
        </CardHeader>
        <CardContent className="space-y-2">
          {context.consensus_periods.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No selected provider consensus available.
            </p>
          ) : (
            <ul className="divide-y text-sm">
              {context.consensus_periods.map((period) => (
                <li
                  key={`${period.metric}:${period.forecast_period}`}
                  className="flex flex-wrap items-center justify-between gap-3 py-2"
                >
                  <span>
                    {period.metric} · {period.forecast_period} ·{" "}
                    {period.period_end ?? "period unavailable"}
                  </span>
                  <span className="font-medium">
                    {period.current_observation
                      ? `${formatDecimal(period.current_observation.value)} ${period.currency ?? period.unit}`
                      : "No observation"}
                    {" · "}
                    {period.current_observation?.data_quality ?? "not verified"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        Exact comparability requires the same period, scope, currency, scale and
        unit. Values with qualifiers or conflicting quality do not produce an
        automated performance verdict. Recorded values are accepted database
        observations, not trade recommendations.
      </p>
    </div>
  );
}

export function CompanyOperatingDriversWorkspace({
  companyId,
}: {
  companyId: string;
}) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/agent-context`,
    isCompanyAgentContext,
  );
  if (!state.data) return <PendingOrError {...state} />;
  return (
    <div className="space-y-8">
      <OperatingDriversPanel context={state.data} />
      <ObservationProposalReview companyId={companyId} />
    </div>
  );
}
