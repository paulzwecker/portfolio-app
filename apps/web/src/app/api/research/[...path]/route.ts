import {
  isAttentionFeed,
  isDetail,
  isEvent,
  isFxObservation,
  isFxObservations,
  isListingMarketData,
  isOverview,
  isPortfolios,
  isScoreCurrents,
  isScoreDefinitions,
  isScoreHistory,
  isScoreHistoryEntry,
  isCompanyModelOutputsCurrent,
  isCompanyFinancialModelMigration,
  isModelOutputHistory,
  isCompanyRankings,
  isRankingDefinitions,
  isRankingRun,
  isRankingRunDetail,
  isRankingRuns,
  isExecutionPaceRun,
  isExecutionPaceRunDetail,
  isExecutionPaceRuns,
  isCompanyExecutionPace,
  isUniverseExecutionPaceSummary,
  isUniverseRankingSummary,
  isUniverseMarketSummary,
  isUniverseEstimateMomentumSummary,
  isUniverseScoreSummary,
  isUniverseModelOutputSummary,
  isUniverse,
  isFinancialModel,
  isFinancialModels,
  isFinancialModelRevisionDetail,
  isFinancialModelRevisionHistory,
  isFinancialModelCalculationPreview,
  isFinancialModelContract,
  isFinancialModelContractPreview,
  isFinancialModelContractImport,
  isExtendedFinancialModel,
  isExtendedFinancialModels,
  isExtendedFinancialModelRevision,
  isAdditionalModelPortableContractResponse,
  isAdditionalModelContractPreview,
  isAdditionalModelContractImport,
  isOwnerCashFlowCalculationPreview,
  isResidualIncomeCalculationPreview,
  isCompanyReportedFundamentals,
  isCompanyConsensusEstimates,
  isCompanyEstimateMomentum,
  isCompanyExpectedReturnHistory,
  isCompanyExpectedReturnAttribution,
  isCompanyTemporalAlignment,
  isCompanySourceDocuments,
  isSourceDocument,
  isReportedFundamentalDefinitions,
} from "@/lib/domain-contracts";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const headers = { "Cache-Control": "no-store" };
const id = "[0-9a-fA-F-]{36}";
const readable = new RegExp(
  `^(attention|universe|universe/score-summary|universe/ranking-summary|universe/execution-pace-summary|universe/market-summary|universe/estimate-momentum-summary|universe/model-output-summary|score-definitions|ranking-definitions|ranking-runs|ranking-runs/${id}|execution-pace-runs|execution-pace-runs/${id}|reported-fundamental-definitions|portfolios|companies/${id}|companies/${id}/(market-data|reported-fundamentals|source-documents|consensus-estimates|estimate-momentum|execution-pace|expected-return-history|expected-return-attribution|temporal-alignment|scores/(current|history)|rankings|model-outputs/(current|history)|model-migration-status|financial-models|canonical-financial-models)|financial-models/${id}(/contract|/revisions(/${id})?)?|canonical-financial-models/${id}(/contract(/(preview|import))?|/revisions/${id})?|listings/${id}/market-data|fx-observations|portfolios/${id}/overview)$`,
);
const writable = new RegExp(
  `^(companies/${id}/(lifecycle-transitions|score-assessments|source-documents|financial-models|financial-models/preview|canonical-financial-models/(owner-cash-flow|residual-income)(/preview)?)|financial-models/${id}/(revisions|revisions/preview|contract/(preview|import))|canonical-financial-models/${id}/(owner-cash-flow|residual-income)/revisions(/preview)?|canonical-financial-models/${id}/contract/(preview|import)|ranking-runs|execution-pace-runs|fx-observations)$`,
);

function validWrite(path: string, data: unknown): boolean {
  if (path.startsWith("canonical-financial-models/")) {
    if (path.endsWith("/contract/preview"))
      return isAdditionalModelContractPreview(data);
    if (path.endsWith("/contract/import"))
      return isAdditionalModelContractImport(data);
    if (path.endsWith("/owner-cash-flow/revisions/preview"))
      return isOwnerCashFlowCalculationPreview(data);
    if (path.endsWith("/residual-income/revisions/preview"))
      return isResidualIncomeCalculationPreview(data);
    if (
      path.endsWith("/owner-cash-flow/revisions") ||
      path.endsWith("/residual-income/revisions")
    )
      return isExtendedFinancialModelRevision(data);
    return false;
  }
  if (path.includes("/canonical-financial-models/")) {
    if (path.endsWith("/owner-cash-flow/preview"))
      return isOwnerCashFlowCalculationPreview(data);
    if (path.endsWith("/residual-income/preview"))
      return isResidualIncomeCalculationPreview(data);
    if (path.endsWith("/owner-cash-flow") || path.endsWith("/residual-income"))
      return isExtendedFinancialModel(data);
    return false;
  }
  if (path.endsWith("score-assessments")) return isScoreHistoryEntry(data);
  if (path.endsWith("/source-documents")) return isSourceDocument(data);
  if (
    path.endsWith("/revisions/preview") ||
    path.endsWith("/financial-models/preview")
  )
    return isFinancialModelCalculationPreview(data);
  if (path.endsWith("/contract/preview"))
    return isFinancialModelContractPreview(data);
  if (path.endsWith("/contract/import"))
    return isFinancialModelContractImport(data);
  if (path.endsWith("/financial-models")) return isFinancialModel(data);
  if (path.endsWith("/revisions")) return isFinancialModelRevisionDetail(data);
  if (path === "ranking-runs") return isRankingRun(data);
  if (path === "execution-pace-runs") return isExecutionPaceRun(data);
  if (path === "fx-observations") return isFxObservation(data);
  return isEvent(data);
}

function validRead(path: string, data: unknown): boolean {
  if (path === "attention") return isAttentionFeed(data);
  if (path.startsWith("canonical-financial-models/")) {
    if (path.endsWith("/contract"))
      return isAdditionalModelPortableContractResponse(data);
    if (path.includes("/revisions/"))
      return isExtendedFinancialModelRevision(data);
    return isExtendedFinancialModel(data);
  }
  if (path === "universe") return isUniverse(data);
  if (path === "reported-fundamental-definitions")
    return isReportedFundamentalDefinitions(data);
  if (path.startsWith("companies/") && path.endsWith("/reported-fundamentals"))
    return isCompanyReportedFundamentals(data);
  if (path.startsWith("companies/") && path.endsWith("/consensus-estimates"))
    return isCompanyConsensusEstimates(data);
  if (path.startsWith("companies/") && path.endsWith("/estimate-momentum"))
    return isCompanyEstimateMomentum(data);
  if (
    path.startsWith("companies/") &&
    path.endsWith("/expected-return-history")
  )
    return isCompanyExpectedReturnHistory(data);
  if (
    path.startsWith("companies/") &&
    path.endsWith("/expected-return-attribution")
  )
    return isCompanyExpectedReturnAttribution(data);
  if (path.startsWith("companies/") && path.endsWith("/temporal-alignment"))
    return isCompanyTemporalAlignment(data);
  if (path.startsWith("companies/") && path.endsWith("/source-documents"))
    return isCompanySourceDocuments(data);
  if (path === "universe/score-summary") return isUniverseScoreSummary(data);
  if (path === "universe/ranking-summary")
    return isUniverseRankingSummary(data);
  if (path === "universe/execution-pace-summary")
    return isUniverseExecutionPaceSummary(data);
  if (path === "universe/market-summary") return isUniverseMarketSummary(data);
  if (path === "universe/estimate-momentum-summary")
    return isUniverseEstimateMomentumSummary(data);
  if (path === "universe/model-output-summary")
    return isUniverseModelOutputSummary(data);
  if (path === "fx-observations") return isFxObservations(data);
  if (path === "score-definitions") return isScoreDefinitions(data);
  if (path === "ranking-definitions") return isRankingDefinitions(data);
  if (path === "ranking-runs") return isRankingRuns(data);
  if (path.startsWith("ranking-runs/")) return isRankingRunDetail(data);
  if (path === "execution-pace-runs") return isExecutionPaceRuns(data);
  if (path.startsWith("execution-pace-runs/"))
    return isExecutionPaceRunDetail(data);
  if (path.startsWith("companies/") && path.endsWith("/execution-pace"))
    return isCompanyExecutionPace(data);
  if (path === "universe/execution-pace-summary")
    return isUniverseExecutionPaceSummary(data);
  if (path.startsWith("companies/") && path.endsWith("/rankings"))
    return isCompanyRankings(data);
  if (path === "portfolios") return isPortfolios(data);
  if (path.endsWith("/overview")) return isOverview(data);
  if (path.endsWith("/scores/current")) return isScoreCurrents(data);
  if (path.endsWith("/scores/history")) return isScoreHistory(data);
  if (path.endsWith("/model-outputs/current"))
    return isCompanyModelOutputsCurrent(data);
  if (path.endsWith("/model-migration-status"))
    return isCompanyFinancialModelMigration(data);
  if (path.endsWith("/model-outputs/history"))
    return isModelOutputHistory(data);
  if (path.endsWith("/contract")) return isFinancialModelContract(data);
  if (path.endsWith("/canonical-financial-models"))
    return isExtendedFinancialModels(data);
  if (path.endsWith("/financial-models")) return isFinancialModels(data);
  if (path.endsWith("/revisions")) return isFinancialModelRevisionHistory(data);
  if (path.includes("/revisions/")) return isFinancialModelRevisionDetail(data);
  if (path.startsWith("financial-models/")) return isFinancialModel(data);
  if (path.endsWith("/market-data") && path.startsWith("listings/"))
    return isListingMarketData(data);
  if (path.endsWith("/market-data"))
    return Array.isArray(data) && data.every(isListingMarketData);
  return isDetail(data);
}

async function proxy(request: Request, path: string[]) {
  const joined = path.join("/");
  if (!(request.method === "GET" ? readable : writable).test(joined)) {
    return Response.json(
      { detail: "Unknown research operation" },
      { status: 404, headers },
    );
  }
  try {
    const base = process.env.API_BASE_URL;
    if (!base) throw new Error("Missing API configuration");
    const url = new URL(`v1/${joined}`, `${base.replace(/\/$/, "")}/`);
    if (!["http:", "https:"].includes(url.protocol))
      throw new Error("Invalid API configuration");
    const search = new URL(request.url).searchParams;
    for (const key of [
      "lifecycle",
      "search",
      "dimension",
      "ranking_type",
      "history_limit",
      "base_currency",
      "quote_currency",
      "period_type",
      "as_of",
      "known_at",
      "outcome_known_at",
      "fiscal_year",
      "horizon_days",
      "prior_point_id",
      "current_point_id",
      "document_type",
      "company_id",
      "event_type",
      "severity",
      "status",
      "lookback_days",
      "limit",
    ]) {
      const value = search.get(key);
      if (
        value !== null &&
        joined === "attention" &&
        [
          "company_id",
          "event_type",
          "lifecycle",
          "severity",
          "status",
          "lookback_days",
          "limit",
        ].includes(key)
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        (joined === "universe" ||
          joined === "universe/score-summary" ||
          joined === "universe/market-summary" ||
          joined === "universe/estimate-momentum-summary") &&
        key !== "dimension"
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        joined === "score-definitions" &&
        key === "dimension"
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        joined === "ranking-definitions" &&
        key === "ranking_type"
      )
        url.searchParams.set(key, value);
      if (value !== null && joined === "ranking-runs" && key === "ranking_type")
        url.searchParams.set(key, value);
      if (
        value !== null &&
        (joined.endsWith("/market-data") || joined === "fx-observations") &&
        ["history_limit", "base_currency", "quote_currency"].includes(key)
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        joined.startsWith("companies/") &&
        joined.endsWith("/rankings") &&
        key === "ranking_type"
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        joined.startsWith("companies/") &&
        joined.endsWith("/source-documents") &&
        ["document_type", "as_of", "known_at", "limit"].includes(key)
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        joined.startsWith("companies/") &&
        joined.endsWith("/temporal-alignment") &&
        [
          "fiscal_year",
          "as_of",
          "known_at",
          "outcome_known_at",
          "horizon_days",
        ].includes(key)
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        joined.startsWith("companies/") &&
        (joined.endsWith("/reported-fundamentals") ||
          joined.endsWith("/consensus-estimates") ||
          joined.endsWith("/estimate-momentum")) &&
        ["period_type", "as_of", "known_at"].includes(key)
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        joined.startsWith("companies/") &&
        joined.endsWith("/expected-return-history") &&
        ["as_of", "known_at"].includes(key)
      )
        url.searchParams.set(key, value);
      if (
        value !== null &&
        joined.startsWith("companies/") &&
        joined.endsWith("/expected-return-attribution") &&
        ["prior_point_id", "current_point_id", "as_of", "known_at"].includes(
          key,
        )
      )
        url.searchParams.set(key, value);
    }
    let body: string | undefined;
    if (request.method === "POST") {
      // Same-origin UI operation. No authenticated cross-origin editing interface.
      const origin = request.headers.get("origin");
      const requestUrl = new URL(request.url);
      // Next.js may construct request.url with its internal "localhost" hostname.
      // Host retains the browser's actual destination, including its local port.
      const host = request.headers.get("host") ?? requestUrl.host;
      if (
        origin &&
        (new URL(origin).host !== host ||
          new URL(origin).protocol !== requestUrl.protocol)
      ) {
        return Response.json(
          { detail: "Invalid request origin" },
          { status: 403, headers },
        );
      }
      body = await request.text();
      if (body.length > (joined.includes("financial-models") ? 100_000 : 5_000))
        return Response.json(
          { detail: "Request is too large" },
          { status: 413, headers },
        );
      try {
        JSON.parse(body);
      } catch {
        return Response.json(
          { detail: "Invalid JSON" },
          { status: 400, headers },
        );
      }
    }
    const response = await fetch(url, {
      method: request.method,
      body,
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(6000),
    });
    const data: unknown = await response.json();
    if (!response.ok) {
      const message =
        response.status === 409
          ? "The record changed or conflicts with existing data. Reload and retry."
          : response.status === 404
            ? "The requested record was not found."
            : response.status === 422
              ? joined.endsWith("score-assessments")
                ? "Check the score, status, reason and effective timestamp."
                : joined === "ranking-runs"
                  ? "Check the ranking type and run reason."
                  : joined === "fx-observations"
                    ? "Check the currencies, positive rate, effective timestamp and source."
                    : joined.includes("financial-models")
                      ? "Check the model inputs, all three scenarios, probabilities, currency and revision base."
                      : "Check the lifecycle selection, reason and effective timestamp."
              : "Research data is unavailable. Check the API, database and migrations.";
      return Response.json(
        { detail: message },
        {
          status: [404, 409, 422].includes(response.status)
            ? response.status
            : 503,
          headers,
        },
      );
    }
    const valid =
      request.method === "POST"
        ? validWrite(joined, data)
        : validRead(joined, data);
    if (!valid) throw new Error("Invalid domain response");
    return Response.json(data, { status: response.status, headers });
  } catch {
    return Response.json(
      {
        detail:
          "Research data is unavailable. Check the API, database and migrations.",
      },
      { status: 503, headers },
    );
  }
}

type Context = { params: Promise<{ path: string[] }> };
export async function GET(request: Request, context: Context) {
  return proxy(request, (await context.params).path);
}
export async function POST(request: Request, context: Context) {
  return proxy(request, (await context.params).path);
}
