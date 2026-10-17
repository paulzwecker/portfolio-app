import type {
  Company,
  CompanyPortfolioContext,
  ExecutionPaceHistoryEntry,
  Overview,
  PortfolioRankInputSnapshot,
  RankingCurrent,
  ReturnMethodology,
  UniverseExecutionPaceSummary,
  UniverseModelOutputSummary,
  UniverseRankingSummary,
  UniverseScoreSummary,
  WatchlistRankInputSnapshot,
} from "@/lib/domain-contracts";

export type AllocationPresence =
  "HELD" | "TARGET_ONLY" | "NO_POSITION" | "HOLDINGS_UNCONFIRMED";

export function allocationPresence(
  row: CompanyPortfolioContext,
  overview: Overview,
): AllocationPresence {
  if (row.positions.length > 0) return "HELD";
  if (overview.snapshot?.completeness !== "COMPLETE")
    return "HOLDINGS_UNCONFIRMED";
  if (row.target_weight !== null) return "TARGET_ONLY";
  return "NO_POSITION";
}

export type DecisionOpportunity = {
  company: Company;
  ranking: RankingCurrent | undefined;
  kind: "PORTFOLIO" | "WATCHLIST";
  rankPosition: number | null;
  rankStatus: string;
  rankReason: string;
  asOf: string | null;
  returnCohort: string | null;
  methodology: ReturnMethodology | null;
  expectedIrr: string | null;
  hurdle: string | null;
  expectedExcess: string | null;
  weightedFairValue: string | null;
  fairValueCurrency: string | null;
  rankTimeUpside: string | null;
  rankTimePriceStatus: string | null;
  rankTimePriceEffectiveAt: string | null;
  durability: string | null;
  compounderQuality: string | null;
  currentWeight: string | null;
  targetWeight: string | null;
  allocationGap: string | null;
  modelStatus: string | null;
  outputs: UniverseModelOutputSummary["outputs"] | undefined;
  scores: UniverseScoreSummary["scores"] | undefined;
  execution: ExecutionPaceHistoryEntry | null;
};

type RankInput = PortfolioRankInputSnapshot | WatchlistRankInputSnapshot;

function portfolioInput(
  ranking: RankingCurrent | undefined,
): PortfolioRankInputSnapshot | null {
  const input = ranking?.entry?.input_snapshot as RankInput | null | undefined;
  return input?.context_version.startsWith("portfolio-rank-inputs-")
    ? (input as PortfolioRankInputSnapshot)
    : null;
}

function watchlistInput(
  ranking: RankingCurrent | undefined,
): WatchlistRankInputSnapshot | null {
  const input = ranking?.entry?.input_snapshot as RankInput | null | undefined;
  return input?.context_version.startsWith("watchlist-rank-inputs-")
    ? (input as WatchlistRankInputSnapshot)
    : null;
}

function modelStatus(
  outputs: UniverseModelOutputSummary["outputs"] | undefined,
) {
  if (!outputs) return null;
  if (outputs.models.length === 0) return outputs.status;
  return outputs.models.map((model) => model.status).join(", ");
}

function currentRanking(
  summary: UniverseRankingSummary | undefined,
  kind: "PORTFOLIO" | "WATCHLIST",
) {
  return summary?.rankings.find(
    (ranking) => ranking.definition.ranking_type === kind,
  );
}

function scoreValue(
  scores: UniverseScoreSummary["scores"] | undefined,
  dimension: "DURABILITY_10Y" | "COMPOUNDER_QUALITY",
) {
  const current = scores?.find(
    (score) => score.definition.dimension === dimension,
  )?.assessment;
  return current?.status === "ASSESSED" ? current.score : null;
}

function baseOpportunity({
  company,
  ranking,
  kind,
  returnCohort,
  methodology,
  expectedIrr,
  hurdle,
  expectedExcess,
  weightedFairValue,
  fairValueCurrency,
  rankTimeUpside,
  rankTimePriceStatus,
  rankTimePriceEffectiveAt,
  durability,
  compounderQuality,
  currentWeight,
  targetWeight,
  allocationGap,
  outputs,
  scores,
  execution,
  rankingsAvailable,
}: {
  company: Company;
  ranking: RankingCurrent | undefined;
  kind: "PORTFOLIO" | "WATCHLIST";
  returnCohort: string | null;
  methodology: ReturnMethodology | null;
  expectedIrr: string | null;
  hurdle: string | null;
  expectedExcess: string | null;
  weightedFairValue: string | null;
  fairValueCurrency: string | null;
  rankTimeUpside: string | null;
  rankTimePriceStatus: string | null;
  rankTimePriceEffectiveAt: string | null;
  durability: string | null;
  compounderQuality: string | null;
  currentWeight: string | null;
  targetWeight: string | null;
  allocationGap: string | null;
  outputs: UniverseModelOutputSummary["outputs"] | undefined;
  scores: UniverseScoreSummary["scores"] | undefined;
  execution: ExecutionPaceHistoryEntry | null;
  rankingsAvailable: boolean;
}): DecisionOpportunity {
  const entry = ranking?.entry;
  const missingRankState = !rankingsAvailable
    ? {
        status: "SUMMARY_UNAVAILABLE",
        reason: "Ranking data has not loaded or is unavailable.",
      }
    : ranking === undefined
      ? {
          status: "NO_COMPANY_SUMMARY",
          reason: "No ranking summary row was returned for this company.",
        }
      : ranking.run === null
        ? {
            status: "NO_RUN",
            reason: "No ranking run is recorded for this company.",
          }
        : {
            status: "NO_COMPANY_RESULT",
            reason: "The latest ranking run returned no company result.",
          };
  return {
    company,
    ranking,
    kind,
    rankPosition: entry?.position ?? null,
    rankStatus: entry?.status ?? missingRankState.status,
    rankReason: entry?.reason ?? missingRankState.reason,
    asOf: ranking?.run?.as_of ?? null,
    returnCohort,
    methodology,
    expectedIrr,
    hurdle,
    expectedExcess,
    weightedFairValue,
    fairValueCurrency,
    rankTimeUpside,
    rankTimePriceStatus,
    rankTimePriceEffectiveAt,
    durability,
    compounderQuality,
    currentWeight,
    targetWeight,
    allocationGap,
    modelStatus: modelStatus(outputs),
    outputs,
    scores,
    execution,
  };
}

export function portfolioOpportunity(
  row: CompanyPortfolioContext,
  rankSummary: UniverseRankingSummary | undefined,
  outputSummary: UniverseModelOutputSummary | undefined,
  scoreSummary: UniverseScoreSummary | undefined,
  paceSummary: UniverseExecutionPaceSummary | undefined,
  rankingsAvailable = true,
): DecisionOpportunity {
  const ranking = currentRanking(rankSummary, "PORTFOLIO");
  const input = portfolioInput(ranking);
  const source = input?.model_source;
  return baseOpportunity({
    company: row.company,
    ranking,
    kind: "PORTFOLIO",
    returnCohort: input?.return_comparability_cohort ?? null,
    methodology: source?.return_methodology ?? null,
    expectedIrr: input?.expected_irr ?? null,
    hurdle: input?.hurdle ?? null,
    expectedExcess: input?.expected_excess ?? null,
    weightedFairValue: input?.weighted_fair_value ?? null,
    fairValueCurrency: source?.model_currency ?? null,
    rankTimeUpside: source?.current_calculation?.weighted_upside ?? null,
    rankTimePriceStatus: source?.current_calculation?.price_status ?? null,
    rankTimePriceEffectiveAt:
      source?.current_calculation?.price_effective_at ?? null,
    durability:
      input?.durability_10y.score ??
      scoreValue(scoreSummary?.scores, "DURABILITY_10Y"),
    compounderQuality:
      input?.compounder_quality.score ??
      scoreValue(scoreSummary?.scores, "COMPOUNDER_QUALITY"),
    currentWeight: row.current_weight,
    targetWeight: row.target_weight,
    allocationGap: row.allocation_gap,
    outputs: outputSummary?.outputs,
    scores: scoreSummary?.scores,
    execution: paceSummary?.decision ?? null,
    rankingsAvailable,
  });
}

export function watchlistOpportunity(
  summary: UniverseRankingSummary,
  outputSummary: UniverseModelOutputSummary | undefined,
  scoreSummary: UniverseScoreSummary | undefined,
  paceSummary: UniverseExecutionPaceSummary | undefined,
  rankingsAvailable = true,
): DecisionOpportunity {
  const ranking = currentRanking(summary, "WATCHLIST");
  const input = watchlistInput(ranking);
  const source = input?.return_source;
  return baseOpportunity({
    company: summary.company,
    ranking,
    kind: "WATCHLIST",
    returnCohort: input?.return_comparability_cohort ?? null,
    methodology: source?.return_methodology ?? null,
    expectedIrr: input?.expected_irr ?? null,
    hurdle: input?.hurdle ?? null,
    expectedExcess: input?.expected_excess ?? null,
    weightedFairValue: input?.weighted_fair_value ?? null,
    fairValueCurrency: source?.model_currency ?? null,
    rankTimeUpside: source?.current_calculation?.weighted_upside ?? null,
    rankTimePriceStatus: source?.current_calculation?.price_status ?? null,
    rankTimePriceEffectiveAt:
      source?.current_calculation?.price_effective_at ?? null,
    durability:
      input?.durability_10y.score ??
      scoreValue(scoreSummary?.scores, "DURABILITY_10Y"),
    compounderQuality:
      input?.compounder_quality.score ??
      scoreValue(scoreSummary?.scores, "COMPOUNDER_QUALITY"),
    currentWeight: null,
    targetWeight: null,
    allocationGap: null,
    outputs: outputSummary?.outputs,
    scores: scoreSummary?.scores,
    execution: paceSummary?.decision ?? null,
    rankingsAvailable,
  });
}

export function executionForCompany(
  companyId: string,
  paceRows: UniverseExecutionPaceSummary[] | undefined,
) {
  return (
    paceRows?.find((row) => row.company.id === companyId)?.decision ?? null
  );
}

export function allocationCompanies(overview: Overview) {
  return overview.companies.filter(
    (row) =>
      row.company.lifecycle === "PORTFOLIO" ||
      row.positions.length > 0 ||
      row.target_weight !== null,
  );
}
