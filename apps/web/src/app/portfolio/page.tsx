"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { AttentionCenter } from "@/components/attention-center";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DataQualityCard,
  ExecutionSummaryCard,
  GapRow,
  MetricCard,
  OpportunityRow,
  ReviewAction,
  RunBadge,
  WatchlistOpportunityRow,
  money,
  momentumFor,
  rankingFor,
  readable,
  ratio,
  sortedByGap,
  sortedByWeight,
} from "@/components/portfolio-dashboard";
import {
  DemoNotice,
  PageTitle,
  PendingOrError,
  useResearch,
} from "@/components/research-frame";
import {
  isExecutionPaceRun,
  isOverview,
  isPortfolios,
  isRankingRun,
  isUniverseEstimateMomentumSummary,
  isUniverseExecutionPaceSummary,
  isUniverseModelOutputSummary,
  isUniverseRankingSummary,
  isUniverseScoreSummary,
} from "@/lib/domain-contracts";
import { date } from "@/lib/display";

export default function PortfolioPage() {
  const state = useResearch("portfolios", isPortfolios);
  if (!state.data)
    return (
      <>
        <PageTitle
          title="Portfolio"
          description="A decision view across current holdings, strategic targets, capital priorities and execution context."
        />
        <PendingOrError {...state} />
      </>
    );
  if (state.data.length === 0)
    return (
      <>
        <PageTitle
          title="Portfolio"
          description="Current ownership and strategic targets remain separate."
        />
        <Card>
          <CardContent className="py-10">
            <h2 className="text-lg font-medium">No portfolio yet</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Create a logical portfolio through the API or use the documented
              development seed to explore fictional examples.
            </p>
          </CardContent>
        </Card>
      </>
    );
  return <PortfolioDashboard id={state.data[0].id} />;
}

function PortfolioDashboard({ id }: { id: string }) {
  const state = useResearch(`portfolios/${id}/overview`, isOverview);
  const rankingView = useResearch(
    "universe/ranking-summary",
    isUniverseRankingSummary,
  );
  const paceView = useResearch(
    "universe/execution-pace-summary",
    isUniverseExecutionPaceSummary,
  );
  const scoreView = useResearch(
    "universe/score-summary",
    isUniverseScoreSummary,
  );
  const momentumView = useResearch(
    "universe/estimate-momentum-summary",
    isUniverseEstimateMomentumSummary,
  );
  const modelView = useResearch(
    "universe/model-output-summary",
    isUniverseModelOutputSummary,
  );
  const [rankReason, setRankReason] = useState(
    "Periodic incremental-capital review.",
  );
  const [rankPending, setRankPending] = useState(false);
  const [rankError, setRankError] = useState("");
  const [paceReason, setPaceReason] = useState(
    "Periodic portfolio execution review.",
  );
  const [pacePending, setPacePending] = useState(false);
  const [paceError, setPaceError] = useState("");
  const view = state.data;

  async function recordPortfolioRank() {
    setRankPending(true);
    setRankError("");
    try {
      const response = await fetch("/api/research/ranking-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ranking_type: "PORTFOLIO",
          actor: "LOCAL_USER",
          reason: rankReason.trim(),
          source: "web-portfolio",
        }),
      });
      const result: unknown = await response.json();
      if (!response.ok || !isRankingRun(result)) {
        throw new Error(
          "Portfolio Rank could not be recorded. Check the API and available inputs, then retry.",
        );
      }
      rankingView.retry();
    } catch (error) {
      setRankError(
        error instanceof Error
          ? error.message
          : "Portfolio Rank could not be recorded.",
      );
    } finally {
      setRankPending(false);
    }
  }

  async function recordExecutionPace() {
    setPacePending(true);
    setPaceError("");
    try {
      const response = await fetch("/api/research/execution-pace-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor: "LOCAL_USER",
          reason: paceReason.trim(),
          source: "web-portfolio",
        }),
      });
      const result: unknown = await response.json();
      if (!response.ok || !isExecutionPaceRun(result)) {
        throw new Error(
          "Execution Pace could not be recorded. Check current portfolio and input coverage, then retry.",
        );
      }
      paceView.retry();
    } catch (error) {
      setPaceError(
        error instanceof Error
          ? error.message
          : "Execution Pace could not be recorded.",
      );
    } finally {
      setPacePending(false);
    }
  }

  if (!view)
    return (
      <>
        <PageTitle
          title="Portfolio"
          description="A decision view across current holdings, strategic targets, capital priorities and execution context."
        />
        <PendingOrError {...state} />
      </>
    );

  const weightedRows = sortedByWeight(view.companies);
  const gapRows = sortedByGap(view.companies).filter(
    (row) => row.allocation_gap !== null,
  );
  const largestExposure = weightedRows.find(
    (row) => row.current_weight !== null,
  );
  const portfolioOpportunities = weightedRows
    .map((row) => ({
      row,
      ranking: rankingFor(rankingView.data, row.company.id, "PORTFOLIO"),
    }))
    .sort((left, right) => {
      const leftRank = left.ranking?.entry?.position ?? Number.MAX_SAFE_INTEGER;
      const rightRank =
        right.ranking?.entry?.position ?? Number.MAX_SAFE_INTEGER;
      return leftRank - rightRank;
    });
  const watchlistOpportunities = (rankingView.data ?? [])
    .filter((item) => item.company.lifecycle === "WATCHLIST")
    .map((item) => ({
      item,
      ranking: item.rankings.find(
        (rank) => rank.definition.ranking_type === "WATCHLIST",
      ),
    }))
    .sort((left, right) => {
      const leftRank = left.ranking?.entry?.position ?? Number.MAX_SAFE_INTEGER;
      const rightRank =
        right.ranking?.entry?.position ?? Number.MAX_SAFE_INTEGER;
      return leftRank - rightRank;
    });

  const dashboardDataErrors = [
    rankingView.error ? "Rankings" : null,
    paceView.error ? "Execution Pace" : null,
    scoreView.error ? "Scores" : null,
    momentumView.error ? "Estimate Momentum" : null,
    modelView.error ? "Model outputs" : null,
  ].filter((item): item is string => item !== null);

  return (
    <>
      <PageTitle
        title="Portfolio"
        description="Own, target, prioritize and act—with each decision layer kept distinct."
        demo={view.portfolio.is_demo}
      />
      {view.portfolio.is_demo && <DemoNotice />}

      {dashboardDataErrors.length > 0 && (
        <div
          role="status"
          className="mb-5 flex flex-col gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 sm:flex-row sm:items-center sm:justify-between dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100"
        >
          <p>
            Some decision context did not load: {dashboardDataErrors.join(", ")}
            . Portfolio values remain sourced from the canonical overview.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              rankingView.retry();
              paceView.retry();
              scoreView.retry();
              momentumView.retry();
              modelView.retry();
            }}
          >
            <RefreshCw aria-hidden="true" /> Retry context
          </Button>
        </div>
      )}

      <section aria-label="Portfolio posture" className="mb-7">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">Portfolio posture</h2>
            <p className="text-sm text-muted-foreground">
              {view.portfolio.name} · {view.valuation_currency} base currency
            </p>
          </div>
          <Badge
            variant={
              view.valuation_status === "VALUED" ? "default" : "secondary"
            }
          >
            {readable(view.valuation_status)}
          </Badge>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Current portfolio value"
            value={money(view.base_market_value, view.valuation_currency)}
            note={
              view.snapshot
                ? `Holdings as of ${date(view.snapshot.effective_at)}`
                : "No holdings observation"
            }
          />
          <MetricCard
            label="Strategic architecture"
            value={
              view.target_revision
                ? `${ratio(view.target_revision.invested_weight)} invested`
                : "Not authored"
            }
            note={
              view.target_revision
                ? `${ratio(view.target_revision.strategic_cash_weight)} strategic cash · accepted ${date(view.target_revision.accepted_at ?? view.target_revision.recorded_at)}`
                : "No accepted target revision"
            }
          />
          <MetricCard
            label="Largest current exposure"
            value={largestExposure?.company.name ?? "Unavailable"}
            note={
              largestExposure
                ? `${ratio(largestExposure.current_weight)} of valued portfolio · ${money(largestExposure.current_market_value, largestExposure.current_market_currency)}`
                : "Comparable market weights unavailable"
            }
          />
          <ExecutionSummaryCard rows={paceView.data} />
        </div>
      </section>

      <section aria-labelledby="allocation-review-heading" className="mb-7">
        <div className="mb-3">
          <h2 id="allocation-review-heading" className="text-lg font-semibold">
            Allocation review
          </h2>
          <p className="text-sm text-muted-foreground">
            Portfolio weights and allocation gaps use the API’s priced,
            FX-comparable snapshot. A positive gap means below target.
          </p>
        </div>
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(280px,0.75fr)]">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                Largest strategic gaps
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {gapRows.length === 0 ? (
                <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                  {view.target_revision
                    ? "Allocation gaps are unavailable until the holdings and portfolio value are comparable."
                    : "No accepted target architecture is available."}
                </p>
              ) : (
                gapRows
                  .slice(0, 6)
                  .map((row) => <GapRow key={row.company.id} row={row} />)
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                Cash and valuation coverage
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {view.cash_valuations.length === 0 ? (
                <p className="text-muted-foreground">
                  No cash balance was observed in the current holdings snapshot.
                </p>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Observed cash
                  </p>
                  {view.cash_valuations.map((cash) => (
                    <div
                      key={cash.currency}
                      className="flex items-start justify-between gap-3"
                    >
                      <span>{money(cash.balance, cash.currency)}</span>
                      <span className="text-right text-xs text-muted-foreground">
                        {cash.valuation_status === "VALUED"
                          ? money(
                              cash.base_market_value,
                              view.valuation_currency,
                            )
                          : readable(cash.valuation_status)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {view.valuation_gaps.length > 0 ? (
                <div className="border-t pt-3">
                  <p className="text-xs font-medium uppercase tracking-wide text-amber-800 dark:text-amber-300">
                    Unresolved valuation inputs
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {view.valuation_gaps.slice(0, 5).map((gap) => (
                      <li
                        key={`${gap.identity}-${gap.reason}`}
                        className="flex justify-between gap-3 text-xs"
                      >
                        <span className="font-medium">{gap.identity}</span>
                        <span className="text-right text-muted-foreground">
                          {readable(gap.reason)}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {view.valuation_gaps.length > 5 && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Plus {view.valuation_gaps.length - 5} additional
                      unresolved inputs.
                    </p>
                  )}
                </div>
              ) : (
                <p className="border-t pt-3 text-xs text-muted-foreground">
                  All observed positions and cash have comparable current
                  valuation inputs.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      <section aria-labelledby="portfolio-rank-heading" className="mb-7">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="portfolio-rank-heading" className="text-lg font-semibold">
              Capital review
            </h2>
            <p className="text-sm text-muted-foreground">
              Portfolio Rank compares current portfolio capital priorities. Rank
              is separate from target weight and does not allocate capital.
            </p>
          </div>
          <RunBadge
            current={
              portfolioOpportunities.find((item) => item.ranking?.run)?.ranking
            }
          />
        </div>
        <Card>
          <CardContent className="divide-y p-0">
            {portfolioOpportunities.length === 0 ? (
              <p className="p-5 text-sm text-muted-foreground">
                No current holdings or explicit targets are available for
                capital review.
              </p>
            ) : (
              portfolioOpportunities.map(({ row, ranking }) => (
                <OpportunityRow
                  key={row.company.id}
                  company={row.company}
                  ranking={ranking}
                  outputs={
                    modelView.data?.find(
                      (item) => item.company.id === row.company.id,
                    )?.outputs
                  }
                  scores={scoreView.data}
                  momentum={momentumFor(momentumView.data, row.company.id)}
                  currentWeight={row.current_weight}
                  targetWeight={row.target_weight}
                  allocationGap={row.allocation_gap}
                  currentValue={row.current_market_value}
                  valueCurrency={row.current_market_currency}
                  positions={row.positions}
                  snapshotCompleteness={view.snapshot?.completeness ?? null}
                  pace={
                    paceView.data?.find(
                      (item) => item.company.id === row.company.id,
                    )?.decision ?? null
                  }
                />
              ))
            )}
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="watchlist-heading" className="mb-7">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="watchlist-heading" className="text-lg font-semibold">
              Watchlist opportunities
            </h2>
            <p className="text-sm text-muted-foreground">
              Watchlist Rank prioritizes research-stage opportunities. Its
              methodology and population stay separate from Portfolio Rank.
            </p>
          </div>
          <RunBadge
            current={
              watchlistOpportunities.find((item) => item.ranking?.run)?.ranking
            }
          />
        </div>
        <Card>
          <CardContent className="divide-y p-0">
            {!rankingView.data ? (
              <p className="p-5 text-sm text-muted-foreground">
                Watchlist Rank is loading or unavailable.
              </p>
            ) : watchlistOpportunities.length === 0 ? (
              <p className="p-5 text-sm text-muted-foreground">
                No explicit Watchlist companies are currently in the research
                universe.
              </p>
            ) : (
              watchlistOpportunities
                .slice(0, 8)
                .map(({ item, ranking }) => (
                  <WatchlistOpportunityRow
                    key={item.company.id}
                    item={item}
                    ranking={ranking}
                    outputs={
                      modelView.data?.find(
                        (model) => model.company.id === item.company.id,
                      )?.outputs
                    }
                    scores={scoreView.data}
                    momentum={momentumFor(momentumView.data, item.company.id)}
                  />
                ))
            )}
          </CardContent>
        </Card>
      </section>

      <section
        aria-label="Portfolio attention and data quality"
        className="grid gap-4 xl:grid-cols-2"
      >
        <AttentionCenter compact />
        <DataQualityCard
          overview={view}
          modelRows={modelView.data}
          scoreRows={scoreView.data}
          momentumRows={momentumView.data}
          paceRows={paceView.data}
          rankingRows={rankingView.data}
        />
      </section>

      <details className="mt-7 rounded-xl border bg-card p-4">
        <summary className="cursor-pointer text-sm font-semibold">
          Record a new analytical review
        </summary>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-muted-foreground">
          These actions append immutable ranking or Execution Pace runs. They do
          not change holdings, lifecycle, model assumptions or strategic
          targets.
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <ReviewAction
            title="Portfolio Rank"
            description="Record incremental-capital priorities from the currently available canonical inputs."
            label="Run reason"
            reason={rankReason}
            onReason={setRankReason}
            pending={rankPending}
            error={rankError}
            onSubmit={recordPortfolioRank}
            buttonLabel="Record Portfolio Rank"
          />
          <ReviewAction
            title="Execution Pace"
            description="Snapshot how quickly to move toward accepted targets. Missing or stale critical inputs remain REVIEW."
            label="Review rationale"
            reason={paceReason}
            onReason={setPaceReason}
            pending={pacePending}
            error={paceError}
            onSubmit={recordExecutionPace}
            buttonLabel="Record Execution Pace"
          />
        </div>
      </details>
    </>
  );
}
