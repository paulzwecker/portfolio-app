"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError, useResearch } from "@/components/research-frame";
import {
  isCompanyExpectedReturnAttribution,
  isCompanyExpectedReturnHistory,
  type CompanyExpectedReturnAttribution,
  type CompanyExpectedReturnHistory,
  type ExpectedReturnHistoryPoint,
} from "@/lib/domain-contracts";
import { date, percent, quantity } from "@/lib/display";

type ChartField =
  | "weighted_fv"
  | "market_price"
  | "expected_cash_flow_irr"
  | "hurdle"
  | "expected_excess";

function eventDate(point: ExpectedReturnHistoryPoint) {
  return point.effective_at
    ? date(point.effective_at)
    : "Effective date unavailable";
}

function formatField(value: string | null, ratio = false) {
  return value === null
    ? "Not recorded"
    : ratio
      ? percent(value)
      : quantity(value);
}

function comparablePrice(point: ExpectedReturnHistoryPoint) {
  if (
    point.effective_at === null ||
    !["AVAILABLE", "STALE"].includes(point.market_price.status) ||
    (point.market_price.effective_at !== null &&
      Date.parse(point.market_price.effective_at) >
        Date.parse(point.effective_at))
  )
    return null;
  if (
    point.market_price.model_reference_price !== null &&
    point.model_currency !== null &&
    point.market_price.model_currency === point.model_currency
  )
    return point.market_price.model_reference_price;
  if (
    point.model_currency &&
    point.market_price.quote_currency === point.model_currency &&
    point.market_price.status !== "CURRENCY_MISMATCH"
  )
    return point.market_price.quote;
  return null;
}

function pointValue(point: ExpectedReturnHistoryPoint, field: ChartField) {
  if (field === "market_price") return comparablePrice(point);
  return point[field];
}

function HistoryChart({
  title,
  points,
  lines,
  ratio = false,
}: {
  title: string;
  points: ExpectedReturnHistoryPoint[];
  lines: { field: ChartField; label: string; color: string }[];
  ratio?: boolean;
}) {
  const width = 720;
  const height = 210;
  const left = 46;
  const right = 14;
  const top = 14;
  const bottom = 34;
  const dated = points.filter((point) => point.effective_at !== null);
  const values = lines.flatMap(({ field }) =>
    dated
      .map((point) => {
        const value = pointValue(point, field);
        return value === null ? null : Number(value) * (ratio ? 100 : 1);
      })
      .filter(
        (value): value is number => value !== null && Number.isFinite(value),
      ),
  );
  if (dated.length === 0 || values.length === 0)
    return (
      <Card className="min-w-0 shadow-none">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">{title}</CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground">
          Not enough dated, comparable values to plot.
        </CardContent>
      </Card>
    );

  const times = dated.map((point) => new Date(point.effective_at!).getTime());
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const padding =
    maxValue === minValue
      ? Math.max(Math.abs(maxValue) * 0.1, 1)
      : (maxValue - minValue) * 0.12;
  const low = minValue - padding;
  const high = maxValue + padding;
  const x = (point: ExpectedReturnHistoryPoint) => {
    const ratioX =
      maxTime === minTime
        ? 0.5
        : (new Date(point.effective_at!).getTime() - minTime) /
          (maxTime - minTime);
    return left + ratioX * (width - left - right);
  };
  const y = (value: number) =>
    top + ((high - value) / (high - low)) * (height - top - bottom);

  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="min-w-0">
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
          {lines.map((line) => (
            <span
              key={line.field}
              className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: line.color }}
              />
              {line.label}
            </span>
          ))}
        </div>
        <svg
          role="img"
          aria-label={title}
          viewBox={`0 0 ${width} ${height}`}
          className="h-auto w-full overflow-visible"
        >
          <line
            x1={left}
            y1={top}
            x2={left}
            y2={height - bottom}
            stroke="currentColor"
            opacity=".2"
          />
          <line
            x1={left}
            y1={height - bottom}
            x2={width - right}
            y2={height - bottom}
            stroke="currentColor"
            opacity=".2"
          />
          <text
            x={left - 5}
            y={top + 4}
            textAnchor="end"
            className="fill-muted-foreground text-[10px]"
          >
            {ratio ? `${high.toFixed(1)}%` : quantity(String(high))}
          </text>
          <text
            x={left - 5}
            y={height - bottom + 4}
            textAnchor="end"
            className="fill-muted-foreground text-[10px]"
          >
            {ratio ? `${low.toFixed(1)}%` : quantity(String(low))}
          </text>
          <text
            x={left}
            y={height - 8}
            textAnchor="start"
            className="fill-muted-foreground text-[10px]"
          >
            {new Date(minTime).toLocaleDateString()}
          </text>
          <text
            x={width - right}
            y={height - 8}
            textAnchor="end"
            className="fill-muted-foreground text-[10px]"
          >
            {new Date(maxTime).toLocaleDateString()}
          </text>
          {lines.map((line) => {
            let drawing = false;
            const path = dated
              .map((point) => {
                const raw = pointValue(point, line.field);
                if (raw === null) {
                  drawing = false;
                  return "";
                }
                const value = Number(raw) * (ratio ? 100 : 1);
                if (!Number.isFinite(value)) {
                  drawing = false;
                  return "";
                }
                const segment = `${drawing ? "L" : "M"}${x(point).toFixed(2)},${y(value).toFixed(2)}`;
                drawing = true;
                return segment;
              })
              .join(" ");
            return (
              <g key={line.field}>
                <path
                  d={path}
                  fill="none"
                  stroke={line.color}
                  strokeWidth="2"
                />
                {dated.map((point) => {
                  const raw = pointValue(point, line.field);
                  if (raw === null || !Number.isFinite(Number(raw)))
                    return null;
                  const value = Number(raw) * (ratio ? 100 : 1);
                  return (
                    <circle
                      key={point.point_id}
                      cx={x(point)}
                      cy={y(value)}
                      r="3"
                      fill={line.color}
                    >
                      <title>{`${eventDate(point)} · ${line.label}: ${formatField(raw, ratio)}`}</title>
                    </circle>
                  );
                })}
              </g>
            );
          })}
        </svg>
      </CardContent>
    </Card>
  );
}

function EstimateContext({
  data,
}: {
  data: ExpectedReturnHistoryPoint["estimate_context"];
}) {
  if (data.periods.length === 0)
    return (
      <p className="text-xs text-muted-foreground">
        Estimate context: {data.status.replaceAll("_", " ")}.
      </p>
    );
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        Point-in-time estimates · {data.provider_id ?? "source unavailable"}
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {data.periods.map((estimate) => (
          <div
            key={`${estimate.metric}:${estimate.period_type}:${estimate.period_end}:${estimate.currency}:${estimate.unit}`}
            className="rounded-md bg-secondary/40 p-2 text-xs"
          >
            <div className="flex flex-wrap justify-between gap-1 font-medium">
              <span>
                {estimate.metric} · {estimate.forecast_period}
              </span>
              <Badge
                variant={
                  estimate.data_quality === "PASS" ? "outline" : "secondary"
                }
              >
                {estimate.data_quality.replaceAll("_", " ")}
              </Badge>
            </div>
            <p className="mt-1 tabular-nums">
              {estimate.currency ?? "Currency unknown"}{" "}
              {quantity(estimate.value)} ·{" "}
              {estimate.analyst_count ?? "Coverage not reported"} analysts
            </p>
            <p className="text-[10px] text-muted-foreground">
              {estimate.period_end ?? "Fiscal period unresolved"} · snapshot{" "}
              {estimate.snapshot_date} · recorded {date(estimate.recorded_at)}
            </p>
            <p className="mt-1 break-all text-[10px] text-muted-foreground">
              Observation {estimate.observation_id} ·{" "}
              <a
                className="underline underline-offset-2"
                href={estimate.source_ref}
                target="_blank"
                rel="noreferrer"
              >
                source
              </a>
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function HistoryPoint({ point }: { point: ExpectedReturnHistoryPoint }) {
  const sourceLabel = {
    IMPORTED_CURRENT_CONTRACT: "Imported current contract",
    IMPORTED_LEGACY_REVISION: "Imported legacy snapshot",
    NATIVE_MODEL_REVISION: "Native model revision",
  }[point.source_kind];
  const price = point.market_price;
  return (
    <details className="rounded-lg border p-3">
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="break-words text-sm font-semibold">
              {point.model_label} · {eventDate(point)}
            </p>
            <p className="mt-1 text-[10px] text-muted-foreground">
              Revision{" "}
              {point.revision_number ??
                point.source_revision_id ??
                "not numbered"}{" "}
              · recorded {date(point.recorded_at)} ·{" "}
              {point.methodology_version ??
                point.model_type ??
                point.source_kind.replaceAll("_", " ")}
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            <Badge variant="outline">{sourceLabel}</Badge>
            {point.is_current_at_cutoff && (
              <Badge>Current accepted revision</Badge>
            )}
            {point.output_quality && point.output_quality !== "COMPLETE" && (
              <Badge variant="secondary">
                {point.output_quality.replaceAll("_", " ")}
              </Badge>
            )}
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs sm:grid-cols-4 xl:grid-cols-8">
          <Metric
            label="Weighted FV"
            value={formatField(point.weighted_fv)}
            currency={point.model_currency}
          />
          <Metric
            label={
              point.return_semantics === "NATIVE_METHOD_OUTPUT"
                ? "Expected Cash-Flow IRR"
                : "Imported return field"
            }
            value={formatField(point.expected_cash_flow_irr, true)}
          />
          <Metric label="Hurdle" value={formatField(point.hurdle, true)} />
          <Metric
            label="Expected Excess"
            value={formatField(point.expected_excess, true)}
          />
          <Metric
            label="Weighted Upside"
            value={formatField(point.weighted_upside, true)}
          />
          <Metric
            label="Forward CAGR"
            value={formatField(point.forward_fundamental_cagr, true)}
          />
          <Metric
            label="Market price"
            value={
              price.quote === null ? "Not recorded" : quantity(price.quote)
            }
            currency={price.quote_currency}
          />
          <Metric
            label="Estimate context"
            value={point.estimate_context.status.replaceAll("_", " ")}
          />
        </div>
      </summary>
      <div className="mt-4 space-y-4 border-t pt-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Scenario
            label="Bear"
            fairValue={point.bear_fv}
            probability={point.bear_probability}
            currency={point.model_currency}
          />
          <Scenario
            label="Base"
            fairValue={point.base_fv}
            probability={point.base_probability}
            currency={point.model_currency}
          />
          <Scenario
            label="Bull"
            fairValue={point.bull_fv}
            probability={point.bull_probability}
            currency={point.model_currency}
          />
          <Card className="shadow-none">
            <CardHeader className="pb-1">
              <CardTitle className="text-xs">
                Reference price & identity
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs">
              <p>
                {point.valuation_ticker && point.valuation_venue
                  ? `${point.valuation_ticker} · ${point.valuation_venue}`
                  : "Valuation listing unmapped"}
              </p>
              <p>Price status · {price.status.replaceAll("_", " ")}</p>
              <p>
                Model reference ·{" "}
                {price.model_reference_price === null
                  ? "Not captured"
                  : `${price.model_currency ?? "Currency unknown"} ${quantity(price.model_reference_price)}`}
              </p>
              <p>
                Quote ·{" "}
                {price.quote === null
                  ? "Not recorded"
                  : `${price.quote_currency ?? "Currency unknown"} ${quantity(price.quote)}`}
              </p>
              <p>
                Quote times · effective{" "}
                {price.effective_at ? date(price.effective_at) : "unknown"} ·
                observed{" "}
                {price.observed_at ? date(price.observed_at) : "unknown"} ·
                recorded{" "}
                {price.recorded_at ? date(price.recorded_at) : "unknown"}
              </p>
              <p>
                Adjustment basis · {price.adjustment_basis ?? "not recorded"}
              </p>
              {price.reason && (
                <p className="text-muted-foreground">{price.reason}</p>
              )}
              {price.source_ref && (
                <p className="break-all text-muted-foreground">
                  {price.provider} · {price.source_ref}
                </p>
              )}
            </CardContent>
          </Card>
        </div>
        <EstimateContext data={point.estimate_context} />
        <div className="grid gap-2 text-[10px] leading-4 text-muted-foreground sm:grid-cols-2">
          <p>
            Return field semantics ·{" "}
            {point.return_semantics.replaceAll("_", " ")}. Legacy outputs retain
            their source methodology and are not normalized into native model
            calculations.
          </p>
          <p>
            Model currency · {point.model_currency ?? "Unknown"} (
            {point.currency_status.toLowerCase()}) · contract{" "}
            {point.contract_status ?? "not applicable"} · source{" "}
            {point.source ?? "not recorded"}
          </p>
          <p>
            Recorded by {point.actor} · source author{" "}
            {point.source_actor ?? "not supplied"} · revision source{" "}
            {point.revision_source ?? "not supplied"} · revision type{" "}
            {point.revision_type ?? "not supplied"}
          </p>
          {(point.rationale || point.evidence) && (
            <p className="sm:col-span-2">
              {point.rationale ?? ""}
              {point.evidence ? ` · ${point.evidence}` : ""}
            </p>
          )}
        </div>
      </div>
    </details>
  );
}

function Metric({
  label,
  value,
  currency,
}: {
  label: string;
  value: string;
  currency?: string | null;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 break-words font-medium tabular-nums">
        {currency ? `${currency} ` : ""}
        {value}
      </p>
    </div>
  );
}

function Scenario({
  label,
  fairValue,
  probability,
  currency,
}: {
  label: string;
  fairValue: string | null;
  probability: string | null;
  currency: string | null;
}) {
  return (
    <Card className="shadow-none">
      <CardHeader className="pb-1">
        <CardTitle className="text-xs">{label} scenario</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-xs">
        <p>
          {currency ?? "Currency unknown"} {formatField(fairValue)}
        </p>
        <p className="text-muted-foreground">
          Probability · {formatField(probability, true)}
        </p>
      </CardContent>
    </Card>
  );
}

function seriesKey(point: ExpectedReturnHistoryPoint) {
  return `${point.series_id}::${point.model_currency ?? "UNKNOWN_CURRENCY"}`;
}

function AttributionComparison({
  companyId,
  points,
  asOf,
  knownAt,
}: {
  companyId: string;
  points: ExpectedReturnHistoryPoint[];
  asOf: string;
  knownAt: string;
}) {
  const dated = points
    .filter((point) => point.effective_at !== null)
    .sort((left, right) => {
      const timeOrder = left.effective_at!.localeCompare(right.effective_at!);
      return timeOrder || left.recorded_at.localeCompare(right.recorded_at);
    });
  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Why Expected IRR changed</CardTitle>
        <p className="text-xs leading-5 text-muted-foreground">
          Native revisions are recalculated across price, scenario
          probabilities, required-return inputs and other assumptions. Fair
          Value and hurdle movements remain separate context.
        </p>
      </CardHeader>
      <CardContent>
        {dated.length < 2 ? (
          <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
            This series needs two dated points for comparison. Imported and
            native model histories remain separate.
          </p>
        ) : (
          <AttributionQuery
            companyId={companyId}
            points={dated}
            asOf={asOf}
            knownAt={knownAt}
          />
        )}
      </CardContent>
    </Card>
  );
}

function AttributionQuery({
  companyId,
  points,
  asOf,
  knownAt,
}: {
  companyId: string;
  points: ExpectedReturnHistoryPoint[];
  asOf: string;
  knownAt: string;
}) {
  const [priorSelection, setPriorSelection] = useState("");
  const [currentSelection, setCurrentSelection] = useState("");
  const latest = points.at(-1)!;
  const latestPrior = [...points]
    .reverse()
    .find(
      (point) =>
        point.point_id !== latest.point_id &&
        point.series_id === latest.series_id,
    );
  const priorId = points.some((point) => point.point_id === priorSelection)
    ? priorSelection
    : (latestPrior?.point_id ?? points.at(-2)!.point_id);
  const currentId = points.some((point) => point.point_id === currentSelection)
    ? currentSelection
    : points.at(-1)!.point_id;
  const params = new URLSearchParams({
    prior_point_id: priorId,
    current_point_id: currentId,
    as_of: asOf,
    known_at: knownAt,
  });
  const endpoint =
    "companies/" +
    encodeURIComponent(companyId) +
    "/expected-return-attribution";
  const state = useResearch(
    endpoint + "?" + params.toString(),
    isCompanyExpectedReturnAttribution,
  );
  const label = (point: ExpectedReturnHistoryPoint) =>
    [
      point.effective_at ? date(point.effective_at) : "Undated",
      point.revision_number
        ? "revision " + point.revision_number
        : point.source_kind.replaceAll("_", " "),
      point.model_currency ?? "currency unknown",
      point.model_label,
    ].join(" · ");
  const distinct = priorId !== currentId;

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="grid min-w-0 gap-1 text-xs">
          Prior state
          <select
            aria-label="Prior Expected IRR state"
            className="h-9 min-w-0 rounded-md border bg-background px-2"
            value={priorId}
            onChange={(event) => setPriorSelection(event.target.value)}
          >
            {points.map((point) => (
              <option key={point.point_id} value={point.point_id}>
                {label(point)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid min-w-0 gap-1 text-xs">
          Current state
          <select
            aria-label="Current Expected IRR state"
            className="h-9 min-w-0 rounded-md border bg-background px-2"
            value={currentId}
            onChange={(event) => setCurrentSelection(event.target.value)}
          >
            {points.map((point) => (
              <option key={point.point_id} value={point.point_id}>
                {label(point)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!distinct ? (
        <p
          role="status"
          className="rounded-md border border-dashed p-3 text-xs"
        >
          Choose two different history points.
        </p>
      ) : !state.data ? (
        <PendingOrError {...state} />
      ) : state.data.status === "ATTRIBUTED" ? (
        <AttributionResult result={state.data} />
      ) : (
        <AttributionUnavailable result={state.data} />
      )}
    </div>
  );
}

function AttributionUnavailable({
  result,
}: {
  result: CompanyExpectedReturnAttribution;
}) {
  const statusText: Record<string, string> = {
    OUTPUTS_ONLY:
      "Legacy outputs are preserved, but their full change remains unexplained because accepted inputs are unavailable.",
    MISSING_RETURN:
      "At least one Expected IRR is missing. Missing values are not treated as zero.",
    RETURN_SEMANTICS_CHANGE:
      "The two return fields have different semantics and are not compared numerically.",
    MODEL_SERIES_CHANGE:
      "These points belong to different model series. The arithmetic difference remains residual.",
    METHODOLOGY_CHANGE:
      "The model method changed. The arithmetic difference remains residual.",
    INPUTS_UNAVAILABLE:
      "Retained inputs or comparable prices are incomplete. No driver effects are inferred.",
    RECALCULATION_MISMATCH:
      "The retained inputs do not reproduce the stored endpoints. No driver effects are reported.",
    UNDATED:
      "An effective timestamp is missing, so the points cannot be aligned.",
  };
  return (
    <div className="space-y-2 rounded-md border border-dashed p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{result.status.replaceAll("_", " ")}</Badge>
        <span className="text-muted-foreground">
          {statusText[result.status] ?? result.residual_reason}
        </span>
      </div>
      {result.expected_irr_change !== null && (
        <p className="font-medium tabular-nums">
          Reported endpoint change · {percent(result.expected_irr_change)}
        </p>
      )}
      {result.residual !== null && (
        <p className="text-muted-foreground">
          Residual / unexplained · {percent(result.residual)}
        </p>
      )}
      <p className="break-all text-[10px] text-muted-foreground">
        {result.prior.point_id} · {result.current.point_id}
      </p>
    </div>
  );
}

function AttributionResult({
  result,
}: {
  result: CompanyExpectedReturnAttribution;
}) {
  const { prior, current, context_changes: changes } = result;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric
          label={"Prior Expected IRR · " + date(prior.effective_at!)}
          value={formatField(prior.expected_cash_flow_irr, true)}
        />
        <Metric
          label={"Current Expected IRR · " + date(current.effective_at!)}
          value={formatField(current.expected_cash_flow_irr, true)}
        />
        <Metric
          label="Total change"
          value={formatField(result.expected_irr_change, true)}
        />
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold">Counterfactual contributions</p>
          <Badge variant="outline">Symmetric engine recalculation</Badge>
        </div>
        {result.drivers.map((driver) => (
          <div
            key={driver.code}
            className="grid gap-1 rounded-md bg-secondary/40 p-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
          >
            <div>
              <p className="text-xs font-medium">{driver.label}</p>
              <p className="text-[10px] leading-4 text-muted-foreground">
                {driver.explanation}
              </p>
            </div>
            <p className="text-sm font-semibold tabular-nums sm:text-right">
              {percent(driver.effect)}
            </p>
          </div>
        ))}
        <div className="rounded-md border p-2">
          <div className="flex flex-wrap justify-between gap-2 text-xs font-semibold">
            <span>Residual / unexplained</span>
            <span className="tabular-nums">
              {result.residual === null
                ? "Unavailable"
                : percent(result.residual)}
            </span>
          </div>
          {result.residual_reason && (
            <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
              {result.residual_reason}
            </p>
          )}
        </div>
      </div>
      <details className="rounded-md border p-2">
        <summary className="cursor-pointer text-xs font-medium">
          Fair Value, hurdle and estimate context
        </summary>
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Metric
              label="Weighted FV change"
              value={formatField(changes.weighted_fv)}
              currency={current.model_currency}
            />
            <Metric
              label="Base FV change"
              value={formatField(changes.base_fv)}
              currency={current.model_currency}
            />
            <Metric
              label="Scenario probability changes"
              value={[
                "Bear " + formatField(changes.bear_probability, true),
                "Base " + formatField(changes.base_probability, true),
                "Bull " + formatField(changes.bull_probability, true),
              ].join(" · ")}
            />
            <Metric
              label="Hurdle change"
              value={formatField(changes.hurdle, true)}
            />
            <Metric
              label="Expected Excess change"
              value={formatField(changes.expected_excess, true)}
            />
          </div>
          <p className="text-[10px] leading-4 text-muted-foreground">
            A lower hurdle is a lower return constraint, not better company
            economics. Fair Value and hurdle changes are context, not additive
            Expected IRR effects. {result.estimate_context_note}
          </p>
          <div className="grid gap-3 xl:grid-cols-2">
            <div className="space-y-2 rounded-md border p-2">
              <p className="text-xs font-semibold">Prior point estimates</p>
              <EstimateContext data={prior.estimate_context} />
            </div>
            <div className="space-y-2 rounded-md border p-2">
              <p className="text-xs font-semibold">Current point estimates</p>
              <EstimateContext data={current.estimate_context} />
            </div>
          </div>
          <div className="grid gap-2 text-[10px] text-muted-foreground sm:grid-cols-2">
            <p className="break-all">
              Prior revision · {prior.revision_id ?? prior.point_id}
            </p>
            <p className="break-all">
              Current revision · {current.revision_id ?? current.point_id}
            </p>
            <p className="break-all">
              {"Prior price input · " +
                prior.market_price.status.replaceAll("_", " ")}
              {" · "}
              {prior.market_price.model_currency ?? "Currency unknown"}{" "}
              {prior.market_price.model_reference_price === null
                ? "not captured"
                : quantity(prior.market_price.model_reference_price)}
              {" · Observation " +
                (prior.market_price.observation_id ?? "not linked")}
              {prior.market_price.source_ref ? (
                <>
                  {" · "}
                  <a
                    className="underline underline-offset-2"
                    href={prior.market_price.source_ref}
                    target="_blank"
                    rel="noreferrer"
                  >
                    source
                  </a>
                </>
              ) : null}
            </p>
            <p className="break-all">
              {"Current price input · " +
                current.market_price.status.replaceAll("_", " ")}
              {" · "}
              {current.market_price.model_currency ?? "Currency unknown"}{" "}
              {current.market_price.model_reference_price === null
                ? "not captured"
                : quantity(current.market_price.model_reference_price)}
              {" · Observation " +
                (current.market_price.observation_id ?? "not linked")}
              {current.market_price.source_ref ? (
                <>
                  {" · "}
                  <a
                    className="underline underline-offset-2"
                    href={current.market_price.source_ref}
                    target="_blank"
                    rel="noreferrer"
                  >
                    source
                  </a>
                </>
              ) : null}
            </p>
          </div>
        </div>
      </details>
    </div>
  );
}

function HistoryContent({
  data,
  companyId,
}: {
  data: CompanyExpectedReturnHistory;
  companyId: string;
}) {
  const series = Array.from(
    new Map(
      data.history.map((point) => [
        seriesKey(point),
        `${point.model_label} (${point.source_kind.replaceAll("_", " ").toLowerCase()}; ${point.model_currency ?? "currency unknown"})`,
      ]),
    ).entries(),
  );
  const [selectedSeries, setSelectedSeries] = useState("");
  const selected = series.some(([id]) => id === selectedSeries)
    ? selectedSeries
    : (series[0]?.[0] ?? "");
  const points = data.history
    .filter((point) => seriesKey(point) === selected)
    .sort((left, right) => {
      if (left.effective_at === null) return 1;
      if (right.effective_at === null) return -1;
      return left.effective_at.localeCompare(right.effective_at);
    });
  const current = points.filter((point) => point.is_current_at_cutoff);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={data.status === "AVAILABLE" ? "default" : "secondary"}>
          {data.status.replaceAll("_", " ")}
        </Badge>
        <span className="text-xs text-muted-foreground">
          Effective through {data.as_of} · recorded by {date(data.known_at)}
        </span>
      </div>
      {data.history.length === 0 ? (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          No dated or imported model outputs are available for this cutoff.
          Missing history is not reconstructed from current state.
        </p>
      ) : (
        <>
          {current.length > 0 && (
            <div className="grid gap-3 xl:grid-cols-2">
              {current.map((point) => (
                <Card key={point.point_id} className="shadow-none">
                  <CardHeader className="pb-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle className="text-sm">
                        Current accepted model state · {point.model_label}
                      </CardTitle>
                      <Badge variant="outline">
                        {point.model_type ?? "Native methodology"}
                      </Badge>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      Calculated {date(point.recorded_at)} · this output does
                      not reprice automatically.
                    </p>
                  </CardHeader>
                  <CardContent className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                    <Metric
                      label="Weighted FV"
                      value={formatField(point.weighted_fv)}
                      currency={point.model_currency}
                    />
                    <Metric
                      label="Expected IRR"
                      value={formatField(point.expected_cash_flow_irr, true)}
                    />
                    <Metric
                      label="Hurdle"
                      value={formatField(point.hurdle, true)}
                    />
                    <Metric
                      label="Expected Excess"
                      value={formatField(point.expected_excess, true)}
                    />
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p role="status" className="text-xs text-muted-foreground">
              {data.history.length} total immutable imported/native model
              point(s); current state is marked separately.
            </p>
            {series.length > 1 && (
              <label className="flex items-center gap-2 text-xs">
                Model series
                <select
                  aria-label="Expected-return model series"
                  className="h-9 max-w-[min(18rem,70vw)] rounded-md border bg-background px-2"
                  value={selected}
                  onChange={(event) => setSelectedSeries(event.target.value)}
                >
                  {series.map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <div className="grid min-w-0 gap-3 xl:grid-cols-2">
            <HistoryChart
              title={`Fair value and comparable price · ${points[0]?.model_currency ?? "currency varies"}`}
              points={points}
              lines={[
                {
                  field: "weighted_fv",
                  label: "Weighted Fair Value",
                  color: "#2563eb",
                },
                {
                  field: "market_price",
                  label: "Comparable price",
                  color: "#16a34a",
                },
              ]}
            />
            <HistoryChart
              title="Return output, hurdle and excess"
              points={points}
              ratio
              lines={[
                {
                  field: "expected_cash_flow_irr",
                  label:
                    points[0]?.return_semantics === "NATIVE_METHOD_OUTPUT"
                      ? "Expected Cash-Flow IRR"
                      : "Imported return field",
                  color: "#2563eb",
                },
                { field: "hurdle", label: "Hurdle", color: "#f97316" },
                {
                  field: "expected_excess",
                  label: "Expected Excess",
                  color: "#16a34a",
                },
              ]}
            />
          </div>
          <AttributionComparison
            companyId={companyId}
            points={data.history}
            asOf={data.as_of}
            knownAt={data.known_at}
          />
          <div className="space-y-2">
            {[...points].reverse().map((point) => (
              <HistoryPoint key={point.point_id} point={point} />
            ))}
          </div>
          <p className="text-[10px] leading-4 text-muted-foreground">
            Native outputs retain their engine methodology. Imported legacy
            outputs retain their workbook output and unknown return semantics.
            Undated snapshots remain visible in the record list but are excluded
            from charts. Estimate and market facts are included only when
            observed and recorded by the model event time.
          </p>
        </>
      )}
    </div>
  );
}

export function ExpectedReturnHistory({ companyId }: { companyId: string }) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/expected-return-history`,
    isCompanyExpectedReturnHistory,
  );
  return (
    <section
      id="expected-return-history"
      aria-labelledby="expected-return-history-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2
          id="expected-return-history-title"
          className="text-xl font-semibold"
        >
          Expected-return history
        </h2>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
          Point-in-time market and estimate context alongside imported outputs
          and immutable native model calculations. Historical rows are composed
          from their source records; no history is rewritten when a model
          changes.
        </p>
      </div>
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <HistoryContent data={state.data} companyId={companyId} />
      )}
    </section>
  );
}
