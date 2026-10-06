import type { components } from "@portfolio/contracts";

export type Company = components["schemas"]["CompanyRead"];
export type Portfolio = components["schemas"]["PortfolioRead"];
export type Overview = components["schemas"]["PortfolioOverview"];
export type CompanyDetail = components["schemas"]["CompanyDetail"];
export type CompanyPortfolioContext =
  components["schemas"]["CompanyPortfolioContext"];
export type Lifecycle = components["schemas"]["Lifecycle"];
export type LifecycleEvent = components["schemas"]["LifecycleEventRead"];
export type ScoreDimension = components["schemas"]["ScoreDimension"];
export type ScoreStatus = components["schemas"]["ScoreAssessmentStatus"];
export type ScoreDefinition = components["schemas"]["ScoreDefinitionRead"];
export type ScoreCurrent = components["schemas"]["ScoreCurrentRead"];
export type ScoreHistoryEntry = components["schemas"]["ScoreHistoryEntry"];
export type UniverseScoreSummary =
  components["schemas"]["UniverseScoreSummary"];
export type RankingType = components["schemas"]["RankingType"];
export type RankingStatus = components["schemas"]["RankingEntryStatus"];
export type RankingCurrent = components["schemas"]["RankingCurrentRead"];
export type RankingDefinition = components["schemas"]["RankingDefinitionRead"];
export type RankingEntryRead = components["schemas"]["RankingEntryRead"];
export type WatchlistRankInputSnapshot =
  components["schemas"]["WatchlistRankInputSnapshot"];
export type PortfolioRankInputSnapshot =
  components["schemas"]["PortfolioRankInputSnapshot"];
export type ResearchRankInputSnapshot =
  components["schemas"]["ResearchRankInputSnapshot"];
export type RankingHistoryEntry = components["schemas"]["RankingHistoryEntry"];
export type RankingRun = components["schemas"]["RankingRunRead"];
export type CompanyRankings = components["schemas"]["CompanyRankingsRead"];
export type RankingRunEntry = components["schemas"]["RankingRunEntryRead"];
export type RankingRunDetail = components["schemas"]["RankingRunDetailRead"];
export type UniverseRankingSummary =
  components["schemas"]["UniverseRankingSummary"];
export type ExecutionPace = components["schemas"]["ExecutionPace"];
export type ExecutionPaceInputSnapshot =
  components["schemas"]["ExecutionPaceInputSnapshot"];
export type ExecutionPaceDecision =
  components["schemas"]["ExecutionPaceDecisionRead"];
export type ExecutionPaceRun = components["schemas"]["ExecutionPaceRunRead"];
export type ExecutionPaceRunDetail =
  components["schemas"]["ExecutionPaceRunDetailRead"];
export type ExecutionPaceHistoryEntry =
  components["schemas"]["ExecutionPaceHistoryEntry"];
export type CompanyExecutionPace =
  components["schemas"]["CompanyExecutionPaceRead"];
export type UniverseExecutionPaceSummary =
  components["schemas"]["UniverseExecutionPaceSummary"];
export type AttentionFeed = components["schemas"]["AttentionFeedRead"];
export type AttentionEvent = components["schemas"]["AttentionEventRead"];
export type ListingMarketData = components["schemas"]["ListingMarketData"];
export type PriceRegime = components["schemas"]["PriceRegimeRead"];
export type UniverseMarketSummary =
  components["schemas"]["UniverseMarketSummary"];
export type FxObservation = components["schemas"]["FxObservationRead"];
export type ReportedFundamentalObservation =
  components["schemas"]["ReportedFundamentalObservationRead"];
export type ReportedFundamentalPeriod =
  components["schemas"]["ReportedFundamentalPeriodRead"];
export type ReportedFundamentalCoverage =
  components["schemas"]["ReportedFundamentalCoverageRead"];
export type CompanyReportedFundamentals =
  components["schemas"]["CompanyReportedFundamentalsRead"];
export type ConsensusEstimateObservation =
  components["schemas"]["ConsensusEstimateObservationRead"];
export type ConsensusEstimatePeriod =
  components["schemas"]["ConsensusEstimatePeriodRead"];
export type ConsensusEstimateProvider =
  components["schemas"]["ConsensusEstimateProviderRead"];
export type CompanyConsensusEstimates =
  components["schemas"]["CompanyConsensusEstimatesRead"];
export type EstimateMomentumWindow =
  components["schemas"]["EstimateMomentumWindowRead"];
export type EstimateMomentumPeriod =
  components["schemas"]["EstimateMomentumPeriodRead"];
export type EstimateMomentumSummary =
  components["schemas"]["EstimateMomentumSummaryRead"];
export type CompanyEstimateMomentum =
  components["schemas"]["CompanyEstimateMomentumRead"];
export type UniverseEstimateMomentumSummary =
  components["schemas"]["UniverseEstimateMomentumRead"];
export type TemporalAlignedValue =
  components["schemas"]["TemporalAlignedValueRead"];
export type TemporalPrice = components["schemas"]["TemporalPriceRead"];
export type TemporalReturn = components["schemas"]["TemporalReturnRead"];
export type TemporalModelForecast =
  components["schemas"]["TemporalModelForecastRead"];
export type CompanyTemporalAlignment =
  components["schemas"]["CompanyTemporalAlignmentRead"];
export type ExpectedReturnEstimate =
  components["schemas"]["ExpectedReturnEstimateRead"];
export type ExpectedReturnEstimateContext =
  components["schemas"]["ExpectedReturnEstimateContextRead"];
export type ExpectedReturnMarketPrice =
  components["schemas"]["ExpectedReturnMarketPriceRead"];
export type ExpectedReturnHistoryPoint =
  components["schemas"]["ExpectedReturnHistoryPointRead"];
export type CompanyExpectedReturnHistory =
  components["schemas"]["CompanyExpectedReturnHistoryRead"];
export type ExpectedReturnAttributionDriver =
  components["schemas"]["ExpectedReturnAttributionDriverRead"];
export type ExpectedReturnAttributionState =
  components["schemas"]["ExpectedReturnAttributionStateRead"];
export type ExpectedReturnAttributionContextChanges =
  components["schemas"]["ExpectedReturnAttributionContextChangesRead"];
export type CompanyExpectedReturnAttribution =
  components["schemas"]["CompanyExpectedReturnAttributionRead"];
export type SourceDocument = components["schemas"]["SourceDocumentRead"];
export type CompanySourceDocuments =
  components["schemas"]["CompanySourceDocumentsRead"];
export type ReportedFundamentalDefinition =
  components["schemas"]["ReportedFundamentalDefinitionRead"];
export type ModelOutputSnapshot =
  components["schemas"]["ModelOutputSnapshotRead"];
export type ModelOutputCurrentModel =
  components["schemas"]["ModelOutputCurrentModelRead"];
export type CompanyModelOutputsCurrent =
  components["schemas"]["CompanyModelOutputsCurrentRead"];
export type CompanyFinancialModelMigration =
  components["schemas"]["CompanyFinancialModelMigrationRead"];
export type CompanyFinancialModelMigrationItem =
  components["schemas"]["CompanyFinancialModelMigrationItemRead"];
export type UniverseModelOutputSummary =
  components["schemas"]["UniverseModelOutputSummary"];
export type FinancialModel = components["schemas"]["FinancialModelRead"];
export type FinancialModelCreate =
  components["schemas"]["FinancialModelCreate"];
export type FinancialModelRevision =
  components["schemas"]["FinancialModelRevisionRead"];
export type FinancialModelRevisionSummary =
  components["schemas"]["FinancialModelRevisionSummary"];
export type FinancialModelRevisionCreate =
  components["schemas"]["FinancialModelRevisionCreate"];
export type DcfScenario = components["schemas"]["DcfScenario"];
export type DcfScenarioInput = components["schemas"]["DcfScenarioInput-Input"];
export type DcfOperatingBase = components["schemas"]["DcfOperatingBase-Input"];
export type DcfYearAssumptionInput =
  components["schemas"]["DcfYearAssumptionInput-Input"];
export type DcfProjection = components["schemas"]["DcfProjectionRead-Output"];
export type FinancialModelOutputs =
  components["schemas"]["FinancialModelOutputsRead-Output"];
export type FinancialModelCalculationOutputs =
  components["schemas"]["FinancialModelCalculationOutputsRead"];
export type FinancialModelCalculationPreview =
  components["schemas"]["FinancialModelCalculationPreviewRead"];
export type DcfProjectionCalculationPreview =
  components["schemas"]["DcfProjectionCalculationPreviewRead"];
export type FinancialModelContract =
  components["schemas"]["FinancialModelContractV1-Output"];
export type FinancialModelContractPreview =
  components["schemas"]["FinancialModelContractPreviewRead"];
export type FinancialModelContractImport =
  components["schemas"]["FinancialModelContractImportRead"];
export type ExtendedFinancialModel =
  components["schemas"]["ExtendedFinancialModelRead"];
export type OwnerCashFlowInput =
  components["schemas"]["OwnerCashFlowInput-Input"];
export type OwnerCashFlowScenario =
  components["schemas"]["OwnerCashFlowScenarioInput-Input"];
export type OwnerCashFlowYear =
  components["schemas"]["OwnerCashFlowYearInput-Input"];
export type ResidualIncomeInput =
  components["schemas"]["ResidualIncomeInput-Input"];
export type ResidualIncomeScenario =
  components["schemas"]["ResidualIncomeScenarioInput-Input"];
export type OwnerCashFlowRevisionRead =
  components["schemas"]["OwnerCashFlowRevisionRead"];
export type ResidualIncomeRevisionRead =
  components["schemas"]["ResidualIncomeRevisionRead"];
export type ExtendedFinancialModelRevision =
  OwnerCashFlowRevisionRead | ResidualIncomeRevisionRead;
export type AdditionalModelPortableContract =
  components["schemas"]["AdditionalModelPortableContractV2-Output"];
export type AdditionalModelContractPreview =
  components["schemas"]["AdditionalModelContractPreviewRead"];
export type AdditionalModelContractImport =
  components["schemas"]["AdditionalModelContractImportRead"];
export type OwnerCashFlowCalculationPreview =
  components["schemas"]["OwnerCashFlowCalculationPreviewRead"];
export type ResidualIncomeCalculationPreview =
  components["schemas"]["ResidualIncomeCalculationPreviewRead"];

export const lifecycleStates: Lifecycle[] = [
  "PORTFOLIO",
  "WATCHLIST",
  "CANDIDATE",
  "DROP",
];
export const scoreDimensions: ScoreDimension[] = [
  "DURABILITY_10Y",
  "COMPOUNDER_QUALITY",
  "EXECUTION",
  "RISK",
];
export const rankingTypes: RankingType[] = [
  "PORTFOLIO",
  "WATCHLIST",
  "RESEARCH",
];
export const executionPaces: ExecutionPace[] = [
  "ACCELERATE",
  "BUILD",
  "NORMAL_BUILD",
  "SMALL_LADDER",
  "LADDER",
  "HOLD",
  "SLOW_LIMIT",
  "WAIT_LIMIT",
  "PATIENT_TRIM",
  "TRIM_FASTER",
  "NORMAL_TRIM",
  "PATIENT_EXIT",
  "NORMAL_EXIT",
];
export const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null;
const string = (v: unknown) => typeof v === "string";
const nullableString = (v: unknown) => v === null || string(v);
const uuid = (v: unknown) =>
  string(v) &&
  /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(v as string);
const nullableUuid = (v: unknown) => v === null || uuid(v);
const decimal = (v: unknown) =>
  string(v) && /^\d+(?:\.\d+)?$/.test(v as string);
const nullableDecimal = (v: unknown) => v === null || decimal(v);
const signedDecimal = (v: unknown) =>
  string(v) && /^-?\d+(?:\.\d+)?$/.test(v as string);
const nullableSignedDecimal = (v: unknown) => v === null || signedDecimal(v);
const timestamp = (v: unknown) =>
  string(v) && Number.isFinite(Date.parse(v as string));
const array = (v: unknown, check: (item: unknown) => boolean) =>
  Array.isArray(v) && v.every(check);
const lifecycle = (v: unknown) => lifecycleStates.includes(v as Lifecycle);

export function isCompany(v: unknown): v is Company {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    string(v.name) &&
    nullableString(v.reporting_currency) &&
    timestamp(v.created_at) &&
    typeof v.is_demo === "boolean" &&
    (v.lifecycle === null || lifecycle(v.lifecycle)) &&
    nullableUuid(v.lifecycle_event_id)
  );
}

const modelOutputFields = [
  "bear_fv",
  "base_fv",
  "bull_fv",
  "bear_probability",
  "base_probability",
  "bull_probability",
  "weighted_fv",
  "weighted_upside",
  "expected_cash_flow_irr",
  "hurdle",
  "expected_excess",
  "forward_fundamental_cagr",
] as const;

export function isModelOutputSnapshot(v: unknown): v is ModelOutputSnapshot {
  if (!isRecord(v)) return false;
  const probabilities = [
    v.bear_probability,
    v.base_probability,
    v.bull_probability,
  ];
  return (
    uuid(v.id) &&
    uuid(v.company_id) &&
    string(v.model_key) &&
    string(v.snapshot_key) &&
    ["CURRENT_CONTRACT", "LEGACY_REVISION"].includes(
      v.snapshot_kind as string,
    ) &&
    nullableString(v.contract_version) &&
    [
      "PASS",
      "NOT_MAPPED",
      "NO_CONTRACT",
      "DATA_CHECK",
      "HISTORICAL_ONLY",
    ].includes(v.contract_status as string) &&
    ["COMPLETE", "PARTIAL", "DATA_CHECK", "UNAVAILABLE"].includes(
      v.output_quality as string,
    ) &&
    (v.model_currency === null ||
      (string(v.model_currency) && /^[A-Z]{3}$/.test(v.model_currency))) &&
    ["DOCUMENTED", "UNKNOWN"].includes(v.currency_status as string) &&
    nullableString(v.currency_source_ref) &&
    nullableString(v.model_status) &&
    (v.effective_at === null || timestamp(v.effective_at)) &&
    timestamp(v.recorded_at) &&
    v.actor === "IMPORT" &&
    string(v.source) &&
    nullableString(v.source_revision_id) &&
    nullableString(v.revision_source) &&
    nullableString(v.revision_type) &&
    nullableString(v.source_actor) &&
    nullableString(v.rationale) &&
    nullableString(v.evidence) &&
    nullableString(v.notes) &&
    array(
      v.field_issues,
      (issue) =>
        isRecord(issue) &&
        Object.values(issue).every(string) &&
        string(issue.field) &&
        string(issue.reason) &&
        string(issue.raw_value) &&
        string(issue.source),
    ) &&
    modelOutputFields.every((field) => nullableSignedDecimal(v[field])) &&
    probabilities.every(
      (value) =>
        value === null ||
        (signedDecimal(value) && Number(value) >= 0 && Number(value) <= 1),
    ) &&
    ((v.model_currency === null && v.currency_status === "UNKNOWN") ||
      (v.model_currency !== null && v.currency_status === "DOCUMENTED"))
  );
}

function isModelOutputCurrentModel(v: unknown): v is ModelOutputCurrentModel {
  return (
    isRecord(v) &&
    string(v.model_key) &&
    [
      "PUBLISHED",
      "PARTIAL",
      "NOT_MAPPED",
      "NO_CONTRACT",
      "DATA_CHECK",
    ].includes(v.status as string) &&
    isModelOutputSnapshot(v.snapshot) &&
    v.snapshot.model_key === v.model_key
  );
}

export function isCompanyModelOutputsCurrent(
  v: unknown,
): v is CompanyModelOutputsCurrent {
  if (
    !isRecord(v) ||
    !uuid(v.company_id) ||
    !Number.isInteger(v.history_count) ||
    Number(v.history_count) < 0 ||
    !array(v.models, isModelOutputCurrentModel) ||
    ![
      "AVAILABLE",
      "PARTIAL",
      "NOT_MAPPED",
      "NO_CONTRACT",
      "DATA_CHECK",
      "NO_MODEL",
    ].includes(v.status as string)
  )
    return false;
  const result = v as CompanyModelOutputsCurrent;
  return result.models.every(
    (item) => item.snapshot.company_id === result.company_id,
  );
}

const modelRepresentationStatuses = [
  "NATIVE_EDITABLE",
  "NATIVE_WITH_PARITY_ISSUE",
  "IMPORTED_OUTPUT_ONLY",
  "UNSUPPORTED_LEGACY",
  "LEGACY_ONLY",
  "NOT_IMPORTED",
];

export function isCompanyFinancialModelMigration(
  v: unknown,
): v is CompanyFinancialModelMigration {
  return (
    isRecord(v) &&
    uuid(v.company_id) &&
    typeof v.inventory_available === "boolean" &&
    array(
      v.models,
      (model) =>
        isRecord(model) &&
        string(model.model_key) &&
        string(model.company_name) &&
        nullableString(model.canonical_ticker) &&
        string(model.lifecycle) &&
        string(model.methodology_family) &&
        nullableString(model.model_currency) &&
        [
          "READY_FOR_NATIVE_IMPORT",
          "NEEDS_MAPPING",
          "UNSUPPORTED_METHOD",
          "DATA_CHECK",
          "LEGACY_ONLY",
        ].includes(model.inventory_status as string) &&
        modelRepresentationStatuses.includes(
          model.representation_status as string,
        ) &&
        typeof model.output_snapshot_available === "boolean" &&
        string(model.output_contract_status) &&
        nullableUuid(model.native_model_id) &&
        (model.native_revision_number === null ||
          (Number.isInteger(model.native_revision_number) &&
            Number(model.native_revision_number) > 0)) &&
        (model.parity_status === null ||
          ["PARITY_PASS", "PARTIAL_MAPPING", "DATA_CHECK", "BLOCKED"].includes(
            model.parity_status as string,
          )) &&
        [
          model.projections_compared,
          model.projections_passed,
          model.outputs_compared,
          model.outputs_passed,
        ].every(
          (count) =>
            count === null || (Number.isInteger(count) && Number(count) >= 0),
        ) &&
        array(model.blockers, string) &&
        nullableString(model.legacy_return_semantics),
    )
  );
}

export function isModelOutputHistory(v: unknown): v is ModelOutputSnapshot[] {
  return array(v, isModelOutputSnapshot);
}

export function isUniverseModelOutputSummary(
  v: unknown,
): v is UniverseModelOutputSummary[] {
  return (
    Array.isArray(v) &&
    v.every(
      (item) =>
        isRecord(item) &&
        isCompany(item.company) &&
        isCompanyModelOutputsCurrent(item.outputs) &&
        item.outputs.company_id === item.company.id,
    )
  );
}
export function isPortfolio(v: unknown): v is Portfolio {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    string(v.name) &&
    string(v.base_currency) &&
    timestamp(v.created_at) &&
    typeof v.is_demo === "boolean"
  );
}
export const isUniverse = (v: unknown): v is Company[] => array(v, isCompany);
function isPriceObservation(
  v: unknown,
): v is components["schemas"]["PriceObservationRead"] {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.listing_id) &&
    timestamp(v.market_date) &&
    timestamp(v.recorded_at) &&
    nullableDecimal(v.provider_close) &&
    nullableDecimal(v.split_adjusted_close) &&
    nullableDecimal(v.total_return_close) &&
    nullableDecimal(v.volume) &&
    string(v.currency) &&
    string(v.provider) &&
    string(v.provider_symbol) &&
    string(v.adjustment_basis) &&
    ["PASS", "PASS_VERIFIED_FALLBACK", "UNSPECIFIED", "INVALID"].includes(
      v.data_quality as string,
    ) &&
    string(v.source_ref)
  );
}
function isPriceRegime(v: unknown): v is PriceRegime {
  return (
    isRecord(v) &&
    uuid(v.listing_id) &&
    timestamp(v.as_of) &&
    [
      "provider_close",
      "split_adjusted_close",
      "dma_20",
      "dma_50",
      "dma_200",
      "high_52w",
      "drawdown_52w",
      "vs_dma_20",
      "vs_dma_50",
      "vs_dma_200",
      "return_1m",
      "return_3m",
      "return_6m",
      "realized_vol_20d",
    ].every((key) => nullableSignedDecimal(v[key])) &&
    nullableString(v.trend_state) &&
    nullableString(v.correction_state) &&
    nullableString(v.regime) &&
    ["PASS", "DATA_CHECK", "UNSPECIFIED"].includes(v.data_quality as string) &&
    nullableString(v.quality_reason) &&
    string(v.methodology_version) &&
    string(v.source_ref)
  );
}
function validListingMarketData(v: unknown): v is ListingMarketData {
  if (!isRecord(v)) return false;
  if (!(
    isRecord(v.listing) &&
    uuid(v.listing.id) &&
    uuid(v.listing.security_id) &&
    string(v.listing.ticker) &&
    string(v.listing.venue) &&
    nullableString(v.listing.currency) &&
    typeof v.listing.is_demo === "boolean" &&
    ["FRESH", "STALE", "QUALITY_CHECK", "NO_DATA"].includes(
      v.freshness as string,
    ) &&
    (v.age_days === null || Number.isInteger(v.age_days)) &&
    (v.price_regime === null || isPriceRegime(v.price_regime)) &&
    array(v.history, isPriceObservation)
  ))
    return false;
  const ageDays = v.age_days;
  const latest = v.latest;
  if (latest === null) return v.freshness === "NO_DATA" && ageDays === null;
  if (!isPriceObservation(latest)) return false;
  if (typeof ageDays !== "number" || ageDays < 0) return false;
  if (v.freshness === "FRESH")
    return (
      ["PASS", "PASS_VERIFIED_FALLBACK"].includes(latest.data_quality) &&
      latest.split_adjusted_close !== null &&
      ageDays <= 5
    );
  if (v.freshness === "STALE") return ageDays > 5;
  return (
    latest.data_quality === "UNSPECIFIED" ||
    latest.data_quality === "INVALID" ||
    latest.split_adjusted_close === null
  );
}
export function isListingMarketData(v: unknown): v is ListingMarketData {
  return validListingMarketData(v);
}
export const isListingMarketDataList = (v: unknown): v is ListingMarketData[] =>
  array(v, validListingMarketData);
export function isUniverseMarketSummary(
  v: unknown,
): v is UniverseMarketSummary[] {
  return array(
    v,
    (item) =>
      isRecord(item) &&
      isCompany(item.company) &&
      array(item.market_data, validListingMarketData),
  );
}
export function isFxObservation(v: unknown): v is FxObservation {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    string(v.base_currency) &&
    string(v.quote_currency) &&
    decimal(v.rate) &&
    timestamp(v.effective_at) &&
    timestamp(v.recorded_at) &&
    string(v.provider) &&
    string(v.source) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string) &&
    string(v.reason)
  );
}
export function isFxObservations(v: unknown): v is FxObservation[] {
  return array(v, isFxObservation);
}
function isScoreDefinition(v: unknown): v is ScoreDefinition {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    scoreDimensions.includes(v.dimension as ScoreDimension) &&
    Number.isInteger(v.version) &&
    decimal(v.minimum_score) &&
    decimal(v.maximum_score) &&
    Number(v.minimum_score) <= Number(v.maximum_score) &&
    ["HIGHER_IS_BETTER", "HIGHER_IS_RISK"].includes(
      v.directionality as string,
    ) &&
    string(v.units) &&
    string(v.methodology) &&
    timestamp(v.effective_from) &&
    ["ACTIVE", "RETIRED"].includes(v.status as string) &&
    timestamp(v.recorded_at) &&
    ((v.dimension === "RISK" &&
      v.directionality === "HIGHER_IS_RISK" &&
      Number(v.minimum_score) === 1 &&
      Number(v.maximum_score) === 5) ||
      (v.dimension !== "RISK" && v.directionality === "HIGHER_IS_BETTER"))
  );
}
function isScoreAssessment(v: unknown, definition?: unknown) {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.company_id) &&
    uuid(v.score_definition_id) &&
    (definition === undefined ||
      (isRecord(definition) && v.score_definition_id === definition.id)) &&
    (v.score === null ||
      (decimal(v.score) &&
        definition !== undefined &&
        isRecord(definition) &&
        Number(v.score) >= Number(definition.minimum_score) &&
        Number(v.score) <= Number(definition.maximum_score))) &&
    ["ASSESSED", "MISSING", "UNAVAILABLE", "INVALID"].includes(
      v.status as string,
    ) &&
    ((v.status === "ASSESSED" && v.score !== null) ||
      (v.status !== "ASSESSED" && v.score === null)) &&
    timestamp(v.effective_at) &&
    timestamp(v.recorded_at) &&
    string(v.rationale) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string) &&
    nullableString(v.source) &&
    nullableUuid(v.superseded_assessment_id)
  );
}
export function isScoreCurrent(v: unknown): v is ScoreCurrent {
  return (
    isRecord(v) &&
    isScoreDefinition(v.definition) &&
    v.definition.status === "ACTIVE" &&
    (v.assessment === null || isScoreAssessment(v.assessment, v.definition))
  );
}
export function isScoreCurrents(v: unknown): v is ScoreCurrent[] {
  if (!Array.isArray(v) || v.length !== scoreDimensions.length) return false;
  if (!v.every(isScoreCurrent)) return false;
  const scores = v as ScoreCurrent[];
  return (
    new Set(scores.map((item) => item.definition.dimension)).size ===
      scoreDimensions.length &&
    scoreDimensions.every((dimension) =>
      scores.some((item) => item.definition.dimension === dimension),
    )
  );
}
export function isScoreHistoryEntry(v: unknown): v is ScoreHistoryEntry {
  return (
    isRecord(v) &&
    isScoreDefinition(v.definition) &&
    isScoreAssessment(v.assessment, v.definition)
  );
}
export const isScoreHistory = (v: unknown): v is ScoreHistoryEntry[] =>
  array(v, isScoreHistoryEntry);
export const isScoreDefinitions = (v: unknown) => array(v, isScoreDefinition);
export const isUniverseScoreSummary = (
  v: unknown,
): v is UniverseScoreSummary[] =>
  array(
    v,
    (item) =>
      isRecord(item) && isCompany(item.company) && isScoreCurrents(item.scores),
  );

function isRankingDefinition(v: unknown): v is RankingDefinition {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    rankingTypes.includes(v.ranking_type as RankingType) &&
    Number.isInteger(v.version) &&
    string(v.title) &&
    string(v.methodology) &&
    string(v.population_rule) &&
    string(v.required_inputs) &&
    string(v.source_reference) &&
    ["NOT_MIGRATED", "PARTIAL", "READY"].includes(
      v.implementation_status as string,
    ) &&
    timestamp(v.effective_from) &&
    ["ACTIVE", "RETIRED"].includes(v.status as string) &&
    timestamp(v.recorded_at)
  );
}
export const isRankingDefinitions = (v: unknown) =>
  array(v, isRankingDefinition);
export function isRankingRun(v: unknown): v is RankingRun {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    isRankingDefinition(v.definition) &&
    timestamp(v.as_of) &&
    timestamp(v.recorded_at) &&
    ["COMPLETE", "PARTIAL", "UNAVAILABLE"].includes(v.status as string) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string) &&
    string(v.reason) &&
    nullableString(v.source) &&
    Number.isInteger(v.company_count) &&
    Number.isInteger(v.ranked_count) &&
    Number(v.ranked_count) <= Number(v.company_count)
  );
}
export const isRankingRuns = (v: unknown) => array(v, isRankingRun);
function isWatchlistRankScore(v: unknown): boolean {
  return (
    isRecord(v) &&
    nullableDecimal(v.score) &&
    ["ASSESSED", "MISSING", "UNAVAILABLE", "INVALID", "NOT_ASSESSED"].includes(
      v.status as string,
    ) &&
    nullableUuid(v.assessment_id) &&
    (v.effective_at === null || timestamp(v.effective_at)) &&
    (v.recorded_at === null || timestamp(v.recorded_at)) &&
    nullableString(v.rationale) &&
    nullableString(v.source)
  );
}
function isWatchlistRankReturnSource(v: unknown): boolean {
  return (
    isRecord(v) &&
    ["NATIVE_MODEL_REVISION", "IMPORTED_CURRENT_CONTRACT"].includes(
      v.source_kind as string,
    ) &&
    uuid(v.record_id) &&
    nullableUuid(v.model_id) &&
    nullableUuid(v.revision_id) &&
    (v.revision_number === null || Number.isInteger(v.revision_number)) &&
    nullableString(v.model_key) &&
    nullableString(v.model_type) &&
    nullableString(v.methodology_version) &&
    nullableString(v.contract_version) &&
    nullableString(v.source_revision_id) &&
    nullableString(v.source) &&
    (v.effective_at === null || timestamp(v.effective_at)) &&
    timestamp(v.recorded_at) &&
    ["KNOWN", "UNKNOWN"].includes(v.effective_time_status as string) &&
    nullableString(v.model_currency) &&
    ["DOCUMENTED", "UNKNOWN"].includes(v.currency_status as string) &&
    ["COMPLETE", "PARTIAL", "DATA_CHECK", "UNAVAILABLE"].includes(
      v.output_quality as string,
    ) &&
    (v.contract_status === null ||
      [
        "PASS",
        "NOT_MAPPED",
        "NO_CONTRACT",
        "DATA_CHECK",
        "HISTORICAL_ONLY",
      ].includes(v.contract_status as string)) &&
    (v.price_status === null ||
      [
        "FRESH",
        "STALE",
        "QUALITY_CHECK",
        "NO_DATA",
        "CURRENCY_MISMATCH",
        "CURRENCY_UNKNOWN",
      ].includes(v.price_status as string)) &&
    (v.price_effective_at === null || timestamp(v.price_effective_at)) &&
    nullableUuid(v.price_observation_id) &&
    nullableUuid(v.listing_id) &&
    nullableString(v.listing_ticker) &&
    nullableString(v.listing_venue) &&
    (v.migration_status === null ||
      ["PARITY_PASS", "PARTIAL_MAPPING", "DATA_CHECK", "BLOCKED"].includes(
        v.migration_status as string,
      ))
  );
}
export function isWatchlistRankInputSnapshot(
  v: unknown,
): v is WatchlistRankInputSnapshot {
  return (
    isRecord(v) &&
    v.context_version === "watchlist-rank-inputs-v1" &&
    nullableSignedDecimal(v.expected_irr) &&
    ["NATIVE_METHOD_OUTPUT", "LEGACY_NORMALIZED_FIELD"].includes(
      v.return_semantics as string,
    ) &&
    isWatchlistRankReturnSource(v.return_source) &&
    isWatchlistRankScore(v.durability_10y) &&
    isWatchlistRankScore(v.compounder_quality) &&
    nullableSignedDecimal(v.forward_fundamental_cagr) &&
    nullableSignedDecimal(v.weighted_fair_value) &&
    nullableSignedDecimal(v.hurdle) &&
    nullableSignedDecimal(v.expected_excess) &&
    v.decision_context === "QUALITY_GATE_THRESHOLDS_NOT_DOCUMENTED" &&
    string(v.context_note)
  );
}
function isPortfolioRankScoreSnapshot(v: unknown): boolean {
  return (
    isRecord(v) &&
    nullableDecimal(v.score) &&
    ["ASSESSED", "MISSING", "UNAVAILABLE", "INVALID", "NOT_ASSESSED"].includes(
      v.status as string,
    ) &&
    nullableUuid(v.assessment_id) &&
    (v.effective_at === null || timestamp(v.effective_at)) &&
    (v.recorded_at === null || timestamp(v.recorded_at)) &&
    nullableString(v.source)
  );
}
function isPortfolioRankModelSource(v: unknown): boolean {
  return (
    isRecord(v) &&
    ["NATIVE_MODEL_REVISION", "IMPORTED_CURRENT_CONTRACT"].includes(
      v.source_kind as string,
    ) &&
    uuid(v.record_id) &&
    nullableUuid(v.model_id) &&
    nullableUuid(v.revision_id) &&
    (v.revision_number === null || Number.isInteger(v.revision_number)) &&
    string(v.model_key) &&
    nullableString(v.model_type) &&
    nullableString(v.methodology_version) &&
    nullableString(v.source) &&
    (v.effective_at === null || timestamp(v.effective_at)) &&
    timestamp(v.recorded_at) &&
    ["KNOWN", "UNKNOWN"].includes(v.effective_time_status as string) &&
    nullableString(v.model_currency) &&
    ["DOCUMENTED", "UNKNOWN"].includes(v.currency_status as string) &&
    ["COMPLETE", "PARTIAL", "DATA_CHECK", "UNAVAILABLE"].includes(
      v.output_quality as string,
    ) &&
    (v.contract_status === null ||
      [
        "PASS",
        "NOT_MAPPED",
        "NO_CONTRACT",
        "DATA_CHECK",
        "HISTORICAL_ONLY",
      ].includes(v.contract_status as string)) &&
    (v.price_status === null ||
      [
        "FRESH",
        "STALE",
        "QUALITY_CHECK",
        "NO_DATA",
        "CURRENCY_MISMATCH",
        "CURRENCY_UNKNOWN",
      ].includes(v.price_status as string)) &&
    (v.price_effective_at === null || timestamp(v.price_effective_at)) &&
    nullableUuid(v.price_observation_id) &&
    nullableUuid(v.listing_id) &&
    nullableString(v.listing_ticker) &&
    nullableString(v.listing_venue)
  );
}
function isPortfolioRankContributions(v: unknown): boolean {
  return (
    isRecord(v) &&
    nullableSignedDecimal(v.target_underweight) &&
    nullableSignedDecimal(v.expected_irr) &&
    nullableSignedDecimal(v.durability_10y) &&
    nullableSignedDecimal(v.compounder_quality) &&
    nullableSignedDecimal(v.execution) &&
    nullableSignedDecimal(v.risk) &&
    nullableSignedDecimal(v.valuation_uncertainty_penalty) &&
    nullableSignedDecimal(v.negative_expected_excess_penalty)
  );
}
export function isPortfolioRankInputSnapshot(
  v: unknown,
): v is PortfolioRankInputSnapshot {
  return (
    isRecord(v) &&
    v.context_version === "portfolio-rank-inputs-v1" &&
    v.score_formula === "LEGACY_IRR_FIRST_ALLOCATION_V1" &&
    nullableSignedDecimal(v.portfolio_score) &&
    nullableSignedDecimal(v.current_weight) &&
    nullableSignedDecimal(v.target_weight) &&
    nullableSignedDecimal(v.target_minus_current_gap) &&
    [
      "VALUED",
      "PRICE_COVERAGE_INCOMPLETE",
      "FX_UNAVAILABLE",
      "PORTFOLIO_TOTAL_UNAVAILABLE",
    ].includes(v.allocation_status as string) &&
    (v.lifecycle === null ||
      ["PORTFOLIO", "WATCHLIST", "CANDIDATE", "DROP"].includes(
        v.lifecycle as string,
      )) &&
    nullableUuid(v.holding_snapshot_id) &&
    (v.holding_effective_at === null || timestamp(v.holding_effective_at)) &&
    nullableUuid(v.target_revision_id) &&
    (v.target_effective_at === null || timestamp(v.target_effective_at)) &&
    nullableSignedDecimal(v.expected_irr) &&
    nullableSignedDecimal(v.expected_excess) &&
    nullableSignedDecimal(v.hurdle) &&
    nullableSignedDecimal(v.bear_fair_value) &&
    nullableSignedDecimal(v.weighted_fair_value) &&
    nullableSignedDecimal(v.bull_fair_value) &&
    nullableSignedDecimal(v.valuation_uncertainty) &&
    isPortfolioRankScoreSnapshot(v.durability_10y) &&
    isPortfolioRankScoreSnapshot(v.compounder_quality) &&
    isPortfolioRankScoreSnapshot(v.execution) &&
    isPortfolioRankScoreSnapshot(v.risk) &&
    (v.model_source === null || isPortfolioRankModelSource(v.model_source)) &&
    isPortfolioRankContributions(v.score_contributions) &&
    string(v.context_note)
  );
}
export function isResearchRankInputSnapshot(
  v: unknown,
): v is ResearchRankInputSnapshot {
  return (
    isRecord(v) &&
    v.context_version === "research-rank-inputs-v1" &&
    (v.lifecycle === null ||
      ["PORTFOLIO", "WATCHLIST", "CANDIDATE", "DROP"].includes(
        v.lifecycle as string,
      )) &&
    (v.candidate_tier === null ||
      ["HIGH", "LOW"].includes(v.candidate_tier as string)) &&
    nullableSignedDecimal(v.priority_seed) &&
    nullableSignedDecimal(v.legacy_default_priority_seed) &&
    typeof v.used_legacy_default === "boolean" &&
    nullableSignedDecimal(v.sort_key) &&
    ["AVAILABLE", "MISSING", "DATA_CHECK"].includes(
      v.input_quality as string,
    ) &&
    nullableString(v.source_digest) &&
    nullableString(v.bucket_source_ref) &&
    nullableString(v.priority_seed_source_ref) &&
    string(v.context_note)
  );
}
function isRankingEntry(v: unknown): v is RankingEntryRead {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.run_id) &&
    uuid(v.company_id) &&
    [
      "RANKED",
      "INPUTS_UNAVAILABLE",
      "NOT_ELIGIBLE",
      "EXCLUDED",
      "NOT_MIGRATED",
      "DATA_CHECK",
    ].includes(v.status as string) &&
    ((v.status === "RANKED" &&
      Number.isInteger(v.position) &&
      Number(v.position) > 0) ||
      (v.status !== "RANKED" && v.position === null)) &&
    string(v.reason) &&
    (v.input_snapshot === null ||
      v.input_snapshot === undefined ||
      isWatchlistRankInputSnapshot(v.input_snapshot) ||
      isPortfolioRankInputSnapshot(v.input_snapshot) ||
      isResearchRankInputSnapshot(v.input_snapshot))
  );
}
export function isRankingCurrent(v: unknown): v is RankingCurrent {
  if (!isRecord(v) || !isRankingDefinition(v.definition)) return false;
  if (v.definition.status !== "ACTIVE") return false;
  if (v.run !== null && !isRankingRun(v.run)) return false;
  if (v.entry !== null && !isRankingEntry(v.entry)) return false;
  if (v.run !== null && v.run.definition.id !== v.definition.id) return false;
  return v.entry === null || (v.run !== null && v.entry.run_id === v.run.id);
}
export function isRankingCurrents(v: unknown): v is RankingCurrent[] {
  if (!Array.isArray(v) || v.length !== rankingTypes.length) return false;
  if (!v.every(isRankingCurrent)) return false;
  const rankings = v as RankingCurrent[];
  return (
    new Set(rankings.map((item) => item.definition.ranking_type)).size ===
      rankingTypes.length &&
    rankingTypes.every((type) =>
      rankings.some((item) => item.definition.ranking_type === type),
    )
  );
}
function isRankingHistoryEntry(v: unknown): v is RankingHistoryEntry {
  if (!isRecord(v) || !isRankingRun(v.run) || !isRankingEntry(v.entry))
    return false;
  return v.run.id === v.entry.run_id;
}
export function isCompanyRankings(v: unknown): v is CompanyRankings {
  if (
    isRecord(v) &&
    isRankingCurrents(v.current) &&
    array(v.history, (item) => {
      if (!isRankingHistoryEntry(item)) return false;
      return true;
    })
  ) {
    const value = v as CompanyRankings;
    const companyIds = [
      ...value.current
        .map((ranking) => ranking.entry?.company_id)
        .filter((companyId): companyId is string => companyId !== undefined),
      ...value.history.map((item) => item.entry.company_id),
    ];
    return new Set(companyIds).size <= 1;
  }
  return false;
}

function isRankingRunEntry(v: unknown): v is RankingRunEntry {
  if (!isRecord(v) || !isCompany(v.company) || !isRankingEntry(v.entry))
    return false;
  return v.entry.company_id === v.company.id;
}

export function isUniverseRankingSummary(
  v: unknown,
): v is UniverseRankingSummary[] {
  if (!Array.isArray(v)) return false;
  return v.every((item) => {
    if (
      !isRecord(item) ||
      !isCompany(item.company) ||
      !isRankingCurrents(item.rankings)
    )
      return false;
    const row = item as UniverseRankingSummary;
    return row.rankings.every(
      (ranking) =>
        ranking.entry === null || ranking.entry.company_id === row.company.id,
    );
  });
}

export function isRankingRunDetail(v: unknown): v is RankingRunDetail {
  return (
    isRecord(v) &&
    isRankingRun(v.run) &&
    Array.isArray(v.entries) &&
    v.entries.every(isRankingRunEntry) &&
    (v.entries as RankingRunEntry[]).every(
      (item) => item.entry.run_id === (v.run as RankingRun).id,
    )
  );
}

const executionDecisionStatuses = [
  "AVAILABLE",
  "REVIEW",
  "UNAVAILABLE",
  "NOT_APPLICABLE",
] as const;

function isExecutionPaceInputSnapshot(
  v: unknown,
): v is ExecutionPaceInputSnapshot {
  if (!isRecord(v) || v.context_version !== "execution-pace-inputs-v1")
    return false;
  const nullableDecimals = [
    "current_weight",
    "target_weight",
    "allocation_gap",
    "expected_irr",
    "hurdle",
    "price",
    "model_reference_price",
    "weighted_fair_value",
    "weighted_upside",
    "valuation_range_ratio",
  ];
  const nullableIds = [
    "target_revision_id",
    "holding_snapshot_id",
    "model_source_id",
    "model_revision_id",
    "model_output_snapshot_id",
    "valuation_listing_id",
    "price_observation_id",
    "model_price_observation_id",
  ];
  const nullableTimes = [
    "target_effective_at",
    "holding_effective_at",
    "model_effective_at",
    "model_recorded_at",
    "price_market_date",
    "price_recorded_at",
    "model_price_effective_at",
    "price_regime_as_of",
  ];
  return (
    (v.lifecycle === null || lifecycle(v.lifecycle)) &&
    nullableIds.every((key) => nullableUuid(v[key])) &&
    nullableTimes.every((key) => v[key] === null || timestamp(v[key])) &&
    nullableDecimals.every((key) => nullableSignedDecimal(v[key])) &&
    [
      "allocation_status",
      "model_key",
      "model_currency",
      "model_output_quality",
      "model_contract_status",
      "model_review_flag",
      "valuation_ticker",
      "valuation_venue",
      "valuation_currency",
      "price_currency",
      "price_provider",
      "price_quality",
      "model_price_status",
      "model_price_currency",
      "estimate_provider_id",
      "estimate_momentum_reason",
      "price_regime_source_ref",
      "price_regime_raw",
      "price_regime",
    ].every((key) => nullableString(v[key])) &&
    ["NATIVE_MODEL_REVISION", "IMPORTED_CURRENT_CONTRACT", null].includes(
      v.model_source_kind as string | null,
    ) &&
    ["NATIVE_METHOD_OUTPUT", "LEGACY_NORMALIZED_FIELD", null].includes(
      v.return_semantics as string | null,
    ) &&
    ["FRESH", "STALE", "QUALITY_CHECK", "NO_DATA"].includes(
      v.price_freshness as string,
    ) &&
    (v.valuation_zone === null ||
      ["DEEP_DISCOUNT", "DISCOUNT", "NEAR_FAIR", "RICH", "VERY_RICH"].includes(
        v.valuation_zone as string,
      )) &&
    (v.estimate_momentum_availability === null ||
      [
        "AVAILABLE",
        "DIRECTION_ONLY",
        "INSUFFICIENT_HISTORY",
        "NO_MAPPING",
        "AMBIGUOUS_SOURCE",
      ].includes(v.estimate_momentum_availability as string)) &&
    (v.estimate_momentum_direction === null ||
      [
        "POSITIVE",
        "MILD_POSITIVE",
        "NEUTRAL_MIXED",
        "MILD_NEGATIVE",
        "NEGATIVE",
      ].includes(v.estimate_momentum_direction as string)) &&
    (v.estimate_momentum_freshness === null ||
      ["FRESH", "STALE", "DATA_CHECK", "NO_DATA"].includes(
        v.estimate_momentum_freshness as string,
      )) &&
    (v.estimate_momentum_quality === null ||
      ["PASS", "DATA_CHECK", "INVALID", "NO_DATA"].includes(
        v.estimate_momentum_quality as string,
      )) &&
    (v.price_regime_quality === null ||
      ["PASS", "DATA_CHECK", "UNSPECIFIED"].includes(
        v.price_regime_quality as string,
      )) &&
    ["FRESH", "STALE", "DATA_CHECK", "NO_DATA"].includes(
      v.price_regime_freshness as string,
    ) &&
    (v.estimate_latest_snapshot_date === null ||
      dateOnly(v.estimate_latest_snapshot_date)) &&
    Array.isArray(v.context_notes) &&
    v.context_notes.every(string)
  );
}

export function isExecutionPaceDecision(
  v: unknown,
): v is ExecutionPaceDecision {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.run_id) &&
    uuid(v.company_id) &&
    nullableUuid(v.target_revision_id) &&
    nullableUuid(v.holding_snapshot_id) &&
    nullableUuid(v.model_revision_id) &&
    nullableUuid(v.model_output_snapshot_id) &&
    nullableUuid(v.price_observation_id) &&
    executionDecisionStatuses.includes(v.decision_status as never) &&
    (v.pace === null || executionPaces.includes(v.pace as ExecutionPace)) &&
    ((v.decision_status === "AVAILABLE" && v.pace !== null) ||
      (v.decision_status !== "AVAILABLE" && v.pace === null)) &&
    string(v.reason) &&
    isExecutionPaceInputSnapshot(v.input_snapshot)
  );
}

export function isExecutionPaceRun(v: unknown): v is ExecutionPaceRun {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.portfolio_id) &&
    timestamp(v.as_of) &&
    timestamp(v.recorded_at) &&
    string(v.methodology_version) &&
    ["COMPLETE", "PARTIAL", "UNAVAILABLE"].includes(v.status as string) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string) &&
    string(v.reason) &&
    nullableString(v.source) &&
    [
      "company_count",
      "available_count",
      "review_count",
      "unavailable_count",
      "not_applicable_count",
    ].every((key) => Number.isInteger(v[key])) &&
    Number(v.available_count) +
      Number(v.review_count) +
      Number(v.unavailable_count) +
      Number(v.not_applicable_count) ===
      Number(v.company_count)
  );
}
export const isExecutionPaceRuns = (v: unknown): v is ExecutionPaceRun[] =>
  array(v, isExecutionPaceRun);

export function isExecutionPaceHistoryEntry(
  v: unknown,
): v is ExecutionPaceHistoryEntry {
  return (
    isRecord(v) &&
    isExecutionPaceRun(v.run) &&
    isExecutionPaceDecision(v.decision) &&
    v.decision.run_id === v.run.id
  );
}

export function isCompanyExecutionPace(v: unknown): v is CompanyExecutionPace {
  if (
    !isRecord(v) ||
    !uuid(v.company_id) ||
    !(v.current === null || isExecutionPaceHistoryEntry(v.current)) ||
    !array(v.history, isExecutionPaceHistoryEntry)
  )
    return false;
  const history = v.history as ExecutionPaceHistoryEntry[];
  return (
    (v.current === null || v.current.decision.company_id === v.company_id) &&
    history.every((item) => item.decision.company_id === v.company_id)
  );
}

export function isUniverseExecutionPaceSummary(
  v: unknown,
): v is UniverseExecutionPaceSummary[] {
  return array(
    v,
    (item) =>
      isRecord(item) &&
      isCompany(item.company) &&
      (item.decision === null ||
        (isExecutionPaceHistoryEntry(item.decision) &&
          item.decision.decision.company_id === item.company.id)),
  );
}

export function isExecutionPaceRunDetail(
  v: unknown,
): v is ExecutionPaceRunDetail {
  if (!isRecord(v) || !isExecutionPaceRun(v.run)) return false;
  const run = v.run;
  return array(
    v.decisions,
    (item) =>
      isRecord(item) &&
      isCompany(item.company) &&
      isExecutionPaceDecision(item.decision) &&
      item.decision.run_id === run.id &&
      item.decision.company_id === item.company.id,
  );
}
export const isPortfolios = (v: unknown): v is Portfolio[] =>
  array(v, isPortfolio);

function isAudit(v: unknown) {
  return (
    isRecord(v) &&
    timestamp(v.effective_at) &&
    timestamp(v.recorded_at) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string) &&
    string(v.reason) &&
    nullableString(v.source)
  );
}
export function isEvent(v: unknown): v is LifecycleEvent {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.company_id) &&
    isAudit(v) &&
    lifecycle(v.new_state) &&
    (v.previous_state === null || lifecycle(v.previous_state)) &&
    Number.isInteger(v.sequence)
  );
}
function isSnapshot(v: unknown) {
  return (
    v === null ||
    (isRecord(v) &&
      uuid(v.id) &&
      uuid(v.portfolio_id) &&
      isAudit(v) &&
      ["COMPLETE", "PARTIAL", "UNAVAILABLE"].includes(
        v.completeness as string,
      ) &&
      array(
        v.positions,
        (p) => isRecord(p) && uuid(p.listing_id) && nullableDecimal(p.quantity),
      ) &&
      array(
        v.cash_positions,
        (p) => isRecord(p) && string(p.currency) && nullableDecimal(p.balance),
      ))
  );
}
function isTarget(v: unknown) {
  return (
    v === null ||
    (isRecord(v) &&
      uuid(v.id) &&
      uuid(v.portfolio_id) &&
      isAudit(v) &&
      ["DRAFT", "ACCEPTED"].includes(v.status as string) &&
      (v.accepted_at === null || timestamp(v.accepted_at)) &&
      decimal(v.invested_weight) &&
      decimal(v.strategic_cash_weight) &&
      array(
        v.allocations,
        (a) => isRecord(a) && uuid(a.company_id) && decimal(a.weight),
      ))
  );
}
function isPosition(p: unknown) {
  return (
    isRecord(p) &&
    uuid(p.listing_id) &&
    uuid(p.security_id) &&
    string(p.ticker) &&
    string(p.venue) &&
    nullableString(p.currency) &&
    string(p.security_name) &&
    nullableDecimal(p.quantity) &&
    nullableDecimal(p.latest_price) &&
    (p.price_date === null || timestamp(p.price_date)) &&
    (p.price_currency === null || string(p.price_currency)) &&
    ["FRESH", "STALE", "QUALITY_CHECK", "NO_DATA"].includes(
      p.price_freshness as string,
    ) &&
    nullableDecimal(p.native_market_value) &&
    nullableDecimal(p.base_market_value) &&
    [
      "VALUED",
      "PRICE_UNAVAILABLE",
      "FX_UNAVAILABLE",
      "QUANTITY_UNAVAILABLE",
    ].includes(p.valuation_status as string)
  );
}
function isCompanyPortfolioContext(v: unknown): v is CompanyPortfolioContext {
  return (
    isRecord(v) &&
    isCompany(v.company) &&
    array(v.positions, isPosition) &&
    nullableDecimal(v.target_weight) &&
    nullableDecimal(v.current_market_value) &&
    nullableString(v.current_market_currency) &&
    nullableDecimal(v.current_weight) &&
    nullableSignedDecimal(v.allocation_gap) &&
    [
      "VALUED",
      "PRICE_COVERAGE_INCOMPLETE",
      "FX_UNAVAILABLE",
      "PORTFOLIO_TOTAL_UNAVAILABLE",
    ].includes(v.allocation_status as string)
  );
}
export function isOverview(v: unknown): v is Overview {
  if (!isRecord(v)) return false;
  if (!(
    isPortfolio(v.portfolio) &&
    isSnapshot(v.snapshot) &&
    isTarget(v.target_revision) &&
    [
      "VALUED",
      "NO_HOLDING_SNAPSHOT",
      "INCOMPLETE_HOLDINGS",
      "INCOMPLETE_PRICE_COVERAGE",
      "INCOMPLETE_FX_COVERAGE",
    ].includes(v.valuation_status as string) &&
    nullableDecimal(v.base_market_value) &&
    string(v.valuation_currency) &&
    array(v.companies, isCompanyPortfolioContext) &&
    array(v.standalone_positions, isPosition) &&
    array(
      v.cash_valuations,
      (cash) =>
        isRecord(cash) &&
        string(cash.currency) &&
        nullableDecimal(cash.balance) &&
        nullableDecimal(cash.base_market_value) &&
        ["VALUED", "FX_UNAVAILABLE", "BALANCE_UNAVAILABLE"].includes(
          cash.valuation_status as string,
        ),
    ) &&
    array(
      v.valuation_gaps,
      (gap) => isRecord(gap) && string(gap.identity) && string(gap.reason),
    )
  ))
    return false;
  const companies = v.companies as Overview["companies"];
  if (v.valuation_status === "VALUED") return v.base_market_value !== null;
  return (
    v.base_market_value === null &&
    companies.every(
      (company) =>
        company.current_weight === null && company.allocation_gap === null,
    )
  );
}
export function isDetail(v: unknown): v is CompanyDetail {
  return (
    isRecord(v) &&
    isCompany(v.company) &&
    array(
      v.securities,
      (s) =>
        isRecord(s) &&
        uuid(s.id) &&
        nullableUuid(s.company_id) &&
        string(s.name) &&
        ["COMMON_STOCK", "ADR", "PREFERRED", "ETF"].includes(
          s.security_type as string,
        ) &&
        nullableString(s.share_class) &&
        nullableUuid(s.underlying_security_id) &&
        typeof s.is_demo === "boolean",
    ) &&
    array(
      v.listings,
      (l) =>
        isRecord(l) &&
        uuid(l.id) &&
        uuid(l.security_id) &&
        string(l.ticker) &&
        string(l.venue) &&
        nullableString(l.currency) &&
        typeof l.is_demo === "boolean",
    ) &&
    array(v.lifecycle_history, isEvent) &&
    (v.portfolio === null || isPortfolio(v.portfolio)) &&
    (v.portfolio_context === null ||
      (v.portfolio !== null &&
        isCompanyPortfolioContext(v.portfolio_context) &&
        v.portfolio_context.company.id === v.company.id)) &&
    isSnapshot(v.holding_snapshot) &&
    array(v.positions, isPosition) &&
    nullableDecimal(v.target_weight) &&
    nullableUuid(v.target_revision_id)
  );
}

export function isFinancialModelOutputs(
  v: unknown,
): v is FinancialModelOutputs {
  if (!isRecord(v) || !uuid(v.id) || !uuid(v.revision_id)) return false;
  return isFinancialModelOutputShape(v);
}

function isFinancialModelOutputShape(v: Record<string, unknown>): boolean {
  if (
    !["COMPLETE", "PARTIAL"].includes(v.status as string) ||
    !string(v.model_currency) ||
    !/^[A-Z]{3}$/.test(v.model_currency) ||
    !nullableUuid(v.price_observation_id) ||
    !nullableSignedDecimal(v.current_price) ||
    !(v.price_effective_at === null || timestamp(v.price_effective_at)) ||
    ![
      "FRESH",
      "STALE",
      "QUALITY_CHECK",
      "NO_DATA",
      "CURRENCY_MISMATCH",
      "CURRENCY_UNKNOWN",
    ].includes(v.price_status as string) ||
    !nullableString(v.price_unavailable_reason) ||
    !nullableString(v.irr_unavailable_reason)
  )
    return false;
  const fields = [
    "bear_fv",
    "base_fv",
    "bull_fv",
    "weighted_fv",
    "hurdle",
  ] as const;
  const optionalFields = [
    "weighted_upside",
    "expected_cash_flow_irr",
    "expected_excess",
    "forward_fundamental_cagr",
  ] as const;
  const probabilities = [
    v.bear_probability,
    v.base_probability,
    v.bull_probability,
  ];
  return (
    fields.every((field) => signedDecimal(v[field])) &&
    optionalFields.every((field) => nullableSignedDecimal(v[field])) &&
    probabilities.every(
      (value) =>
        signedDecimal(value) && Number(value) >= 0 && Number(value) <= 1,
    ) &&
    (v.expected_cash_flow_irr !== null || v.expected_excess === null) &&
    (v.status !== "COMPLETE" ||
      (v.price_status === "FRESH" &&
        v.current_price !== null &&
        Number(v.current_price) > 0 &&
        v.price_observation_id !== null &&
        v.weighted_upside !== null &&
        v.expected_cash_flow_irr !== null &&
        v.expected_excess !== null)) &&
    (v.status !== "PARTIAL" || v.irr_unavailable_reason !== null)
  );
}

export function isFinancialModelCalculationPreview(
  v: unknown,
): v is FinancialModelCalculationPreview {
  if (
    !isRecord(v) ||
    !nullableUuid(v.model_id) ||
    !nullableUuid(v.base_revision_id) ||
    !nullableUuid(v.current_revision_id) ||
    !string(v.model_currency) ||
    !/^[A-Z]{3}$/.test(v.model_currency) ||
    !isRecord(v.outputs) ||
    v.outputs.model_currency !== v.model_currency ||
    !isFinancialModelOutputShape(v.outputs) ||
    !Array.isArray(v.projections) ||
    !v.projections.every(isDcfProjectionCalculationPreview) ||
    v.projections.length !== 30
  )
    return false;
  if (v.model_id === null)
    return (
      v.base_revision_id === null &&
      v.current_revision_id === null &&
      v.current_revision_number === null
    );
  if (
    !uuid(v.base_revision_id) ||
    v.base_revision_id !== v.current_revision_id ||
    !Number.isInteger(v.current_revision_number) ||
    Number(v.current_revision_number) < 1
  )
    return false;
  const projections = v.projections as DcfProjectionCalculationPreview[];
  return ["BEAR", "BASE", "BULL"].every((scenario) => {
    const rows = projections.filter(
      (projection) => projection.scenario === scenario,
    );
    return (
      rows.length === 10 &&
      rows.every((projection, index) => projection.forecast_year === index + 1)
    );
  });
}

function isDcfYearInput(v: unknown): v is DcfYearAssumptionInput {
  return (
    isRecord(v) &&
    Number.isInteger(v.forecast_year) &&
    signedDecimal(v.revenue_growth) &&
    signedDecimal(v.ebit_margin) &&
    decimal(v.tax_rate) &&
    decimal(v.da_to_revenue) &&
    decimal(v.capex_to_revenue) &&
    signedDecimal(v.nwc_to_revenue) &&
    decimal(v.discount_rate)
  );
}

function isDcfScenario(v: unknown): boolean {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.revision_id) &&
    ["BEAR", "BASE", "BULL"].includes(v.scenario as string) &&
    decimal(v.probability) &&
    Number(v.probability) >= 0 &&
    Number(v.probability) <= 1 &&
    signedDecimal(v.terminal_growth) &&
    signedDecimal(v.year10_ufcf_growth) &&
    string(v.rationale) &&
    array(v.years, (year) => {
      if (!isRecord(year)) return false;
      const { id, scenario_id, ...input } = year;
      return uuid(id) && uuid(scenario_id) && isDcfYearInput(input);
    }) &&
    (v.years as unknown[]).length === 5
  );
}

function isDcfProjection(v: unknown): v is DcfProjection {
  return (
    isRecord(v) && uuid(v.id) && uuid(v.scenario_id) && isDcfProjectionShape(v)
  );
}

function isDcfProjectionCalculationPreview(
  v: unknown,
): v is DcfProjectionCalculationPreview {
  return (
    isRecord(v) &&
    ["BEAR", "BASE", "BULL"].includes(v.scenario as string) &&
    isDcfProjectionShape(v)
  );
}

function isDcfProjectionShape(v: Record<string, unknown>): boolean {
  if (
    !Number.isInteger(v.forecast_year) ||
    Number(v.forecast_year) < 1 ||
    Number(v.forecast_year) > 10 ||
    ![
      "revenue",
      "ebit",
      "nopat",
      "depreciation_amortization",
      "capex",
      "net_working_capital",
      "change_in_nwc",
    ].every((field) => nullableSignedDecimal(v[field])) ||
    !signedDecimal(v.unlevered_free_cash_flow) ||
    !signedDecimal(v.revenue_growth) ||
    !decimal(v.discount_rate) ||
    !decimal(v.discount_factor) ||
    !signedDecimal(v.present_value_ufcf) ||
    !nullableSignedDecimal(v.terminal_value)
  )
    return false;
  if (Number(v.forecast_year) > 5)
    return [
      "revenue",
      "ebit",
      "nopat",
      "depreciation_amortization",
      "capex",
      "net_working_capital",
      "change_in_nwc",
    ].every((field) => v[field] === null);
  return [
    "revenue",
    "ebit",
    "nopat",
    "depreciation_amortization",
    "capex",
    "net_working_capital",
    "change_in_nwc",
  ].every((field) => signedDecimal(v[field]));
}

function isFinancialModelRevisionSummary(
  v: unknown,
): v is FinancialModelRevisionSummary {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.model_id) &&
    Number.isInteger(v.revision_number) &&
    Number(v.revision_number) > 0 &&
    nullableUuid(v.base_revision_id) &&
    v.methodology_version === "ufcf-dcf-fade-v1" &&
    nullableString(v.source_revision_id) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string) &&
    nullableString(v.source) &&
    string(v.rationale) &&
    timestamp(v.effective_at) &&
    timestamp(v.recorded_at) &&
    isFinancialModelOutputs(v.outputs) &&
    v.outputs.revision_id === v.id
  );
}

function isFinancialModelRevision(v: unknown): v is FinancialModelRevision {
  if (!isRecord(v) || !isFinancialModelRevisionSummary(v)) return false;
  const detail = v as unknown as FinancialModelRevision;
  if (
    !isRecord(detail.base) ||
    !decimal(detail.base.base_revenue) ||
    !signedDecimal(detail.base.base_ebit_margin) ||
    !decimal(detail.base.base_tax_rate) ||
    !decimal(detail.base.base_da_to_revenue) ||
    !decimal(detail.base.base_capex_to_revenue) ||
    !signedDecimal(detail.base.base_nwc_to_revenue) ||
    !signedDecimal(detail.base.net_cash_debt) ||
    !decimal(detail.base.diluted_shares) ||
    !array(detail.scenarios, isDcfScenario) ||
    !array(detail.projections, isDcfProjection) ||
    detail.scenarios.length !== 3 ||
    detail.projections.length !== 30
  )
    return false;
  const scenarios = detail.scenarios as unknown as Array<
    Record<string, unknown>
  >;
  const projections = detail.projections as unknown as Array<
    Record<string, unknown>
  >;
  const names = scenarios.map((item) => item.scenario);
  if (
    new Set(names).size !== 3 ||
    !["BEAR", "BASE", "BULL"].every((x) => names.includes(x))
  )
    return false;
  return scenarios.every(
    (scenario) =>
      scenario.revision_id === detail.id &&
      (scenario.years as Array<Record<string, unknown>>).every(
        (year, index) => Number(year.forecast_year) === index + 1,
      ) &&
      projections
        .filter((projection) => projection.scenario_id === scenario.id)
        .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year))
        .every(
          (projection, index) => Number(projection.forecast_year) === index + 1,
        ),
  );
}

function isFinancialModelSummary(
  v: unknown,
): v is FinancialModelRevisionSummary {
  return isFinancialModelRevisionSummary(v);
}

export function isFinancialModel(v: unknown): v is FinancialModel {
  if (!isRecord(v)) return false;
  if (!array(v.history, isFinancialModelSummary)) return false;
  const history = v.history as FinancialModelRevisionSummary[];
  const currentRevision = v.current_revision;
  return (
    uuid(v.id) &&
    uuid(v.company_id) &&
    v.model_type === "UFCF_DCF_10Y_FADE" &&
    string(v.model_name) &&
    isRecord(v.valuation_listing) &&
    uuid(v.valuation_listing.id) &&
    uuid(v.valuation_listing.security_id) &&
    string(v.valuation_listing.ticker) &&
    string(v.valuation_listing.venue) &&
    (v.valuation_listing.currency === undefined ||
      nullableString(v.valuation_listing.currency)) &&
    typeof v.valuation_listing.is_demo === "boolean" &&
    string(v.model_currency) &&
    /^[A-Z]{3}$/.test(v.model_currency) &&
    nullableString(v.source_model_key) &&
    timestamp(v.created_at) &&
    uuid(v.current_revision_id) &&
    isFinancialModelRevision(currentRevision) &&
    currentRevision.id === v.current_revision_id &&
    history.length > 0 &&
    history.every((revision) => revision.model_id === v.id) &&
    history.some((revision) => revision.id === v.current_revision_id)
  );
}

export function isFinancialModels(v: unknown): v is FinancialModel[] {
  return array(v, isFinancialModel);
}

export function isFinancialModelRevisionHistory(
  v: unknown,
): v is FinancialModelRevisionSummary[] {
  return array(v, isFinancialModelRevisionSummary);
}

export function isFinancialModelRevisionDetail(
  v: unknown,
): v is FinancialModelRevision {
  return isFinancialModelRevision(v);
}

function isDcfOperatingBaseInput(v: unknown): boolean {
  return (
    isRecord(v) &&
    decimal(v.base_revenue) &&
    signedDecimal(v.base_ebit_margin) &&
    decimal(v.base_tax_rate) &&
    decimal(v.base_da_to_revenue) &&
    decimal(v.base_capex_to_revenue) &&
    signedDecimal(v.base_nwc_to_revenue) &&
    signedDecimal(v.net_cash_debt) &&
    decimal(v.diluted_shares)
  );
}

function isDcfScenarioInput(v: unknown): boolean {
  if (
    !isRecord(v) ||
    !["BEAR", "BASE", "BULL"].includes(v.scenario as string) ||
    !decimal(v.probability) ||
    !signedDecimal(v.terminal_growth) ||
    !signedDecimal(v.year10_ufcf_growth) ||
    !string(v.rationale) ||
    !Array.isArray(v.years) ||
    v.years.length !== 5 ||
    !v.years.every(isDcfYearInput)
  )
    return false;
  return (v.years as Array<Record<string, unknown>>).every(
    (year, index) => Number(year.forecast_year) === index + 1,
  );
}

function isListingIdentity(v: unknown): v is Record<string, unknown> {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.security_id) &&
    string(v.venue) &&
    string(v.ticker) &&
    nullableString(v.currency) &&
    typeof v.is_demo === "boolean"
  );
}

export function isFinancialModelContract(
  v: unknown,
): v is FinancialModelContract {
  if (!isRecord(v) || !isRecord(v.model)) return false;
  const model = v.model;
  const listing = model.valuation_listing;
  if (!isListingIdentity(listing)) return false;
  if (
    v.contract_version !== "1.0.0" ||
    !timestamp(v.exported_at) ||
    !uuid(model.model_id) ||
    !uuid(model.company_id) ||
    model.model_type !== "UFCF_DCF_10Y_FADE" ||
    !string(model.model_name) ||
    !uuid(model.valuation_listing_id) ||
    listing.id !== model.valuation_listing_id ||
    !string(model.model_currency) ||
    !/^[A-Z]{3}$/.test(model.model_currency) ||
    !nullableString(model.source_model_key) ||
    !isRecord(v.base_revision) ||
    !uuid(v.base_revision.revision_id) ||
    !Number.isInteger(v.base_revision.revision_number) ||
    Number(v.base_revision.revision_number) < 1 ||
    v.base_revision.methodology_version !== "ufcf-dcf-fade-v1" ||
    !isRecord(v.candidate_revision) ||
    v.candidate_revision.actor !== "IMPORT" ||
    !string(v.candidate_revision.source_revision_id) ||
    !nullableString(v.candidate_revision.source) ||
    !string(v.candidate_revision.rationale) ||
    !timestamp(v.candidate_revision.effective_at) ||
    !isDcfOperatingBaseInput(v.candidate_revision.base) ||
    !Array.isArray(v.candidate_revision.scenarios) ||
    v.candidate_revision.scenarios.length !== 3 ||
    !v.candidate_revision.scenarios.every(isDcfScenarioInput) ||
    !isRecord(v.base_calculation) ||
    v.base_calculation.revision_id !== v.base_revision.revision_id ||
    !isFinancialModelOutputs(v.base_calculation.outputs) ||
    v.base_calculation.outputs.revision_id !== v.base_revision.revision_id ||
    v.base_calculation.outputs.model_currency !== model.model_currency ||
    !Array.isArray(v.base_calculation.projections) ||
    v.base_calculation.projections.length !== 30 ||
    !v.base_calculation.projections.every(isDcfProjection)
  )
    return false;
  const scenarios = v.candidate_revision.scenarios as Array<
    Record<string, unknown>
  >;
  const names = scenarios.map((scenario) => scenario.scenario);
  return (
    new Set(names).size === 3 &&
    ["BEAR", "BASE", "BULL"].every((name) => names.includes(name))
  );
}

function isContractOutputSummary(v: unknown): boolean {
  return (
    isRecord(v) &&
    ["COMPLETE", "PARTIAL"].includes(v.status as string) &&
    string(v.model_currency) &&
    /^[A-Z]{3}$/.test(v.model_currency) &&
    [
      "FRESH",
      "STALE",
      "QUALITY_CHECK",
      "NO_DATA",
      "CURRENCY_MISMATCH",
      "CURRENCY_UNKNOWN",
    ].includes(v.price_status as string) &&
    nullableSignedDecimal(v.current_price) &&
    (v.price_effective_at === null || timestamp(v.price_effective_at)) &&
    nullableString(v.price_unavailable_reason) &&
    signedDecimal(v.bear_fv) &&
    signedDecimal(v.base_fv) &&
    signedDecimal(v.bull_fv) &&
    signedDecimal(v.weighted_fv) &&
    nullableSignedDecimal(v.weighted_upside) &&
    nullableSignedDecimal(v.expected_cash_flow_irr) &&
    signedDecimal(v.hurdle) &&
    nullableSignedDecimal(v.expected_excess) &&
    nullableString(v.irr_unavailable_reason)
  );
}

function isContractChanges(v: unknown): boolean {
  return array(
    v,
    (item) =>
      isRecord(item) &&
      string(item.path) &&
      nullableString(item.previous) &&
      nullableString(item.proposed),
  );
}

export function isFinancialModelContractPreview(
  v: unknown,
): v is FinancialModelContractPreview {
  return (
    isRecord(v) &&
    [
      "READY",
      "NO_CHANGES",
      "RATIONALE_REQUIRED",
      "CONFLICT",
      "INVALID_BASE_SNAPSHOT",
      "ALREADY_IMPORTED",
    ].includes(v.status as string) &&
    uuid(v.model_id) &&
    uuid(v.base_revision_id) &&
    uuid(v.current_revision_id) &&
    Number.isInteger(v.current_revision_number) &&
    string(v.source_revision_id) &&
    v.actor === "IMPORT" &&
    nullableString(v.source) &&
    timestamp(v.effective_at) &&
    (v.proposed_revision_number === null ||
      Number.isInteger(v.proposed_revision_number)) &&
    nullableUuid(v.already_imported_revision_id) &&
    nullableString(v.reason) &&
    isContractChanges(v.changes) &&
    isContractChanges(v.output_changes) &&
    isContractOutputSummary(v.current_outputs) &&
    (v.calculated_outputs === null ||
      isContractOutputSummary(v.calculated_outputs))
  );
}

export function isFinancialModelContractImport(
  v: unknown,
): v is FinancialModelContractImport {
  return (
    isRecord(v) &&
    ["IMPORTED", "ALREADY_IMPORTED"].includes(v.status as string) &&
    isFinancialModel(v.model) &&
    isFinancialModelRevisionDetail(v.revision) &&
    v.revision.model_id === v.model.id
  );
}

function isOwnerCashFlowYear(v: unknown): boolean {
  return (
    isRecord(v) &&
    Number.isInteger(v.forecast_year) &&
    signedDecimal(v.revenue_growth) &&
    signedDecimal(v.owner_cash_flow_margin)
  );
}

function isOwnerCashFlowInput(v: unknown): v is OwnerCashFlowInput {
  if (!isRecord(v) || !isRecord(v.base) || !Array.isArray(v.scenarios))
    return false;
  const base = v.base;
  if (
    !decimal(base.base_revenue) ||
    !signedDecimal(base.net_cash) ||
    !decimal(base.diluted_shares) ||
    v.scenarios.length !== 3
  )
    return false;
  return v.scenarios.every((scenario) => {
    if (!isRecord(scenario) || !Array.isArray(scenario.years)) return false;
    return (
      ["BEAR", "BASE", "BULL"].includes(scenario.scenario as string) &&
      decimal(scenario.probability) &&
      decimal(scenario.required_return) &&
      signedDecimal(scenario.terminal_growth) &&
      string(scenario.rationale) &&
      scenario.years.length === 10 &&
      scenario.years.every(isOwnerCashFlowYear)
    );
  });
}

function isResidualIncomeInput(v: unknown): v is ResidualIncomeInput {
  if (!isRecord(v) || !isRecord(v.base) || !Array.isArray(v.scenarios))
    return false;
  const base = v.base;
  return (
    decimal(base.current_book_value_per_share) &&
    decimal(base.payout_ratio) &&
    v.scenarios.length === 3 &&
    v.scenarios.every(
      (scenario) =>
        isRecord(scenario) &&
        ["BEAR", "BASE", "BULL"].includes(scenario.scenario as string) &&
        decimal(scenario.probability) &&
        signedDecimal(scenario.starting_roe) &&
        decimal(scenario.cost_of_equity) &&
        signedDecimal(scenario.terminal_growth) &&
        signedDecimal(scenario.mature_roe) &&
        string(scenario.rationale),
    )
  );
}

function isExtendedModelRevisionSummary(v: unknown): boolean {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.model_id) &&
    Number.isInteger(v.revision_number) &&
    Number(v.revision_number) > 0 &&
    nullableUuid(v.base_revision_id) &&
    ["owner-cash-flow-10y-v1", "residual-income-10y-fade-v1"].includes(
      v.methodology_version as string,
    ) &&
    nullableString(v.source_revision_id) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string) &&
    nullableString(v.source) &&
    string(v.rationale) &&
    timestamp(v.effective_at) &&
    timestamp(v.recorded_at) &&
    isFinancialModelOutputs(v.outputs) &&
    v.outputs.revision_id === v.id
  );
}

function isOwnerCashFlowRevisionRead(
  v: unknown,
): v is OwnerCashFlowRevisionRead {
  if (
    !isRecord(v) ||
    !isExtendedModelRevisionSummary(v) ||
    !isRecord(v.base) ||
    !Array.isArray(v.projections) ||
    v.projections.length !== 30
  )
    return false;
  return (
    decimal(v.base.base_revenue) &&
    signedDecimal(v.base.net_cash) &&
    decimal(v.base.diluted_shares) &&
    isOwnerCashFlowInput({ base: v.base, scenarios: v.scenarios }) &&
    v.projections.every(
      (row) => isRecord(row) && isOwnerCashFlowYearProjection(row),
    )
  );
}

function isOwnerCashFlowYearProjection(v: Record<string, unknown>): boolean {
  return (
    ["BEAR", "BASE", "BULL"].includes(v.scenario as string) &&
    Number.isInteger(v.forecast_year) &&
    decimal(v.revenue) &&
    signedDecimal(v.owner_cash_flow) &&
    signedDecimal(v.owner_cash_flow_per_share) &&
    signedDecimal(v.present_value_per_share) &&
    nullableSignedDecimal(v.terminal_value_per_share)
  );
}

function isResidualIncomeRevisionRead(
  v: unknown,
): v is ResidualIncomeRevisionRead {
  if (
    !isRecord(v) ||
    !isExtendedModelRevisionSummary(v) ||
    !isRecord(v.base) ||
    !Array.isArray(v.projections) ||
    v.projections.length !== 30
  )
    return false;
  return (
    decimal(v.base.current_book_value_per_share) &&
    decimal(v.base.payout_ratio) &&
    isResidualIncomeInput({ base: v.base, scenarios: v.scenarios }) &&
    v.projections.every(
      (row) =>
        isRecord(row) &&
        ["BEAR", "BASE", "BULL"].includes(row.scenario as string) &&
        Number.isInteger(row.forecast_year) &&
        signedDecimal(row.beginning_book_value_per_share) &&
        signedDecimal(row.return_on_equity) &&
        signedDecimal(row.net_income_per_share) &&
        signedDecimal(row.dividend_per_share) &&
        signedDecimal(row.ending_book_value_per_share) &&
        signedDecimal(row.residual_income_per_share) &&
        signedDecimal(row.present_value_residual_income) &&
        nullableSignedDecimal(row.terminal_value_per_share),
    )
  );
}

export function isExtendedFinancialModel(
  v: unknown,
): v is ExtendedFinancialModel {
  if (!isRecord(v)) return false;
  if (
    !Array.isArray(v.history) ||
    !v.history.every(isExtendedModelRevisionSummary)
  )
    return false;
  const history = v.history;
  const current =
    v.model_type === "OWNER_CASH_FLOW_10Y"
      ? isOwnerCashFlowRevisionRead(v.current_revision)
      : v.model_type === "RESIDUAL_INCOME_10Y_FADE"
        ? isResidualIncomeRevisionRead(v.current_revision)
        : false;
  return (
    uuid(v.id) &&
    uuid(v.company_id) &&
    string(v.model_name) &&
    isRecord(v.valuation_listing) &&
    uuid(v.valuation_listing.id) &&
    uuid(v.valuation_listing.security_id) &&
    string(v.valuation_listing.ticker) &&
    string(v.valuation_listing.venue) &&
    nullableString(v.valuation_listing.currency) &&
    typeof v.valuation_listing.is_demo === "boolean" &&
    string(v.model_currency) &&
    /^[A-Z]{3}$/.test(v.model_currency) &&
    nullableString(v.source_model_key) &&
    timestamp(v.created_at) &&
    uuid(v.current_revision_id) &&
    current &&
    isRecord(v.current_revision) &&
    v.current_revision.id === v.current_revision_id &&
    history.length > 0 &&
    history.some(
      (revision) => isRecord(revision) && revision.id === v.current_revision_id,
    )
  );
}

export function isExtendedFinancialModels(
  v: unknown,
): v is ExtendedFinancialModel[] {
  return array(v, isExtendedFinancialModel);
}

export function isExtendedFinancialModelRevision(
  v: unknown,
): v is ExtendedFinancialModelRevision {
  return isOwnerCashFlowRevisionRead(v) || isResidualIncomeRevisionRead(v);
}

function isAdditionalModelPortableContract(
  v: unknown,
): v is AdditionalModelPortableContract {
  if (!isRecord(v) || !isRecord(v.candidate_revision)) return false;
  const candidate = v.candidate_revision;
  if (
    v.contract_version !== "2.0.0" ||
    !timestamp(v.exported_at) ||
    !uuid(v.model_id) ||
    !uuid(v.company_id) ||
    !string(v.model_name) ||
    !uuid(v.valuation_listing_id) ||
    !string(v.model_currency) ||
    !nullableString(v.source_model_key) ||
    !uuid(v.base_revision_id) ||
    !Number.isInteger(v.base_revision_number) ||
    !string(candidate.source_revision_id) ||
    candidate.actor !== "IMPORT" ||
    !nullableString(candidate.source) ||
    !nullableString(candidate.rationale) ||
    !timestamp(candidate.effective_at)
  )
    return false;
  return v.model_type === "OWNER_CASH_FLOW_10Y"
    ? isOwnerCashFlowInput(candidate.owner_cash_flow) &&
        candidate.residual_income == null
    : v.model_type === "RESIDUAL_INCOME_10Y_FADE"
      ? isResidualIncomeInput(candidate.residual_income) &&
        candidate.owner_cash_flow == null
      : false;
}

export function isAdditionalModelPortableContractResponse(
  v: unknown,
): v is AdditionalModelPortableContract {
  return isAdditionalModelPortableContract(v);
}

export function isAdditionalModelContractPreview(
  v: unknown,
): v is AdditionalModelContractPreview {
  return (
    isRecord(v) &&
    [
      "READY",
      "NO_CHANGES",
      "RATIONALE_REQUIRED",
      "CONFLICT",
      "ALREADY_IMPORTED",
    ].includes(v.status as string) &&
    uuid(v.model_id) &&
    uuid(v.base_revision_id) &&
    uuid(v.current_revision_id) &&
    Number.isInteger(v.current_revision_number) &&
    string(v.source_revision_id) &&
    isContractChanges(v.changes) &&
    isContractChanges(v.output_changes) &&
    isRecord(v.current_outputs) &&
    isFinancialModelOutputShape(v.current_outputs) &&
    (v.calculated_outputs === null ||
      (isRecord(v.calculated_outputs) &&
        isFinancialModelOutputShape(v.calculated_outputs))) &&
    nullableString(v.reason)
  );
}

export function isAdditionalModelContractImport(
  v: unknown,
): v is AdditionalModelContractImport {
  return (
    isRecord(v) &&
    ["IMPORTED", "ALREADY_IMPORTED"].includes(v.status as string) &&
    isExtendedFinancialModel(v.model) &&
    isExtendedFinancialModelRevision(v.revision) &&
    v.revision.model_id === v.model.id
  );
}

function isArchetypeCalculationPreview(v: unknown): boolean {
  if (!isRecord(v) || !Array.isArray(v.projections) || !isRecord(v.outputs))
    return false;
  return (
    nullableUuid(v.model_id) &&
    nullableUuid(v.base_revision_id) &&
    nullableUuid(v.current_revision_id) &&
    (v.current_revision_number === null ||
      Number.isInteger(v.current_revision_number)) &&
    string(v.model_currency) &&
    /^[A-Z]{3}$/.test(v.model_currency) &&
    isRecord(v.outputs) &&
    isFinancialModelOutputShape(v.outputs) &&
    v.projections.every(isRecord) &&
    v.projections.length === 30
  );
}

export function isOwnerCashFlowCalculationPreview(
  v: unknown,
): v is OwnerCashFlowCalculationPreview {
  if (
    !isRecord(v) ||
    !isArchetypeCalculationPreview(v) ||
    !Array.isArray(v.projections)
  )
    return false;
  return v.projections.every(
    (row: unknown) =>
      isRecord(row) &&
      ["BEAR", "BASE", "BULL"].includes(row.scenario as string) &&
      Number.isInteger(row.forecast_year) &&
      decimal(row.revenue) &&
      signedDecimal(row.owner_cash_flow) &&
      signedDecimal(row.owner_cash_flow_per_share) &&
      signedDecimal(row.present_value_per_share) &&
      nullableSignedDecimal(row.terminal_value_per_share),
  );
}

export function isResidualIncomeCalculationPreview(
  v: unknown,
): v is ResidualIncomeCalculationPreview {
  if (
    !isRecord(v) ||
    !isArchetypeCalculationPreview(v) ||
    !Array.isArray(v.projections)
  )
    return false;
  return v.projections.every(
    (row: unknown) =>
      isRecord(row) &&
      ["BEAR", "BASE", "BULL"].includes(row.scenario as string) &&
      Number.isInteger(row.forecast_year) &&
      signedDecimal(row.beginning_book_value_per_share) &&
      signedDecimal(row.return_on_equity) &&
      signedDecimal(row.net_income_per_share) &&
      signedDecimal(row.dividend_per_share) &&
      signedDecimal(row.ending_book_value_per_share) &&
      signedDecimal(row.residual_income_per_share) &&
      signedDecimal(row.present_value_residual_income) &&
      nullableSignedDecimal(row.terminal_value_per_share),
  );
}

const reportedFundamentalMetrics = [
  "REVENUE",
  "GROSS_PROFIT",
  "OPERATING_INCOME",
  "NET_INCOME",
  "CASH_AND_CASH_EQUIVALENTS",
  "CURRENT_DEBT",
  "NONCURRENT_DEBT",
  "OPERATING_CASH_FLOW",
  "CAPITAL_EXPENDITURES",
  "DILUTED_WEIGHTED_AVERAGE_SHARES",
] as const;

function isReportedFundamentalObservation(
  v: unknown,
): v is ReportedFundamentalObservation {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.company_id) &&
    nullableUuid(v.security_id) &&
    string(v.provider_id) &&
    string(v.provider_entity_id) &&
    Number.isInteger(v.source_priority) &&
    reportedFundamentalMetrics.includes(
      v.metric as (typeof reportedFundamentalMetrics)[number],
    ) &&
    ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW_STATEMENT"].includes(
      v.statement as string,
    ) &&
    ["ANNUAL", "QUARTERLY", "INSTANT"].includes(v.period_type as string) &&
    (v.period_start === null || timestamp(v.period_start)) &&
    timestamp(v.period_end) &&
    (v.fiscal_year === null || Number.isInteger(v.fiscal_year)) &&
    nullableString(v.fiscal_period) &&
    (v.filed_at === null || timestamp(v.filed_at)) &&
    timestamp(v.observed_at) &&
    timestamp(v.recorded_at) &&
    signedDecimal(v.value) &&
    (v.currency === null ||
      (string(v.currency) && /^[A-Z]{3}$/.test(v.currency))) &&
    string(v.unit) &&
    string(v.source_taxonomy) &&
    string(v.source_concept) &&
    string(v.source_unit) &&
    nullableString(v.accession_number) &&
    nullableString(v.form) &&
    nullableString(v.frame) &&
    string(v.source_record_id) &&
    string(v.source_url) &&
    string(v.source_ref) &&
    [
      "ORIGINAL",
      "COMPARATIVE_REPORTED",
      "POTENTIAL_RESTATEMENT",
      "AMENDED_FILING",
    ].includes(v.revision_context as string) &&
    ["PASS", "DATA_CHECK", "INVALID"].includes(v.data_quality as string) &&
    nullableString(v.quality_reason) &&
    nullableUuid(v.supersedes_observation_id)
  );
}

function isReportedFundamentalPeriod(
  v: unknown,
): v is ReportedFundamentalPeriod {
  return (
    isRecord(v) &&
    reportedFundamentalMetrics.includes(
      v.metric as (typeof reportedFundamentalMetrics)[number],
    ) &&
    ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW_STATEMENT"].includes(
      v.statement as string,
    ) &&
    ["ANNUAL", "QUARTERLY", "INSTANT"].includes(v.period_type as string) &&
    (v.period_start === null || timestamp(v.period_start)) &&
    timestamp(v.period_end) &&
    (v.fiscal_year === null || Number.isInteger(v.fiscal_year)) &&
    nullableString(v.fiscal_period) &&
    (v.currency === null ||
      (string(v.currency) && /^[A-Z]{3}$/.test(v.currency))) &&
    string(v.unit) &&
    nullableSignedDecimal(v.value) &&
    ["AVAILABLE", "CONFLICT", "DATA_CHECK"].includes(
      v.selection_status as string,
    ) &&
    (v.selected_observation === null ||
      isReportedFundamentalObservation(v.selected_observation)) &&
    array(v.observations, isReportedFundamentalObservation)
  );
}

export function isCompanyReportedFundamentals(
  v: unknown,
): v is CompanyReportedFundamentals {
  return (
    isRecord(v) &&
    uuid(v.company_id) &&
    ["MAPPED", "UNMAPPED", "AMBIGUOUS"].includes(
      v.provider_identity_status as string,
    ) &&
    array(v.provider_ids, string) &&
    array(
      v.coverage,
      (item) =>
        isRecord(item) &&
        reportedFundamentalMetrics.includes(
          item.metric as (typeof reportedFundamentalMetrics)[number],
        ) &&
        ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW_STATEMENT"].includes(
          item.statement as string,
        ) &&
        Number.isInteger(item.observation_count) &&
        (item.latest_period_end === null ||
          timestamp(item.latest_period_end)) &&
        ["AVAILABLE", "CONFLICT", "DATA_CHECK", "NOT_IMPORTED"].includes(
          item.status as string,
        ),
    ) &&
    array(v.periods, isReportedFundamentalPeriod) &&
    (v.as_of === null ||
      (string(v.as_of) && /^\d{4}-\d{2}-\d{2}$/.test(v.as_of))) &&
    (v.known_at === null || timestamp(v.known_at)) &&
    (v.latest_observed_at === null || timestamp(v.latest_observed_at))
  );
}

const sourceDocumentTypes = [
  "10-K",
  "10-Q",
  "8-K",
  "20-F",
  "6-K",
  "ANNUAL_REPORT",
  "EARNINGS_RELEASE",
  "OTHER",
] as const;

export function isSourceDocument(v: unknown): v is SourceDocument {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.company_id) &&
    (v.security_id === null || uuid(v.security_id)) &&
    (v.batch_id === null || uuid(v.batch_id)) &&
    string(v.provider_id) &&
    string(v.source_name) &&
    nullableString(v.source_jurisdiction) &&
    string(v.external_identifier) &&
    sourceDocumentTypes.includes(
      v.document_type as (typeof sourceDocumentTypes)[number],
    ) &&
    nullableString(v.source_form) &&
    string(v.title) &&
    nullableString(v.reporting_period) &&
    (v.fiscal_year === null || Number.isInteger(v.fiscal_year)) &&
    nullableString(v.fiscal_period) &&
    (v.period_end === null ||
      (string(v.period_end) && dateOnly(v.period_end))) &&
    (v.filed_at === null || (string(v.filed_at) && dateOnly(v.filed_at))) &&
    (v.published_at === null ||
      (string(v.published_at) && dateOnly(v.published_at))) &&
    string(v.canonical_url) &&
    v.canonical_url.startsWith("https://") &&
    (v.retrieved_at === null || timestamp(v.retrieved_at)) &&
    timestamp(v.recorded_at) &&
    typeof v.is_amendment === "boolean" &&
    (v.amends_document_id === null || uuid(v.amends_document_id)) &&
    (v.supersedes_document_id === null || uuid(v.supersedes_document_id)) &&
    ["PASS", "DATA_CHECK"].includes(v.data_quality as string) &&
    nullableString(v.quality_reason) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string)
  );
}

export function isCompanySourceDocuments(
  v: unknown,
): v is CompanySourceDocuments {
  return (
    isRecord(v) &&
    uuid(v.company_id) &&
    ["MAPPED", "UNMAPPED", "AMBIGUOUS"].includes(
      v.sec_identity_status as string,
    ) &&
    Number.isInteger(v.source_count) &&
    (v.as_of === null || (string(v.as_of) && dateOnly(v.as_of))) &&
    (v.known_at === null || timestamp(v.known_at)) &&
    array(v.documents, isSourceDocument)
  );
}

export function isReportedFundamentalDefinitions(
  v: unknown,
): v is ReportedFundamentalDefinition[] {
  return array(
    v,
    (item) =>
      isRecord(item) &&
      string(item.metric) &&
      (item.statement === null ||
        ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW_STATEMENT"].includes(
          item.statement as string,
        )) &&
      string(item.display_name) &&
      string(item.canonical_unit) &&
      ["REPORTED_FACT", "DERIVED_ANALYTIC"].includes(
        item.evidence_type as string,
      ) &&
      string(item.description),
  );
}

function isConsensusEstimateObservation(
  value: unknown,
): value is ConsensusEstimateObservation {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    uuid(value.company_id) &&
    nullableUuid(value.listing_id) &&
    uuid(value.provider_mapping_id) &&
    string(value.provider_id) &&
    ["REVENUE", "EPS"].includes(value.metric as string) &&
    ["ANNUAL", "QUARTERLY"].includes(value.period_type as string) &&
    string(value.forecast_period) &&
    (value.period_end === null || dateOnly(value.period_end)) &&
    signedDecimal(value.value) &&
    nullableSignedDecimal(value.low_value) &&
    nullableSignedDecimal(value.high_value) &&
    (value.analyst_count === null ||
      (Number.isInteger(value.analyst_count) &&
        (value.analyst_count as number) >= 0)) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    string(value.unit) &&
    dateOnly(value.snapshot_date) &&
    (value.observed_at === null || timestamp(value.observed_at)) &&
    timestamp(value.recorded_at) &&
    string(value.source_record_id) &&
    string(value.source_ref) &&
    ["SNAPSHOT", "REVISED", "LEGACY_BASELINE"].includes(
      value.revision_context as string,
    ) &&
    ["PASS", "DATA_CHECK", "INVALID"].includes(value.data_quality as string) &&
    nullableString(value.quality_reason) &&
    nullableUuid(value.supersedes_observation_id)
  );
}

function isConsensusEstimatePeriod(
  value: unknown,
): value is ConsensusEstimatePeriod {
  return (
    isRecord(value) &&
    ["REVENUE", "EPS"].includes(value.metric as string) &&
    ["ANNUAL", "QUARTERLY"].includes(value.period_type as string) &&
    string(value.forecast_period) &&
    (value.period_end === null || dateOnly(value.period_end)) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    string(value.unit) &&
    (value.current_observation === null ||
      isConsensusEstimateObservation(value.current_observation)) &&
    array(value.history, isConsensusEstimateObservation)
  );
}

function isConsensusEstimateProvider(
  value: unknown,
): value is ConsensusEstimateProvider {
  return (
    isRecord(value) &&
    string(value.provider_id) &&
    string(value.provider_symbol) &&
    ["PRIMARY", "FALLBACK"].includes(value.role as string) &&
    Number.isInteger(value.priority) &&
    typeof value.selected === "boolean" &&
    ["SELECTED", "ALTERNATE", "AMBIGUOUS"].includes(
      value.mapping_status as string,
    ) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    nullableString(value.currency_evidence_source) &&
    string(value.identity_evidence_source) &&
    timestamp(value.effective_from) &&
    ["FRESH", "STALE", "DATA_CHECK", "NO_DATA"].includes(
      value.freshness as string,
    ) &&
    (value.latest_snapshot_date === null ||
      dateOnly(value.latest_snapshot_date)) &&
    (value.latest_observed_at === null ||
      timestamp(value.latest_observed_at)) &&
    Number.isInteger(value.observation_count) &&
    array(value.missing_metrics, (metric) =>
      ["REVENUE", "EPS"].includes(metric as string),
    ) &&
    array(value.periods, isConsensusEstimatePeriod)
  );
}

export function isCompanyConsensusEstimates(
  value: unknown,
): value is CompanyConsensusEstimates {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    [
      "PRIMARY_SELECTED",
      "FALLBACK_SELECTED",
      "PRIMARY_NO_DATA",
      "NO_MAPPING",
      "AMBIGUOUS_FALLBACK",
    ].includes(value.continuity_status as string) &&
    nullableString(value.selected_provider_id) &&
    (value.as_of === null || dateOnly(value.as_of)) &&
    (value.known_at === null || timestamp(value.known_at)) &&
    array(value.providers, isConsensusEstimateProvider) &&
    (value.continuity_status !== "NO_MAPPING" ||
      (value.selected_provider_id === null &&
        Array.isArray(value.providers) &&
        value.providers.length === 0))
  );
}

function isEstimateMomentumWindow(
  value: unknown,
): value is EstimateMomentumWindow {
  return (
    isRecord(value) &&
    ["12M", "6M", "3M"].includes(value.window as string) &&
    [
      "AVAILABLE",
      "MISSING_REFERENCE",
      "STALE_REFERENCE",
      "DATA_CHECK",
      "INVALID_BASELINE",
    ].includes(value.status as string) &&
    nullableSignedDecimal(value.reference_value) &&
    (value.reference_snapshot_date === null ||
      dateOnly(value.reference_snapshot_date)) &&
    (value.reference_days_before_target === null ||
      (Number.isInteger(value.reference_days_before_target) &&
        Number(value.reference_days_before_target) >= 0)) &&
    nullableSignedDecimal(value.revision_fraction) &&
    nullableSignedDecimal(value.component_score) &&
    nullableString(value.reason)
  );
}

function isEstimateMomentumPeriod(
  value: unknown,
): value is EstimateMomentumPeriod {
  return (
    isRecord(value) &&
    ["REVENUE", "EPS"].includes(value.metric as string) &&
    ["FY+1", "FY+2"].includes(value.horizon as string) &&
    string(value.forecast_period) &&
    dateOnly(value.period_end) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    string(value.unit) &&
    (value.analyst_count === null ||
      (Number.isInteger(value.analyst_count) &&
        Number(value.analyst_count) >= 0)) &&
    nullableSignedDecimal(value.current_value) &&
    (value.current_snapshot_date === null ||
      dateOnly(value.current_snapshot_date)) &&
    ["PASS", "DATA_CHECK", "INVALID"].includes(value.data_quality as string) &&
    nullableString(value.quality_reason) &&
    array(value.windows, isEstimateMomentumWindow)
  );
}

function isEstimateMomentumSummary(
  value: unknown,
): value is EstimateMomentumSummary {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    string(value.methodology_version) &&
    [
      "AVAILABLE",
      "DIRECTION_ONLY",
      "INSUFFICIENT_HISTORY",
      "NO_MAPPING",
      "AMBIGUOUS_SOURCE",
    ].includes(value.availability as string) &&
    (value.direction === null ||
      [
        "POSITIVE",
        "MILD_POSITIVE",
        "NEUTRAL_MIXED",
        "MILD_NEGATIVE",
        "NEGATIVE",
      ].includes(value.direction as string)) &&
    nullableSignedDecimal(value.raw_score) &&
    nullableSignedDecimal(value.confidence_adjusted_score) &&
    ((value.raw_score === null &&
      value.direction === null &&
      value.confidence_adjusted_score === null) ||
      (value.raw_score !== null && value.direction !== null)) &&
    (!["NO_MAPPING", "AMBIGUOUS_SOURCE", "INSUFFICIENT_HISTORY"].includes(
      value.availability as string,
    ) ||
      value.raw_score === null) &&
    decimal(value.confidence) &&
    Number(value.confidence) >= 0 &&
    Number(value.confidence) <= 1 &&
    ["HIGH", "MEDIUM", "LOW", "COLLECTING", "NO_DATA"].includes(
      value.confidence_band as string,
    ) &&
    decimal(value.coverage_fraction) &&
    Number(value.coverage_fraction) >= 0 &&
    Number(value.coverage_fraction) <= 1 &&
    Number.isInteger(value.coverage_count) &&
    Number(value.coverage_count) >= 0 &&
    Number.isInteger(value.coverage_total) &&
    Number(value.coverage_total) > 0 &&
    ["FRESH", "STALE", "DATA_CHECK", "NO_DATA"].includes(
      value.freshness as string,
    ) &&
    ["PASS", "DATA_CHECK", "INVALID", "NO_DATA"].includes(
      value.data_quality as string,
    ) &&
    nullableString(value.provider_id) &&
    (value.latest_snapshot_date === null ||
      dateOnly(value.latest_snapshot_date)) &&
    dateOnly(value.as_of) &&
    (value.known_at === null || timestamp(value.known_at)) &&
    nullableString(value.reason)
  );
}

export function isCompanyEstimateMomentum(
  value: unknown,
): value is CompanyEstimateMomentum {
  const periods = isRecord(value) ? value.periods : undefined;
  return (
    isEstimateMomentumSummary(value) && array(periods, isEstimateMomentumPeriod)
  );
}

export function isUniverseEstimateMomentumSummary(
  value: unknown,
): value is UniverseEstimateMomentumSummary[] {
  return array(
    value,
    (row) =>
      isRecord(row) &&
      isCompany(row.company) &&
      isEstimateMomentumSummary(row.estimate_momentum),
  );
}

function isTemporalAlignedValue(value: unknown): value is TemporalAlignedValue {
  return (
    isRecord(value) &&
    string(value.status) &&
    nullableSignedDecimal(value.value) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    nullableString(value.unit) &&
    nullableString(value.source_name) &&
    nullableString(value.source_reference) &&
    nullableUuid(value.source_observation_id) &&
    (value.period_end === null || dateOnly(value.period_end)) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    (value.observed_at === null || timestamp(value.observed_at)) &&
    (value.recorded_at === null || timestamp(value.recorded_at)) &&
    nullableString(value.data_quality) &&
    nullableString(value.quality_reason) &&
    (value.low_value === undefined || nullableSignedDecimal(value.low_value)) &&
    (value.high_value === undefined ||
      nullableSignedDecimal(value.high_value)) &&
    (value.analyst_count === undefined ||
      value.analyst_count === null ||
      (typeof value.analyst_count === "number" &&
        Number.isInteger(value.analyst_count) &&
        value.analyst_count >= 0))
  );
}

function isExpectedReturnEstimate(
  value: unknown,
): value is ExpectedReturnEstimate {
  return (
    isRecord(value) &&
    uuid(value.observation_id) &&
    ["REVENUE", "EPS"].includes(value.metric as string) &&
    ["ANNUAL", "QUARTERLY"].includes(value.period_type as string) &&
    string(value.forecast_period) &&
    (value.period_end === null || dateOnly(value.period_end)) &&
    decimal(value.value) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    string(value.unit) &&
    (value.analyst_count === null ||
      (Number.isInteger(value.analyst_count) &&
        Number(value.analyst_count) >= 0)) &&
    dateOnly(value.snapshot_date) &&
    (value.observed_at === null || timestamp(value.observed_at)) &&
    timestamp(value.recorded_at) &&
    string(value.provider_id) &&
    string(value.source_ref) &&
    ["PASS", "DATA_CHECK", "INVALID"].includes(value.data_quality as string) &&
    nullableString(value.quality_reason)
  );
}

function isExpectedReturnEstimateContext(
  value: unknown,
): value is ExpectedReturnEstimateContext {
  return (
    isRecord(value) &&
    [
      "AVAILABLE",
      "NO_MAPPING",
      "AMBIGUOUS_SOURCE",
      "NO_OBSERVATIONS",
      "UNDATED",
    ].includes(value.status as string) &&
    nullableString(value.provider_id) &&
    array(value.periods, isExpectedReturnEstimate)
  );
}

function isExpectedReturnMarketPrice(
  value: unknown,
): value is ExpectedReturnMarketPrice {
  return (
    isRecord(value) &&
    [
      "AVAILABLE",
      "STALE",
      "DATA_CHECK",
      "NO_DATA",
      "CURRENCY_MISMATCH",
      "CURRENCY_UNKNOWN",
      "LISTING_UNMAPPED",
      "PRICE_NOT_CAPTURED",
      "UNDATED",
    ].includes(value.status as string) &&
    nullableUuid(value.listing_id) &&
    nullableString(value.ticker) &&
    nullableString(value.venue) &&
    (value.listing_currency === null ||
      (string(value.listing_currency) &&
        /^[A-Z]{3}$/.test(value.listing_currency))) &&
    nullableSignedDecimal(value.quote) &&
    (value.quote_currency === null ||
      (string(value.quote_currency) &&
        /^[A-Z]{3}$/.test(value.quote_currency))) &&
    nullableSignedDecimal(value.model_reference_price) &&
    (value.model_currency === null ||
      (string(value.model_currency) &&
        /^[A-Z]{3}$/.test(value.model_currency))) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    (value.observed_at === null || timestamp(value.observed_at)) &&
    (value.recorded_at === null || timestamp(value.recorded_at)) &&
    nullableString(value.provider) &&
    nullableString(value.adjustment_basis) &&
    nullableUuid(value.observation_id) &&
    nullableString(value.source_ref) &&
    nullableString(value.reason)
  );
}

function isExpectedReturnHistoryPoint(
  value: unknown,
): value is ExpectedReturnHistoryPoint {
  return (
    isRecord(value) &&
    string(value.point_id) &&
    [
      "IMPORTED_CURRENT_CONTRACT",
      "IMPORTED_LEGACY_REVISION",
      "NATIVE_MODEL_REVISION",
    ].includes(value.source_kind as string) &&
    ["DATED", "EFFECTIVE_DATE_UNKNOWN"].includes(
      value.event_status as string,
    ) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    timestamp(value.recorded_at) &&
    string(value.series_id) &&
    nullableString(value.model_key) &&
    nullableUuid(value.model_id) &&
    nullableUuid(value.revision_id) &&
    (value.revision_number === null ||
      (Number.isInteger(value.revision_number) &&
        Number(value.revision_number) > 0)) &&
    (value.model_type === null ||
      [
        "UFCF_DCF_10Y_FADE",
        "OWNER_CASH_FLOW_10Y",
        "RESIDUAL_INCOME_10Y_FADE",
      ].includes(value.model_type as string)) &&
    nullableString(value.methodology_version) &&
    string(value.model_label) &&
    (value.model_currency === null ||
      (string(value.model_currency) &&
        /^[A-Z]{3}$/.test(value.model_currency))) &&
    ["DOCUMENTED", "UNKNOWN"].includes(value.currency_status as string) &&
    nullableUuid(value.valuation_listing_id) &&
    nullableString(value.valuation_ticker) &&
    nullableString(value.valuation_venue) &&
    (value.valuation_listing_currency === null ||
      (string(value.valuation_listing_currency) &&
        /^[A-Z]{3}$/.test(value.valuation_listing_currency))) &&
    typeof value.is_current_at_cutoff === "boolean" &&
    nullableString(value.output_status) &&
    nullableString(value.output_quality) &&
    nullableString(value.contract_status) &&
    ["NATIVE_METHOD_OUTPUT", "LEGACY_NORMALIZED_FIELD"].includes(
      value.return_semantics as string,
    ) &&
    nullableSignedDecimal(value.bear_fv) &&
    nullableSignedDecimal(value.base_fv) &&
    nullableSignedDecimal(value.bull_fv) &&
    nullableSignedDecimal(value.bear_probability) &&
    nullableSignedDecimal(value.base_probability) &&
    nullableSignedDecimal(value.bull_probability) &&
    nullableSignedDecimal(value.weighted_fv) &&
    nullableSignedDecimal(value.weighted_upside) &&
    nullableSignedDecimal(value.expected_cash_flow_irr) &&
    nullableSignedDecimal(value.hurdle) &&
    nullableSignedDecimal(value.expected_excess) &&
    nullableSignedDecimal(value.forward_fundamental_cagr) &&
    isExpectedReturnMarketPrice(value.market_price) &&
    isExpectedReturnEstimateContext(value.estimate_context) &&
    string(value.actor) &&
    nullableString(value.source_actor) &&
    nullableString(value.revision_source) &&
    nullableString(value.revision_type) &&
    nullableString(value.source) &&
    nullableString(value.source_revision_id) &&
    nullableString(value.rationale) &&
    nullableString(value.evidence)
  );
}

export function isCompanyExpectedReturnHistory(
  value: unknown,
): value is CompanyExpectedReturnHistory {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    dateOnly(value.as_of) &&
    timestamp(value.known_at) &&
    ["AVAILABLE", "PARTIAL", "NO_HISTORY"].includes(value.status as string) &&
    array(value.history, isExpectedReturnHistoryPoint)
  );
}

function isExpectedReturnAttributionState(
  value: unknown,
): value is ExpectedReturnAttributionState {
  return (
    isRecord(value) &&
    string(value.point_id) &&
    [
      "IMPORTED_CURRENT_CONTRACT",
      "IMPORTED_LEGACY_REVISION",
      "NATIVE_MODEL_REVISION",
    ].includes(value.source_kind as string) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    timestamp(value.recorded_at) &&
    string(value.series_id) &&
    nullableUuid(value.model_id) &&
    nullableUuid(value.revision_id) &&
    (value.revision_number === null ||
      (Number.isInteger(value.revision_number) &&
        Number(value.revision_number) > 0)) &&
    (value.model_type === null ||
      [
        "UFCF_DCF_10Y_FADE",
        "OWNER_CASH_FLOW_10Y",
        "RESIDUAL_INCOME_10Y_FADE",
      ].includes(value.model_type as string)) &&
    nullableString(value.methodology_version) &&
    ["NATIVE_METHOD_OUTPUT", "LEGACY_NORMALIZED_FIELD"].includes(
      value.return_semantics as string,
    ) &&
    (value.model_currency === null ||
      (string(value.model_currency) &&
        /^[A-Z]{3}$/.test(value.model_currency))) &&
    nullableSignedDecimal(value.expected_cash_flow_irr) &&
    nullableSignedDecimal(value.hurdle) &&
    nullableSignedDecimal(value.expected_excess) &&
    nullableSignedDecimal(value.bear_fv) &&
    nullableSignedDecimal(value.base_fv) &&
    nullableSignedDecimal(value.bull_fv) &&
    nullableSignedDecimal(value.bear_probability) &&
    nullableSignedDecimal(value.base_probability) &&
    nullableSignedDecimal(value.bull_probability) &&
    nullableSignedDecimal(value.weighted_fv) &&
    isExpectedReturnMarketPrice(value.market_price) &&
    isExpectedReturnEstimateContext(value.estimate_context) &&
    nullableString(value.source) &&
    nullableString(value.source_revision_id) &&
    nullableString(value.rationale)
  );
}

export function isCompanyExpectedReturnAttribution(
  value: unknown,
): value is CompanyExpectedReturnAttribution {
  const valid =
    isRecord(value) &&
    uuid(value.company_id) &&
    [
      "ATTRIBUTED",
      "OUTPUTS_ONLY",
      "MISSING_RETURN",
      "RETURN_SEMANTICS_CHANGE",
      "MODEL_SERIES_CHANGE",
      "METHODOLOGY_CHANGE",
      "INPUTS_UNAVAILABLE",
      "RECALCULATION_MISMATCH",
      "UNDATED",
    ].includes(value.status as string) &&
    ["SYMMETRIC_COUNTERFACTUAL_SHAPLEY", "UNAVAILABLE"].includes(
      value.method as string,
    ) &&
    isExpectedReturnAttributionState(value.prior) &&
    isExpectedReturnAttributionState(value.current) &&
    nullableSignedDecimal(value.expected_irr_change) &&
    array(
      value.drivers,
      (driver): driver is ExpectedReturnAttributionDriver =>
        isRecord(driver) &&
        [
          "MARKET_PRICE",
          "MODEL_ASSUMPTIONS",
          "REQUIRED_RETURN_ASSUMPTIONS",
          "SCENARIO_PROBABILITIES",
        ].includes(driver.code as string) &&
        string(driver.label) &&
        signedDecimal(driver.effect) &&
        string(driver.explanation),
    ) &&
    nullableSignedDecimal(value.residual) &&
    nullableString(value.residual_reason) &&
    isExpectedReturnAttributionContextChanges(value.context_changes) &&
    string(value.estimate_context_note);
  if (!valid || !isRecord(value)) return false;
  if (
    ["MISSING_RETURN", "RETURN_SEMANTICS_CHANGE", "UNDATED"].includes(
      value.status as string,
    )
  )
    return (
      value.expected_irr_change === null &&
      value.residual === null &&
      Array.isArray(value.drivers) &&
      value.drivers.length === 0
    );
  if (value.status === "ATTRIBUTED") {
    if (
      value.method !== "SYMMETRIC_COUNTERFACTUAL_SHAPLEY" ||
      value.expected_irr_change === null ||
      value.residual === null ||
      !Array.isArray(value.drivers)
    )
      return false;
    const codes = value.drivers.map((driver) =>
      isRecord(driver) ? driver.code : null,
    );
    return (
      codes.length === 4 &&
      new Set(codes).size === 4 &&
      [
        "MARKET_PRICE",
        "SCENARIO_PROBABILITIES",
        "REQUIRED_RETURN_ASSUMPTIONS",
        "MODEL_ASSUMPTIONS",
      ].every((code) => codes.includes(code))
    );
  }
  if (
    [
      "OUTPUTS_ONLY",
      "MODEL_SERIES_CHANGE",
      "METHODOLOGY_CHANGE",
      "INPUTS_UNAVAILABLE",
      "RECALCULATION_MISMATCH",
    ].includes(value.status as string)
  )
    return (
      value.expected_irr_change !== null &&
      value.residual === value.expected_irr_change &&
      Array.isArray(value.drivers) &&
      value.drivers.length === 0
    );
  return true;
}

function isExpectedReturnAttributionContextChanges(
  value: unknown,
): value is ExpectedReturnAttributionContextChanges {
  if (!isRecord(value)) return false;
  return [
    "weighted_fv",
    "bear_fv",
    "base_fv",
    "bull_fv",
    "bear_probability",
    "base_probability",
    "bull_probability",
    "hurdle",
    "expected_excess",
  ].every((key) => nullableSignedDecimal(value[key]));
}

function isTemporalPrice(value: unknown): value is TemporalPrice {
  return (
    isRecord(value) &&
    string(value.status) &&
    (value.listing === null || isRecord(value.listing)) &&
    (value.market_date === null || timestamp(value.market_date)) &&
    nullableSignedDecimal(value.close) &&
    nullableSignedDecimal(value.total_return_close) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    nullableString(value.provider) &&
    (value.observed_at === null || timestamp(value.observed_at)) &&
    (value.recorded_at === null || timestamp(value.recorded_at)) &&
    nullableString(value.data_quality) &&
    (value.age_days === null ||
      (typeof value.age_days === "number" &&
        Number.isInteger(value.age_days) &&
        value.age_days >= 0)) &&
    nullableString(value.reason)
  );
}

function isTemporalReturn(value: unknown): value is TemporalReturn {
  return (
    isRecord(value) &&
    string(value.status) &&
    Number.isInteger(value.horizon_days) &&
    dateOnly(value.target_date) &&
    (value.start_market_date === null || timestamp(value.start_market_date)) &&
    (value.end_market_date === null || timestamp(value.end_market_date)) &&
    nullableSignedDecimal(value.start_total_return_close) &&
    nullableSignedDecimal(value.end_total_return_close) &&
    nullableSignedDecimal(value.return_fraction) &&
    (value.actual_days === null || Number.isInteger(value.actual_days)) &&
    string(value.basis) &&
    nullableString(value.reason)
  );
}

function isTemporalModelForecast(
  value: unknown,
): value is TemporalModelForecast {
  return (
    isRecord(value) &&
    uuid(value.model_id) &&
    string(value.model_name) &&
    [
      "UFCF_DCF_10Y_FADE",
      "OWNER_CASH_FLOW_10Y",
      "RESIDUAL_INCOME_10Y_FADE",
    ].includes(value.model_type as string) &&
    string(value.model_currency) &&
    isRecord(value.valuation_listing) &&
    string(value.status) &&
    (value.forecast_year === null || Number.isInteger(value.forecast_year)) &&
    string(value.fiscal_year_mapping_basis) &&
    nullableSignedDecimal(value.value) &&
    string(value.unit) &&
    nullableUuid(value.revision_id) &&
    (value.revision_number === null ||
      Number.isInteger(value.revision_number)) &&
    nullableString(value.methodology_version) &&
    nullableString(value.revision_source) &&
    nullableString(value.rationale) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    (value.recorded_at === null || timestamp(value.recorded_at)) &&
    isTemporalPrice(value.price_at_forecast) &&
    isTemporalReturn(value.subsequent_market_return)
  );
}

export function isCompanyTemporalAlignment(
  value: unknown,
): value is CompanyTemporalAlignment {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    value.metric === "REVENUE" &&
    Number.isInteger(value.fiscal_year) &&
    dateOnly(value.as_of) &&
    timestamp(value.forecast_known_at) &&
    timestamp(value.outcome_known_at) &&
    Number.isInteger(value.horizon_days) &&
    string(value.fiscal_year_mapping_basis) &&
    string(value.comparison_status) &&
    array(value.model_forecasts, isTemporalModelForecast) &&
    isTemporalAlignedValue(value.consensus) &&
    isTemporalAlignedValue(value.actual)
  );
}

export function isAttentionFeed(value: unknown): value is AttentionFeed {
  return (
    isRecord(value) &&
    timestamp(value.as_of) &&
    Number.isInteger(value.lookback_days) &&
    Number.isInteger(value.total) &&
    array(value.events, isAttentionEvent)
  );
}

function isAttentionEvent(value: unknown): value is AttentionEvent {
  return (
    isRecord(value) &&
    string(value.id) &&
    nullableUuid(value.company_id) &&
    nullableString(value.company_name) &&
    (value.lifecycle === null ||
      ["PORTFOLIO", "WATCHLIST", "CANDIDATE", "DROP"].includes(
        value.lifecycle as string,
      )) &&
    [
      "MODEL_REVISION",
      "MODEL_OUTPUT_IMPORT",
      "EXPECTED_IRR_CHANGE",
      "CONSENSUS_REVISION",
      "NEW_FILING",
      "PRICE_MOVE",
      "RANK_CHANGE",
      "EXECUTION_PACE_CHANGE",
      "DATA_QUALITY",
    ].includes(value.event_type as string) &&
    ["HIGH", "MEDIUM", "LOW"].includes(value.severity as string) &&
    ["REVIEW", "INFORMATIONAL"].includes(value.status as string) &&
    string(value.title) &&
    string(value.explanation) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    ["TIMESTAMP", "DATE", "UNKNOWN"].includes(value.time_precision as string) &&
    ((value.effective_at === null && value.time_precision === "UNKNOWN") ||
      (value.effective_at !== null && value.time_precision !== "UNKNOWN")) &&
    (value.recorded_at === null || timestamp(value.recorded_at)) &&
    string(value.source_domain) &&
    nullableString(value.source_id) &&
    nullableString(value.source_reference) &&
    nullableString(value.href) &&
    nullableString(value.prior_value) &&
    nullableString(value.current_value) &&
    nullableString(value.unit)
  );
}

const dateOnly = (value: unknown) =>
  string(value) && /^\d{4}-\d{2}-\d{2}$/.test(value);
