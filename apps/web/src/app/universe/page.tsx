"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  DemoNotice,
  PageTitle,
  PendingOrError,
  useResearch,
} from "@/components/research-frame";
import {
  isUniverseScoreSummary,
  isUniverseRankingSummary,
  isUniverseMarketSummary,
  isUniverseModelOutputSummary,
  isUniverseEstimateMomentumSummary,
  isUniverseExecutionPaceSummary,
  isRankingRun,
  isWatchlistRankInputSnapshot,
  isResearchRankInputSnapshot,
  lifecycleStates,
  rankingTypes,
  scoreDimensions,
  type RankingCurrent,
  type RankingType,
  type ScoreDimension,
  type ScoreCurrent,
  type ListingMarketData,
  type UniverseModelOutputSummary,
  type EstimateMomentumSummary,
} from "@/lib/domain-contracts";
import { quantity } from "@/lib/display";
import {
  ExecutionPaceCompact,
  executionPaceLabel,
} from "@/components/execution-pace";

const scoreLabels: Record<ScoreDimension, string> = {
  DURABILITY_10Y: "10Y Durability",
  COMPOUNDER_QUALITY: "Compounder Quality",
  EXECUTION: "Execution",
  RISK: "Risk",
};
const rankingLabels: Record<RankingType, string> = {
  PORTFOLIO: "Portfolio Rank",
  WATCHLIST: "Watchlist Rank",
  RESEARCH: "Research Rank",
};

function scoreLabel(score: ScoreCurrent | undefined) {
  const assessment = score?.assessment;
  if (!assessment) return "Not assessed";
  if (assessment.status !== "ASSESSED") return assessment.status;
  return `${assessment.score} / ${score.definition.maximum_score}`;
}

function quoteLabel(market: ListingMarketData) {
  const price = market.latest?.split_adjusted_close;
  if (price === null || price === undefined)
    return market.freshness.replaceAll("_", " ");
  return `${quantity(price)} ${market.latest?.currency ?? market.listing.currency ?? "?"}`;
}

function outputIrr(row: UniverseModelOutputSummary): number | null {
  if (row.outputs.models.length !== 1) return null;
  const model = row.outputs.models[0];
  if (!model || !["PUBLISHED", "PARTIAL"].includes(model.status)) return null;
  const value = model.snapshot.expected_cash_flow_irr;
  return value === null ? null : Number(value);
}

function modelSummaryValue(value: string | null, percentage = false) {
  if (value === null) return "Not supplied";
  return percentage
    ? new Intl.NumberFormat("en", {
        style: "percent",
        maximumFractionDigits: 2,
      }).format(Number(value))
    : quantity(value);
}

function rowMomentumScore(momentum: EstimateMomentumSummary | undefined) {
  return momentum?.confidence_adjusted_score === null || !momentum
    ? null
    : Number(momentum.confidence_adjusted_score);
}

export default function UniversePage() {
  const [lifecycle, setLifecycle] = useState("");
  const [search, setSearch] = useState("");
  const [focus, setFocus] = useState<ScoreDimension>("DURABILITY_10Y");
  const [scoreState, setScoreState] = useState("");
  const [rankingFocus, setRankingFocus] = useState<RankingType>("WATCHLIST");
  const [rankingState, setRankingState] = useState("");
  const [rankRunReason, setRankRunReason] = useState(
    "Current canonical ranking review.",
  );
  const [rankRunPending, setRankRunPending] = useState(false);
  const [rankRunError, setRankRunError] = useState("");
  const [priceState, setPriceState] = useState("");
  const [modelState, setModelState] = useState("");
  const [momentumState, setMomentumState] = useState("");
  const [paceState, setPaceState] = useState("");
  const [sort, setSort] = useState("name");
  const query = new URLSearchParams();
  if (lifecycle) query.set("lifecycle", lifecycle);
  if (search.trim()) query.set("search", search.trim());
  const state = useResearch(
    `universe/score-summary?${query.toString()}`,
    isUniverseScoreSummary,
  );
  const rankingView = useResearch(
    `universe/ranking-summary?${query.toString()}`,
    isUniverseRankingSummary,
  );
  const marketView = useResearch(
    `universe/market-summary?${query.toString()}`,
    isUniverseMarketSummary,
  );
  const modelView = useResearch(
    `universe/model-output-summary?${query.toString()}`,
    isUniverseModelOutputSummary,
  );
  const momentumView = useResearch(
    `universe/estimate-momentum-summary?${query.toString()}`,
    isUniverseEstimateMomentumSummary,
  );
  const paceView = useResearch(
    `universe/execution-pace-summary?${query.toString()}`,
    isUniverseExecutionPaceSummary,
  );
  const companies = useMemo(() => {
    const rankingRows = new Map(
      (rankingView.data ?? []).map((row) => [row.company.id, row.rankings]),
    );
    const marketRows = new Map(
      (marketView.data ?? []).map((row) => [row.company.id, row.market_data]),
    );
    const modelRows = new Map(
      (modelView.data ?? []).map((row) => [row.company.id, row]),
    );
    const momentumRows = new Map(
      (momentumView.data ?? []).map((row) => [
        row.company.id,
        row.estimate_momentum,
      ]),
    );
    const paceRows = new Map(
      (paceView.data ?? []).map((row) => [row.company.id, row.decision]),
    );
    const rows = (state.data ?? []).map((row) => ({
      ...row,
      rankings: rankingRows.get(row.company.id) ?? [],
      market_data: marketRows.get(row.company.id) ?? [],
      model_outputs: modelRows.get(row.company.id),
      estimate_momentum: momentumRows.get(row.company.id),
      execution_pace: paceRows.get(row.company.id),
    }));
    const visible = rows.filter((row) => {
      const selected = row.scores.find(
        (score) => score.definition.dimension === focus,
      );
      const assessed = selected?.assessment?.status === "ASSESSED";
      if (scoreState && (scoreState === "ASSESSED" ? !assessed : assessed))
        return false;
      if (rankingState) {
        const ranking = row.rankings.find(
          (item) => item.definition.ranking_type === rankingFocus,
        );
        const ranked = ranking?.entry?.status === "RANKED";
        if (rankingState === "RANKED" ? !ranked : ranked) return false;
      }
      const hasFreshPrice = row.market_data.some(
        (item) => item.freshness === "FRESH",
      );
      if (priceState === "FRESH" && !hasFreshPrice) return false;
      if (priceState === "GAP" && hasFreshPrice) return false;
      if (
        modelState === "AVAILABLE" &&
        !["AVAILABLE", "PARTIAL"].includes(
          row.model_outputs?.outputs.status ?? "",
        )
      )
        return false;
      if (
        modelState === "NO_OUTPUT" &&
        ["AVAILABLE", "PARTIAL"].includes(
          row.model_outputs?.outputs.status ?? "",
        )
      )
        return false;
      const momentum = row.estimate_momentum;
      if (
        momentumState === "AVAILABLE" &&
        momentum?.availability !== "AVAILABLE"
      )
        return false;
      if (
        momentumState === "DIRECTION_ONLY" &&
        momentum?.availability !== "DIRECTION_ONLY"
      )
        return false;
      if (
        momentumState === "UNAVAILABLE" &&
        ["AVAILABLE", "DIRECTION_ONLY"].includes(momentum?.availability ?? "")
      )
        return false;
      if (momentumState === "STALE" && momentum?.freshness !== "STALE")
        return false;
      const pace = row.execution_pace?.decision;
      if (paceState === "AVAILABLE" && pace?.decision_status !== "AVAILABLE")
        return false;
      if (paceState === "REVIEW" && pace?.decision_status !== "REVIEW")
        return false;
      if (paceState === "NO_RUN" && row.execution_pace) return false;
      return true;
    });
    visible.sort((left, right) => {
      if (sort === "name")
        return left.company.name.localeCompare(right.company.name);
      if (sort === "rank-asc") {
        const rankLeft = left.rankings.find(
          (item) => item.definition.ranking_type === rankingFocus,
        );
        const rankRight = right.rankings.find(
          (item) => item.definition.ranking_type === rankingFocus,
        );
        const a =
          rankLeft?.entry?.status === "RANKED" ? rankLeft.entry.position : null;
        const b =
          rankRight?.entry?.status === "RANKED"
            ? rankRight.entry.position
            : null;
        if (a === null || b === null) {
          if (a === b)
            return left.company.name.localeCompare(right.company.name);
          return a === null ? 1 : -1;
        }
        return a - b;
      }
      if (sort === "irr-desc") {
        const a = left.model_outputs ? outputIrr(left.model_outputs) : null;
        const b = right.model_outputs ? outputIrr(right.model_outputs) : null;
        if (a === null || b === null) {
          if (a === b)
            return left.company.name.localeCompare(right.company.name);
          return a === null ? 1 : -1;
        }
        return b - a;
      }
      if (sort === "momentum-desc" || sort === "momentum-asc") {
        const a = rowMomentumScore(left.estimate_momentum);
        const b = rowMomentumScore(right.estimate_momentum);
        if (a === null || b === null) {
          if (a === b)
            return left.company.name.localeCompare(right.company.name);
          return a === null ? 1 : -1;
        }
        return sort === "momentum-asc" ? a - b : b - a;
      }
      const leftScore = left.scores.find(
        (score) => score.definition.dimension === focus,
      );
      const rightScore = right.scores.find(
        (score) => score.definition.dimension === focus,
      );
      const a =
        leftScore?.assessment?.status === "ASSESSED"
          ? Number(leftScore.assessment.score)
          : null;
      const b =
        rightScore?.assessment?.status === "ASSESSED"
          ? Number(rightScore.assessment.score)
          : null;
      if (a === null || b === null) {
        if (a === b) return left.company.name.localeCompare(right.company.name);
        return a === null ? 1 : -1;
      }
      return sort === "score-asc" ? a - b : b - a;
    });
    return visible;
  }, [
    state.data,
    rankingView.data,
    marketView.data,
    modelView.data,
    momentumView.data,
    paceView.data,
    priceState,
    modelState,
    momentumState,
    paceState,
    scoreState,
    focus,
    rankingFocus,
    rankingState,
    sort,
  ]);
  async function recordSelectedRank() {
    setRankRunPending(true);
    setRankRunError("");
    try {
      const response = await fetch("/api/research/ranking-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ranking_type: rankingFocus,
          actor: "LOCAL_USER",
          reason: rankRunReason.trim(),
          source: "web-universe",
        }),
      });
      const result: unknown = await response.json();
      if (!response.ok || !isRankingRun(result)) {
        throw new Error(
          "Ranking run could not be recorded. Check the API and current input states, then retry.",
        );
      }
      rankingView.retry();
    } catch (error) {
      setRankRunError(
        error instanceof Error
          ? error.message
          : "Ranking run could not be recorded.",
      );
    } finally {
      setRankRunPending(false);
    }
  }
  return (
    <>
      <PageTitle
        title="Universe"
        description="Tracked businesses, independent quality scores, explicit ranking snapshots and listing-specific market facts. Missing prices stay visibly unavailable."
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <label className="text-xs font-medium">
          Company name
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Find a business…"
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          />
        </label>
        <label className="text-xs font-medium">
          Lifecycle
          <select
            value={lifecycle}
            onChange={(event) => setLifecycle(event.target.value)}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            <option value="">All lifecycle states</option>
            {lifecycleStates.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium">
          Score dimension
          <select
            value={focus}
            onChange={(event) => setFocus(event.target.value as ScoreDimension)}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            {scoreDimensions.map((item) => (
              <option key={item} value={item}>
                {scoreLabels[item]}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium">
          Score filter / sort
          <select
            value={scoreState}
            onChange={(event) => {
              setScoreState(event.target.value);
              if (event.target.value) setSort("name");
            }}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            <option value="">All score states</option>
            <option value="ASSESSED">Assessed for selected dimension</option>
            <option value="INCOMPLETE">Missing or unavailable</option>
          </select>
        </label>
        <label className="text-xs font-medium">
          Ranking type
          <select
            value={rankingFocus}
            onChange={(event) =>
              setRankingFocus(event.target.value as RankingType)
            }
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            {rankingTypes.map((item) => (
              <option key={item} value={item}>
                {rankingLabels[item]}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium">
          Ranking filter
          <select
            value={rankingState}
            onChange={(event) => setRankingState(event.target.value)}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            <option value="">All ranking states</option>
            <option value="RANKED">Has numeric position</option>
            <option value="UNRANKED">
              Unavailable, excluded, data-check or not migrated
            </option>
          </select>
        </label>
        <label className="text-xs font-medium">
          Market price coverage
          <select
            value={priceState}
            onChange={(event) => setPriceState(event.target.value)}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            <option value="">All price states</option>
            <option value="FRESH">At least one fresh quote</option>
            <option value="GAP">No fresh quote</option>
          </select>
        </label>
        <label className="text-xs font-medium">
          Model output coverage
          <select
            value={modelState}
            onChange={(event) => setModelState(event.target.value)}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            <option value="">All model states</option>
            <option value="AVAILABLE">Has output values</option>
            <option value="NO_OUTPUT">No output values or not mapped</option>
          </select>
        </label>
        <label className="text-xs font-medium">
          Estimate Momentum state
          <select
            value={momentumState}
            onChange={(event) => setMomentumState(event.target.value)}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            <option value="">All signal states</option>
            <option value="AVAILABLE">Available with coverage</option>
            <option value="DIRECTION_ONLY">Direction only</option>
            <option value="UNAVAILABLE">
              No signal / insufficient history
            </option>
            <option value="STALE">Stale estimates</option>
          </select>
        </label>
        <label className="text-xs font-medium">
          Execution Pace state
          <select
            value={paceState}
            onChange={(event) => setPaceState(event.target.value)}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
          >
            <option value="">All pace states</option>
            <option value="AVAILABLE">Available decision</option>
            <option value="REVIEW">Review required</option>
            <option value="NO_RUN">No recorded run</option>
          </select>
        </label>
        <label className="text-xs font-medium sm:col-span-2 xl:col-span-4">
          Sort companies
          <select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value);
              setScoreState("");
              setRankingState("");
            }}
            className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm sm:max-w-sm"
          >
            <option value="name">Company name</option>
            <option value="score-asc">Selected score · low to high</option>
            <option value="score-desc">Selected score · high to low</option>
            <option value="rank-asc">Selected ranking · position order</option>
            <option value="irr-desc">
              Expected cash-flow IRR · high to low
            </option>
            <option value="momentum-desc">
              Estimate Momentum · high to low
            </option>
            <option value="momentum-asc">
              Estimate Momentum · low to high
            </option>
          </select>
        </label>
      </div>
      {(rankingFocus === "WATCHLIST" || rankingFocus === "RESEARCH") && (
        <div className="mb-6 flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1 text-xs font-medium">
            Ranking run reason
            <input
              value={rankRunReason}
              onChange={(event) => setRankRunReason(event.target.value)}
              maxLength={1000}
              className="mt-2 block h-10 w-full rounded-md border bg-background px-3 text-sm"
            />
          </label>
          <Button
            type="button"
            onClick={recordSelectedRank}
            disabled={rankRunPending || !rankRunReason.trim()}
            className="shrink-0"
          >
            {rankRunPending
              ? "Recording rank…"
              : `Record ${rankingLabels[rankingFocus]}`}
          </Button>
          <p className="basis-full text-xs leading-5 text-muted-foreground sm:basis-auto">
            {rankingFocus === "RESEARCH"
              ? "Research Rank orders Candidate High/Low deep-dive priority and its persistent seed. It is a research-attention queue, not an investment-attractiveness signal or lifecycle decision."
              : "Watchlist Rank orders comparable Expected IRR among explicit Watchlist companies. It does not change lifecycle, models, targets or holdings."}{" "}
            Each run is an immutable snapshot of inputs available now.
          </p>
          {rankRunError && (
            <p role="alert" className="basis-full text-xs text-destructive">
              {rankRunError}
            </p>
          )}
        </div>
      )}
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <>
          {state.data.some((row) => row.company.is_demo) && <DemoNotice />}
          <p role="status" className="mb-4 text-xs text-muted-foreground">
            {companies.length} businesses shown
            {sort !== "name" && " · unavailable values appear last"}
          </p>
          {companies.length === 0 && (
            <Card>
              <CardContent className="py-9">
                <h2 className="font-medium">No companies match</h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  Adjust the filters, create a company through the API, or
                  explore the opt-in demo seed.
                </p>
              </CardContent>
            </Card>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            {companies.map(
              ({
                company,
                scores,
                rankings,
                market_data,
                model_outputs,
                estimate_momentum,
                execution_pace,
              }) => (
                <Card key={company.id} className="min-w-0 shadow-none">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-3">
                      <Link
                        href={`/company/${company.id}`}
                        className="break-words font-medium leading-6 hover:text-primary"
                      >
                        {company.name}
                      </Link>
                      <ArrowUpRight
                        aria-hidden="true"
                        className="mt-1 size-4 shrink-0 text-muted-foreground"
                      />
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      <Badge
                        variant={
                          company.lifecycle === "PORTFOLIO"
                            ? "default"
                            : "secondary"
                        }
                      >
                        {company.lifecycle ?? "Unassigned"}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Reporting currency:{" "}
                        {company.reporting_currency ?? "Unknown"}
                      </span>
                    </div>
                    <div className="mt-4 grid gap-2 border-t pt-3 sm:grid-cols-2">
                      {marketView.error ? (
                        <p className="text-xs text-muted-foreground">
                          Market facts are unavailable.
                        </p>
                      ) : !marketView.data ? (
                        <p className="text-xs text-muted-foreground">
                          Loading listing prices…
                        </p>
                      ) : market_data.length === 0 ? (
                        <p className="text-xs text-muted-foreground">
                          No supported listing or dated quote.
                        </p>
                      ) : (
                        market_data.map((market) => (
                          <div
                            key={market.listing.id}
                            className="min-w-0 rounded-md bg-secondary/40 p-2"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-[11px] font-medium">
                                {market.listing.ticker} · {market.listing.venue}{" "}
                                · {market.listing.currency ?? "?"}
                              </span>
                              <Badge
                                variant={
                                  market.freshness === "FRESH"
                                    ? "default"
                                    : "secondary"
                                }
                              >
                                {market.freshness.replaceAll("_", " ")}
                              </Badge>
                            </div>
                            <p className="mt-1 text-sm font-semibold tabular-nums">
                              {quoteLabel(market)}
                            </p>
                            <p className="mt-1 text-[10px] text-muted-foreground">
                              {market.latest
                                ? `${new Date(market.latest.market_date).toLocaleDateString()} · ${market.price_regime?.regime ?? "Regime unavailable"}`
                                : "No dated price for this listing"}
                              {market.price_regime?.return_3m !== null &&
                                market.price_regime?.return_3m !== undefined &&
                                ` · 3M ${new Intl.NumberFormat("en", { style: "percent", maximumFractionDigits: 1 }).format(Number(market.price_regime.return_3m))}`}
                            </p>
                          </div>
                        ))
                      )}
                    </div>
                    <div className="mt-4 border-t pt-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h2 className="text-xs font-semibold">
                          Valuation and return outputs
                        </h2>
                        <Badge
                          variant={
                            model_outputs?.outputs.status === "AVAILABLE"
                              ? "default"
                              : "secondary"
                          }
                        >
                          {model_outputs?.outputs.status ??
                            (modelView.error
                              ? "UNAVAILABLE"
                              : modelView.data
                                ? "NO MODEL"
                                : "LOADING")}
                        </Badge>
                      </div>
                      {modelView.error ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Model outputs are unavailable.
                        </p>
                      ) : !modelView.data ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Loading model outputs…
                        </p>
                      ) : !model_outputs ||
                        model_outputs.outputs.models.length === 0 ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          No current model contract is published. Missing values
                          are not zero.
                        </p>
                      ) : (
                        <div className="mt-2 space-y-2">
                          {model_outputs.outputs.models.map(
                            ({ model_key, status, snapshot }) => (
                              <div
                                key={model_key}
                                className="min-w-0 rounded-md bg-secondary/40 p-2"
                              >
                                <p className="break-words text-[11px] font-medium">
                                  {model_key} · {status.replaceAll("_", " ")} ·{" "}
                                  {snapshot.model_currency ??
                                    "currency unknown"}
                                </p>
                                <dl className="mt-2 grid grid-cols-2 gap-2">
                                  <div>
                                    <dt className="text-[10px] text-muted-foreground">
                                      Weighted FV
                                    </dt>
                                    <dd className="mt-1 break-words text-xs font-medium tabular-nums">
                                      {modelSummaryValue(snapshot.weighted_fv)}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt className="text-[10px] text-muted-foreground">
                                      Expected Cash-Flow IRR
                                    </dt>
                                    <dd className="mt-1 break-words text-xs font-medium tabular-nums">
                                      {modelSummaryValue(
                                        snapshot.expected_cash_flow_irr,
                                        true,
                                      )}
                                    </dd>
                                  </div>
                                </dl>
                                {snapshot.model_currency === null && (
                                  <p className="mt-1 text-[10px] text-muted-foreground">
                                    Currency is not documented; no conversion is
                                    applied.
                                  </p>
                                )}
                              </div>
                            ),
                          )}
                        </div>
                      )}
                    </div>
                    <dl className="mt-5 grid grid-cols-2 gap-3 border-t pt-4 sm:grid-cols-4">
                      {scoreDimensions.map((dimension) => {
                        const selected = scores.find(
                          (score) => score.definition.dimension === dimension,
                        );
                        const assessed =
                          selected?.assessment?.status === "ASSESSED";
                        return (
                          <div key={dimension} className="min-w-0">
                            <dt className="text-[11px] leading-4 text-muted-foreground">
                              {scoreLabels[dimension]}
                            </dt>
                            <dd className="mt-1 break-words text-sm font-medium tabular-nums">
                              {scoreLabel(selected)}
                            </dd>
                            {selected?.assessment && (
                              <dd className="mt-1 text-[10px] leading-4 text-muted-foreground">
                                {selected.assessment.status}
                              </dd>
                            )}
                            {!selected && (
                              <dd className="mt-1 text-[10px] text-muted-foreground">
                                Not assessed
                              </dd>
                            )}
                            {assessed && dimension === "RISK" && (
                              <dd className="mt-1 text-[10px] text-muted-foreground">
                                Higher means greater risk
                              </dd>
                            )}
                          </div>
                        );
                      })}
                    </dl>
                    <p className="mt-4 text-xs text-muted-foreground">
                      Higher is better for Durability, Compounder Quality and
                      Execution. Risk is separate and excludes valuation.
                    </p>
                    <div className="mt-4 border-t pt-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h2 className="text-xs font-semibold">
                          Execution Pace
                        </h2>
                        {execution_pace && (
                          <Badge
                            variant={
                              execution_pace.decision.decision_status ===
                              "AVAILABLE"
                                ? "default"
                                : "secondary"
                            }
                          >
                            {executionPaceLabel(
                              execution_pace.decision.pace ??
                                execution_pace.decision.decision_status,
                            )}
                          </Badge>
                        )}
                      </div>
                      {paceView.error ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Execution Pace data is unavailable.
                        </p>
                      ) : !paceView.data ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Loading latest pace decisions…
                        </p>
                      ) : (
                        <ExecutionPaceCompact entry={execution_pace} />
                      )}
                      <p className="mt-2 text-[10px] leading-4 text-muted-foreground">
                        Portfolio timing only. It does not change target weight,
                        lifecycle, model assumptions or the business Execution
                        score.
                      </p>
                    </div>
                    <div className="mt-4 border-t pt-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h2 className="text-xs font-semibold">
                          Estimate Momentum
                        </h2>
                        {momentumView.data && estimate_momentum && (
                          <Badge
                            variant={
                              estimate_momentum.availability === "AVAILABLE"
                                ? "default"
                                : "secondary"
                            }
                          >
                            {estimate_momentum.availability.replaceAll(
                              "_",
                              " ",
                            )}
                          </Badge>
                        )}
                      </div>
                      {momentumView.error ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Estimate Momentum is unavailable.
                        </p>
                      ) : !momentumView.data ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Loading point-in-time estimate history…
                        </p>
                      ) : !estimate_momentum ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          No signal summary is available.
                        </p>
                      ) : (
                        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                          <span className="text-sm font-semibold">
                            {estimate_momentum.direction?.replaceAll(
                              "_",
                              " ",
                            ) ?? "No direction"}
                          </span>
                          <span className="text-xs tabular-nums text-muted-foreground">
                            Confidence-adjusted{" "}
                            {modelSummaryValue(
                              estimate_momentum.confidence_adjusted_score,
                            )}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            Coverage {estimate_momentum.coverage_count}/
                            {estimate_momentum.coverage_total} · Confidence{" "}
                            {new Intl.NumberFormat("en", {
                              style: "percent",
                              maximumFractionDigits: 0,
                            }).format(Number(estimate_momentum.confidence))}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {estimate_momentum.freshness.replaceAll("_", " ")} ·{" "}
                            {estimate_momentum.provider_id ??
                              "no selected source"}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="mt-4 border-t pt-4">
                      <h2 className="text-xs font-semibold">
                        Latest ranking snapshots
                      </h2>
                      {!rankingView.data ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          {rankingView.error
                            ? "Ranking snapshots are unavailable."
                            : "Loading ranking snapshots…"}
                        </p>
                      ) : (
                        <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                          {rankingTypes.map((type) => {
                            const current: RankingCurrent | undefined =
                              rankings.find(
                                (item) => item.definition.ranking_type === type,
                              );
                            const entry = current?.entry;
                            const rankContext =
                              type === "WATCHLIST" &&
                              isWatchlistRankInputSnapshot(
                                entry?.input_snapshot,
                              )
                                ? entry.input_snapshot
                                : null;
                            const researchRankContext =
                              type === "RESEARCH" &&
                              isResearchRankInputSnapshot(entry?.input_snapshot)
                                ? entry.input_snapshot
                                : null;
                            return (
                              <div key={type} className="min-w-0">
                                <dt className="text-[11px] leading-4 text-muted-foreground">
                                  {rankingLabels[type]}
                                </dt>
                                <dd className="mt-1 break-words text-sm font-medium">
                                  {!current?.run
                                    ? "No run recorded"
                                    : !entry
                                      ? "Not included in latest run"
                                      : entry.status === "RANKED"
                                        ? `#${entry.position}`
                                        : entry.status}
                                </dd>
                                {entry && entry.status !== "RANKED" && (
                                  <dd className="mt-1 break-words text-[10px] leading-4 text-muted-foreground">
                                    {entry.reason}
                                  </dd>
                                )}
                                {rankContext && (
                                  <dd className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] leading-4">
                                    <span className="text-muted-foreground">
                                      Durability / Quality
                                    </span>
                                    <span className="text-right tabular-nums">
                                      {rankContext.durability_10y.score ??
                                        rankContext.durability_10y.status}
                                      {" / "}
                                      {rankContext.compounder_quality.score ??
                                        rankContext.compounder_quality.status}
                                    </span>
                                    <span className="text-muted-foreground">
                                      Fundamental CAGR
                                    </span>
                                    <span className="text-right tabular-nums">
                                      {modelSummaryValue(
                                        rankContext.forward_fundamental_cagr,
                                        true,
                                      )}
                                    </span>
                                    <span className="text-muted-foreground">
                                      Expected IRR
                                    </span>
                                    <span className="text-right tabular-nums">
                                      {modelSummaryValue(
                                        rankContext.expected_irr,
                                        true,
                                      )}
                                    </span>
                                    <span className="col-span-2 text-right text-muted-foreground">
                                      {rankContext.return_source.source_kind ===
                                      "NATIVE_MODEL_REVISION"
                                        ? `Native revision ${rankContext.return_source.revision_number ?? "?"}`
                                        : "Legacy output · separate return semantics"}
                                    </span>
                                  </dd>
                                )}
                                {researchRankContext && (
                                  <dd className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] leading-4">
                                    <span className="text-muted-foreground">
                                      Candidate tier / sort key
                                    </span>
                                    <span className="text-right tabular-nums">
                                      {researchRankContext.candidate_tier ??
                                        "Unavailable"}{" "}
                                      /{" "}
                                      {modelSummaryValue(
                                        researchRankContext.sort_key,
                                      )}
                                    </span>
                                    <span className="text-muted-foreground">
                                      Persistent seed
                                    </span>
                                    <span className="text-right tabular-nums">
                                      {researchRankContext.priority_seed ===
                                      null
                                        ? researchRankContext.used_legacy_default
                                          ? `Fallback ${quantity(researchRankContext.legacy_default_priority_seed)}`
                                          : "Unavailable"
                                        : quantity(
                                            researchRankContext.priority_seed,
                                          )}
                                    </span>
                                    <span className="col-span-2 text-right text-muted-foreground">
                                      Research attention queue · not an
                                      investment rank
                                    </span>
                                  </dd>
                                )}
                              </div>
                            );
                          })}
                        </dl>
                      )}
                      {rankingView.error && (
                        <button
                          type="button"
                          onClick={rankingView.retry}
                          className="mt-2 text-xs font-medium text-primary underline"
                        >
                          Retry ranking data
                        </button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ),
            )}
          </div>
        </>
      )}
    </>
  );
}
