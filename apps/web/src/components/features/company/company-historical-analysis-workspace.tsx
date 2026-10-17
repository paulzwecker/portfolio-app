"use client";

import { useMemo, useState } from "react";
import {
  ChevronRight,
  Clock3,
  GitCompareArrows,
  History,
  LineChart,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer } from "@/components/app/chart-container";
import { DetailDrawer } from "@/components/app/detail-drawer";
import { EmptyState, PendingOrError } from "@/components/app/empty-state";
import { MetricCard } from "@/components/app/metric-card";
import { PageSection } from "@/components/app/page-section";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyEstimateMomentum,
  isCompanyExpectedReturnHistory,
  isCompanyInvestmentThesis,
  isCompanyRankings,
  isCompanyTemporalAlignment,
  isCompanyExecutionPace,
  type CompanyEstimateMomentum,
  type CompanyExpectedReturnHistory,
  type CompanyInvestmentThesis,
  type CompanyRankings,
  type CompanyTemporalAlignment,
  type CompanyExecutionPace,
  type ExpectedReturnHistoryPoint,
  type ListingMarketData,
  type RankingHistoryEntry,
  type ExecutionPaceHistoryEntry,
} from "@/lib/domain-contracts";
import {
  dateOnly,
  dateTime,
  formatCurrency,
  formatNumber,
  formatPercent,
  marketDate,
  quantity,
  statusLabel,
} from "@/lib/display";

type MarketState = {
  data?: ListingMarketData[];
  error?: string;
  retry: () => void;
};

export type HistoricalRange = "90D" | "1Y" | "3Y" | "ALL";
export type HistoricalEventKind =
  "MODEL" | "RANK" | "EXECUTION" | "ESTIMATE" | "THESIS";

export type HistoricalTimelineEvent = {
  id: string;
  kind: HistoricalEventKind;
  title: string;
  summary: string;
  status: string | null;
  eventAt: string | null;
  recordedAt: string | null;
  source: string | null;
  sourceReference: string | null;
  detail: string;
};

const RANGE_OPTIONS: { value: HistoricalRange; label: string }[] = [
  { value: "90D", label: "90 days" },
  { value: "1Y", label: "1 year" },
  { value: "3Y", label: "3 years" },
  { value: "ALL", label: "All available" },
];

const EVENT_OPTIONS: { value: HistoricalEventKind | "ALL"; label: string }[] = [
  { value: "ALL", label: "All events" },
  { value: "MODEL", label: "Model revisions" },
  { value: "RANK", label: "Ranking runs" },
  { value: "EXECUTION", label: "Execution Pace" },
  { value: "ESTIMATE", label: "Estimate context" },
  { value: "THESIS", label: "Thesis" },
];

export function expectedReturnLabel(
  perspective: string | null | undefined,
): string {
  if (perspective === "EQUITY") return "Expected shareholder return";
  if (perspective === "ENTERPRISE") return "Expected enterprise return";
  return "Expected return";
}

function readablePercent(value: string | null) {
  return formatPercent(value, 2, "No target");
}

function parseTime(value: string | null | undefined) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function rangeStart(range: HistoricalRange, end: number) {
  if (range === "ALL") return null;
  const days = range === "90D" ? 90 : range === "1Y" ? 365 : 1095;
  return end - days * 24 * 60 * 60 * 1000;
}

export function filterByHistoricalRange<T>(
  values: T[],
  range: HistoricalRange,
  getTime: (value: T) => string | null | undefined,
) {
  if (range === "ALL" || values.length === 0) return values;
  const times = values
    .map((value) => parseTime(getTime(value)))
    .filter((time): time is number => time !== null);
  if (times.length === 0) return values;
  const start = rangeStart(range, Math.max(...times));
  if (start === null) return values;
  return values.filter((value) => {
    const time = parseTime(getTime(value));
    return time === null || time >= start;
  });
}

function pointTime(point: ExpectedReturnHistoryPoint) {
  return point.effective_at ?? point.recorded_at;
}

function comparablePrice(point: ExpectedReturnHistoryPoint) {
  const modelCurrency = point.model_currency;
  if (!modelCurrency || point.effective_at === null) return null;
  if (
    point.market_price.status !== "AVAILABLE" &&
    point.market_price.status !== "STALE"
  )
    return null;
  const marketEffective = parseTime(point.market_price.effective_at);
  const modelEffective = parseTime(point.effective_at);
  if (
    marketEffective !== null &&
    modelEffective !== null &&
    marketEffective > modelEffective
  )
    return null;
  if (
    point.market_price.listing_id !== point.valuation_listing_id ||
    point.market_price.listing_currency !== point.valuation_listing_currency
  )
    return null;
  if (
    point.market_price.quote !== null &&
    point.market_price.quote_currency === modelCurrency
  )
    return point.market_price.quote;
  return null;
}

export function comparableExpectationPoints(
  points: ExpectedReturnHistoryPoint[],
) {
  return points.filter(
    (point) => comparablePrice(point) !== null && point.weighted_fv !== null,
  );
}

function eventLabel(kind: HistoricalEventKind) {
  return {
    MODEL: "Model revision",
    RANK: "Ranking run",
    EXECUTION: "Execution Pace",
    ESTIMATE: "Estimate context",
    THESIS: "Thesis revision",
  }[kind];
}

export function buildHistoricalTimelineEvents({
  expectedReturn,
  rankings,
  execution,
  momentum,
  thesis,
}: {
  expectedReturn?: CompanyExpectedReturnHistory;
  rankings?: CompanyRankings;
  execution?: CompanyExecutionPace;
  momentum?: CompanyEstimateMomentum;
  thesis?: CompanyInvestmentThesis;
}) {
  const events: HistoricalTimelineEvent[] = [];
  for (const point of expectedReturn?.history ?? []) {
    events.push({
      id: `model:${point.point_id}`,
      kind: "MODEL",
      title: point.model_label,
      summary:
        point.expected_cash_flow_irr === null
          ? `${expectedReturnLabel(point.return_methodology?.perspective)} unavailable`
          : `${readablePercent(point.expected_cash_flow_irr)} ${expectedReturnLabel(point.return_methodology?.perspective).toLowerCase()} · ${point.methodology_version ?? statusLabel(point.model_type)}`,
      status: point.output_quality ?? point.output_status,
      eventAt: point.effective_at,
      recordedAt: point.recorded_at,
      source: point.source ?? point.revision_source,
      sourceReference: point.source_revision_id ?? point.source,
      detail: `${point.return_semantics === "NATIVE_METHOD_OUTPUT" ? "Native method output" : "Imported legacy output"}. ${point.rationale ?? "No rationale recorded."}`,
    });
    const estimateDates = new Set(
      point.estimate_context.periods.map((period) => period.snapshot_date),
    );
    for (const snapshotDate of estimateDates) {
      events.push({
        id: `estimate:${point.point_id}:${snapshotDate}`,
        kind: "ESTIMATE",
        title: `${point.estimate_context.provider_id ?? "Estimate source"} snapshot`,
        summary: `${point.model_label} used estimate context from ${dateOnly(snapshotDate)}`,
        status: point.estimate_context.status,
        eventAt: snapshotDate,
        recordedAt: point.recorded_at,
        source: point.estimate_context.provider_id,
        sourceReference: point.source,
        detail:
          "Estimate context is displayed as evidence around the model event; it is not blended into the model output.",
      });
    }
  }
  for (const item of rankings?.history ?? []) {
    events.push(rankingEvent(item));
  }
  for (const item of execution?.history ?? []) {
    events.push(executionEvent(item));
  }
  if (momentum) {
    events.push({
      id: `estimate-momentum:${momentum.as_of}:${momentum.provider_id ?? "none"}`,
      kind: "ESTIMATE",
      title: "Estimate Momentum snapshot",
      summary: momentum.direction
        ? `${statusLabel(momentum.direction)} · ${momentum.coverage_count}/${momentum.coverage_total} components covered`
        : statusLabel(momentum.availability),
      status: momentum.data_quality,
      eventAt: momentum.as_of,
      recordedAt: momentum.known_at,
      source: momentum.provider_id,
      sourceReference: null,
      detail: momentum.reason ?? "No momentum explanation recorded.",
    });
  }
  for (const stream of thesis?.streams ?? []) {
    for (const revision of stream.history) {
      events.push({
        id: `thesis:${revision.id}`,
        kind: "THESIS",
        title: `${stream.stream_key} · revision ${revision.revision_number}`,
        summary: revision.thesis_statement ?? "Thesis statement unavailable",
        status: revision.confidence,
        eventAt: revision.observed_at,
        recordedAt: revision.recorded_at,
        source: revision.source_id,
        sourceReference: revision.source_reference,
        detail: revision.rationale,
      });
    }
  }
  return events.sort((left, right) => {
    const leftTime = parseTime(left.eventAt) ?? parseTime(left.recordedAt) ?? 0;
    const rightTime =
      parseTime(right.eventAt) ?? parseTime(right.recordedAt) ?? 0;
    return rightTime - leftTime;
  });
}

function rankingEvent(item: RankingHistoryEntry): HistoricalTimelineEvent {
  const type = item.run.definition.ranking_type;
  return {
    id: `rank:${item.entry.id}`,
    kind: "RANK",
    title: `${statusLabel(type)} Rank · ${item.entry.status === "RANKED" ? `#${item.entry.position}` : statusLabel(item.entry.status)}`,
    summary: item.entry.reason,
    status: item.entry.status,
    eventAt: item.run.as_of,
    recordedAt: item.run.recorded_at,
    source: item.run.source,
    sourceReference: item.run.definition.source_reference,
    detail: `${item.run.definition.title} v${item.run.definition.version}. ${item.run.definition.methodology}`,
  };
}

function executionEvent(
  item: ExecutionPaceHistoryEntry,
): HistoricalTimelineEvent {
  return {
    id: `execution:${item.decision.id}`,
    kind: "EXECUTION",
    title: item.decision.pace
      ? statusLabel(item.decision.pace)
      : statusLabel(item.decision.decision_status),
    summary: item.decision.reason,
    status: item.decision.decision_status,
    eventAt: item.run.as_of,
    recordedAt: item.run.recorded_at,
    source: item.run.source,
    sourceReference: item.decision.price_observation_id,
    detail: `${item.run.methodology_version}. Decision input snapshot recorded with the run; it is not a hypothetical recalculation.`,
  };
}

function chartBounds(values: number[]) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding =
    max === min ? Math.max(Math.abs(max) * 0.1, 1) : (max - min) * 0.12;
  return { low: min - padding, high: max + padding };
}

function PriceHistoryChart({
  market,
  observations,
}: {
  market: ListingMarketData;
  observations: ListingMarketData["history"];
}) {
  const values = observations
    .map((item) => item.split_adjusted_close)
    .filter((value): value is string => value !== null)
    .map(Number)
    .filter(Number.isFinite);
  if (values.length < 2)
    return (
      <EmptyState
        title="Price history is unavailable"
        description="At least two exact-listing observations are required for a line chart. Existing observations remain available in the history list."
      />
    );
  const ordered = [...observations].reverse();
  const dated = ordered.filter((item) => item.split_adjusted_close !== null);
  const times = dated.map((item) => parseTime(item.market_date) ?? 0);
  const numeric = dated.map((item) => Number(item.split_adjusted_close));
  const bounds = chartBounds(numeric);
  const width = 760;
  const height = 230;
  const left = 54;
  const right = 16;
  const top = 18;
  const bottom = 36;
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const x = (time: number) =>
    left +
    (maxTime === minTime ? 0.5 : (time - minTime) / (maxTime - minTime)) *
      (width - left - right);
  const y = (value: number) =>
    top +
    ((bounds.high - value) / (bounds.high - bounds.low)) *
      (height - top - bottom);
  const path = dated
    .map(
      (item, index) =>
        `${index === 0 ? "M" : "L"}${x(times[index]).toFixed(2)},${y(numeric[index]).toFixed(2)}`,
    )
    .join(" ");
  return (
    <div className="min-w-0">
      <svg
        role="img"
        aria-label={`Exact-listing price history for ${market.listing.ticker}`}
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
          x={left - 7}
          y={top + 4}
          textAnchor="end"
          className="fill-muted-foreground text-[10px]"
        >
          {formatNumber(String(bounds.high), 2)}
        </text>
        <text
          x={left - 7}
          y={height - bottom + 4}
          textAnchor="end"
          className="fill-muted-foreground text-[10px]"
        >
          {formatNumber(String(bounds.low), 2)}
        </text>
        <text
          x={left}
          y={height - 9}
          textAnchor="start"
          className="fill-muted-foreground text-[10px]"
        >
          {marketDate(dated[0].market_date)}
        </text>
        <text
          x={width - right}
          y={height - 9}
          textAnchor="end"
          className="fill-muted-foreground text-[10px]"
        >
          {marketDate(dated[dated.length - 1].market_date)}
        </text>
        <path
          d={path}
          fill="none"
          stroke="hsl(var(--primary))"
          strokeWidth="2.4"
        />
        {dated.map((item, index) => (
          <circle
            key={item.id}
            cx={x(times[index])}
            cy={y(numeric[index])}
            r="3"
            fill="hsl(var(--primary))"
          >
            <title>{`${marketDate(item.market_date)} · ${formatCurrency(item.split_adjusted_close, item.currency)} · observed ${dateTime(item.observed_at)} · recorded ${dateTime(item.recorded_at)}`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

function MarketHistory({
  marketState,
  range,
}: {
  marketState: MarketState;
  range: HistoricalRange;
}) {
  const markets = marketState.data ?? [];
  const [listingId, setListingId] = useState<string | null>(null);
  const selected =
    markets.find((item) => item.listing.id === listingId) ?? markets[0] ?? null;
  const observations = selected
    ? filterByHistoricalRange(
        selected.history,
        range,
        (item) => item.market_date,
      )
    : [];
  if (!marketState.data)
    return (
      <PendingOrError error={marketState.error} retry={marketState.retry} />
    );
  if (markets.length === 0)
    return (
      <EmptyState
        title="No exact listing history"
        description="A listing-specific market observation has not been recorded for this company."
      />
    );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Exact listing and price basis</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Split-adjusted daily closes are shown for one listing at a time.
            Listing identity and currency are never substituted.
          </p>
        </div>
        {markets.length > 1 && (
          <label className="grid gap-1 text-xs text-muted-foreground">
            Listing
            <select
              aria-label="Historical listing"
              value={selected?.listing.id ?? ""}
              onChange={(event) => setListingId(event.target.value)}
              className="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
            >
              {markets.map((item) => (
                <option key={item.listing.id} value={item.listing.id}>
                  {item.listing.ticker} · {item.listing.venue} ·{" "}
                  {item.listing.currency ?? "Currency unknown"}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {selected && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(260px,.75fr)]">
          <ChartContainer
            title={`${selected.listing.ticker} price history`}
            description={`${observations.length} observations in the selected range · exact listing · split-adjusted close`}
            source={
              <StatusIndicator
                status={selected.availability}
                label={`${statusLabel(selected.availability)} · ${statusLabel(selected.freshness)}`}
              />
            }
          >
            <PriceHistoryChart market={selected} observations={observations} />
          </ChartContainer>
          <Card className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Market regime</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Latest close</span>
                <strong>
                  {selected.latest
                    ? formatCurrency(
                        selected.latest.split_adjusted_close,
                        selected.latest.currency,
                      )
                    : "Unavailable"}
                </strong>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Market date</span>
                <span>
                  {selected.latest
                    ? marketDate(selected.latest.market_date)
                    : "Unknown"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Trend</span>
                <StatusIndicator status={selected.price_regime?.trend_state} />
              </div>
              <div className="grid grid-cols-2 gap-2 border-t pt-3">
                {[
                  ["20DMA", selected.analytics.dma_20],
                  ["50DMA", selected.analytics.dma_50],
                  ["200DMA", selected.analytics.dma_200],
                  [
                    "3M return",
                    selected.analytics.price_return_3m === null
                      ? null
                      : readablePercent(selected.analytics.price_return_3m),
                  ],
                  [
                    "Volatility",
                    selected.analytics.realized_vol_20d === null
                      ? null
                      : readablePercent(selected.analytics.realized_vol_20d),
                  ],
                  [
                    "Drawdown",
                    selected.analytics.drawdown_52w === null
                      ? null
                      : readablePercent(selected.analytics.drawdown_52w),
                  ],
                ].map(([label, value]) => (
                  <div key={label as string}>
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="mt-1 font-medium tabular-nums">
                      {value === null
                        ? "Unavailable"
                        : label === "20DMA" ||
                            label === "50DMA" ||
                            label === "200DMA"
                          ? formatCurrency(
                              value as string,
                              selected.listing.currency ?? null,
                            )
                          : value}
                    </dd>
                  </div>
                ))}
              </div>
              <p className="border-t pt-3 leading-5 text-muted-foreground">
                {selected.analytics.status === "AVAILABLE"
                  ? `Analytics as of ${dateTime(selected.analytics.as_of)} · ${selected.analytics.methodology_version}`
                  : `Analytics ${statusLabel(selected.analytics.status)}. ${selected.analytics.observation_count} observations are retained.`}
              </p>
            </CardContent>
          </Card>
        </div>
      )}
      {selected && (
        <details className="rounded-lg border">
          <summary className="cursor-pointer px-3 py-2 text-xs font-medium">
            Inspect price observations ({observations.length})
          </summary>
          <div className="overflow-x-auto border-t">
            <table className="w-full min-w-[640px] text-left text-xs">
              <thead>
                <tr className="text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Market session</th>
                  <th className="px-3 py-2 font-medium">Close</th>
                  <th className="px-3 py-2 font-medium">Observed</th>
                  <th className="px-3 py-2 font-medium">Recorded</th>
                  <th className="px-3 py-2 font-medium">Source / quality</th>
                </tr>
              </thead>
              <tbody>
                {observations.slice(0, 60).map((item) => (
                  <tr key={item.id} className="border-t">
                    <td className="px-3 py-2">
                      {marketDate(item.market_date)}
                    </td>
                    <td className="px-3 py-2 tabular-nums">
                      {formatCurrency(item.split_adjusted_close, item.currency)}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {dateTime(item.observed_at)}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {dateTime(item.recorded_at)}
                    </td>
                    <td className="px-3 py-2">
                      <SourceReference
                        label={item.provider}
                        reference={item.data_quality}
                        href={
                          item.source_ref.startsWith("http")
                            ? item.source_ref
                            : null
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

function ExpectationChart({
  points,
  percentMode = false,
}: {
  points: ExpectedReturnHistoryPoint[];
  percentMode?: boolean;
}) {
  const lines = percentMode
    ? [
        {
          key: "expected_cash_flow_irr" as const,
          label: "Expected IRR",
          color: "hsl(var(--primary))",
        },
        {
          key: "hurdle" as const,
          label: "Hurdle",
          color: "hsl(var(--warning))",
        },
        {
          key: "expected_excess" as const,
          label: "Expected excess",
          color: "hsl(var(--positive))",
        },
      ]
    : [
        {
          key: "weighted_fv" as const,
          label: "Weighted Fair Value",
          color: "hsl(var(--primary))",
        },
        {
          key: "market_price" as const,
          label: "Comparable price",
          color: "hsl(var(--info))",
        },
      ];
  const getValue = (
    point: ExpectedReturnHistoryPoint,
    key: (typeof lines)[number]["key"],
  ) => (key === "market_price" ? comparablePrice(point) : point[key]);
  const dated = points.filter((point) => point.effective_at !== null);
  const numeric = lines.flatMap((line) =>
    dated
      .map((point) => getValue(point, line.key))
      .filter((value): value is string => value !== null)
      .map((value) => Number(value) * (percentMode ? 100 : 1))
      .filter(Number.isFinite),
  );
  if (dated.length === 0 || numeric.length === 0)
    return (
      <EmptyState
        title="No comparable expectation history"
        description="The selected series has no dated, currency-compatible values to plot. Undated or incompatible points remain in the audit list."
      />
    );
  const bounds = chartBounds(numeric);
  const width = 760;
  const height = 230;
  const left = 54;
  const right = 16;
  const top = 18;
  const bottom = 36;
  const times = dated.map((point) => parseTime(point.effective_at) ?? 0);
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const x = (time: number) =>
    left +
    (maxTime === minTime ? 0.5 : (time - minTime) / (maxTime - minTime)) *
      (width - left - right);
  const y = (value: number) =>
    top +
    ((bounds.high - value) / (bounds.high - bounds.low)) *
      (height - top - bottom);
  return (
    <div className="min-w-0">
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
        {lines.map((line) => (
          <span
            key={line.key}
            className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
          >
            <span
              className="size-2 rounded-full"
              style={{ backgroundColor: line.color }}
            />
            {line.label}
          </span>
        ))}
      </div>
      <svg
        role="img"
        aria-label={
          percentMode
            ? "Expected return history"
            : "Fair value and comparable price history"
        }
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
          x={left - 7}
          y={top + 4}
          textAnchor="end"
          className="fill-muted-foreground text-[10px]"
        >
          {percentMode
            ? `${bounds.high.toFixed(1)}%`
            : formatNumber(String(bounds.high), 2)}
        </text>
        <text
          x={left - 7}
          y={height - bottom + 4}
          textAnchor="end"
          className="fill-muted-foreground text-[10px]"
        >
          {percentMode
            ? `${bounds.low.toFixed(1)}%`
            : formatNumber(String(bounds.low), 2)}
        </text>
        <text
          x={left}
          y={height - 9}
          textAnchor="start"
          className="fill-muted-foreground text-[10px]"
        >
          {dateOnly(dated[0].effective_at!)}
        </text>
        <text
          x={width - right}
          y={height - 9}
          textAnchor="end"
          className="fill-muted-foreground text-[10px]"
        >
          {dateOnly(dated[dated.length - 1].effective_at!)}
        </text>
        {lines.map((line) => {
          let drawing = false;
          const path = dated
            .map((point, index) => {
              const raw = getValue(point, line.key);
              const value =
                raw === null ? null : Number(raw) * (percentMode ? 100 : 1);
              if (value === null || !Number.isFinite(value)) {
                drawing = false;
                return "";
              }
              const segment = `${drawing ? "L" : "M"}${x(times[index]).toFixed(2)},${y(value).toFixed(2)}`;
              drawing = true;
              return segment;
            })
            .join(" ");
          return (
            <g key={line.key}>
              <path
                d={path}
                fill="none"
                stroke={line.color}
                strokeWidth="2.2"
              />
              {dated.map((point, index) => {
                const raw = getValue(point, line.key);
                if (raw === null || !Number.isFinite(Number(raw))) return null;
                const value = Number(raw) * (percentMode ? 100 : 1);
                return (
                  <circle
                    key={`${point.point_id}:${line.key}`}
                    cx={x(times[index])}
                    cy={y(value)}
                    r="3"
                    fill={line.color}
                  >
                    <title>{`${dateOnly(point.effective_at!)} · ${line.label}: ${percentMode ? readablePercent(raw) : formatCurrency(raw, point.model_currency)}`}</title>
                  </circle>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function ExpectationsHistory({
  state,
  range,
  onInspect,
}: {
  state: {
    data?: CompanyExpectedReturnHistory;
    error?: string;
    retry: () => void;
  };
  range: HistoricalRange;
  onInspect: (point: ExpectedReturnHistoryPoint) => void;
}) {
  const [series, setSeries] = useState<string>("");
  const [chart, setChart] = useState<"VALUE" | "RETURN">("VALUE");
  if (!state.data)
    return <PendingOrError error={state.error} retry={state.retry} />;
  const points = state.data.history;
  const seriesOptions = [
    ...new Map(points.map((point) => [point.series_id, point])).values(),
  ];
  const selectedSeries =
    series ||
    seriesOptions.find((point) => point.is_current_at_cutoff)?.series_id ||
    seriesOptions[0]?.series_id ||
    "";
  const selectedPoints = filterByHistoricalRange(
    points.filter((point) => point.series_id === selectedSeries),
    range,
    pointTime,
  );
  const comparable = comparableExpectationPoints(selectedPoints);
  const current = state.data.current_calculations?.[0];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Accepted expectations over time</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Each point is a recorded model state. Imported legacy outputs and
            native revisions stay labeled separately.
          </p>
        </div>
        {seriesOptions.length > 0 && (
          <label className="grid gap-1 text-xs text-muted-foreground">
            Model series
            <select
              aria-label="Historical model series"
              value={selectedSeries}
              onChange={(event) => setSeries(event.target.value)}
              className="h-9 max-w-full rounded-md border bg-background px-2 text-sm text-foreground"
            >
              {seriesOptions.map((point) => (
                <option key={point.series_id} value={point.series_id}>
                  {point.model_label} · {point.source_kind.replaceAll("_", " ")}{" "}
                  · {point.model_currency ?? "Currency unknown"}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        <MetricCard
          label="Accepted model"
          value={current ? current.model_name : "Unavailable"}
          note={
            current
              ? `${current.methodology_version} · revision ${current.revision_number}`
              : "No current native calculation"
          }
        />
        <MetricCard
          label="Weighted Fair Value"
          value={
            current
              ? formatCurrency(
                  current.outputs.weighted_fv,
                  current.outputs.model_currency,
                )
              : "Unavailable"
          }
          note={current?.outputs.status ?? "No current output"}
        />
        <MetricCard
          label={expectedReturnLabel(
            current?.outputs.return_methodology?.perspective,
          )}
          value={
            current
              ? readablePercent(current.outputs.expected_cash_flow_irr)
              : "Unavailable"
          }
          note={
            current?.outputs.return_methodology?.title ?? "Method not available"
          }
        />
        <MetricCard
          label="Historical coverage"
          value={`${selectedPoints.length} point${selectedPoints.length === 1 ? "" : "s"}`}
          note={state.data.status.replaceAll("_", " ")}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/20 p-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <GitCompareArrows aria-hidden="true" className="size-4" />
          Comparable series: {comparable.length} dated point
          {comparable.length === 1 ? "" : "s"}. Incompatible currency, listing
          or later-known price points are excluded.
        </div>
        <div
          className="flex gap-1"
          role="group"
          aria-label="Expectation chart metric"
        >
          <Button
            size="sm"
            variant={chart === "VALUE" ? "secondary" : "ghost"}
            onClick={() => setChart("VALUE")}
          >
            Fair value / price
          </Button>
          <Button
            size="sm"
            variant={chart === "RETURN" ? "secondary" : "ghost"}
            onClick={() => setChart("RETURN")}
          >
            Return rates
          </Button>
        </div>
      </div>
      <ChartContainer
        title={
          chart === "VALUE"
            ? "Fair value and comparable price"
            : "Return output, hurdle and excess"
        }
        description={
          chart === "VALUE"
            ? "Only values with the same model currency, exact listing and point-in-time eligible price are plotted together."
            : "Rates are kept separate from price and fair-value units."
        }
      >
        <ExpectationChart
          points={chart === "VALUE" ? comparable : selectedPoints}
          percentMode={chart === "RETURN"}
        />
      </ChartContainer>
      <div className="rounded-lg border">
        <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
          <h3 className="text-sm font-medium">Model event history</h3>
          <Badge variant="secondary">{selectedPoints.length} points</Badge>
        </div>
        {selectedPoints.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">
            No model points are available in this range. Missing history is not
            interpreted as a neutral return.
          </p>
        ) : (
          <div className="divide-y">
            {selectedPoints.map((point) => (
              <button
                type="button"
                key={point.point_id}
                onClick={() => onInspect(point)}
                className="flex w-full min-w-0 items-center justify-between gap-3 px-3 py-3 text-left hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {point.model_label}
                    </span>
                    <StatusIndicator
                      status={point.source_kind}
                      label={
                        point.source_kind === "NATIVE_MODEL_REVISION"
                          ? "Native revision"
                          : "Imported output"
                      }
                    />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {point.effective_at
                      ? dateTime(point.effective_at)
                      : "Effective time unavailable"}{" "}
                    · recorded {dateTime(point.recorded_at)} ·{" "}
                    {point.methodology_version ?? point.return_semantics}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-right">
                  <div>
                    <p className="text-sm font-semibold tabular-nums">
                      {readablePercent(point.expected_cash_flow_irr)}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {expectedReturnLabel(
                        point.return_methodology?.perspective,
                      )}
                    </p>
                  </div>
                  <ChevronRight
                    aria-hidden="true"
                    className="size-4 text-muted-foreground"
                  />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        Fair Value is a valuation reference, not a prediction of the future
        stock price. Current calculations use the current canonical quote
        without creating a new model revision.
      </p>
    </div>
  );
}

function ForecastOutcome({
  state,
}: {
  state: { data?: CompanyTemporalAlignment; error?: string; retry: () => void };
}) {
  if (!state.data)
    return <PendingOrError error={state.error} retry={state.retry} />;
  const data = state.data;
  const values = [
    ["Consensus", data.consensus],
    ["Actual", data.actual],
  ] as const;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusIndicator status={data.comparison_status} />
        <span className="text-xs text-muted-foreground">
          Forecast known {dateTime(data.forecast_known_at)} · outcome known{" "}
          {dateTime(data.outcome_known_at)} · FY{data.fiscal_year}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {data.model_forecasts.slice(0, 2).map((model) => (
          <Card key={model.model_id} className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{model.model_name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <StatusIndicator status={model.status} />
              <p className="text-lg font-semibold tabular-nums">
                {model.value === null
                  ? "Unavailable"
                  : formatCurrency(model.value, model.model_currency)}
              </p>
              <p className="text-muted-foreground">
                {model.forecast_year
                  ? `FY${model.forecast_year}`
                  : "Forecast year unresolved"}{" "}
                · revision {model.revision_number ?? "unknown"}
              </p>
              <p className="text-muted-foreground">
                Source: {model.revision_source ?? "Unavailable"}
              </p>
              <p className="text-muted-foreground">
                Price at forecast:{" "}
                {model.price_at_forecast.close === null
                  ? statusLabel(model.price_at_forecast.status)
                  : formatCurrency(
                      model.price_at_forecast.close,
                      model.price_at_forecast.currency,
                    )}
              </p>
            </CardContent>
          </Card>
        ))}
        {values.map(([label, value]) => (
          <Card key={label} className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{label}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <StatusIndicator status={value.status} />
              <p className="text-lg font-semibold tabular-nums">
                {value.value === null
                  ? "Unavailable"
                  : formatCurrency(value.value, value.currency)}
              </p>
              <p className="text-muted-foreground">
                {value.unit ?? "Unit unavailable"} · effective{" "}
                {value.effective_at
                  ? dateTime(value.effective_at)
                  : "not recorded"}
              </p>
              <p className="text-muted-foreground">
                Source: {value.source_name ?? "Unavailable"}
              </p>
              <p className="text-muted-foreground">
                {value.quality_reason ??
                  "Source and point-in-time constraints are shown in the status."}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function DecisionHistory({
  rankings,
  execution,
}: {
  rankings: { data?: CompanyRankings; error?: string; retry: () => void };
  execution: { data?: CompanyExecutionPace; error?: string; retry: () => void };
}) {
  if (!rankings.data || !execution.data)
    return (
      <div className="grid gap-3 md:grid-cols-2">
        <PendingOrError error={rankings.error} retry={rankings.retry} />
        <PendingOrError error={execution.error} retry={execution.retry} />
      </div>
    );
  const current = rankings.data.current;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        {current.map((item) => (
          <Card key={item.definition.ranking_type} className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{item.definition.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <p className="text-xl font-semibold tabular-nums">
                {item.entry?.status === "RANKED"
                  ? `#${item.entry.position}`
                  : item.entry
                    ? statusLabel(item.entry.status)
                    : "No run recorded"}
              </p>
              <StatusIndicator
                status={item.entry?.status ?? item.run?.status ?? "UNAVAILABLE"}
              />
              <p className="text-muted-foreground">
                {item.entry?.reason ?? item.definition.methodology}
              </p>
              {item.run && (
                <p className="text-muted-foreground">
                  Run as of {dateTime(item.run.as_of)} · recorded{" "}
                  {dateTime(item.run.recorded_at)}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="shadow-none">
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-sm">Recorded decision history</CardTitle>
            <Badge variant="secondary">
              {rankings.data.history.length + execution.data.history.length}{" "}
              snapshots
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs leading-5 text-muted-foreground">
            Ranking and Execution Pace entries are immutable snapshots with the
            original run context. They are recorded decisions, not recalculated
            historical what-if results.
          </p>
          <div className="grid gap-2 md:grid-cols-2">
            {rankings.data.history.slice(0, 8).map((item) => (
              <DecisionRow
                key={`rank:${item.entry.id}`}
                title={`${item.run.definition.title} · ${item.entry.status === "RANKED" ? `#${item.entry.position}` : statusLabel(item.entry.status)}`}
                status={item.entry.status}
                asOf={item.run.as_of}
                recordedAt={item.run.recorded_at}
                reason={item.entry.reason}
              />
            ))}
            {execution.data.history.slice(0, 8).map((item) => (
              <DecisionRow
                key={`execution:${item.decision.id}`}
                title={
                  item.decision.pace
                    ? statusLabel(item.decision.pace)
                    : statusLabel(item.decision.decision_status)
                }
                status={item.decision.decision_status}
                asOf={item.run.as_of}
                recordedAt={item.run.recorded_at}
                reason={item.decision.reason}
              />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function DecisionRow({
  title,
  status,
  asOf,
  recordedAt,
  reason,
}: {
  title: string;
  status: string;
  asOf: string;
  recordedAt: string;
  reason: string;
}) {
  return (
    <div className="rounded-lg border p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{title}</span>
        <StatusIndicator status={status} />
      </div>
      <p className="mt-2 leading-5">{reason}</p>
      <p className="mt-2 text-muted-foreground">
        Decision run {dateTime(asOf)} · recorded {dateTime(recordedAt)}
      </p>
    </div>
  );
}

function EstimateSummary({
  state,
}: {
  state: { data?: CompanyEstimateMomentum; error?: string; retry: () => void };
}) {
  if (!state.data)
    return <PendingOrError error={state.error} retry={state.retry} />;
  const data = state.data;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-4">
        <MetricCard
          label="Momentum"
          value={data.direction ? statusLabel(data.direction) : "Unavailable"}
          note={statusLabel(data.availability)}
        />
        <MetricCard
          label="Coverage"
          value={`${data.coverage_count}/${data.coverage_total}`}
          note={`${readablePercent(data.confidence)} confidence · ${statusLabel(data.confidence_band)}`}
        />
        <MetricCard
          label="Provider"
          value={data.provider_id ?? "Unavailable"}
          note={
            data.latest_snapshot_date
              ? `Latest ${dateOnly(data.latest_snapshot_date)}`
              : "No dated snapshot"
          }
        />
        <MetricCard
          label="Freshness"
          value={statusLabel(data.freshness)}
          note={data.reason ?? "No additional quality note"}
        />
      </div>
      {data.periods.length === 0 ? (
        <EmptyState
          title="No estimate revision series"
          description="A current or historical consensus point with a resolved fiscal period is required. Missing consensus is not neutral momentum."
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.periods.map((period) => (
            <Card
              key={`${period.metric}:${period.period_end}`}
              className="shadow-none"
            >
              <CardHeader className="pb-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-sm">
                    {statusLabel(period.metric)} · {period.horizon}
                  </CardTitle>
                  <StatusIndicator status={period.data_quality} />
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <p className="text-lg font-semibold tabular-nums">
                  {period.current_value === null
                    ? "Unavailable"
                    : `${period.currency ?? "Currency unknown"} ${quantity(period.current_value)}`}
                </p>
                <p className="text-muted-foreground">
                  FY end {dateOnly(period.period_end)} · snapshot{" "}
                  {period.current_snapshot_date
                    ? dateOnly(period.current_snapshot_date)
                    : "not recorded"}{" "}
                  · Analyst coverage: {period.analyst_count ?? "not reported"}
                </p>
                <div className="grid grid-cols-3 gap-2 border-t pt-2">
                  {period.windows.map((window) => (
                    <div key={window.window}>
                      <p className="text-muted-foreground">{window.window}</p>
                      <p className="mt-1 font-medium tabular-nums">
                        {window.revision_fraction === null
                          ? "Unavailable"
                          : readablePercent(window.revision_fraction)}
                      </p>
                      <StatusIndicator
                        status={window.status}
                        className="mt-1 text-[10px]"
                      />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function ThesisContext({
  state,
}: {
  state: { data?: CompanyInvestmentThesis; error?: string; retry: () => void };
}) {
  if (!state.data)
    return (
      <EmptyState
        title="Thesis history unavailable"
        description={
          state.error ??
          "No accepted thesis revisions are available for this company."
        }
      />
    );
  const revisions = state.data.streams.flatMap((stream) =>
    stream.history.map((revision) => ({ stream, revision })),
  );
  const current = state.data.streams[0]?.current_revision;
  return (
    <div className="grid gap-3 md:grid-cols-[minmax(0,1.4fr)_minmax(220px,.6fr)]">
      <Card className="shadow-none">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Latest thesis context</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-6">
            {current?.thesis_statement ?? "No accepted thesis statement."}
          </p>
          <p className="mt-3 text-xs text-muted-foreground">
            Observed {current ? dateTime(current.observed_at) : "unknown"} ·
            recorded {current ? dateTime(current.recorded_at) : "unknown"} ·
            confidence{" "}
            {current ? statusLabel(current.confidence) : "unavailable"}
          </p>
        </CardContent>
      </Card>
      <Card className="shadow-none">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Thesis history</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-semibold tabular-nums">
            {revisions.length}
          </p>
          <p className="text-xs text-muted-foreground">
            accepted revision{revisions.length === 1 ? "" : "s"} available in
            the selected stream.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export function CompanyHistoricalAnalysisWorkspace({
  companyId,
  marketState,
}: {
  companyId: string;
  marketState: MarketState;
}) {
  const [range, setRange] = useState<HistoricalRange>("1Y");
  const [eventFilter, setEventFilter] = useState<HistoricalEventKind | "ALL">(
    "ALL",
  );
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const [fiscalYear, setFiscalYear] = useState(
    String(new Date().getUTCFullYear() + 1),
  );
  const [horizonDays, setHorizonDays] = useState("365");
  const [showAllTimelineEvents, setShowAllTimelineEvents] = useState(false);
  const [selectedPoint, setSelectedPoint] =
    useState<ExpectedReturnHistoryPoint | null>(null);
  const [selectedTimelineEvent, setSelectedTimelineEvent] =
    useState<HistoricalTimelineEvent | null>(null);
  const expectedState = useResearch(
    `companies/${encodeURIComponent(companyId)}/expected-return-history`,
    isCompanyExpectedReturnHistory,
  );
  const momentumState = useResearch(
    `companies/${encodeURIComponent(companyId)}/estimate-momentum`,
    isCompanyEstimateMomentum,
  );
  const rankingsState = useResearch(
    `companies/${encodeURIComponent(companyId)}/rankings`,
    isCompanyRankings,
  );
  const executionState = useResearch(
    `companies/${encodeURIComponent(companyId)}/execution-pace`,
    isCompanyExecutionPace,
  );
  const temporalState = useResearch(
    `companies/${encodeURIComponent(companyId)}/temporal-alignment?fiscal_year=${encodeURIComponent(fiscalYear)}&as_of=${encodeURIComponent(asOf)}&horizon_days=${encodeURIComponent(horizonDays)}`,
    isCompanyTemporalAlignment,
  );
  const thesisState = useResearch(
    `companies/${encodeURIComponent(companyId)}/thesis`,
    isCompanyInvestmentThesis,
  );
  const events = useMemo(
    () =>
      buildHistoricalTimelineEvents({
        expectedReturn: expectedState.data,
        rankings: rankingsState.data,
        execution: executionState.data,
        momentum: momentumState.data,
        thesis: thesisState.data,
      }),
    [
      expectedState.data,
      executionState.data,
      momentumState.data,
      rankingsState.data,
      thesisState.data,
    ],
  );
  const filteredEvents = events
    .filter((event) => eventFilter === "ALL" || event.kind === eventFilter)
    .filter(
      (event) =>
        range === "ALL" ||
        filterByHistoricalRange([event], range, (item) => item.eventAt)[0],
    );
  const visibleEvents = showAllTimelineEvents
    ? filteredEvents
    : filteredEvents.slice(0, 12);
  const selectedEvent = selectedPoint
    ? {
        title: selectedPoint.model_label,
        description: "Accepted model point and its source context",
        body: (
          <div className="space-y-4 text-sm">
            <dl className="grid gap-2 sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">Effective</dt>
                <dd>
                  {selectedPoint.effective_at
                    ? dateTime(selectedPoint.effective_at)
                    : "Unknown"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Recorded</dt>
                <dd>{dateTime(selectedPoint.recorded_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Method</dt>
                <dd>
                  {selectedPoint.methodology_version ??
                    statusLabel(selectedPoint.model_type)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Source kind</dt>
                <dd>{statusLabel(selectedPoint.source_kind)}</dd>
              </div>
            </dl>
            <p className="leading-6">
              {selectedPoint.rationale ?? "No rationale recorded."}
            </p>
            <p className="leading-6 text-muted-foreground">
              {selectedPoint.evidence ?? "No additional evidence recorded."}
            </p>
            <SourceReference
              label={selectedPoint.source ?? "Source unavailable"}
              reference={selectedPoint.source_revision_id}
              href={
                selectedPoint.source?.startsWith("http")
                  ? selectedPoint.source
                  : null
              }
            />
          </div>
        ),
      }
    : selectedTimelineEvent
      ? {
          title: selectedTimelineEvent.title,
          description: `${eventLabel(selectedTimelineEvent.kind)} source context`,
          body: (
            <div className="space-y-4 text-sm">
              <dl className="grid gap-2 sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">
                    Effective / event time
                  </dt>
                  <dd>
                    {selectedTimelineEvent.eventAt
                      ? dateTime(selectedTimelineEvent.eventAt)
                      : "Unavailable"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Recorded</dt>
                  <dd>
                    {selectedTimelineEvent.recordedAt
                      ? dateTime(selectedTimelineEvent.recordedAt)
                      : "Unavailable"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Status</dt>
                  <dd>{statusLabel(selectedTimelineEvent.status)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Source</dt>
                  <dd>{selectedTimelineEvent.source ?? "Unavailable"}</dd>
                </div>
              </dl>
              <p className="leading-6">{selectedTimelineEvent.detail}</p>
              <SourceReference
                label={selectedTimelineEvent.source ?? "Source unavailable"}
                reference={selectedTimelineEvent.sourceReference}
                href={
                  selectedTimelineEvent.sourceReference?.startsWith("http")
                    ? selectedTimelineEvent.sourceReference
                    : null
                }
              />
            </div>
          ),
        }
      : null;
  return (
    <section
      id="historical-analysis"
      aria-labelledby="historical-analysis-title"
      className="space-y-8"
    >
      <div className="rounded-xl border bg-card p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <History aria-hidden="true" className="size-5 text-primary" />
              <h2
                id="historical-analysis-title"
                className="text-xl font-semibold tracking-tight"
              >
                Historical analysis
              </h2>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              How market prices, our expectations and our investment decisions
              changed over time. Each source keeps its own effective, observed,
              recorded and decision-run timestamps.
            </p>
          </div>
          <div
            className="flex flex-wrap gap-1"
            role="group"
            aria-label="Historical date range"
          >
            {RANGE_OPTIONS.map((option) => (
              <Button
                key={option.value}
                size="sm"
                variant={range === option.value ? "secondary" : "ghost"}
                aria-pressed={range === option.value}
                onClick={() => setRange(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <MetricCard
            label="Price history"
            value={
              marketState.data?.reduce(
                (count, item) =>
                  count +
                  filterByHistoricalRange(
                    item.history,
                    range,
                    (observation) => observation.market_date,
                  ).length,
                0,
              ) ?? "Unavailable"
            }
            note="Exact-listing observations in range"
          />
          <MetricCard
            label="Expectation history"
            value={
              expectedState.data
                ? `${expectedState.data.history.length} points`
                : "Loading"
            }
            note={
              expectedState.data?.status.replaceAll("_", " ") ??
              "Point-in-time model records"
            }
          />
          <MetricCard
            label="Recorded decisions"
            value={
              rankingsState.data && executionState.data
                ? `${rankingsState.data.history.length + executionState.data.history.length}`
                : "Loading"
            }
            note="Ranking and Execution Pace snapshots"
          />
        </div>
      </div>
      <PageSection
        title="Market history"
        description="What the exact listing was worth in each market session, with canonical analytics and freshness."
        id="market-history"
      >
        <MarketHistory marketState={marketState} range={range} />
      </PageSection>
      <PageSection
        title="Expectations history"
        description="How accepted valuation and return expectations changed, while preserving methodology and return-basis differences."
        id="expectations-history"
      >
        <ExpectationsHistory
          state={expectedState}
          range={range}
          onInspect={(point) => {
            setSelectedTimelineEvent(null);
            setSelectedPoint(point);
          }}
        />
        <section
          className="mt-6"
          role="region"
          aria-labelledby="historical-forecast-outcome-title"
        >
          <h3
            id="historical-forecast-outcome-title"
            className="text-base font-semibold"
          >
            Forecast vs. outcome
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            A point-in-time comparison; later actuals are never shown as
            information available before publication.
          </p>
          <div className="mt-3 rounded-lg border p-3">
            <div className="mb-3 grid gap-2 sm:grid-cols-3">
              <label className="grid gap-1 text-xs text-muted-foreground">
                Fiscal year
                <input
                  aria-label="Historical fiscal year"
                  type="number"
                  value={fiscalYear}
                  onChange={(event) => setFiscalYear(event.target.value)}
                  className="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
                />
              </label>
              <label className="grid gap-1 text-xs text-muted-foreground">
                Forecast date
                <input
                  aria-label="Historical forecast date"
                  type="date"
                  value={asOf}
                  onChange={(event) => setAsOf(event.target.value)}
                  className="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
                />
              </label>
              <label className="grid gap-1 text-xs text-muted-foreground">
                Outcome horizon
                <select
                  aria-label="Historical return horizon"
                  value={horizonDays}
                  onChange={(event) => setHorizonDays(event.target.value)}
                  className="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
                >
                  <option value="90">90 days</option>
                  <option value="180">180 days</option>
                  <option value="365">1 year</option>
                  <option value="730">2 years</option>
                </select>
              </label>
            </div>
            <ForecastOutcome state={temporalState} />
          </div>
        </section>
        <div className="mt-6">
          <h3 className="text-base font-semibold">Estimate Momentum</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Revision direction and coverage are contextual. Sparse or stale
            consensus remains explicitly unavailable.
          </p>
          <div className="mt-3">
            <EstimateSummary state={momentumState} />
          </div>
        </div>
        <div className="mt-6">
          <h3 className="text-base font-semibold">Thesis developments</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Research confidence and thesis revisions are shown as recorded
            context, separate from factual observations and model outputs.
          </p>
          <div className="mt-3">
            <ThesisContext state={thesisState} />
          </div>
        </div>
      </PageSection>
      <PageSection
        title="Decision history"
        description="Recorded ranking and Execution Pace outcomes with the run context used at that time. Historical entries are not recomputed from today's state."
        id="decision-history"
      >
        <DecisionHistory rankings={rankingsState} execution={executionState} />
      </PageSection>
      <PageSection
        title="Change timeline"
        description="Filter the dated events that connect market, model, research and decision history. Event times and recorded times remain separate."
        id="change-timeline"
        actions={
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <SlidersHorizontal aria-hidden="true" className="size-4" />
            <span className="sr-only">Event type</span>
            <select
              aria-label="Historical event type"
              value={eventFilter}
              onChange={(event) =>
                setEventFilter(
                  event.target.value as HistoricalEventKind | "ALL",
                )
              }
              className="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
            >
              {EVENT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        }
      >
        <div className="space-y-2">
          {filteredEvents.length === 0 ? (
            <EmptyState
              title="No events in this range"
              description="No dated source event matches the selected time range and filter. Missing history remains visible as unavailable in its source section."
            />
          ) : (
            visibleEvents.map((event) => (
              <div
                key={event.id}
                className="flex min-w-0 items-start gap-3 rounded-lg border p-3"
              >
                <div className="mt-1 rounded-full bg-primary/10 p-1.5 text-primary">
                  <LineChart aria-hidden="true" className="size-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold">
                      {eventLabel(event.kind)}
                    </span>
                    <StatusIndicator
                      status={event.status}
                      label={statusLabel(event.status)}
                    />
                  </div>
                  <p className="mt-1 break-words text-sm font-medium">
                    {event.title}
                  </p>
                  <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">
                    {event.summary}
                  </p>
                  <p className="mt-2 text-[10px] text-muted-foreground">
                    {event.eventAt
                      ? `Effective ${dateTime(event.eventAt)}`
                      : "Effective time unavailable"}{" "}
                    · recorded{" "}
                    {event.recordedAt ? dateTime(event.recordedAt) : "unknown"}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSelectedPoint(null);
                    setSelectedTimelineEvent(event);
                  }}
                  aria-label={`Inspect ${event.title}`}
                >
                  <Search aria-hidden="true" className="size-4" />
                  <span className="sr-only">Inspect</span>
                </Button>
              </div>
            ))
          )}
          {filteredEvents.length > 12 && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
              <p className="text-xs text-muted-foreground">
                Showing {visibleEvents.length} of {filteredEvents.length} dated
                events in this filter.
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowAllTimelineEvents((current) => !current)}
              >
                {showAllTimelineEvents
                  ? "Show fewer events"
                  : "Show more events"}
              </Button>
            </div>
          )}
        </div>
      </PageSection>
      <div className="rounded-lg border border-dashed bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
        <div className="flex items-start gap-2">
          <Clock3 aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <p>
            Historical series do not share one coverage window. Market session
            dates, source observation dates, model effective times and decision
            run times are preserved independently. Price-only history does not
            imply dividend-inclusive portfolio performance.
          </p>
        </div>
      </div>
      <DetailDrawer
        open={selectedEvent !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedPoint(null);
            setSelectedTimelineEvent(null);
          }
        }}
        title={selectedEvent?.title ?? "Historical detail"}
        description={selectedEvent?.description}
      >
        {selectedEvent?.body}
      </DetailDrawer>
    </section>
  );
}
