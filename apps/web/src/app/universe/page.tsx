"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
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
  lifecycleStates,
  rankingTypes,
  scoreDimensions,
  type RankingCurrent,
  type RankingType,
  type ScoreDimension,
  type ScoreCurrent,
  type ListingMarketData,
  type UniverseModelOutputSummary,
} from "@/lib/domain-contracts";
import { quantity } from "@/lib/display";

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

export default function UniversePage() {
  const [lifecycle, setLifecycle] = useState("");
  const [search, setSearch] = useState("");
  const [focus, setFocus] = useState<ScoreDimension>("DURABILITY_10Y");
  const [scoreState, setScoreState] = useState("");
  const [rankingFocus, setRankingFocus] = useState<RankingType>("PORTFOLIO");
  const [rankingState, setRankingState] = useState("");
  const [priceState, setPriceState] = useState("");
  const [modelState, setModelState] = useState("");
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
    const rows = (state.data ?? []).map((row) => ({
      ...row,
      rankings: rankingRows.get(row.company.id) ?? [],
      market_data: marketRows.get(row.company.id) ?? [],
      model_outputs: modelRows.get(row.company.id),
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
    priceState,
    modelState,
    scoreState,
    focus,
    rankingFocus,
    rankingState,
    sort,
  ]);
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
              Unavailable, excluded or not migrated
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
          </select>
        </label>
      </div>
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
              ({ company, scores, rankings, market_data, model_outputs }) => (
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
