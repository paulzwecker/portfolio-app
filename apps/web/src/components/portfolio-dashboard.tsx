"use client";

import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExecutionPaceCompact } from "@/components/execution-pace";
import {
  type CompanyPortfolioContext,
  type EstimateMomentumSummary,
  type ModelOutputSnapshot,
  type Overview,
  type RankingCurrent,
  type RankingType,
  type UniverseEstimateMomentumSummary,
  type UniverseExecutionPaceSummary,
  type UniverseModelOutputSummary,
  type UniverseRankingSummary,
  type UniverseScoreSummary,
} from "@/lib/domain-contracts";
import { date, percent, quantity } from "@/lib/display";

const scoreLabels = [
  ["DURABILITY_10Y", "10Y Durability"],
  ["COMPOUNDER_QUALITY", "Compounder Quality"],
  ["EXECUTION", "Business Execution"],
  ["RISK", "Risk"],
] as const;

export function money(value: string | null, currency: string | null) {
  if (value === null) return "Unavailable";
  if (!currency) return `${quantity(value)} · currency unknown`;
  try {
    return new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(Number(value));
  } catch {
    return `${quantity(value)} ${currency}`;
  }
}

export function ratio(value: string | null, missing = "Unavailable") {
  return value === null ? missing : percent(value);
}

export function readable(
  value: string | null | undefined,
  missing = "Unavailable",
) {
  return value ? value.replaceAll("_", " ") : missing;
}

export function rankingFor(
  rows: UniverseRankingSummary[] | undefined,
  companyId: string,
  type: RankingType,
): RankingCurrent | undefined {
  return rows
    ?.find((item) => item.company.id === companyId)
    ?.rankings.find((item) => item.definition.ranking_type === type);
}

function rankLabel(current: RankingCurrent | undefined) {
  if (!current?.run) return "No run";
  if (current.entry?.status === "RANKED" && current.entry.position !== null)
    return `#${current.entry.position}`;
  return readable(current.entry?.status, "No company result");
}

function rankContext(current: RankingCurrent | undefined) {
  const input = current?.entry?.input_snapshot;
  return input?.context_version === "portfolio-rank-inputs-v1" ? input : null;
}

function scoreValue(
  rows: UniverseScoreSummary[] | undefined,
  companyId: string,
  dimension: (typeof scoreLabels)[number][0],
) {
  const assessment = rows
    ?.find((item) => item.company.id === companyId)
    ?.scores.find(
      (item) => item.definition.dimension === dimension,
    )?.assessment;
  if (!assessment) return "Not assessed";
  return assessment.score === null
    ? readable(assessment.status)
    : `${quantity(assessment.score)} / 5`;
}

function modelCurrency(outputs: UniverseModelOutputSummary["outputs"]) {
  if (outputs.models.length !== 1) return null;
  return outputs.models[0].snapshot.model_currency;
}

function currentSnapshot(
  outputs: UniverseModelOutputSummary["outputs"],
): ModelOutputSnapshot | null {
  return outputs.models.length === 1 ? outputs.models[0].snapshot : null;
}

export function momentumFor(
  rows: UniverseEstimateMomentumSummary[] | undefined,
  companyId: string,
): EstimateMomentumSummary | undefined {
  return rows?.find((item) => item.company.id === companyId)?.estimate_momentum;
}

function momentumLabel(signal: EstimateMomentumSummary | undefined) {
  if (!signal) return "Loading";
  if (signal.direction) return readable(signal.direction);
  return readable(signal.availability);
}

export function sortedByGap(rows: CompanyPortfolioContext[]) {
  return [...rows].sort((left, right) => {
    if (left.allocation_gap === null)
      return right.allocation_gap === null ? 0 : 1;
    if (right.allocation_gap === null) return -1;
    return (
      Math.abs(Number(right.allocation_gap)) -
      Math.abs(Number(left.allocation_gap))
    );
  });
}

export function sortedByWeight(rows: CompanyPortfolioContext[]) {
  return [...rows].sort((left, right) => {
    if (left.current_weight === null)
      return right.current_weight === null ? 0 : 1;
    if (right.current_weight === null) return -1;
    return Number(right.current_weight) - Number(left.current_weight);
  });
}

function gapMeaning(value: string | null) {
  if (value === null) return "Gap unavailable";
  const amount = Number(value);
  if (amount > 0) return "Below target";
  if (amount < 0) return "Above target";
  return "At target";
}

export function MetricCard({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p
          className="truncate text-xl font-semibold tabular-nums"
          title={value}
        >
          {value}
        </p>
        <p className="mt-1 min-h-8 text-xs leading-4 text-muted-foreground">
          {note}
        </p>
      </CardContent>
    </Card>
  );
}

export function ExecutionSummaryCard({
  rows,
}: {
  rows: UniverseExecutionPaceSummary[] | undefined;
}) {
  const run = rows?.find((item) => item.decision)?.decision?.run;
  return (
    <MetricCard
      label="Latest Execution Pace"
      value={run ? readable(run.status) : "No run recorded"}
      note={
        run
          ? `${run.available_count} available · ${run.review_count} review · as of ${date(run.as_of)}`
          : rows
            ? "No decision history; no neutral pace is implied."
            : "Decision history is loading."
      }
    />
  );
}

export function RunBadge({ current }: { current: RankingCurrent | undefined }) {
  if (!current?.run) return <Badge variant="secondary">No run recorded</Badge>;
  return (
    <Badge
      variant={current.run.status === "COMPLETE" ? "default" : "secondary"}
    >
      {readable(current.run.status)} · {date(current.run.as_of)}
    </Badge>
  );
}

export function GapRow({ row }: { row: CompanyPortfolioContext }) {
  const gap = row.allocation_gap;
  const isUnder = gap !== null && Number(gap) > 0;
  const Icon =
    gap === null || Number(gap) === 0
      ? Minus
      : isUnder
        ? ArrowUpRight
        : ArrowDownRight;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 py-2.5 hover:bg-secondary/40 sm:grid-cols-[minmax(0,1.2fr)_auto_auto_auto]">
      <Link
        href={`/company/${row.company.id}`}
        className="min-w-0 truncate text-sm font-medium hover:text-primary"
      >
        {row.company.name}
      </Link>
      <span className="text-right text-xs tabular-nums text-muted-foreground">
        {ratio(row.current_weight, readable(row.allocation_status))} →{" "}
        {ratio(row.target_weight, "No target")}
      </span>
      <span
        className={`flex items-center justify-end gap-1 text-sm font-semibold tabular-nums ${isUnder ? "text-amber-800 dark:text-amber-300" : ""}`}
      >
        <Icon aria-hidden="true" className="size-3.5" /> {ratio(gap)}
      </span>
      <span className="col-span-2 text-right text-[10px] uppercase tracking-wide text-muted-foreground sm:col-span-1">
        {gapMeaning(gap)}
      </span>
    </div>
  );
}

export function OpportunityRow({
  company,
  ranking,
  outputs,
  scores,
  momentum,
  currentWeight,
  targetWeight,
  allocationGap,
  currentValue,
  valueCurrency,
  positions,
  snapshotCompleteness,
  pace,
}: {
  company: CompanyPortfolioContext["company"];
  ranking: RankingCurrent | undefined;
  outputs: UniverseModelOutputSummary["outputs"] | undefined;
  scores: UniverseScoreSummary[] | undefined;
  momentum: EstimateMomentumSummary | undefined;
  currentWeight: string | null;
  targetWeight: string | null;
  allocationGap: string | null;
  currentValue: string | null;
  valueCurrency: string | null;
  positions: CompanyPortfolioContext["positions"];
  snapshotCompleteness: string | null;
  pace: NonNullable<UniverseExecutionPaceSummary["decision"]> | null;
}) {
  const context = rankContext(ranking);
  const gapUnder = allocationGap !== null && Number(allocationGap) > 0;
  return (
    <article className="grid gap-3 px-4 py-4 sm:px-5 lg:grid-cols-[minmax(175px,1.1fr)_repeat(3,minmax(0,1fr))] lg:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/company/${company.id}`}
            className="truncate text-sm font-semibold hover:text-primary"
          >
            {company.name}
          </Link>
          <Badge
            variant={
              ranking?.entry?.status === "RANKED" ? "default" : "secondary"
            }
          >
            Portfolio {rankLabel(ranking)}
          </Badge>
        </div>
        <p className="mt-1 truncate text-xs text-muted-foreground">
          {company.lifecycle ?? "Lifecycle unassigned"} ·{" "}
          {currentValue === null
            ? "Value unavailable"
            : money(currentValue, valueCurrency)}
        </p>
        <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted-foreground">
          {positions.length > 0
            ? positions
                .map(
                  (position) =>
                    `${position.ticker} · ${position.venue} · ${quantity(position.quantity)} shares · ${money(position.latest_price, position.price_currency)} · ${readable(position.price_freshness)}`,
                )
                .join("; ")
            : snapshotCompleteness === "COMPLETE"
              ? "No security position in the complete holdings snapshot."
              : "No position record; holdings may be partial or unavailable."}
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs lg:block">
        <MetricPair label="Current" value={ratio(currentWeight)} />
        <MetricPair label="Target" value={ratio(targetWeight, "No target")} />
        <MetricPair
          label="Gap"
          value={ratio(allocationGap)}
          emphasis={gapUnder}
        />
      </div>
      <AttractivenessSummary
        outputs={outputs}
        snapshotIrr={context?.expected_irr ?? null}
      />
      <div className="grid grid-cols-2 gap-2 text-xs lg:grid-cols-1">
        <SignalChip
          label="Execution Pace"
          value={
            pace
              ? (pace.decision.pace ?? readable(pace.decision.decision_status))
              : "No run"
          }
          note={pace ? date(pace.run.as_of) : "No decision history"}
          warning={pace?.decision.decision_status === "REVIEW"}
        />
        <SignalChip
          label="Estimate Momentum"
          value={momentumLabel(momentum)}
          note={
            momentum
              ? `${readable(momentum.freshness)} · ${readable(momentum.confidence_band)}`
              : "No observation"
          }
          warning={momentum !== undefined && momentum.freshness !== "FRESH"}
        />
      </div>
      <details className="rounded-md border bg-secondary/20 p-3 text-xs lg:col-span-4">
        <summary className="cursor-pointer font-medium">
          Quality, model and decision evidence
        </summary>
        <div className="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <ScoreSummary scores={scores} companyId={company.id} />
          <ModelOutputsSummary outputs={outputs} />
          <MomentumSummary signal={momentum} />
          <div>
            <p className="font-medium">Portfolio Rank snapshot</p>
            <p className="mt-1 text-muted-foreground">
              {context
                ? `As of ${ranking?.run ? date(ranking.run.as_of) : "unknown"} · score ${context.portfolio_score === null ? "Unavailable" : `${quantity(context.portfolio_score)} / 100`}`
                : (ranking?.entry?.reason ??
                  "No rank input snapshot is available.")}
            </p>
            {pace && (
              <details className="mt-2 rounded border p-2">
                <summary className="cursor-pointer font-medium">
                  Execution Pace source inputs
                </summary>
                <ExecutionPaceCompact entry={pace} />
              </details>
            )}
          </div>
        </div>
      </details>
    </article>
  );
}

export function WatchlistOpportunityRow({
  item,
  ranking,
  outputs,
  scores,
  momentum,
}: {
  item: UniverseRankingSummary;
  ranking: RankingCurrent | undefined;
  outputs: UniverseModelOutputSummary["outputs"] | undefined;
  scores: UniverseScoreSummary[] | undefined;
  momentum: EstimateMomentumSummary | undefined;
}) {
  const input = ranking?.entry?.input_snapshot;
  const watchlistContext =
    input?.context_version === "watchlist-rank-inputs-v1" ? input : null;
  return (
    <article className="grid gap-3 px-4 py-4 sm:px-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/company/${item.company.id}`}
            className="truncate text-sm font-semibold hover:text-primary"
          >
            {item.company.name}
          </Link>
          <Badge
            variant={
              ranking?.entry?.status === "RANKED" ? "default" : "secondary"
            }
          >
            Watchlist {rankLabel(ranking)}
          </Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {watchlistContext
            ? `Rank snapshot · Expected IRR ${ratio(watchlistContext.expected_irr)} · ${readable(watchlistContext.return_semantics)}`
            : (ranking?.entry?.reason ??
              "No rank input snapshot is available.")}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2 md:min-w-72">
        <AttractivenessSummary
          outputs={outputs}
          snapshotIrr={watchlistContext?.expected_irr ?? null}
        />
        <SignalChip
          label="Estimate Momentum"
          value={momentumLabel(momentum)}
          note={
            momentum
              ? `${readable(momentum.freshness)} · ${readable(momentum.confidence_band)}`
              : "No observation"
          }
          warning={momentum !== undefined && momentum.freshness !== "FRESH"}
        />
      </div>
      <details className="rounded-md border bg-secondary/20 p-3 text-xs md:col-span-2">
        <summary className="cursor-pointer font-medium">
          Quality, model and source evidence
        </summary>
        <div className="mt-3 grid gap-4 md:grid-cols-3">
          <ScoreSummary scores={scores} companyId={item.company.id} />
          <ModelOutputsSummary outputs={outputs} />
          <MomentumSummary signal={momentum} />
        </div>
        {watchlistContext && (
          <p className="mt-3 border-t pt-3 text-muted-foreground">
            Source:{" "}
            {watchlistContext.return_source.source ?? "Source unavailable"} ·{" "}
            {watchlistContext.return_source.model_key ?? "Model unavailable"} ·{" "}
            {watchlistContext.return_source.model_currency ??
              "Currency unknown"}{" "}
            · recorded {date(watchlistContext.return_source.recorded_at)}
          </p>
        )}
      </details>
    </article>
  );
}

function MetricPair({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p
        className={`mt-0.5 font-semibold tabular-nums ${emphasis ? "text-amber-800 dark:text-amber-300" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}

function SignalChip({
  label,
  value,
  note,
  warning,
}: {
  label: string;
  value: string;
  note: string;
  warning: boolean;
}) {
  return (
    <div className="min-w-0 rounded-md border px-2.5 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 truncate font-semibold" title={value}>
        {value}
      </p>
      <p
        className={`mt-0.5 truncate text-[10px] ${warning ? "text-amber-800 dark:text-amber-300" : "text-muted-foreground"}`}
      >
        {note}
      </p>
    </div>
  );
}

function AttractivenessSummary({
  outputs,
  snapshotIrr,
}: {
  outputs: UniverseModelOutputSummary["outputs"] | undefined;
  snapshotIrr: string | null;
}) {
  const snapshot = outputs ? currentSnapshot(outputs) : null;
  const currency = outputs ? modelCurrency(outputs) : null;
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
      <MetricPair
        label="Current Expected IRR"
        value={
          snapshot
            ? ratio(snapshot.expected_cash_flow_irr)
            : outputs?.models.length === 1
              ? "Unavailable"
              : readable(outputs?.status, "Loading")
        }
      />
      <MetricPair
        label="Hurdle"
        value={
          snapshot
            ? ratio(snapshot.hurdle)
            : snapshotIrr === null
              ? "Unavailable"
              : "Snapshot only"
        }
      />
      <p className="col-span-2 mt-1 truncate text-[10px] text-muted-foreground">
        {snapshot
          ? `Weighted FV ${money(snapshot.weighted_fv, currency)} · upside ${ratio(snapshot.weighted_upside)} · ${readable(snapshot.output_quality)}`
          : snapshotIrr !== null
            ? `Rank-time Expected IRR ${ratio(snapshotIrr)} · current model output ${readable(outputs?.status, "Loading")}`
            : outputs?.models.length && outputs.models.length > 1
              ? `${outputs.models.length} model outputs · open evidence to inspect each`
              : `${readable(outputs?.status, "Model output loading")}; values remain unavailable`}
      </p>
    </div>
  );
}

function ScoreSummary({
  scores,
  companyId,
}: {
  scores: UniverseScoreSummary[] | undefined;
  companyId: string;
}) {
  return (
    <div>
      <p className="font-medium">Quality and risk assessments</p>
      <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
        {scoreLabels.map(([dimension, label]) => (
          <div key={dimension}>
            <dt className="text-[10px]">
              {label}
              {dimension === "RISK" ? " · higher is more risk" : ""}
            </dt>
            <dd className="font-medium text-foreground">
              {scores ? scoreValue(scores, companyId, dimension) : "Loading"}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ModelOutputsSummary({
  outputs,
}: {
  outputs: UniverseModelOutputSummary["outputs"] | undefined;
}) {
  if (!outputs)
    return (
      <div>
        <p className="font-medium">Model outputs</p>
        <p className="mt-1 text-muted-foreground">
          Loading current model status.
        </p>
      </div>
    );
  if (outputs.models.length === 0)
    return (
      <div>
        <p className="font-medium">Model outputs</p>
        <Badge className="mt-1" variant="secondary">
          {readable(outputs.status)}
        </Badge>
        <p className="mt-1 text-muted-foreground">
          No canonical current output is available; no valuation or return is
          inferred.
        </p>
      </div>
    );
  return (
    <div>
      <p className="font-medium">
        Normalized model output{outputs.models.length === 1 ? "" : "s"}
      </p>
      {outputs.models.length === 1 ? (
        <ModelOutputMetrics
          snapshot={outputs.models[0].snapshot}
          status={outputs.models[0].status}
        />
      ) : (
        <div className="mt-1 space-y-2">
          {outputs.models.map((model) => (
            <details key={model.snapshot.id} className="rounded border p-2">
              <summary className="cursor-pointer font-medium">
                {model.model_key} · {readable(model.status)}
              </summary>
              <ModelOutputMetrics
                snapshot={model.snapshot}
                status={model.status}
              />
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function ModelOutputMetrics({
  snapshot,
  status,
}: {
  snapshot: ModelOutputSnapshot;
  status: string;
}) {
  return (
    <div className="mt-1 text-muted-foreground">
      <p>
        {snapshot.model_key} · {snapshot.model_currency ?? "Currency unknown"} ·{" "}
        {readable(snapshot.output_quality)} / {readable(status)}
      </p>
      <p className="mt-1">
        Expected IRR {ratio(snapshot.expected_cash_flow_irr)} · hurdle{" "}
        {ratio(snapshot.hurdle)} · excess {ratio(snapshot.expected_excess)}
      </p>
      <p className="mt-1">
        Bear / Base / Bull FV {money(snapshot.bear_fv, snapshot.model_currency)}{" "}
        / {money(snapshot.base_fv, snapshot.model_currency)} /{" "}
        {money(snapshot.bull_fv, snapshot.model_currency)}
      </p>
      <p className="mt-1">
        Weighted FV {money(snapshot.weighted_fv, snapshot.model_currency)} ·
        weighted upside {ratio(snapshot.weighted_upside)}
      </p>
      <p className="mt-1 break-words text-[10px]">
        {snapshot.source} · recorded {date(snapshot.recorded_at)}
        {snapshot.effective_at
          ? ` · effective ${date(snapshot.effective_at)}`
          : " · effective time unknown"}
      </p>
      {snapshot.field_issues.length > 0 && (
        <p className="mt-1 text-amber-800 dark:text-amber-300">
          {snapshot.field_issues.length} output mapping issue
          {snapshot.field_issues.length === 1 ? "" : "s"} need review.
        </p>
      )}
    </div>
  );
}

function MomentumSummary({
  signal,
}: {
  signal: EstimateMomentumSummary | undefined;
}) {
  if (!signal)
    return (
      <div>
        <p className="font-medium">Estimate Momentum</p>
        <p className="mt-1 text-muted-foreground">Loading.</p>
      </div>
    );
  return (
    <div>
      <p className="font-medium">Estimate Momentum</p>
      <p className="mt-1">
        {momentumLabel(signal)} · {readable(signal.availability)}
      </p>
      <p className="mt-1 text-muted-foreground">
        {readable(signal.freshness)} · {readable(signal.data_quality)} ·{" "}
        {readable(signal.confidence_band)} confidence · {signal.coverage_count}/
        {signal.coverage_total} periods
      </p>
      <p className="mt-1 text-muted-foreground">
        {signal.latest_snapshot_date
          ? `Latest estimate ${signal.latest_snapshot_date}`
          : "No dated estimate observation"}
        {signal.reason ? ` · ${signal.reason}` : ""}
      </p>
    </div>
  );
}

export function DataQualityCard({
  overview,
  modelRows,
  scoreRows,
  momentumRows,
  paceRows,
  rankingRows,
}: {
  overview: Overview;
  modelRows: UniverseModelOutputSummary[] | undefined;
  scoreRows: UniverseScoreSummary[] | undefined;
  momentumRows: UniverseEstimateMomentumSummary[] | undefined;
  paceRows: UniverseExecutionPaceSummary[] | undefined;
  rankingRows: UniverseRankingSummary[] | undefined;
}) {
  const issues: { id: string; label: string; detail: string; href?: string }[] =
    [];
  for (const gap of overview.valuation_gaps) {
    issues.push({
      id: `valuation-${gap.identity}`,
      label: gap.identity,
      detail: readable(gap.reason),
    });
  }
  for (const row of overview.companies) {
    const href = `/company/${row.company.id}`;
    if (row.allocation_status !== "VALUED") {
      issues.push({
        id: `allocation-${row.company.id}`,
        label: row.company.name,
        detail: `Allocation ${readable(row.allocation_status)}`,
        href,
      });
    }
    for (const position of row.positions) {
      if (
        position.price_freshness !== "FRESH" ||
        position.valuation_status !== "VALUED"
      ) {
        issues.push({
          id: `price-${position.listing_id}`,
          label: `${position.venue}:${position.ticker}`,
          detail: `${readable(position.price_freshness)} price · ${readable(position.valuation_status)}`,
          href,
        });
      }
    }
    const outputs = modelRows?.find(
      (item) => item.company.id === row.company.id,
    )?.outputs;
    if (
      outputs &&
      (outputs.status !== "AVAILABLE" ||
        outputs.models.some((model) => model.status !== "PUBLISHED"))
    ) {
      issues.push({
        id: `model-${row.company.id}`,
        label: row.company.name,
        detail: `Model outputs ${readable(outputs.status)}`,
        href,
      });
    }
    const currentScores = scoreRows?.find(
      (item) => item.company.id === row.company.id,
    )?.scores;
    const missingScores = currentScores
      ? currentScores.filter((score) => score.assessment?.status !== "ASSESSED")
      : Array.from({ length: 4 });
    if (scoreRows && missingScores.length > 0) {
      issues.push({
        id: `scores-${row.company.id}`,
        label: row.company.name,
        detail: `${missingScores.length} of 4 score dimensions missing or unavailable`,
        href,
      });
    }
    const momentum = momentumFor(momentumRows, row.company.id);
    if (
      momentum &&
      (momentum.freshness !== "FRESH" ||
        !["AVAILABLE", "DIRECTION_ONLY"].includes(momentum.availability))
    ) {
      issues.push({
        id: `momentum-${row.company.id}`,
        label: row.company.name,
        detail: `Estimate Momentum ${readable(momentum.availability)} · ${readable(momentum.freshness)}`,
        href,
      });
    }
    const pace = paceRows?.find(
      (item) => item.company.id === row.company.id,
    )?.decision;
    if (pace?.decision.decision_status === "REVIEW") {
      issues.push({
        id: `pace-${row.company.id}`,
        label: row.company.name,
        detail: `Execution Pace review · ${pace.decision.reason}`,
        href,
      });
    }
    const rank = rankingFor(rankingRows, row.company.id, "PORTFOLIO");
    if (rank?.entry && rank.entry.status !== "RANKED") {
      issues.push({
        id: `rank-${row.company.id}`,
        label: row.company.name,
        detail: `Portfolio Rank ${readable(rank.entry.status)} · ${rank.entry.reason}`,
        href,
      });
    }
  }
  for (const row of rankingRows ?? []) {
    if (row.company.lifecycle !== "WATCHLIST") continue;
    const href = `/company/${row.company.id}`;
    const outputs = modelRows?.find(
      (item) => item.company.id === row.company.id,
    )?.outputs;
    if (
      outputs &&
      (outputs.status !== "AVAILABLE" ||
        outputs.models.some((model) => model.status !== "PUBLISHED"))
    ) {
      issues.push({
        id: `model-${row.company.id}`,
        label: row.company.name,
        detail: `Model outputs ${readable(outputs.status)}`,
        href,
      });
    }
    const currentScores = scoreRows?.find(
      (item) => item.company.id === row.company.id,
    )?.scores;
    const missingScores = currentScores
      ? currentScores.filter((score) => score.assessment?.status !== "ASSESSED")
      : Array.from({ length: 4 });
    if (scoreRows && missingScores.length > 0) {
      issues.push({
        id: `scores-${row.company.id}`,
        label: row.company.name,
        detail: `${missingScores.length} of 4 score dimensions missing or unavailable`,
        href,
      });
    }
    const momentum = momentumFor(momentumRows, row.company.id);
    if (
      momentum &&
      (momentum.freshness !== "FRESH" ||
        !["AVAILABLE", "DIRECTION_ONLY"].includes(momentum.availability))
    ) {
      issues.push({
        id: `momentum-${row.company.id}`,
        label: row.company.name,
        detail: `Estimate Momentum ${readable(momentum.availability)} · ${readable(momentum.freshness)}`,
        href,
      });
    }
    const rank = row.rankings.find(
      (item) => item.definition.ranking_type === "WATCHLIST",
    );
    if (rank?.entry && rank.entry.status !== "RANKED") {
      issues.push({
        id: `watchlist-rank-${row.company.id}`,
        label: row.company.name,
        detail: `Watchlist Rank ${readable(rank.entry.status)} · ${rank.entry.reason}`,
        href,
      });
    }
  }
  const uniqueIssues = [
    ...new Map(issues.map((issue) => [issue.id, issue])).values(),
  ].slice(0, 8);
  const stillLoading =
    !modelRows || !scoreRows || !momentumRows || !paceRows || !rankingRows;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Data and model checks</CardTitle>
        <p className="text-sm text-muted-foreground">
          Coverage blockers remain visible; missing inputs never become neutral
          signals or zero values.
        </p>
      </CardHeader>
      <CardContent>
        {uniqueIssues.length === 0 ? (
          <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            {stillLoading
              ? "Checking current prices, model outputs, scores and decision inputs."
              : "No portfolio-specific coverage issues were returned by the loaded canonical summaries."}
          </p>
        ) : (
          <ul className="space-y-2">
            {uniqueIssues.map((issue) => (
              <li
                key={issue.id}
                className="flex flex-col gap-1 rounded-md border px-3 py-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3"
              >
                {issue.href ? (
                  <Link
                    href={issue.href}
                    className="text-sm font-medium hover:text-primary"
                  >
                    {issue.label}
                  </Link>
                ) : (
                  <span className="text-sm font-medium">{issue.label}</span>
                )}
                <span className="text-xs text-muted-foreground sm:text-right">
                  {issue.detail}
                </span>
              </li>
            ))}
          </ul>
        )}
        {overview.snapshot?.completeness === "PARTIAL" && (
          <p className="mt-3 rounded-md bg-amber-50 p-3 text-xs leading-5 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">
            Holdings snapshot is partial: {overview.snapshot.reason}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function ReviewAction({
  title,
  description,
  label,
  reason,
  onReason,
  pending,
  error,
  onSubmit,
  buttonLabel,
}: {
  title: string;
  description: string;
  label: string;
  reason: string;
  onReason: (reason: string) => void;
  pending: boolean;
  error: string;
  onSubmit: () => void;
  buttonLabel: string;
}) {
  return (
    <div className="rounded-lg border p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        {description}
      </p>
      <label className="mt-3 block text-xs font-medium">
        {label}
        <input
          value={reason}
          onChange={(event) => onReason(event.target.value)}
          maxLength={1000}
          className="mt-1.5 block h-10 w-full rounded-md border bg-background px-3 text-sm"
        />
      </label>
      <Button
        type="button"
        className="mt-3 w-full sm:w-auto"
        variant="outline"
        onClick={onSubmit}
        disabled={pending || !reason.trim()}
      >
        {pending ? "Recording…" : buttonLabel}
      </Button>
      {error && (
        <p role="alert" className="mt-2 text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
