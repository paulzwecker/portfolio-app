"use client";

import { Badge } from "@/components/ui/badge";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError } from "@/components/app/empty-state";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyRankings,
  isWatchlistRankInputSnapshot,
  isPortfolioRankInputSnapshot,
  isResearchRankInputSnapshot,
  rankingTypes,
  type RankingType,
} from "@/lib/domain-contracts";
import { date, percent, quantity } from "@/lib/display";

const rankingLabels: Record<RankingType, string> = {
  PORTFOLIO: "Portfolio Rank",
  WATCHLIST: "Watchlist Rank",
  RESEARCH: "Research Rank",
};

export function RankingPanel({ companyId }: { companyId: string }) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/rankings`,
    isCompanyRankings,
  );
  return (
    <section
      id="ranking-context"
      aria-labelledby="ranking-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="ranking-title" className="text-xl font-semibold">
          Ranking snapshots
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Portfolio, Watchlist and Research ranks remain separate. A missing
          input or rank is shown explicitly and never becomes position zero.
        </p>
      </div>
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          {rankingTypes.map((type) => {
            const current = state.data!.current.find(
              (ranking) => ranking.definition.ranking_type === type,
            );
            const history = state.data!.history.filter(
              (item) => item.run.definition.ranking_type === type,
            );
            const entry = current?.entry;
            const rankContext =
              type === "WATCHLIST" &&
              isWatchlistRankInputSnapshot(entry?.input_snapshot)
                ? entry.input_snapshot
                : null;
            const portfolioRankContext =
              type === "PORTFOLIO" &&
              isPortfolioRankInputSnapshot(entry?.input_snapshot)
                ? entry.input_snapshot
                : null;
            const researchRankContext =
              type === "RESEARCH" &&
              isResearchRankInputSnapshot(entry?.input_snapshot)
                ? entry.input_snapshot
                : null;
            const value = !current?.run
              ? "No run recorded"
              : !entry
                ? "Not included in latest run"
                : entry.status === "RANKED"
                  ? `#${entry.position}`
                  : entry.status;
            return (
              <Card key={type} className="min-w-0 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    {rankingLabels[type]}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="text-xl font-semibold tabular-nums">{value}</p>
                  <p className="text-xs leading-5 text-muted-foreground">
                    {current?.definition.implementation_status ===
                    "NOT_MIGRATED"
                      ? "Ranking inputs are not migrated. Any stored position is a source snapshot, not a recalculated rank."
                      : current?.definition.methodology}
                  </p>
                  {current?.run && (
                    <>
                      <Badge variant="secondary">
                        Run {current.run.status} · {current.run.ranked_count}/
                        {current.run.company_count} ranked
                      </Badge>
                      {entry && entry.status !== "RANKED" && (
                        <p className="break-words text-xs leading-5">
                          {entry.reason}
                        </p>
                      )}
                      {rankContext && (
                        <div className="rounded-md bg-secondary/40 p-3 text-xs">
                          <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
                            <div>
                              <dt className="text-muted-foreground">
                                10Y Durability
                              </dt>
                              <dd className="mt-0.5 font-medium">
                                {rankContext.durability_10y.score === null
                                  ? rankContext.durability_10y.status.replaceAll(
                                      "_",
                                      " ",
                                    )
                                  : `${rankContext.durability_10y.score} / 5`}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Compounder Quality
                              </dt>
                              <dd className="mt-0.5 font-medium">
                                {rankContext.compounder_quality.score === null
                                  ? rankContext.compounder_quality.status.replaceAll(
                                      "_",
                                      " ",
                                    )
                                  : `${rankContext.compounder_quality.score} / 5`}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Forward Fundamental CAGR
                              </dt>
                              <dd className="mt-0.5 font-medium">
                                {percent(rankContext.forward_fundamental_cagr)}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Expected IRR
                              </dt>
                              <dd className="mt-0.5 font-medium">
                                {percent(rankContext.expected_irr)}
                              </dd>
                            </div>
                          </dl>
                          <p className="mt-2 text-muted-foreground">
                            {rankContext.return_source.source_kind ===
                            "NATIVE_MODEL_REVISION"
                              ? `Native revision ${rankContext.return_source.revision_number ?? "?"}`
                              : "Imported current contract"}
                            {rankContext.return_source.model_currency
                              ? ` · ${rankContext.return_source.model_currency}`
                              : " · currency unknown"}
                            {rankContext.return_source.price_effective_at
                              ? ` · price ${date(rankContext.return_source.price_effective_at)}`
                              : rankContext.return_source
                                    .effective_time_status === "UNKNOWN"
                                ? " · output effective date unknown"
                                : ""}
                          </p>
                          <details className="mt-2 border-t pt-2">
                            <summary className="cursor-pointer font-medium">
                              Assessment rationale and source
                            </summary>
                            <p className="mt-2 leading-5">
                              Durability:{" "}
                              {rankContext.durability_10y.rationale ??
                                "No rationale recorded."}
                            </p>
                            <p className="mt-1 leading-5">
                              Quality:{" "}
                              {rankContext.compounder_quality.rationale ??
                                "No rationale recorded."}
                            </p>
                            <p className="mt-1 break-words leading-5 text-muted-foreground">
                              {rankContext.return_source.source ??
                                "No model source recorded."}
                            </p>
                            <p className="mt-2 leading-5 text-muted-foreground">
                              {rankContext.context_note}
                            </p>
                          </details>
                        </div>
                      )}
                      {portfolioRankContext && (
                        <div className="rounded-md bg-secondary/40 p-3 text-xs">
                          <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
                            <div>
                              <dt className="text-muted-foreground">
                                Portfolio Score
                              </dt>
                              <dd className="mt-0.5 font-semibold tabular-nums">
                                {portfolioRankContext.portfolio_score === null
                                  ? "Unavailable"
                                  : `${quantity(portfolioRankContext.portfolio_score)} / 100`}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Expected Cash-Flow IRR
                              </dt>
                              <dd className="mt-0.5 font-medium tabular-nums">
                                {percent(portfolioRankContext.expected_irr)}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Current weight / target
                              </dt>
                              <dd className="mt-0.5 font-medium tabular-nums">
                                {percent(portfolioRankContext.current_weight)} /{" "}
                                {percent(portfolioRankContext.target_weight)}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Allocation gap
                              </dt>
                              <dd className="mt-0.5 font-medium tabular-nums">
                                {percent(
                                  portfolioRankContext.target_minus_current_gap,
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Lifecycle / valuation
                              </dt>
                              <dd className="mt-0.5 font-medium">
                                {portfolioRankContext.lifecycle ??
                                  "Unavailable"}{" "}
                                ·{" "}
                                {portfolioRankContext.allocation_status.replaceAll(
                                  "_",
                                  " ",
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Durability / Quality
                              </dt>
                              <dd className="mt-0.5 font-medium tabular-nums">
                                {portfolioRankContext.durability_10y.score ??
                                  portfolioRankContext.durability_10y
                                    .status}{" "}
                                /{" "}
                                {portfolioRankContext.compounder_quality
                                  .score ??
                                  portfolioRankContext.compounder_quality
                                    .status}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Execution / Risk
                              </dt>
                              <dd className="mt-0.5 font-medium tabular-nums">
                                {portfolioRankContext.execution.score ??
                                  portfolioRankContext.execution.status}{" "}
                                /{" "}
                                {portfolioRankContext.risk.score ??
                                  portfolioRankContext.risk.status}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Valuation uncertainty
                              </dt>
                              <dd className="mt-0.5 font-medium tabular-nums">
                                {percent(
                                  portfolioRankContext.valuation_uncertainty,
                                )}
                              </dd>
                            </div>
                          </dl>
                          <p className="mt-2 text-muted-foreground">
                            {portfolioRankContext.model_source?.model_key ??
                              "No model source"}{" "}
                            ·{" "}
                            {portfolioRankContext.model_source
                              ?.model_currency ?? "currency unknown"}{" "}
                            · reference price{" "}
                            {portfolioRankContext.model_source
                              ?.price_effective_at
                              ? date(
                                  portfolioRankContext.model_source
                                    .price_effective_at,
                                )
                              : "unavailable"}
                          </p>
                          <details className="mt-2 border-t pt-2">
                            <summary className="cursor-pointer font-medium">
                              Score contribution breakdown
                            </summary>
                            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
                              {Object.entries(
                                portfolioRankContext.score_contributions,
                              ).map(([name, value]) => (
                                <div key={name} className="contents">
                                  <dt className="text-muted-foreground">
                                    {name.replaceAll("_", " ")}
                                  </dt>
                                  <dd className="text-right tabular-nums">
                                    {value === null
                                      ? "Unavailable"
                                      : quantity(value)}
                                  </dd>
                                </div>
                              ))}
                            </dl>
                            <p className="mt-2 leading-5 text-muted-foreground">
                              {portfolioRankContext.context_note} Target,
                              current weight, allocation gap and Execution Pace
                              remain separate state; this rank does not change
                              them.
                            </p>
                          </details>
                        </div>
                      )}
                      {researchRankContext && (
                        <div className="rounded-md bg-secondary/40 p-3 text-xs">
                          <p className="font-medium">
                            Research attention context
                          </p>
                          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2">
                            <div>
                              <dt className="text-muted-foreground">
                                Candidate tier
                              </dt>
                              <dd className="mt-0.5 font-medium">
                                {researchRankContext.candidate_tier ??
                                  "Unavailable"}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Research Sort Key
                              </dt>
                              <dd className="mt-0.5 font-medium tabular-nums">
                                {researchRankContext.sort_key === null
                                  ? "Unavailable"
                                  : quantity(researchRankContext.sort_key)}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Persistent priority seed
                              </dt>
                              <dd className="mt-0.5 font-medium tabular-nums">
                                {researchRankContext.priority_seed === null
                                  ? researchRankContext.used_legacy_default
                                    ? `Blank · source fallback ${quantity(researchRankContext.legacy_default_priority_seed)}`
                                    : "Unavailable"
                                  : quantity(researchRankContext.priority_seed)}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">
                                Input state
                              </dt>
                              <dd className="mt-0.5 font-medium">
                                {researchRankContext.input_quality.replaceAll(
                                  "_",
                                  " ",
                                )}
                              </dd>
                            </div>
                          </dl>
                          <p className="mt-2 leading-5 text-muted-foreground">
                            {researchRankContext.context_note} Research Rank
                            prioritizes research attention only; it is separate
                            from Watchlist/Portfolio Rank and does not change
                            lifecycle.
                          </p>
                        </div>
                      )}
                      <p className="text-xs text-muted-foreground">
                        As of {date(current.run.as_of)} · Recorded{" "}
                        {date(current.run.recorded_at)} · {current.run.actor}
                      </p>
                    </>
                  )}
                  <details className="border-t pt-3">
                    <summary className="cursor-pointer text-xs font-medium">
                      Ranking history ({history.length})
                    </summary>
                    {history.length === 0 ? (
                      <p className="mt-3 text-xs text-muted-foreground">
                        No historical run contains this company.
                      </p>
                    ) : (
                      <ol className="mt-3 space-y-3">
                        {history.map(({ run, entry: historicalEntry }) => (
                          <li
                            key={historicalEntry.id}
                            className="border-l-2 pl-3 text-xs"
                          >
                            <p className="font-medium">
                              {historicalEntry.status === "RANKED"
                                ? `#${historicalEntry.position}`
                                : historicalEntry.status}
                            </p>
                            <p className="mt-1 text-muted-foreground">
                              As of {date(run.as_of)} · Recorded{" "}
                              {date(run.recorded_at)} · {run.actor}
                            </p>
                            <p className="mt-2 break-words leading-5">
                              {historicalEntry.reason}
                            </p>
                            <p className="mt-1 text-muted-foreground">
                              Run: {run.status} · Definition v
                              {run.definition.version}
                            </p>
                          </li>
                        ))}
                      </ol>
                    )}
                  </details>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}
