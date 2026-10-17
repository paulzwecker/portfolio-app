"use client";

import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { AttentionCenter } from "@/components/attention-center";
import { PendingOrError } from "@/components/app/empty-state";
import { PageHeader } from "@/components/app/page-header";
import { DemoNotice } from "@/components/app/demo-notice";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DataQualityCard,
  ExecutionSummaryCard,
  OpportunityRow,
  ReviewAction,
  RunBadge,
  WatchlistOpportunityRow,
  momentumFor,
  rankingFor,
  sortedByWeight,
} from "@/components/features/portfolio/decision-components";
import {
  PortfolioAllocationSection,
  PortfolioPerformanceSection,
} from "@/components/features/portfolio/portfolio-allocation-section";
import { PortfolioHoldingsSection } from "@/components/features/portfolio/portfolio-holdings-section";
import { PortfolioOverviewSection } from "@/components/features/portfolio/portfolio-overview-section";
import {
  portfolioHoldingRows,
  portfolioCoverageTone,
} from "@/components/features/portfolio/portfolio-data";
import { useResearch } from "@/hooks/use-research";
import {
  isExecutionPaceRun,
  isOverview,
  isRankingRun,
  isUniverseEstimateMomentumSummary,
  isUniverseExecutionPaceSummary,
  isUniverseModelOutputSummary,
  isUniverseRankingSummary,
  isUniverseScoreSummary,
} from "@/lib/domain-contracts";
export function PortfolioWorkspace({ id }: { id: string }) {
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
  const decisionDetailsRef = useRef<HTMLDetailsElement>(null);
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
  const [confirmationMessage, setConfirmationMessage] = useState("");
  const view = state.data;

  useEffect(() => {
    const handleHash = () => {
      if (window.location.hash === "#portfolio-rank-heading") {
        if (decisionDetailsRef.current) decisionDetailsRef.current.open = true;
        window.requestAnimationFrame(() =>
          document
            .getElementById("portfolio-rank-heading")
            ?.scrollIntoView({ block: "start" }),
        );
      }
      if (window.location.hash === "#holdings-confirmation") {
        const confirmation = document.getElementById(
          "holdings-confirmation-details",
        ) as HTMLDetailsElement | null;
        if (confirmation) confirmation.open = true;
      }
    };
    handleHash();
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, [view]);

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
      if (!response.ok || !isRankingRun(result))
        throw new Error(
          "Portfolio Rank could not be recorded. Check the API and available inputs, then retry.",
        );
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
      if (!response.ok || !isExecutionPaceRun(result))
        throw new Error(
          "Execution Pace could not be recorded. Check current portfolio and input coverage, then retry.",
        );
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

  if (!view) return <PendingOrError error={state.error} retry={state.retry} />;

  const rows = portfolioHoldingRows(view);
  const weightedRows = sortedByWeight(view.companies);
  const portfolioOpportunities = weightedRows
    .map((row) => ({
      row,
      ranking: rankingFor(rankingView.data, row.company.id, "PORTFOLIO"),
    }))
    .sort(
      (left, right) =>
        (left.ranking?.entry?.position ?? Number.MAX_SAFE_INTEGER) -
        (right.ranking?.entry?.position ?? Number.MAX_SAFE_INTEGER),
    );
  const watchlistOpportunities = (rankingView.data ?? [])
    .filter((item) => item.company.lifecycle === "WATCHLIST")
    .map((item) => ({
      item,
      ranking: item.rankings.find(
        (rank) => rank.definition.ranking_type === "WATCHLIST",
      ),
    }))
    .sort(
      (left, right) =>
        (left.ranking?.entry?.position ?? Number.MAX_SAFE_INTEGER) -
        (right.ranking?.entry?.position ?? Number.MAX_SAFE_INTEGER),
    );
  const dashboardDataErrors = [
    rankingView.error ? "Rankings" : null,
    paceView.error ? "Execution Pace" : null,
    scoreView.error ? "Scores" : null,
    momentumView.error ? "Estimate Momentum" : null,
    modelView.error ? "Model outputs" : null,
  ].filter((item): item is string => item !== null);
  const decisionRunsBlockedReason =
    view.holdings_freshness !== "FRESH"
      ? "Confirm positions and cash to refresh the holdings baseline first."
      : view.valuation_status !== "VALUED"
        ? "Complete current price and FX valuation inputs first."
        : undefined;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Portfolio"
        description="Understand current ownership, its canonical market value and the portfolio's strategic position."
        demo={view.portfolio.is_demo}
        badge={
          <StatusIndicator
            status={view.valuation_status}
            tone={portfolioCoverageTone(view.valuation_status)}
          />
        }
        context={
          <>
            <Badge variant="secondary">{view.portfolio.name}</Badge>
            <Badge variant="outline">
              Base currency · {view.valuation_currency}
            </Badge>
          </>
        }
        actions={
          <a
            href="#holdings-confirmation"
            className="inline-flex min-h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Confirm holdings
          </a>
        }
      />
      {view.portfolio.is_demo && <DemoNotice />}
      <nav
        aria-label="Portfolio sections"
        className="-mt-3 flex flex-wrap gap-2 border-b pb-3 text-sm"
      >
        <a
          className="rounded-md px-3 py-2 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href="#portfolio-overview"
        >
          Overview
        </a>
        <a
          className="rounded-md px-3 py-2 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href="#portfolio-holdings"
        >
          Holdings
        </a>
        <a
          className="rounded-md px-3 py-2 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href="#portfolio-allocation"
        >
          Allocation &amp; exposure
        </a>
        <a
          className="rounded-md px-3 py-2 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href="#portfolio-performance"
        >
          Performance
        </a>
      </nav>

      <PortfolioOverviewSection overview={view} rows={rows} />
      <PortfolioHoldingsSection
        overview={view}
        rows={rows}
        onConfirmed={() => {
          setConfirmationMessage(
            "A new immutable holdings snapshot was appended. Refreshing the portfolio view.",
          );
          state.retry();
        }}
      />
      {confirmationMessage && (
        <p role="status" className="-mt-6 text-sm text-positive">
          {confirmationMessage}
        </p>
      )}
      <PortfolioAllocationSection overview={view} />
      <PortfolioPerformanceSection />

      <details
        ref={decisionDetailsRef}
        className="rounded-xl border bg-card"
        id="portfolio-decision-context"
      >
        <summary className="cursor-pointer list-none p-4 text-sm font-semibold [&::-webkit-details-marker]:hidden">
          Decision and research context
          <span className="mt-1 block text-xs font-normal text-muted-foreground">
            Portfolio Rank, Watchlist Rank, Execution Pace, attention and
            source-quality details are available here; none changes holdings or
            target architecture.
          </span>
        </summary>
        <div className="space-y-7 border-t p-4 sm:p-5">
          {dashboardDataErrors.length > 0 && (
            <div
              role="status"
              className="flex flex-col gap-3 rounded-lg border border-warning/35 bg-warning/10 p-4 text-sm text-warning sm:flex-row sm:items-center sm:justify-between"
            >
              <p>
                Some decision context did not load:{" "}
                {dashboardDataErrors.join(", ")}. Portfolio values remain
                sourced from the canonical overview.
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

          <section
            aria-labelledby="portfolio-rank-heading"
            className="scroll-mt-6 space-y-3"
          >
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h2
                  id="portfolio-rank-heading"
                  className="text-lg font-semibold"
                >
                  Portfolio Rank
                </h2>
                <p className="text-sm text-muted-foreground">
                  Incremental-capital context remains separate from current
                  weight, strategic targets and execution timing.
                </p>
              </div>
              <RunBadge
                current={
                  portfolioOpportunities.find((item) => item.ranking?.run)
                    ?.ranking
                }
              />
            </div>
            <Card className="shadow-none">
              <CardContent className="divide-y p-0">
                {portfolioOpportunities.length === 0 ? (
                  <p className="p-5 text-sm text-muted-foreground">
                    No current holdings or explicit targets were returned for
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

          <section aria-labelledby="watchlist-heading" className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h2 id="watchlist-heading" className="text-lg font-semibold">
                  Watchlist Rank
                </h2>
                <p className="text-sm text-muted-foreground">
                  Research-stage opportunities are kept separate from Portfolio
                  Rank and holdings.
                </p>
              </div>
              <RunBadge
                current={
                  watchlistOpportunities.find((item) => item.ranking?.run)
                    ?.ranking
                }
              />
            </div>
            <Card className="shadow-none">
              <CardContent className="divide-y p-0">
                {!rankingView.data ? (
                  <p className="p-5 text-sm text-muted-foreground">
                    Watchlist Rank is loading or unavailable.
                  </p>
                ) : watchlistOpportunities.length === 0 ? (
                  <p className="p-5 text-sm text-muted-foreground">
                    No explicit Watchlist companies are currently in the
                    research universe.
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
                        momentum={momentumFor(
                          momentumView.data,
                          item.company.id,
                        )}
                      />
                    ))
                )}
              </CardContent>
            </Card>
          </section>

          <div className="grid gap-4 xl:grid-cols-2">
            <ExecutionSummaryCard rows={paceView.data} />
            <AttentionCenter compact />
          </div>
          <DataQualityCard
            overview={view}
            modelRows={modelView.data}
            scoreRows={scoreView.data}
            momentumRows={momentumView.data}
            paceRows={paceView.data}
            rankingRows={rankingView.data}
          />
          <details className="rounded-xl border p-4">
            <summary className="cursor-pointer text-sm font-semibold">
              Record a new analytical review
            </summary>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-muted-foreground">
              These actions append immutable Portfolio Rank or Execution Pace
              runs. They do not change holdings, lifecycle, model assumptions or
              strategic targets.
            </p>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <ReviewAction
                title="Portfolio Rank"
                description="Record incremental-capital priorities from currently available canonical inputs."
                label="Run reason"
                reason={rankReason}
                onReason={setRankReason}
                pending={rankPending}
                error={rankError}
                onSubmit={recordPortfolioRank}
                buttonLabel="Record Portfolio Rank"
                disabled={decisionRunsBlockedReason !== undefined}
                disabledReason={decisionRunsBlockedReason}
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
                disabled={decisionRunsBlockedReason !== undefined}
                disabledReason={decisionRunsBlockedReason}
              />
            </div>
          </details>
        </div>
      </details>
    </div>
  );
}
