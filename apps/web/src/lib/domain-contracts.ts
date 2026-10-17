import type { components } from "@portfolio/contracts";

export type CompanyFinancialStatements =
  components["schemas"]["CompanyFinancialStatementsRead"];
export type FinancialStatementRow =
  components["schemas"]["FinancialStatementRowRead"];
export type FinancialStatementCell =
  components["schemas"]["FinancialStatementCellRead"];
export type FinancialStatementColumn =
  components["schemas"]["FinancialStatementColumnRead"];

export function isCompanyFinancialStatements(
  value: unknown,
): value is CompanyFinancialStatements {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    ["ANNUAL", "QUARTERLY"].includes(value.period_type as string) &&
    (value.as_of === null || dateOnly(value.as_of)) &&
    (value.known_at === null || timestamp(value.known_at)) &&
    (value.latest_observed_at === null ||
      timestamp(value.latest_observed_at)) &&
    array(
      value.periods,
      (p) =>
        isRecord(p) &&
        dateOnly(p.period_end) &&
        string(p.label) &&
        (p.fiscal_year === null || Number.isInteger(p.fiscal_year)) &&
        nullableString(p.fiscal_period) &&
        typeof p.is_forecast === "boolean",
    ) &&
    array(
      value.rows,
      (r) =>
        isRecord(r) &&
        string(r.id) &&
        string(r.metric) &&
        string(r.label) &&
        ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW_STATEMENT"].includes(
          r.statement as string,
        ) &&
        ["REPORTED_ACTUAL", "CONSENSUS", "AGENT_FORECAST"].includes(
          r.source_kind as string,
        ) &&
        string(r.source_name) &&
        nullableString(r.scenario) &&
        nullableString(r.currency) &&
        string(r.unit) &&
        nullableString(r.availability_reason) &&
        array(
          r.cells,
          (c) =>
            isRecord(c) &&
            dateOnly(c.period_end) &&
            nullableSignedDecimal(c.value) &&
            ["AVAILABLE", "CONFLICT", "DATA_CHECK", "UNAVAILABLE"].includes(
              c.status as string,
            ) &&
            nullableString(c.reason) &&
            nullableUuid(c.selected_source_id) &&
            array(c.source_ids, uuid),
        ),
    ) &&
    array(value.reported_periods, isReportedFundamentalPeriod) &&
    isCompanyConsensusEstimates(value.consensus) &&
    isCompanyResearch(value.research) &&
    array(
      value.limitations,
      (l) =>
        isRecord(l) &&
        string(l.source_name) &&
        string(l.reason) &&
        nullableUuid(l.reference_id),
    )
  );
}

export type Company = components["schemas"]["CompanyRead"];
export type Portfolio = components["schemas"]["PortfolioRead"];
export type Overview = components["schemas"]["PortfolioOverview"];
export type HoldingSnapshot = components["schemas"]["SnapshotRead"];
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
export type ReturnMethodology = components["schemas"]["ReturnMethodologyRead"];
export type ReturnMethodologies =
  components["schemas"]["ReturnMethodologiesRead"];
export type ReturnComparabilityRule =
  components["schemas"]["ReturnComparabilityRuleRead"];
export type RankingEntryRead = components["schemas"]["RankingEntryRead"];
export type WatchlistRankInputSnapshot =
  components["schemas"]["WatchlistRankInputSnapshot"];
export type PortfolioRankInputSnapshot =
  components["schemas"]["PortfolioRankInputSnapshot"];
export type ResearchRankInputSnapshot =
  components["schemas"]["ResearchRankInputSnapshot"];
export type CandidateResearchStage =
  components["schemas"]["CandidateResearchStage"];
export type CandidateGateOutcome =
  components["schemas"]["CandidateGateOutcome"];
export type CandidateGateEvidenceInput =
  components["schemas"]["CandidatePipelineEvidenceInput"];
export type CandidatePipelineEvidenceOption =
  components["schemas"]["CandidatePipelineEvidenceOption"];
export type CandidatePipelineGate =
  components["schemas"]["CandidatePipelineGateRead"];
export type CandidatePipelineRevision =
  components["schemas"]["CandidatePipelineRevisionRead"];
export type CandidatePipelineRevisionSummary =
  components["schemas"]["CandidatePipelineRevisionSummaryRead"];
export type CandidatePipelineQueueEntry =
  components["schemas"]["CandidatePipelineQueueEntry"];
export type CompanyCandidatePipeline =
  components["schemas"]["CompanyCandidatePipelineRead"];
export type CandidatePipelineRevisionCreate =
  components["schemas"]["CandidatePipelineRevisionCreate"];
export type CandidatePipelinePublicationResult =
  components["schemas"]["CandidatePipelinePublicationResult"];
export type ResearchQueue = components["schemas"]["ResearchQueueRead"];
export type ResearchQueueTask = components["schemas"]["ResearchQueueTask"];
export type ResearchQueueCompletion =
  components["schemas"]["ResearchQueueCompletionRead"];
export type ResearchQueueCompletionCreate =
  components["schemas"]["ResearchQueueCompletionCreate"];
export type ResearchQueueCompletionResult =
  components["schemas"]["ResearchQueueCompletionResult"];
export type ResearchTriggerRead = components["schemas"]["ResearchTriggerRead"];
export type ResearchTriggerReadResult =
  components["schemas"]["ResearchTriggerReadResult"];
export type ResearchTriggerRefreshResult =
  components["schemas"]["ResearchTriggerRefreshResult"];
export type ResearchTriggerContext =
  components["schemas"]["ResearchTriggerContextRead"];
export type ResearchTriggerReferenceRead =
  components["schemas"]["ResearchTriggerReferenceRead"];
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
export type GoogleSheetsSyncStatus =
  components["schemas"]["GoogleSheetsSyncStatusRead"];
export type GoogleSheetsConnectionTest =
  components["schemas"]["GoogleSheetsConnectionTestRead"];
export type GoogleSheetsSyncRun =
  components["schemas"]["GoogleSheetsSyncRunRead"];
export type GoogleSheetsSyncCandidate =
  components["schemas"]["GoogleSheetsSyncCandidateRead"];
export type FinancialModelEvidenceReference =
  components["schemas"]["FinancialModelEvidenceReference"];
export type FinancialModelEvidenceRead =
  components["schemas"]["FinancialModelEvidenceRead"];
export type GoogleSheetsSyncCheck =
  components["schemas"]["GoogleSheetsSyncCheckRead"];
export type GoogleSheetsPortfolioStatePublish =
  components["schemas"]["GoogleSheetsPortfolioStatePublishRead"];
export type GoogleSheetsThesisWatchPublish =
  components["schemas"]["GoogleSheetsThesisWatchPublishRead"];
export type GoogleSheetsAgentWorkPublish =
  components["schemas"]["GoogleSheetsAgentWorkPublishRead"];
export type GoogleSheetsRiskSyncStatus =
  components["schemas"]["GoogleSheetsRiskSyncStatusRead"];
export type GoogleSheetsRiskSyncRun =
  components["schemas"]["GoogleSheetsRiskSyncRunRead"];
export type GoogleSheetsRiskCandidate =
  components["schemas"]["GoogleSheetsRiskCandidateRead"];
export type GoogleSheetsRiskSyncCheck =
  components["schemas"]["GoogleSheetsRiskSyncCheckRead"];
export type GoogleSheetsResearchSyncStatus =
  components["schemas"]["GoogleSheetsResearchSyncStatusRead"];
export type GoogleSheetsResearchSyncRun =
  components["schemas"]["GoogleSheetsResearchSyncRunRead"];
export type GoogleSheetsResearchCandidate =
  components["schemas"]["GoogleSheetsResearchCandidateRead"];
export type GoogleSheetsResearchSyncCheck =
  components["schemas"]["GoogleSheetsResearchSyncCheckRead"];
export type GoogleSheetsResearchConnectionTest =
  components["schemas"]["GoogleSheetsResearchConnectionTestRead"];
export type RiskAssessmentEvidence =
  components["schemas"]["RiskAssessmentEvidenceRead"];
export type RiskAssessmentFinding =
  components["schemas"]["RiskAssessmentFindingRead"];
export type RiskAssessmentRevision =
  components["schemas"]["RiskAssessmentRevisionRead"];
export type CompanyRiskAssessments =
  components["schemas"]["CompanyRiskAssessmentsRead"];
export type PortfolioRiskAssessments =
  components["schemas"]["PortfolioRiskAssessmentsRead"];
export type ListingMarketData = components["schemas"]["ListingMarketData"];
export type PriceRegime = components["schemas"]["PriceRegimeRead"];
export type PriceHistoryAnalytics =
  components["schemas"]["PriceHistoryAnalyticsRead"];
export type MarketRefreshStatus =
  components["schemas"]["MarketRefreshStatusRead"];
export type RecurringOperationJob =
  components["schemas"]["RecurringOperationJobRead"];
export type RecurringOperationsStatus =
  components["schemas"]["RecurringOperationsStatusRead"];
export type OperationalJobRequestCreate =
  components["schemas"]["OperationalJobRequestCreate"];
export type OperationalJobName = OperationalJobRequestCreate["job_name"];
export type OperationalJobRequest =
  components["schemas"]["OperationalJobRequestRead"];
export type ResearchAgentWorkEvent =
  components["schemas"]["ResearchAgentWorkEventRead"];
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
export type ForecastAccuracyMetric =
  components["schemas"]["ForecastAccuracyMetric"];
export type ForecastAccuracySource =
  components["schemas"]["ForecastAccuracySourceType"];
export type ForecastAccuracyObservation =
  components["schemas"]["ForecastAccuracyObservationRead"];
export type ForecastAccuracySummary =
  components["schemas"]["ForecastAccuracySummaryRead"];
export type CompanyForecastAccuracy =
  components["schemas"]["CompanyForecastAccuracyRead"];
export type ScenarioForecastPoint =
  components["schemas"]["ScenarioForecastPointRead"];
export type ScenarioEvaluation =
  components["schemas"]["ScenarioEvaluationRead"];
export type ValuationScenarioContext =
  components["schemas"]["ValuationScenarioContextRead"];
export type DecisionOutcome = components["schemas"]["DecisionOutcomeRead"];
export type DecisionSignalEvaluation =
  components["schemas"]["DecisionSignalEvaluationRead"];
export type DecisionEvaluationSummary =
  components["schemas"]["DecisionEvaluationSummaryRead"];
export type CompanyDecisionEvaluation =
  components["schemas"]["CompanyDecisionEvaluationRead"];
export type ExpectedReturnEstimate =
  components["schemas"]["ExpectedReturnEstimateRead"];
export type ExpectedReturnEstimateContext =
  components["schemas"]["ExpectedReturnEstimateContextRead"];
export type ExpectedReturnMarketPrice =
  components["schemas"]["ExpectedReturnMarketPriceRead"];
export type ExpectedReturnHistoryPoint =
  components["schemas"]["ExpectedReturnHistoryPointRead"];
export type CurrentNativeModelCalculation =
  components["schemas"]["CurrentNativeModelCalculationRead"];
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
export type ResearchForecast = components["schemas"]["ResearchForecastRead"];
export type ResearchAssessment =
  components["schemas"]["ResearchAssessmentRead"];
export type ResearchEvidence = components["schemas"]["ResearchEvidenceRead"];
export type ResearchRevision = components["schemas"]["ResearchRevisionRead"];
export type ResearchStream = components["schemas"]["ResearchStreamRead"];
export type CompanyResearch = components["schemas"]["CompanyResearchRead"];
export type ResearchPublicationResult =
  components["schemas"]["ResearchPublicationResult"];
export type InvestmentThesisFact =
  components["schemas"]["InvestmentThesisFactRead"];
export type InvestmentThesisEvidence =
  components["schemas"]["InvestmentThesisEvidenceRead"];
export type InvestmentThesisClaim =
  components["schemas"]["InvestmentThesisClaimRead"];
export type InvestmentThesisRevision =
  components["schemas"]["InvestmentThesisRevisionRead"];
export type InvestmentThesisStream =
  components["schemas"]["InvestmentThesisStreamRead"];
export type CompanyInvestmentThesis =
  components["schemas"]["CompanyInvestmentThesisRead"];
export type InvestmentThesisPublicationResult =
  components["schemas"]["InvestmentThesisPublicationResult"];
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

export function isReturnMethodology(v: unknown): v is ReturnMethodology {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    string(v.code) &&
    Number.isInteger(v.version) &&
    Number(v.version) > 0 &&
    string(v.title) &&
    string(v.cash_flow_basis) &&
    ["ENTERPRISE", "EQUITY"].includes(v.perspective as string) &&
    string(v.entry_value_basis) &&
    string(v.share_price_basis) &&
    string(v.comparability_group) &&
    ["SAME_METHOD_ONLY", "CONDITIONAL_EQUITY_CROSS_METHOD"].includes(
      v.cross_method_policy as string,
    ) &&
    string(v.limitation) &&
    timestamp(v.effective_from) &&
    timestamp(v.recorded_at)
  );
}

export function isReturnMethodologies(v: unknown): v is ReturnMethodologies {
  return (
    isRecord(v) &&
    array(v.definitions, isReturnMethodology) &&
    array(
      v.rules,
      (rule) =>
        isRecord(rule) &&
        string(rule.left_methodology) &&
        string(rule.right_methodology) &&
        [
          "DIRECT",
          "CONDITIONAL_EQUITY",
          "NOT_COMPARABLE_PERSPECTIVE",
          "NOT_COMPARABLE_METHOD",
          "NOT_COMPARABLE_VERSION",
          "UNKNOWN_METHOD",
        ].includes(rule.status as string) &&
        string(rule.rationale),
    ) &&
    string(v.currency_policy)
  );
}

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
    (v.return_methodology === null ||
      isReturnMethodology(v.return_methodology)) &&
    ["CLASSIFIED", "UNCLASSIFIED"].includes(
      v.return_methodology_status as string,
    ) &&
    ["CAPTURED", "NOT_RETAINED", "UNAVAILABLE"].includes(
      v.share_price_basis_status as string,
    ) &&
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
function isPriceHistoryAnalytics(v: unknown): v is PriceHistoryAnalytics {
  return (
    isRecord(v) &&
    ["AVAILABLE", "PARTIAL", "UNAVAILABLE"].includes(v.status as string) &&
    string(v.methodology_version) &&
    Number.isInteger(v.observation_count) &&
    (v.as_of === null || timestamp(v.as_of)) &&
    [
      "daily_return",
      "dma_20",
      "dma_50",
      "dma_200",
      "high_52w",
      "drawdown_52w",
      "price_return_1m",
      "price_return_3m",
      "price_return_6m",
      "realized_vol_20d",
    ].every((key) => nullableSignedDecimal(v[key])) &&
    nullableString(v.trend_state) &&
    nullableString(v.correction_state)
  );
}
export function isMarketRefreshStatus(v: unknown): v is MarketRefreshStatus {
  return (
    isRecord(v) &&
    ["AVAILABLE", "STALE", "REFRESHING", "PARTIAL", "UNAVAILABLE"].includes(
      v.state as string,
    ) &&
    (v.last_attempt_at === null || timestamp(v.last_attempt_at)) &&
    (v.last_successful_update === null ||
      timestamp(v.last_successful_update)) &&
    (v.market_run_id === null || uuid(v.market_run_id)) &&
    (v.fx_run_id === null || uuid(v.fx_run_id)) &&
    nullableString(v.message)
  );
}

export function isRecurringOperationsStatus(
  value: unknown,
): value is RecurringOperationsStatus {
  return (
    isRecord(value) &&
    typeof value.enabled === "boolean" &&
    [
      "STARTING",
      "RUNNING",
      "FAILED",
      "STALE",
      "STOPPED",
      "NOT_STARTED",
      "DISABLED",
    ].includes(value.worker_state as string) &&
    (value.worker_started_at === null || timestamp(value.worker_started_at)) &&
    (value.worker_last_seen_at === null ||
      timestamp(value.worker_last_seen_at)) &&
    typeof value.sec_user_agent_configured === "boolean" &&
    typeof value.google_sheets_configured === "boolean" &&
    typeof value.google_sheets_credentials_available === "boolean" &&
    Number.isInteger(value.google_sheets_poll_seconds) &&
    typeof value.fmp_consensus_ingestion_enabled === "boolean" &&
    array(value.jobs, isRecurringOperationJob) &&
    isMarketRefreshStatus(value.market_data)
  );
}

function isOperationalJobAttempt(value: unknown): boolean {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    Number.isInteger(value.attempt_number) &&
    string(value.step_name) &&
    [
      "RUNNING",
      "SUCCEEDED",
      "PARTIAL",
      "BLOCKED",
      "FAILED",
      "SKIPPED",
      "DEFERRED",
    ].includes(value.status as string) &&
    Array.isArray(value.affected_domains) &&
    value.affected_domains.every(string) &&
    timestamp(value.started_at) &&
    (value.finished_at === null || timestamp(value.finished_at)) &&
    isRecord(value.result) &&
    nullableString(value.error_code) &&
    nullableString(value.error_message)
  );
}

export function isOperationalJobRequest(
  value: unknown,
): value is OperationalJobRequest {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    [
      "MARKET_DATA",
      "FX",
      "MARKET_AND_FX",
      "SEC_FUNDAMENTALS",
      "SEC_FILINGS",
      "SHEETS_DISCOVERY",
      "RESEARCH_REFRESH",
      "AGENT_WORK_FEED",
      "COMPANY_REFRESH",
      "REFRESH_ALL",
    ].includes(value.job_name as string) &&
    ["ACTIVE_UNIVERSE", "COMPANY"].includes(value.scope_kind as string) &&
    nullableUuid(value.company_id) &&
    nullableString(value.company_name) &&
    (value.lifecycle === null || lifecycle(value.lifecycle)) &&
    value.requested_by === "LOCAL_USER" &&
    ["QUEUED", "RUNNING", "SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED"].includes(
      value.status as string,
    ) &&
    timestamp(value.requested_at) &&
    (value.started_at === null || timestamp(value.started_at)) &&
    (value.finished_at === null || timestamp(value.finished_at)) &&
    (value.next_attempt_at === null || timestamp(value.next_attempt_at)) &&
    Number.isInteger(value.attempt_count) &&
    nullableUuid(value.retry_of_id) &&
    Array.isArray(value.affected_domains) &&
    value.affected_domains.every(string) &&
    isRecord(value.scope_detail) &&
    isRecord(value.result) &&
    nullableString(value.error_code) &&
    nullableString(value.error_message) &&
    typeof value.retry_available === "boolean" &&
    typeof value.deduplicated === "boolean" &&
    timestamp(value.cooldown_until) &&
    array(value.attempts, isOperationalJobAttempt)
  );
}

export function isOperationalJobRequestList(
  value: unknown,
): value is OperationalJobRequest[] {
  return array(value, isOperationalJobRequest);
}

export function isResearchAgentWorkEvent(
  value: unknown,
): value is ResearchAgentWorkEvent {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    nullableUuid(value.delivery_id) &&
    [
      "DATA_UNIVERSE_STEWARD",
      "PORTFOLIO_THESIS_SENTINEL",
      "MODEL_ALLOCATION_STEWARD",
    ].includes(value.agent_role as string) &&
    ["TRIGGER", "QUEUE_TASK", "DATA_DOMAIN", "PORTFOLIO_STATE"].includes(
      value.work_type as string,
    ) &&
    string(value.work_key) &&
    /^[0-9a-f]{64}$/i.test(String(value.work_fingerprint)) &&
    ["API", "GOOGLE_SHEETS"].includes(value.channel as string) &&
    [
      "DELIVERY_SUCCEEDED",
      "DELIVERY_FAILED",
      "ACKNOWLEDGED",
      "IN_PROGRESS",
      "COMPLETED",
      "BLOCKED",
      "SOURCE_UNAVAILABLE",
      "STALE_SOURCE",
      "UNRESOLVED_REVIEW",
    ].includes(value.event_type as string) &&
    nullableString(value.reason) &&
    nullableString(value.blocker_code) &&
    nullableString(value.external_update_id) &&
    (value.proposal_domain === null ||
      ["MODEL", "RESEARCH", "THESIS", "RISK"].includes(
        value.proposal_domain as string,
      )) &&
    nullableUuid(value.proposal_candidate_id) &&
    timestamp(value.recorded_at)
  );
}

export function isResearchAgentWorkEvents(
  value: unknown,
): value is ResearchAgentWorkEvent[] {
  return array(value, isResearchAgentWorkEvent);
}

function isRecurringOperationJob(
  value: unknown,
): value is RecurringOperationJob {
  return (
    isRecord(value) &&
    [
      "SEC_FUNDAMENTALS",
      "SEC_FILINGS",
      "FMP_CONSENSUS",
      "SHEETS_DISCOVERY",
      "RESEARCH_TRIGGER_SCAN",
      "AGENT_WORK_FEED",
      "DECISION_RECOMPUTE",
    ].includes(value.job_name as string) &&
    [
      "NOT_RUN",
      "RUNNING",
      "SUCCEEDED",
      "PARTIAL",
      "BLOCKED",
      "FAILED",
      "SKIPPED",
    ].includes(value.status as string) &&
    Number.isInteger(value.cadence_seconds) &&
    (value.last_attempt_at === null || timestamp(value.last_attempt_at)) &&
    (value.last_successful_at === null ||
      timestamp(value.last_successful_at)) &&
    (value.next_attempt_at === null || timestamp(value.next_attempt_at)) &&
    nullableString(value.failure_code) &&
    nullableString(value.failure_message) &&
    isRecord(value.result)
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
    ["AVAILABLE", "STALE", "REFRESHING", "PARTIAL", "UNAVAILABLE"].includes(
      v.availability as string,
    ) &&
    (v.age_days === null || Number.isInteger(v.age_days)) &&
    (v.price_regime === null || isPriceRegime(v.price_regime)) &&
    isPriceHistoryAnalytics(v.analytics) &&
    (v.last_market_update === null || timestamp(v.last_market_update)) &&
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
    (v.return_methodology === undefined ||
      v.return_methodology === null ||
      isReturnMethodology(v.return_methodology)) &&
    (v.return_methodology_status === undefined ||
      ["CLASSIFIED", "UNCLASSIFIED"].includes(
        v.return_methodology_status as string,
      )) &&
    (v.share_price_basis_status === undefined ||
      ["CAPTURED", "NOT_RETAINED", "UNAVAILABLE"].includes(
        v.share_price_basis_status as string,
      )) &&
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
    ["watchlist-rank-inputs-v1", "watchlist-rank-inputs-v2"].includes(
      v.context_version as string,
    ) &&
    nullableSignedDecimal(v.expected_irr) &&
    ["NATIVE_METHOD_OUTPUT", "LEGACY_NORMALIZED_FIELD"].includes(
      v.return_semantics as string,
    ) &&
    (v.return_comparability_cohort === undefined ||
      nullableString(v.return_comparability_cohort)) &&
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
    (v.return_methodology === undefined ||
      v.return_methodology === null ||
      isReturnMethodology(v.return_methodology)) &&
    (v.return_methodology_status === undefined ||
      ["CLASSIFIED", "UNCLASSIFIED"].includes(
        v.return_methodology_status as string,
      )) &&
    (v.share_price_basis_status === undefined ||
      ["CAPTURED", "NOT_RETAINED", "UNAVAILABLE"].includes(
        v.share_price_basis_status as string,
      )) &&
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
    [
      "portfolio-rank-inputs-v1",
      "portfolio-rank-inputs-v2",
      "portfolio-rank-inputs-v3",
    ].includes(v.context_version as string) &&
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
    (v.return_comparability_cohort === undefined ||
      nullableString(v.return_comparability_cohort)) &&
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

const candidateStages = [
  "DISCOVERY",
  "INITIAL_SCREEN",
  "QUALITY_DURABILITY",
  "FUNDAMENTAL_COMPOUNDING",
  "DEEP_DIVE",
  "RESOLUTION",
] as const;
const candidateOutcomes = [
  "NOT_ASSESSED",
  "INCOMPLETE",
  "PASS",
  "FAIL",
  "DATA_CHECK",
] as const;

function isCandidatePipelineEvidence(v: unknown): boolean {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    [
      "RESEARCH_REVISION",
      "THESIS_REVISION",
      "THESIS_CLAIM",
      "SCORE_ASSESSMENT",
      "FINANCIAL_MODEL_OUTPUT",
      "LEGACY_MODEL_OUTPUT",
      "SOURCE_DOCUMENT",
      "SOURCE_URL",
    ].includes(v.evidence_type as string) &&
    nullableUuid(v.reference_id) &&
    nullableString(v.source_url) &&
    ["SUPPORTS", "CONTRADICTS", "CONTEXT"].includes(v.relationship as string) &&
    nullableString(v.note)
  );
}

function isCandidatePipelineEvidenceOption(
  v: unknown,
): v is CandidatePipelineEvidenceOption {
  return (
    isRecord(v) &&
    [
      "RESEARCH_REVISION",
      "THESIS_REVISION",
      "THESIS_CLAIM",
      "SCORE_ASSESSMENT",
      "FINANCIAL_MODEL_OUTPUT",
      "LEGACY_MODEL_OUTPUT",
      "SOURCE_DOCUMENT",
      "SOURCE_URL",
    ].includes(v.evidence_type as string) &&
    uuid(v.reference_id) &&
    string(v.label) &&
    typeof v.current === "boolean" &&
    string(v.availability_status) &&
    nullableSignedDecimal(v.forward_fundamental_cagr)
  );
}

function isCandidatePipelineGate(v: unknown): v is CandidatePipelineGate {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    candidateStages
      .slice(0, -1)
      .includes(v.gate as (typeof candidateStages)[number]) &&
    candidateOutcomes.includes(
      v.outcome as (typeof candidateOutcomes)[number],
    ) &&
    nullableString(v.rationale) &&
    typeof v.normalized_per_share_basis_confirmed === "boolean" &&
    array(v.evidence, isCandidatePipelineEvidence)
  );
}

function isCandidatePipelineRevision(
  v: unknown,
): v is CandidatePipelineRevision {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.company_id) &&
    Number.isInteger(v.revision_number) &&
    Number(v.revision_number) > 0 &&
    nullableUuid(v.base_revision_id) &&
    uuid(v.submission_id) &&
    candidateStages.includes(v.stage as (typeof candidateStages)[number]) &&
    (v.disposition === null ||
      ["WATCHLIST", "INCUBATE", "DROP"].includes(v.disposition as string)) &&
    nullableString(v.next_action) &&
    array(v.unresolved_questions, string) &&
    ["LOCAL_USER", "SYSTEM", "IMPORT"].includes(v.actor as string) &&
    string(v.author_id) &&
    nullableString(v.source) &&
    string(v.rationale) &&
    timestamp(v.effective_at) &&
    timestamp(v.recorded_at) &&
    string(v.content_fingerprint) &&
    array(v.gates, isCandidatePipelineGate)
  );
}

function isCandidatePipelineRevisionSummary(
  v: unknown,
): v is CandidatePipelineRevisionSummary {
  return (
    isRecord(v) &&
    uuid(v.id) &&
    uuid(v.company_id) &&
    Number.isInteger(v.revision_number) &&
    Number(v.revision_number) > 0 &&
    nullableUuid(v.base_revision_id) &&
    candidateStages.includes(v.stage as (typeof candidateStages)[number]) &&
    (v.disposition === null ||
      ["WATCHLIST", "INCUBATE", "DROP"].includes(v.disposition as string)) &&
    nullableString(v.next_action) &&
    array(v.unresolved_questions, string) &&
    string(v.author_id) &&
    string(v.rationale) &&
    timestamp(v.effective_at) &&
    timestamp(v.recorded_at) &&
    candidateOutcomes.includes(
      v.current_gate_outcome as (typeof candidateOutcomes)[number],
    )
  );
}

function isCandidatePipelineQueueEntry(
  v: unknown,
): v is CandidatePipelineQueueEntry {
  return (
    isRecord(v) &&
    isCompany(v.company) &&
    ["NOT_STARTED", "IN_PROGRESS", "BLOCKED", "COMPLETE"].includes(
      v.status as string,
    ) &&
    (v.stage === null ||
      candidateStages.includes(v.stage as (typeof candidateStages)[number])) &&
    (v.disposition === null ||
      ["WATCHLIST", "INCUBATE", "DROP"].includes(v.disposition as string)) &&
    (v.candidate_tier === null ||
      ["HIGH", "LOW"].includes(v.candidate_tier as string)) &&
    nullableSignedDecimal(v.priority_seed) &&
    (v.priority_recorded_at === null || timestamp(v.priority_recorded_at)) &&
    (v.research_rank_position === null ||
      (Number.isInteger(v.research_rank_position) &&
        Number(v.research_rank_position) > 0)) &&
    (v.research_rank_status === null ||
      [
        "RANKED",
        "INPUTS_UNAVAILABLE",
        "NOT_ELIGIBLE",
        "EXCLUDED",
        "NOT_MIGRATED",
        "DATA_CHECK",
      ].includes(v.research_rank_status as string)) &&
    nullableString(v.research_rank_reason) &&
    (v.current_revision === null ||
      isCandidatePipelineRevisionSummary(v.current_revision))
  );
}

export function isCandidatePipelineQueue(
  v: unknown,
): v is CandidatePipelineQueueEntry[] {
  return array(v, isCandidatePipelineQueueEntry);
}

export function isCompanyCandidatePipeline(
  v: unknown,
): v is CompanyCandidatePipeline {
  return (
    isRecord(v) &&
    isCompany(v.company) &&
    (v.lifecycle === null || lifecycle(v.lifecycle)) &&
    isCandidatePipelineQueueEntry(v.queue_entry) &&
    array(v.history, isCandidatePipelineRevision) &&
    array(v.evidence_options, isCandidatePipelineEvidenceOption)
  );
}

export function isCandidatePipelinePublicationResult(
  v: unknown,
): v is CandidatePipelinePublicationResult {
  return (
    isRecord(v) &&
    ["RECORDED", "ALREADY_RECORDED"].includes(v.result as string) &&
    isCandidatePipelineRevision(v.revision)
  );
}

const researchQueueTaskTypes = [
  "CANDIDATE_STAGE",
  "THESIS_REVIEW",
  "THESIS_QUESTION",
  "MATERIAL_EVIDENCE",
  "RESEARCH_TRIGGER",
  "MODEL_REUNDERWRITE",
  "MODEL_INTEGRITY",
  "WATCHLIST_READINESS",
  "STRUCTURAL_RISK",
] as const;

const researchTriggerTypes = [
  "NEW_FILING",
  "MODEL_REVISION",
  "EXPECTED_IRR_CHANGE",
  "CONSENSUS_REVISION",
  "REPORTED_FACT_CORRECTION",
  "THESIS_EVIDENCE_LINKED",
  "RISK_ASSESSMENT",
] as const;
const thesisWatchClassifications = [
  "NOISE",
  "INCREMENTAL",
  "MAJOR-STRUCTURAL",
] as const;

function isResearchQueueSource(v: unknown): boolean {
  return (
    isRecord(v) &&
    string(v.source_type) &&
    string(v.source_record_id) &&
    string(v.title) &&
    nullableString(v.source_url) &&
    (v.effective_at === null || timestamp(v.effective_at)) &&
    (v.published_at === null || dateOnly(v.published_at)) &&
    (v.recorded_at === null || timestamp(v.recorded_at))
  );
}

export function isResearchQueueTask(v: unknown): v is ResearchQueueTask {
  return (
    isRecord(v) &&
    string(v.task_id) &&
    /^[0-9a-f]{64}$/.test(v.task_id) &&
    string(v.condition_fingerprint) &&
    /^[0-9a-f]{64}$/.test(v.condition_fingerprint) &&
    isCompany(v.company) &&
    researchQueueTaskTypes.includes(
      v.task_type as (typeof researchQueueTaskTypes)[number],
    ) &&
    string(v.title) &&
    string(v.reason) &&
    Number.isInteger(v.lifecycle_priority) &&
    (v.research_rank_position === null ||
      (Number.isInteger(v.research_rank_position) &&
        Number(v.research_rank_position) > 0)) &&
    string(v.trigger_rule) &&
    typeof v.judgment_required === "boolean" &&
    ["LOCAL_ANALYST", "RESEARCH_AGENT", "DATA_REVIEW"].includes(
      v.owner_workflow as string,
    ) &&
    (v.source_effective_at === null || timestamp(v.source_effective_at)) &&
    (v.source_published_at === null || dateOnly(v.source_published_at)) &&
    (v.source_recorded_at === null || timestamp(v.source_recorded_at)) &&
    (v.due_at === null || timestamp(v.due_at)) &&
    array(v.sources, isResearchQueueSource) &&
    ["OPEN", "COMPLETE"].includes(v.status as string) &&
    nullableString(v.completed_by) &&
    (v.completed_at === null || timestamp(v.completed_at)) &&
    nullableString(v.completion_note) &&
    (v.trigger_classification === undefined ||
      v.trigger_classification === null ||
      thesisWatchClassifications.includes(
        v.trigger_classification as (typeof thesisWatchClassifications)[number],
      ))
  );
}

export function isResearchQueue(v: unknown): v is ResearchQueue {
  return (
    isRecord(v) &&
    timestamp(v.as_of) &&
    isRecord(v.counts) &&
    Number.isInteger(v.counts.open) &&
    Number.isInteger(v.counts.complete) &&
    Number.isInteger(v.counts.portfolio) &&
    Number.isInteger(v.counts.watchlist) &&
    Number.isInteger(v.counts.candidate) &&
    array(v.tasks, isResearchQueueTask)
  );
}

export function isResearchQueueHistory(
  v: unknown,
): v is ResearchQueueCompletion[] {
  return array(
    v,
    (item) =>
      isRecord(item) &&
      uuid(item.id) &&
      isResearchQueueTask(item.task) &&
      item.task.status === "COMPLETE" &&
      string(item.completed_by) &&
      nullableString(item.completion_note) &&
      (item.trigger_classification === undefined ||
        item.trigger_classification === null ||
        thesisWatchClassifications.includes(
          item.trigger_classification as (typeof thesisWatchClassifications)[number],
        )) &&
      timestamp(item.completed_at),
  );
}

export function isResearchQueueCompletionResult(
  v: unknown,
): v is ResearchQueueCompletionResult {
  return (
    isRecord(v) &&
    ["COMPLETED", "ALREADY_COMPLETED"].includes(v.result as string) &&
    isResearchQueueTask(v.task) &&
    v.task.status === "COMPLETE"
  );
}

function isResearchTriggerRead(v: unknown): v is ResearchTriggerRead {
  return (
    isRecord(v) &&
    string(v.id) &&
    isCompany(v.company) &&
    string(v.event_key) &&
    Number.isInteger(v.version) &&
    string(v.fingerprint) &&
    /^[0-9a-f]{64}$/.test(v.fingerprint) &&
    researchTriggerTypes.includes(
      v.trigger_type as (typeof researchTriggerTypes)[number],
    ) &&
    string(v.title) &&
    string(v.reason) &&
    string(v.source_domain) &&
    string(v.source_record_id) &&
    nullableString(v.source_reference) &&
    (v.effective_at === null || timestamp(v.effective_at)) &&
    (v.source_observed_at === null || timestamp(v.source_observed_at)) &&
    timestamp(v.source_recorded_at) &&
    timestamp(v.detected_at) &&
    isRecord(v.source_snapshot) &&
    (v.queue_task_id === null ||
      (string(v.queue_task_id) && /^[0-9a-f]{64}$/.test(v.queue_task_id))) &&
    (v.queue_condition_fingerprint === null ||
      (string(v.queue_condition_fingerprint) &&
        /^[0-9a-f]{64}$/.test(v.queue_condition_fingerprint))) &&
    ["OPEN", "REVIEWED", "SUPERSEDED", "STALE"].includes(
      v.processing_state as string,
    )
  );
}

function isResearchTriggerReferenceRead(
  value: unknown,
): value is ResearchTriggerReferenceRead {
  return (
    isRecord(value) &&
    uuid(value.trigger_id) &&
    string(value.event_key) &&
    researchTriggerTypes.includes(
      value.trigger_type as (typeof researchTriggerTypes)[number],
    ) &&
    string(value.title) &&
    thesisWatchClassifications.includes(
      value.classification as (typeof thesisWatchClassifications)[number],
    ) &&
    string(value.classification_rationale) &&
    nullableString(value.source_reference) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    (value.source_observed_at === null ||
      timestamp(value.source_observed_at)) &&
    timestamp(value.source_recorded_at) &&
    timestamp(value.detected_at)
  );
}

export function isResearchTriggerReadResult(
  v: unknown,
): v is ResearchTriggerReadResult {
  return (
    isRecord(v) &&
    timestamp(v.as_of) &&
    array(v.triggers, isResearchTriggerRead)
  );
}

export function isResearchTriggerRefreshResult(
  v: unknown,
): v is ResearchTriggerRefreshResult {
  return (
    isRecord(v) &&
    timestamp(v.as_of) &&
    Number.isInteger(v.lookback_days) &&
    Number.isInteger(v.examined) &&
    Number.isInteger(v.created) &&
    Number.isInteger(v.replayed) &&
    array(v.triggers, isResearchTriggerRead)
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
  if (
    !isRecord(v) ||
    !["execution-pace-inputs-v1", "execution-pace-inputs-v2"].includes(
      v.context_version as string,
    )
  )
    return false;
  const nullableDecimals = [
    "current_weight",
    "target_weight",
    "allocation_gap",
    "expected_irr",
    "hurdle",
    "price",
    "model_reference_price",
    "accepted_reference_price",
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
    "accepted_reference_price_observation_id",
  ];
  const nullableTimes = [
    "target_effective_at",
    "holding_effective_at",
    "model_effective_at",
    "model_recorded_at",
    "price_market_date",
    "price_recorded_at",
    "model_price_effective_at",
    "accepted_reference_price_effective_at",
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
function isSnapshot(v: unknown): v is HoldingSnapshot | null {
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
export function isSnapshotRead(v: unknown): v is HoldingSnapshot {
  return isRecord(v) && isSnapshot(v);
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
    (p.price_observed_at === undefined ||
      p.price_observed_at === null ||
      timestamp(p.price_observed_at)) &&
    (p.portfolio_weight === undefined || nullableDecimal(p.portfolio_weight)) &&
    (p.price_date === null || timestamp(p.price_date)) &&
    (p.price_currency === null || string(p.price_currency)) &&
    (p.fx_rate === undefined || nullableDecimal(p.fx_rate)) &&
    (p.fx_effective_at === undefined ||
      p.fx_effective_at === null ||
      timestamp(p.fx_effective_at)) &&
    (p.valuation_sync_status === undefined ||
      [
        "NOT_REQUIRED",
        "SYNCHRONOUS",
        "NON_SYNCHRONOUS",
        "TIMING_UNKNOWN",
        "UNAVAILABLE",
      ].includes(p.valuation_sync_status as string)) &&
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
    (v.valuation_mode === undefined ||
      ["CURRENT_MARK_TO_MARKET", "HISTORICAL_AS_OF"].includes(
        v.valuation_mode as string,
      )) &&
    (v.valuation_as_of === undefined ||
      v.valuation_as_of === null ||
      timestamp(v.valuation_as_of)) &&
    (v.market_data_through === undefined ||
      v.market_data_through === null ||
      timestamp(v.market_data_through)) &&
    (v.fx_data_through === undefined ||
      v.fx_data_through === null ||
      timestamp(v.fx_data_through)) &&
    (v.holdings_age_days === undefined ||
      v.holdings_age_days === null ||
      (typeof v.holdings_age_days === "number" &&
        Number.isInteger(v.holdings_age_days) &&
        v.holdings_age_days >= 0)) &&
    (v.holdings_freshness === undefined ||
      ["FRESH", "STALE", "NO_DATA"].includes(v.holdings_freshness as string)) &&
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
        (cash.portfolio_weight === undefined ||
          nullableDecimal(cash.portfolio_weight)) &&
        (cash.fx_rate === undefined || nullableDecimal(cash.fx_rate)) &&
        (cash.fx_effective_at === undefined ||
          cash.fx_effective_at === null ||
          timestamp(cash.fx_effective_at)) &&
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
  return (
    isReturnMethodology(v.return_methodology) && isFinancialModelOutputShape(v)
  );
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
    !isReturnMethodology(v.outputs.return_methodology) ||
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

function isDcfTailGrowthInput(v: unknown): boolean {
  return (
    isRecord(v) &&
    Number.isInteger(v.forecast_year) &&
    Number(v.forecast_year) >= 6 &&
    Number(v.forecast_year) <= 10 &&
    signedDecimal(v.ufcf_growth)
  );
}

function isDcfTailGrowthRead(v: unknown): boolean {
  if (!isRecord(v)) return false;
  const { id, scenario_id, ...input } = v;
  return uuid(id) && uuid(scenario_id) && isDcfTailGrowthInput(input);
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
    (v.years as unknown[]).length === 5 &&
    (v.tail_ufcf_growth === undefined ||
      v.tail_ufcf_growth === null ||
      (Array.isArray(v.tail_ufcf_growth) &&
        v.tail_ufcf_growth.length === 5 &&
        v.tail_ufcf_growth.every(isDcfTailGrowthRead) &&
        v.tail_ufcf_growth.every(
          (year, index) =>
            isRecord(year) && Number(year.forecast_year) === index + 6,
        )))
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
    (v.proposal_author_id === undefined ||
      nullableString(v.proposal_author_id)) &&
    (v.proposal_authored_at === undefined ||
      v.proposal_authored_at === null ||
      timestamp(v.proposal_authored_at)) &&
    (v.proposal_source_reference === undefined ||
      nullableString(v.proposal_source_reference)) &&
    (v.supporting_evidence === undefined ||
      array(v.supporting_evidence, isFinancialModelEvidenceRead)) &&
    isFinancialModelOutputs(v.outputs) &&
    v.outputs.revision_id === v.id
  );
}

function isFinancialModelEvidenceReference(v: unknown): boolean {
  return (
    isRecord(v) &&
    [
      "RESEARCH_REVISION",
      "RESEARCH_FORECAST",
      "THESIS_REVISION",
      "THESIS_CLAIM",
    ].includes(v.evidence_type as string) &&
    uuid(v.reference_id) &&
    ["SUPPORTS", "CONTRADICTS", "CONTEXT"].includes(v.relationship as string) &&
    (v.note === undefined || nullableString(v.note))
  );
}

function isFinancialModelEvidenceRead(
  v: unknown,
): v is FinancialModelEvidenceRead {
  return (
    isRecord(v) &&
    isFinancialModelEvidenceReference(v) &&
    nullableString(v.summary) &&
    string(v.evidence_status) &&
    nullableString(v.author_id) &&
    nullableString(v.source_reference) &&
    (v.observed_at === null || timestamp(v.observed_at)) &&
    timestamp(v.recorded_at) &&
    ["VERIFIED", "UNRESOLVED"].includes(v.resolution_status as string) &&
    nullableString(v.resolution_issue) &&
    (v.trigger_references === undefined ||
      array(v.trigger_references, isResearchTriggerReferenceRead))
  );
}

function isFinancialModelProposalProvenance(v: unknown): boolean {
  return (
    isRecord(v) &&
    string(v.author_id) &&
    timestamp(v.authored_at) &&
    string(v.source_reference) &&
    v.source_reference.startsWith("https://")
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
    !v.years.every(isDcfYearInput) ||
    (v.tail_ufcf_growth !== undefined &&
      v.tail_ufcf_growth !== null &&
      (!Array.isArray(v.tail_ufcf_growth) ||
        v.tail_ufcf_growth.length !== 5 ||
        !v.tail_ufcf_growth.every(isDcfTailGrowthInput) ||
        !v.tail_ufcf_growth.every(
          (year, index) =>
            isRecord(year) && Number(year.forecast_year) === index + 6,
        )))
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
    !["1.0.0", "1.1.0", "1.2.0"].includes(v.contract_version as string) ||
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
    !["ufcf-dcf-fade-v1", "ufcf-dcf-explicit-tail-v1"].includes(
      v.base_revision.methodology_version as string,
    ) ||
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
  if (
    (v.proposal !== undefined &&
      v.proposal !== null &&
      !isFinancialModelProposalProvenance(v.proposal)) ||
    (v.supporting_evidence !== undefined &&
      (!Array.isArray(v.supporting_evidence) ||
        !v.supporting_evidence.every(isFinancialModelEvidenceReference)))
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
    !["2.0.0", "2.1.0"].includes(v.contract_version as string) ||
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
  if (
    (v.proposal !== undefined &&
      v.proposal !== null &&
      !isFinancialModelProposalProvenance(v.proposal)) ||
    (v.supporting_evidence !== undefined &&
      (!Array.isArray(v.supporting_evidence) ||
        !v.supporting_evidence.every(isFinancialModelEvidenceReference)))
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
    isReturnMethodology(v.outputs.return_methodology) &&
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

const researchMetrics = [
  "REVENUE",
  "EPS",
  "EBIT",
  "EBITDA",
  "FREE_CASH_FLOW",
  "DILUTED_SHARES",
] as const;
const researchScenarios = ["POINT", "BEAR", "BASE", "BULL"] as const;
const researchConfidence = ["HIGH", "MEDIUM", "LOW", "UNASSESSED"] as const;

function isResearchForecast(value: unknown): value is ResearchForecast {
  if (!isRecord(value)) return false;
  const valueStatusIsValid =
    (value.availability_status === "AVAILABLE" &&
      signedDecimal(value.value) &&
      value.availability_reason === null) ||
    (value.availability_status === "UNAVAILABLE" &&
      value.value === null &&
      string(value.availability_reason) &&
      value.availability_reason.length > 0) ||
    (value.availability_status === "DATA_CHECK" &&
      nullableSignedDecimal(value.value) &&
      string(value.availability_reason) &&
      value.availability_reason.length > 0);
  return (
    uuid(value.id) &&
    researchMetrics.includes(
      value.metric as (typeof researchMetrics)[number],
    ) &&
    ["ANNUAL", "QUARTERLY"].includes(value.period_type as string) &&
    Number.isInteger(value.fiscal_year) &&
    ((value.period_type === "ANNUAL" && value.fiscal_period === "FY") ||
      (value.period_type === "QUARTERLY" &&
        ["Q1", "Q2", "Q3", "Q4"].includes(value.fiscal_period as string))) &&
    (value.period_end === null || dateOnly(value.period_end)) &&
    researchScenarios.includes(
      value.scenario as (typeof researchScenarios)[number],
    ) &&
    nullableSignedDecimal(value.value) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    string(value.unit) &&
    ["AVAILABLE", "UNAVAILABLE", "DATA_CHECK"].includes(
      value.availability_status as string,
    ) &&
    nullableString(value.availability_reason) &&
    valueStatusIsValid &&
    ((value.metric === "DILUTED_SHARES" &&
      value.currency === null &&
      value.unit === "shares") ||
      (value.metric === "EPS" &&
        string(value.currency) &&
        value.unit === "currency/share") ||
      (researchMetrics.includes(
        value.metric as (typeof researchMetrics)[number],
      ) &&
        value.metric !== "DILUTED_SHARES" &&
        value.metric !== "EPS" &&
        string(value.currency) &&
        value.unit === "currency")) &&
    researchConfidence.includes(
      value.confidence as (typeof researchConfidence)[number],
    ) &&
    nullableString(value.rationale) &&
    nullableString(value.uncertainty)
  );
}

function isResearchAssessment(value: unknown): value is ResearchAssessment {
  if (!isRecord(value)) return false;
  const statusIsValid =
    (value.status === "AVAILABLE" &&
      string(value.narrative) &&
      value.narrative.length > 0 &&
      value.status_reason === null) ||
    (value.status === "UNAVAILABLE" &&
      value.narrative === null &&
      string(value.status_reason) &&
      value.status_reason.length > 0) ||
    (value.status === "DATA_CHECK" &&
      nullableString(value.narrative) &&
      string(value.status_reason) &&
      value.status_reason.length > 0);
  return (
    uuid(value.id) &&
    ["BUSINESS_OUTLOOK", "COMPETITIVE_POSITION", "KEY_RISKS"].includes(
      value.assessment_type as string,
    ) &&
    ["AVAILABLE", "UNAVAILABLE", "DATA_CHECK"].includes(
      value.status as string,
    ) &&
    nullableString(value.status_reason) &&
    nullableString(value.narrative) &&
    statusIsValid &&
    researchConfidence.includes(
      value.confidence as (typeof researchConfidence)[number],
    ) &&
    nullableString(value.uncertainty)
  );
}

function isResearchEvidence(value: unknown): value is ResearchEvidence {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    nullableUuid(value.source_document_id) &&
    nullableString(value.source_document_title) &&
    string(value.source_name) &&
    nullableString(value.external_identifier) &&
    (value.source_url === null ||
      (string(value.source_url) && value.source_url.startsWith("https://"))) &&
    (value.published_at === null || dateOnly(value.published_at)) &&
    nullableString(value.excerpt) &&
    nullableString(value.note)
  );
}

function isResearchRevision(value: unknown): value is ResearchRevision {
  if (!isRecord(value)) return false;
  const hasContent =
    (Array.isArray(value.forecasts) && value.forecasts.length > 0) ||
    (Array.isArray(value.assessments) && value.assessments.length > 0);
  return (
    uuid(value.id) &&
    uuid(value.company_id) &&
    nullableUuid(value.security_id) &&
    string(value.stream_key) &&
    Number.isInteger(value.revision_number) &&
    Number(value.revision_number) > 0 &&
    ["1.0.0", "1.1.0"].includes(value.contract_version as string) &&
    string(value.external_revision_id) &&
    nullableUuid(value.supersedes_revision_id) &&
    string(value.author_id) &&
    string(value.source_id) &&
    string(value.source_reference) &&
    timestamp(value.observed_at) &&
    timestamp(value.recorded_at) &&
    ["PUBLISHED", "WITHDRAWN"].includes(value.status as string) &&
    string(value.rationale) &&
    nullableString(value.uncertainty) &&
    string(value.content_fingerprint) &&
    /^[0-9a-f]{64}$/i.test(value.content_fingerprint) &&
    array(value.forecasts, isResearchForecast) &&
    array(value.assessments, isResearchAssessment) &&
    array(value.evidence, isResearchEvidence) &&
    (value.trigger_references === undefined ||
      array(value.trigger_references, isResearchTriggerReferenceRead)) &&
    ((value.status === "PUBLISHED" && hasContent) ||
      (value.status === "WITHDRAWN" && !hasContent))
  );
}

export function isCompanyResearch(value: unknown): value is CompanyResearch {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    (value.as_of === null || dateOnly(value.as_of)) &&
    (value.known_at === null || timestamp(value.known_at)) &&
    array(value.streams, (stream) => {
      if (
        !isRecord(stream) ||
        !string(stream.stream_key) ||
        !isResearchRevision(stream.current_revision) ||
        !Array.isArray(stream.history)
      )
        return false;
      const currentRevision = stream.current_revision;
      return (
        stream.history.every(isResearchRevision) &&
        stream.history.some(
          (revision: ResearchRevision) => revision.id === currentRevision.id,
        )
      );
    })
  );
}

export function isResearchPublicationResult(
  value: unknown,
): value is ResearchPublicationResult {
  return (
    isRecord(value) &&
    ["PUBLISHED", "ALREADY_PUBLISHED"].includes(value.result as string) &&
    isResearchRevision(value.revision)
  );
}

const thesisClaimTypes = [
  "COMPETITIVE_ADVANTAGE",
  "DURABILITY",
  "GROWTH_DRIVER",
  "PRINCIPAL_RISK",
  "THESIS_BREAKER",
  "CATALYST",
  "IMPORTANT_DEVELOPMENT",
  "UNRESOLVED_QUESTION",
] as const;
const thesisClaimStatuses = [
  "ACTIVE",
  "UNDER_REVIEW",
  "RESOLVED",
  "INVALIDATED",
];
const thesisEvidenceRelationships = ["SUPPORTS", "CONTRADICTS", "CONTEXT"];

function isInvestmentThesisFact(value: unknown): value is InvestmentThesisFact {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    string(value.metric) &&
    [
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
    ].includes(value.metric as string) &&
    ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW_STATEMENT"].includes(
      value.statement as string,
    ) &&
    ["ANNUAL", "QUARTERLY", "INSTANT"].includes(value.period_type as string) &&
    (value.period_start === null || timestamp(value.period_start)) &&
    timestamp(value.period_end) &&
    (value.fiscal_year === null || Number.isInteger(value.fiscal_year)) &&
    nullableString(value.fiscal_period) &&
    (value.filed_at === null || timestamp(value.filed_at)) &&
    timestamp(value.observed_at) &&
    timestamp(value.recorded_at) &&
    signedDecimal(value.value) &&
    (value.currency === null ||
      (string(value.currency) && /^[A-Z]{3}$/.test(value.currency))) &&
    string(value.unit) &&
    string(value.provider_id) &&
    ["PASS", "DATA_CHECK", "INVALID"].includes(value.data_quality as string) &&
    string(value.source_url) &&
    value.source_url.startsWith("https://")
  );
}

function isInvestmentThesisEvidence(
  value: unknown,
): value is InvestmentThesisEvidence {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    thesisEvidenceRelationships.includes(value.relationship as string) &&
    nullableUuid(value.source_document_id) &&
    nullableString(value.source_document_title) &&
    (value.source_document_type === null ||
      sourceDocumentTypes.includes(
        value.source_document_type as (typeof sourceDocumentTypes)[number],
      )) &&
    (value.source_document_url === null ||
      (string(value.source_document_url) &&
        value.source_document_url.startsWith("https://"))) &&
    nullableUuid(value.reported_fundamental_observation_id) &&
    (value.reported_fundamental === null ||
      isInvestmentThesisFact(value.reported_fundamental)) &&
    string(value.source_name) &&
    nullableString(value.external_identifier) &&
    (value.source_url === null ||
      (string(value.source_url) && value.source_url.startsWith("https://"))) &&
    (value.published_at === null || dateOnly(value.published_at)) &&
    nullableString(value.excerpt) &&
    nullableString(value.note)
  );
}

function isInvestmentThesisClaim(
  value: unknown,
): value is InvestmentThesisClaim {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    string(value.claim_key) &&
    thesisClaimTypes.includes(
      value.claim_type as (typeof thesisClaimTypes)[number],
    ) &&
    thesisClaimStatuses.includes(value.status as string) &&
    string(value.statement) &&
    researchConfidence.includes(
      value.confidence as (typeof researchConfidence)[number],
    ) &&
    nullableString(value.uncertainty) &&
    array(value.evidence, isInvestmentThesisEvidence)
  );
}

function isInvestmentThesisRevision(
  value: unknown,
): value is InvestmentThesisRevision {
  if (!isRecord(value)) return false;
  const hasClaims = Array.isArray(value.claims) && value.claims.length > 0;
  const statementIsValid =
    (value.status === "PUBLISHED" && string(value.thesis_statement)) ||
    (value.status === "WITHDRAWN" &&
      value.thesis_statement === null &&
      !hasClaims);
  return (
    uuid(value.id) &&
    uuid(value.company_id) &&
    nullableUuid(value.security_id) &&
    string(value.stream_key) &&
    Number.isInteger(value.revision_number) &&
    Number(value.revision_number) > 0 &&
    ["1.0.0", "1.1.0"].includes(value.contract_version as string) &&
    string(value.external_revision_id) &&
    nullableUuid(value.supersedes_revision_id) &&
    string(value.author_id) &&
    string(value.source_id) &&
    string(value.source_reference) &&
    timestamp(value.observed_at) &&
    timestamp(value.recorded_at) &&
    ["PUBLISHED", "WITHDRAWN"].includes(value.status as string) &&
    statementIsValid &&
    researchConfidence.includes(
      value.confidence as (typeof researchConfidence)[number],
    ) &&
    string(value.rationale) &&
    nullableString(value.uncertainty) &&
    string(value.content_fingerprint) &&
    /^[0-9a-f]{64}$/i.test(value.content_fingerprint) &&
    array(value.claims, isInvestmentThesisClaim) &&
    (value.trigger_references === undefined ||
      array(value.trigger_references, isResearchTriggerReferenceRead))
  );
}

export function isCompanyInvestmentThesis(
  value: unknown,
): value is CompanyInvestmentThesis {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    (value.as_of === null || dateOnly(value.as_of)) &&
    (value.known_at === null || timestamp(value.known_at)) &&
    array(value.streams, (stream) => {
      if (
        !isRecord(stream) ||
        !string(stream.stream_key) ||
        !isInvestmentThesisRevision(stream.current_revision) ||
        !Array.isArray(stream.history)
      )
        return false;
      const currentRevision = stream.current_revision;
      return (
        stream.history.every(isInvestmentThesisRevision) &&
        stream.history.some(
          (revision: InvestmentThesisRevision) =>
            revision.id === currentRevision.id,
        )
      );
    })
  );
}

export function isInvestmentThesisPublicationResult(
  value: unknown,
): value is InvestmentThesisPublicationResult {
  return (
    isRecord(value) &&
    ["PUBLISHED", "ALREADY_PUBLISHED"].includes(value.result as string) &&
    isInvestmentThesisRevision(value.revision)
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
    (value.effective_at === null || timestamp(value.effective_at)) &&
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
    (value.return_methodology === null ||
      isReturnMethodology(value.return_methodology)) &&
    ["CLASSIFIED", "UNCLASSIFIED"].includes(
      value.return_methodology_status as string,
    ) &&
    ["CAPTURED", "NOT_RETAINED", "UNAVAILABLE"].includes(
      value.share_price_basis_status as string,
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

function isCurrentNativeModelCalculation(
  value: unknown,
): value is CurrentNativeModelCalculation {
  if (!isRecord(value)) return false;
  const outputs = value.outputs;
  return (
    uuid(value.model_id) &&
    string(value.model_name) &&
    [
      "UFCF_DCF_10Y_FADE",
      "OWNER_CASH_FLOW_10Y",
      "RESIDUAL_INCOME_10Y_FADE",
    ].includes(value.model_type as string) &&
    uuid(value.revision_id) &&
    Number.isInteger(value.revision_number) &&
    Number(value.revision_number) > 0 &&
    string(value.methodology_version) &&
    timestamp(value.effective_at) &&
    timestamp(value.recorded_at) &&
    timestamp(value.calculated_as_of) &&
    timestamp(value.known_at) &&
    uuid(value.accepted_output_id) &&
    nullableSignedDecimal(value.accepted_reference_price) &&
    nullableUuid(value.accepted_reference_price_observation_id) &&
    (value.accepted_reference_price_effective_at === null ||
      timestamp(value.accepted_reference_price_effective_at)) &&
    isExpectedReturnMarketPrice(value.market_price) &&
    isRecord(outputs) &&
    isReturnMethodology(outputs.return_methodology) &&
    ["COMPLETE", "PARTIAL"].includes(outputs.status as string) &&
    string(outputs.model_currency) &&
    /^[A-Z]{3}$/.test(outputs.model_currency) &&
    nullableUuid(outputs.price_observation_id) &&
    nullableSignedDecimal(outputs.current_price) &&
    (outputs.price_effective_at === null ||
      timestamp(outputs.price_effective_at)) &&
    [
      "FRESH",
      "STALE",
      "QUALITY_CHECK",
      "NO_DATA",
      "CURRENCY_MISMATCH",
      "CURRENCY_UNKNOWN",
    ].includes(outputs.price_status as string) &&
    nullableString(outputs.price_unavailable_reason) &&
    nullableString(outputs.irr_unavailable_reason) &&
    [
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
    ].every((key) => nullableSignedDecimal(outputs[key]))
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
    array(value.history, isExpectedReturnHistoryPoint) &&
    (value.current_calculations === undefined ||
      array(value.current_calculations, isCurrentNativeModelCalculation))
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
    (value.return_methodology === null ||
      isReturnMethodology(value.return_methodology)) &&
    ["CLASSIFIED", "UNCLASSIFIED"].includes(
      value.return_methodology_status as string,
    ) &&
    nullableUuid(value.valuation_listing_id) &&
    nullableString(value.valuation_ticker) &&
    nullableString(value.valuation_venue) &&
    (value.valuation_listing_currency === null ||
      (string(value.valuation_listing_currency) &&
        /^[A-Z]{3}$/.test(value.valuation_listing_currency))) &&
    ["CAPTURED", "NOT_RETAINED", "UNAVAILABLE"].includes(
      value.share_price_basis_status as string,
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
      "RETURN_BASIS_UNAVAILABLE",
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
    [
      "MISSING_RETURN",
      "RETURN_SEMANTICS_CHANGE",
      "RETURN_BASIS_UNAVAILABLE",
      "UNDATED",
    ].includes(value.status as string)
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

function isForecastAccuracyActual(value: unknown): boolean {
  return (
    isRecord(value) &&
    string(value.status) &&
    nullableString(value.metric) &&
    nullableString(value.period_type) &&
    (value.fiscal_year === null || Number.isInteger(value.fiscal_year)) &&
    nullableString(value.fiscal_period) &&
    (value.period_end === null || dateOnly(value.period_end)) &&
    nullableSignedDecimal(value.value) &&
    nullableString(value.currency) &&
    nullableString(value.unit) &&
    nullableString(value.provider_id) &&
    nullableString(value.source_reference) &&
    nullableUuid(value.source_observation_id) &&
    (value.published_at === null || timestamp(value.published_at)) &&
    (value.observed_at === null || timestamp(value.observed_at)) &&
    (value.recorded_at === null || timestamp(value.recorded_at)) &&
    nullableString(value.revision_context) &&
    nullableUuid(value.supersedes_observation_id) &&
    nullableString(value.data_quality) &&
    nullableString(value.reason)
  );
}

function isForecastAccuracyError(value: unknown): boolean {
  return (
    isRecord(value) &&
    string(value.status) &&
    nullableSignedDecimal(value.signed_error) &&
    nullableSignedDecimal(value.absolute_error) &&
    nullableSignedDecimal(value.signed_percentage_error) &&
    nullableSignedDecimal(value.absolute_percentage_error) &&
    nullableString(value.reason)
  );
}

function isForecastAccuracyObservation(value: unknown): boolean {
  return (
    isRecord(value) &&
    ["AGENT_RESEARCH", "FINANCIAL_MODEL", "ANALYST_CONSENSUS"].includes(
      value.source_type as string,
    ) &&
    string(value.source_name) &&
    nullableString(value.source_reference) &&
    nullableString(value.author_id) &&
    nullableString(value.stream_key) &&
    nullableString(value.methodology) &&
    nullableString(value.methodology_version) &&
    (value.model_type === null ||
      [
        "UFCF_DCF_10Y_FADE",
        "OWNER_CASH_FLOW_10Y",
        "RESIDUAL_INCOME_10Y_FADE",
      ].includes(value.model_type as string)) &&
    nullableString(value.scenario) &&
    nullableSignedDecimal(value.scenario_probability) &&
    nullableUuid(value.forecast_id) &&
    nullableUuid(value.revision_id) &&
    (value.revision_number === null ||
      Number.isInteger(value.revision_number)) &&
    nullableUuid(value.supersedes_revision_id) &&
    nullableUuid(value.supersedes_observation_id) &&
    ["REVENUE", "EPS", "EBIT", "EBITDA", "FREE_CASH_FLOW"].includes(
      value.metric as string,
    ) &&
    (value.period_type === null ||
      ["ANNUAL", "QUARTERLY"].includes(value.period_type as string)) &&
    (value.fiscal_year === null || Number.isInteger(value.fiscal_year)) &&
    nullableString(value.fiscal_period) &&
    nullableString(value.forecast_period_label) &&
    (value.period_end === null || dateOnly(value.period_end)) &&
    (value.forecast_year === null || Number.isInteger(value.forecast_year)) &&
    nullableString(value.forecast_basis) &&
    nullableSignedDecimal(value.value) &&
    nullableString(value.currency) &&
    nullableString(value.unit) &&
    nullableString(value.confidence) &&
    (value.analyst_count === null || Number.isInteger(value.analyst_count)) &&
    (value.observed_at === null || timestamp(value.observed_at)) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    (value.recorded_at === null || timestamp(value.recorded_at)) &&
    (value.forecast_known_at === null || timestamp(value.forecast_known_at)) &&
    (value.horizon_days === null || Number.isInteger(value.horizon_days)) &&
    nullableString(value.horizon_bucket) &&
    string(value.status) &&
    nullableString(value.status_reason) &&
    isForecastAccuracyActual(value.actual) &&
    isForecastAccuracyError(value.error)
  );
}

function isForecastAccuracySummary(value: unknown): boolean {
  return (
    isRecord(value) &&
    ["AGENT_RESEARCH", "FINANCIAL_MODEL", "ANALYST_CONSENSUS"].includes(
      value.source_type as string,
    ) &&
    string(value.source_name) &&
    nullableString(value.methodology) &&
    nullableString(value.methodology_version) &&
    ["REVENUE", "EPS", "EBIT", "EBITDA", "FREE_CASH_FLOW"].includes(
      value.metric as string,
    ) &&
    ["ANNUAL", "QUARTERLY"].includes(value.period_type as string) &&
    string(value.horizon_bucket) &&
    Number.isInteger(value.sample_count) &&
    Number.isInteger(value.minimum_sample_count) &&
    string(value.status) &&
    nullableSignedDecimal(value.mean_absolute_percentage_error) &&
    nullableSignedDecimal(value.mean_signed_percentage_error) &&
    nullableString(value.reason)
  );
}

export function isCompanyForecastAccuracy(
  value: unknown,
): value is CompanyForecastAccuracy {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    timestamp(value.outcome_known_at) &&
    (value.selected_metric === null ||
      ["REVENUE", "EPS", "EBIT", "EBITDA", "FREE_CASH_FLOW"].includes(
        value.selected_metric as string,
      )) &&
    (value.selected_source === null ||
      ["AGENT_RESEARCH", "FINANCIAL_MODEL", "ANALYST_CONSENSUS"].includes(
        value.selected_source as string,
      )) &&
    (value.selected_period_type === null ||
      ["ANNUAL", "QUARTERLY"].includes(value.selected_period_type as string)) &&
    (value.selected_fiscal_year === null ||
      Number.isInteger(value.selected_fiscal_year)) &&
    nullableString(value.selected_fiscal_period) &&
    Number.isInteger(value.total_count) &&
    Number.isInteger(value.returned_count) &&
    typeof value.truncated === "boolean" &&
    array(value.observations, isForecastAccuracyObservation) &&
    array(value.summaries, isForecastAccuracySummary)
  );
}

function isScenarioForecastPoint(
  value: unknown,
): value is ScenarioForecastPoint {
  return (
    isRecord(value) &&
    ["BEAR", "BASE", "BULL"].includes(value.scenario as string) &&
    nullableSignedDecimal(value.probability) &&
    nullableSignedDecimal(value.value)
  );
}

function isScenarioEvaluation(value: unknown): value is ScenarioEvaluation {
  return (
    isRecord(value) &&
    string(value.model_name) &&
    [
      "UFCF_DCF_10Y_FADE",
      "OWNER_CASH_FLOW_10Y",
      "RESIDUAL_INCOME_10Y_FADE",
    ].includes(value.model_type as string) &&
    nullableString(value.methodology_version) &&
    uuid(value.revision_id) &&
    Number.isInteger(value.revision_number) &&
    timestamp(value.forecast_known_at) &&
    ["REVENUE", "EPS", "EBIT", "EBITDA", "FREE_CASH_FLOW"].includes(
      value.metric as string,
    ) &&
    Number.isInteger(value.forecast_year) &&
    (value.fiscal_year === null || Number.isInteger(value.fiscal_year)) &&
    nullableString(value.fiscal_period) &&
    (value.period_end === null || dateOnly(value.period_end)) &&
    nullableString(value.currency) &&
    nullableString(value.unit) &&
    array(value.scenarios, isScenarioForecastPoint) &&
    string(value.actual_status) &&
    nullableSignedDecimal(value.actual_value) &&
    (value.actual_published_at === null ||
      timestamp(value.actual_published_at)) &&
    (value.actual_observed_at === null ||
      timestamp(value.actual_observed_at)) &&
    (value.actual_recorded_at === null ||
      timestamp(value.actual_recorded_at)) &&
    string(value.score_status) &&
    nullableSignedDecimal(value.continuous_ranked_probability_score) &&
    string(value.probability_calibration_status) &&
    nullableString(value.reason)
  );
}

function isValuationScenarioContext(
  value: unknown,
): value is ValuationScenarioContext {
  return (
    isRecord(value) &&
    uuid(value.snapshot_id) &&
    string(value.model_key) &&
    string(value.snapshot_kind) &&
    string(value.snapshot_status) &&
    nullableString(value.methodology) &&
    (value.methodology_version === null ||
      Number.isInteger(value.methodology_version)) &&
    nullableString(value.currency) &&
    nullableSignedDecimal(value.bear_fair_value) &&
    nullableSignedDecimal(value.bear_probability) &&
    nullableSignedDecimal(value.base_fair_value) &&
    nullableSignedDecimal(value.base_probability) &&
    nullableSignedDecimal(value.bull_fair_value) &&
    nullableSignedDecimal(value.bull_probability) &&
    (value.effective_at === null || timestamp(value.effective_at)) &&
    timestamp(value.recorded_at) &&
    string(value.source) &&
    string(value.evaluation_status) &&
    string(value.reason)
  );
}

function isDecisionOutcome(value: unknown): value is DecisionOutcome {
  return (
    isRecord(value) &&
    Number.isInteger(value.horizon_days) &&
    string(value.status) &&
    dateOnly(value.target_date) &&
    (value.start_market_date === null || timestamp(value.start_market_date)) &&
    (value.end_market_date === null || timestamp(value.end_market_date)) &&
    nullableSignedDecimal(value.total_return) &&
    nullableSignedDecimal(value.annualized_return) &&
    string(value.basis) &&
    nullableUuid(value.start_observation_id) &&
    nullableUuid(value.end_observation_id) &&
    nullableString(value.start_provider) &&
    nullableString(value.end_provider) &&
    nullableString(value.currency) &&
    nullableString(value.reason)
  );
}

function isDecisionSignalEvaluation(
  value: unknown,
): value is DecisionSignalEvaluation {
  return (
    isRecord(value) &&
    string(value.signal_type) &&
    uuid(value.signal_id) &&
    uuid(value.run_id) &&
    timestamp(value.run_as_of) &&
    timestamp(value.recorded_at) &&
    string(value.source_methodology) &&
    string(value.status) &&
    nullableString(value.value) &&
    (value.position === null || Number.isInteger(value.position)) &&
    nullableSignedDecimal(value.expected_irr) &&
    nullableString(value.return_methodology) &&
    (value.return_methodology_version === null ||
      Number.isInteger(value.return_methodology_version)) &&
    nullableString(value.return_perspective) &&
    nullableUuid(value.valuation_listing_id) &&
    nullableString(value.valuation_ticker) &&
    nullableString(value.valuation_venue) &&
    nullableString(value.listing_currency) &&
    nullableString(value.model_currency) &&
    nullableString(value.estimate_momentum_direction) &&
    nullableString(value.estimate_momentum_availability) &&
    nullableString(value.estimate_momentum_freshness) &&
    nullableString(value.estimate_momentum_quality) &&
    nullableUuid(value.price_observation_id) &&
    array(value.outcomes, isDecisionOutcome) &&
    string(value.reason)
  );
}

function isDecisionEvaluationSummary(
  value: unknown,
): value is DecisionEvaluationSummary {
  return (
    isRecord(value) &&
    string(value.signal_type) &&
    uuid(value.run_id) &&
    timestamp(value.run_as_of) &&
    string(value.source_methodology) &&
    Number.isInteger(value.horizon_days) &&
    string(value.grouping) &&
    string(value.group_value) &&
    nullableString(value.listing_currency) &&
    Number.isInteger(value.sample_count) &&
    Number.isInteger(value.minimum_sample_count) &&
    string(value.status) &&
    nullableSignedDecimal(value.spearman_correlation) &&
    nullableSignedDecimal(value.mean_annualized_return) &&
    nullableSignedDecimal(value.median_annualized_return) &&
    string(value.interpretation)
  );
}

export function isCompanyDecisionEvaluation(
  value: unknown,
): value is CompanyDecisionEvaluation {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    timestamp(value.outcome_known_at) &&
    Array.isArray(value.horizon_days) &&
    value.horizon_days.every(Number.isInteger) &&
    Number.isInteger(value.minimum_cross_section_sample) &&
    array(value.scenario_evaluations, isScenarioEvaluation) &&
    array(value.valuation_scenarios, isValuationScenarioContext) &&
    array(value.signals, isDecisionSignalEvaluation) &&
    array(value.summaries, isDecisionEvaluationSummary) &&
    string(value.portfolio_implementation_status) &&
    string(value.portfolio_implementation_reason) &&
    Array.isArray(value.limitations) &&
    value.limitations.every(string)
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

export function isGoogleSheetsSyncStatus(
  value: unknown,
): value is GoogleSheetsSyncStatus {
  return (
    isRecord(value) &&
    typeof value.configured === "boolean" &&
    typeof value.credentials_available === "boolean" &&
    nullableString(value.spreadsheet_id) &&
    nullableString(value.spreadsheet_url) &&
    string(value.sync_tab) &&
    Number.isInteger(value.polling_interval_seconds) &&
    (value.last_run === null || isGoogleSheetsSyncRun(value.last_run))
  );
}

export function isGoogleSheetsConnectionTest(
  value: unknown,
): value is GoogleSheetsConnectionTest {
  return (
    isRecord(value) &&
    typeof value.connected === "boolean" &&
    nullableString(value.spreadsheet_id) &&
    nullableString(value.spreadsheet_title) &&
    typeof value.sync_tab_exists === "boolean" &&
    timestamp(value.checked_at) &&
    string(value.message)
  );
}

export function isGoogleSheetsSyncRun(
  value: unknown,
): value is GoogleSheetsSyncRun {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    ["CONNECTED", "SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED"].includes(
      value.status as string,
    ) &&
    timestamp(value.started_at) &&
    (value.completed_at === null || timestamp(value.completed_at)) &&
    nullableString(value.spreadsheet_id) &&
    nullableString(value.spreadsheet_title) &&
    Number.isInteger(value.candidate_count) &&
    Number.isInteger(value.new_count) &&
    Number.isInteger(value.unchanged_count) &&
    Number.isInteger(value.issue_count) &&
    nullableString(value.error_code) &&
    nullableString(value.error_message)
  );
}

export function isGoogleSheetsSyncCandidate(
  value: unknown,
): value is GoogleSheetsSyncCandidate {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    string(value.spreadsheet_id) &&
    string(value.spreadsheet_title) &&
    Number.isInteger(value.sheet_id) &&
    string(value.sheet_title) &&
    Number.isInteger(value.source_row_number) &&
    string(value.source_url) &&
    nullableString(value.external_revision_id) &&
    nullableString(value.contract_version) &&
    string(value.content_fingerprint) &&
    nullableUuid(value.model_id) &&
    nullableString(value.model_name) &&
    nullableString(value.model_type) &&
    nullableString(value.source_model_key) &&
    nullableUuid(value.company_id) &&
    nullableString(value.company_name) &&
    nullableUuid(value.valuation_listing_id) &&
    (value.model_currency === null ||
      (string(value.model_currency) &&
        /^[A-Z]{3}$/.test(value.model_currency))) &&
    nullableString(value.rationale) &&
    (value.proposal === undefined ||
      value.proposal === null ||
      isFinancialModelProposalProvenance(value.proposal)) &&
    (value.supporting_evidence === undefined ||
      array(value.supporting_evidence, isFinancialModelEvidenceRead)) &&
    [
      "PENDING",
      "READY",
      "CONFLICT",
      "INVALID",
      "NO_CHANGES",
      "ACCEPTED",
      "REJECTED",
    ].includes(value.status as string) &&
    nullableString(value.issue) &&
    nullableString(value.preview_status) &&
    (value.preview_data === null || isRecord(value.preview_data)) &&
    (value.previewed_at === null || timestamp(value.previewed_at)) &&
    timestamp(value.first_observed_at) &&
    timestamp(value.last_observed_at) &&
    nullableString(value.reviewer) &&
    nullableString(value.decision_note) &&
    nullableUuid(value.accepted_revision_id) &&
    (value.accepted_at === null || timestamp(value.accepted_at)) &&
    (value.rejected_at === null || timestamp(value.rejected_at))
  );
}

export function isGoogleSheetsSyncCheck(
  value: unknown,
): value is GoogleSheetsSyncCheck {
  return (
    isRecord(value) &&
    isGoogleSheetsSyncRun(value.run) &&
    array(value.new_candidates, isGoogleSheetsSyncCandidate)
  );
}

export function isGoogleSheetsPortfolioStatePublish(
  value: unknown,
): value is GoogleSheetsPortfolioStatePublish {
  return (
    isRecord(value) &&
    ["PUBLISHED", "UNCHANGED"].includes(value.status as string) &&
    string(value.spreadsheet_id) &&
    string(value.spreadsheet_title) &&
    value.tab === "Application Portfolio State" &&
    uuid(value.portfolio_id) &&
    value.contract_version === "1.0.0" &&
    string(value.content_fingerprint) &&
    timestamp(value.published_at) &&
    (value.valuation_as_of === null || timestamp(value.valuation_as_of)) &&
    string(value.valuation_status) &&
    Number.isInteger(value.row_count) &&
    typeof value.read_back_verified === "boolean" &&
    string(value.message)
  );
}

export function isGoogleSheetsThesisWatchPublish(
  value: unknown,
): value is GoogleSheetsThesisWatchPublish {
  return (
    isRecord(value) &&
    ["PUBLISHED", "UNCHANGED"].includes(value.status as string) &&
    string(value.spreadsheet_id) &&
    string(value.spreadsheet_title) &&
    value.tab === "Application Thesis Watch Feed" &&
    value.contract_version === "1.0.0" &&
    string(value.content_fingerprint) &&
    timestamp(value.published_at) &&
    Number.isInteger(value.row_count) &&
    Number.isInteger(value.added_count) &&
    array(value.trigger_ids, string) &&
    typeof value.read_back_verified === "boolean" &&
    string(value.message)
  );
}

export function isGoogleSheetsAgentWorkPublish(
  value: unknown,
): value is GoogleSheetsAgentWorkPublish {
  return (
    isRecord(value) &&
    ["PUBLISHED", "UNCHANGED", "NO_WORK", "BLOCKED"].includes(
      value.status as string,
    ) &&
    [
      "DATA_UNIVERSE_STEWARD",
      "PORTFOLIO_THESIS_SENTINEL",
      "MODEL_ALLOCATION_STEWARD",
    ].includes(value.agent_role as string) &&
    (value.spreadsheet_id === null || string(value.spreadsheet_id)) &&
    (value.spreadsheet_title === null || string(value.spreadsheet_title)) &&
    value.tab === "Application Agent Work Feed" &&
    value.contract_version === "1.0.0" &&
    (value.content_fingerprint === null || string(value.content_fingerprint)) &&
    timestamp(value.published_at) &&
    Number.isInteger(value.row_count) &&
    Number.isInteger(value.added_count) &&
    Number.isInteger(value.work_item_count) &&
    typeof value.read_back_verified === "boolean" &&
    nullableString(value.status_reason) &&
    string(value.message)
  );
}

function isRiskAssessmentEvidence(
  value: unknown,
): value is RiskAssessmentEvidence {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    nullableUuid(value.source_document_id) &&
    nullableString(value.source_document_title) &&
    nullableString(value.source_document_url) &&
    nullableUuid(value.reported_fundamental_observation_id) &&
    nullableUuid(value.thesis_revision_id) &&
    nullableUuid(value.thesis_claim_id) &&
    string(value.source_name) &&
    nullableString(value.external_identifier) &&
    nullableString(value.source_url) &&
    (value.published_at === null || dateOnly(value.published_at)) &&
    nullableString(value.excerpt) &&
    nullableString(value.note)
  );
}

function isRiskAssessmentFinding(
  value: unknown,
): value is RiskAssessmentFinding {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    string(value.finding_key) &&
    ["COMPANY", "PORTFOLIO"].includes(value.scope as string) &&
    nullableUuid(value.company_id) &&
    nullableString(value.company_name) &&
    [
      "BUSINESS",
      "FINANCIAL",
      "GEOGRAPHIC",
      "CURRENCY",
      "BUSINESS_MODEL",
      "REGULATORY",
      "GOVERNANCE",
      "GEOPOLITICAL",
      "PORTFOLIO_CONCENTRATION",
      "PORTFOLIO_EXPOSURE",
      "THESIS_CHANGE",
      "OTHER",
    ].includes(value.category as string) &&
    string(value.title) &&
    string(value.description) &&
    ["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(value.severity as string) &&
    ["LOW", "MEDIUM", "HIGH", "UNASSESSED"].includes(
      value.confidence as string,
    ) &&
    ["ACTIVE", "UNDER_REVIEW", "RESOLVED"].includes(value.status as string) &&
    ["NEW", "WORSENING", "UNCHANGED", "IMPROVING", "RESOLVED"].includes(
      value.change_direction as string,
    ) &&
    string(value.rationale) &&
    array(value.evidence, isRiskAssessmentEvidence)
  );
}

function isRiskAssessmentRevision(
  value: unknown,
): value is RiskAssessmentRevision {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    uuid(value.portfolio_id) &&
    string(value.stream_key) &&
    Number.isInteger(value.revision_number) &&
    string(value.contract_version) &&
    string(value.external_revision_id) &&
    nullableUuid(value.supersedes_revision_id) &&
    string(value.author_id) &&
    string(value.source_id) &&
    string(value.source_reference) &&
    timestamp(value.authored_at) &&
    timestamp(value.published_at) &&
    timestamp(value.recorded_at) &&
    string(value.reviewer) &&
    string(value.reviewer_note) &&
    timestamp(value.accepted_at) &&
    [
      "CURRENT",
      "STALE_PORTFOLIO_STATE",
      "STALE_HOLDINGS",
      "INCOMPLETE_VALUATION",
    ].includes(value.baseline_status_at_accept as string) &&
    typeof value.baseline_stale_acknowledged === "boolean" &&
    string(value.portfolio_state_contract_version) &&
    /^sha256:[0-9a-f]{64}$/i.test(String(value.portfolio_state_fingerprint)) &&
    uuid(value.holdings_snapshot_id) &&
    nullableUuid(value.target_revision_id) &&
    timestamp(value.valuation_as_of) &&
    ["COMPLETE", "PARTIAL"].includes(value.coverage_status as string) &&
    nullableString(value.coverage_note) &&
    string(value.summary) &&
    string(value.rationale) &&
    /^[0-9a-f]{64}$/i.test(String(value.content_fingerprint)) &&
    array(value.findings, isRiskAssessmentFinding)
  );
}

export function isCompanyRiskAssessments(
  value: unknown,
): value is CompanyRiskAssessments {
  return (
    isRecord(value) &&
    uuid(value.company_id) &&
    array(value.current, isRiskAssessmentRevision) &&
    array(value.history, isRiskAssessmentRevision)
  );
}

export function isPortfolioRiskAssessments(
  value: unknown,
): value is PortfolioRiskAssessments {
  return (
    isRecord(value) &&
    uuid(value.portfolio_id) &&
    array(value.current, isRiskAssessmentRevision) &&
    array(value.history, isRiskAssessmentRevision)
  );
}

export function isGoogleSheetsRiskSyncStatus(
  value: unknown,
): value is GoogleSheetsRiskSyncStatus {
  return (
    isRecord(value) &&
    typeof value.configured === "boolean" &&
    typeof value.credentials_available === "boolean" &&
    nullableString(value.spreadsheet_id) &&
    nullableString(value.spreadsheet_url) &&
    value.inbox_tab === "Application Risk Assessment Inbox" &&
    (value.last_run === null || isGoogleSheetsRiskSyncRun(value.last_run))
  );
}

export function isGoogleSheetsRiskSyncRun(
  value: unknown,
): value is GoogleSheetsRiskSyncRun {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    nullableString(value.spreadsheet_id) &&
    nullableString(value.spreadsheet_title) &&
    ["CONNECTED", "SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED"].includes(
      value.status as string,
    ) &&
    timestamp(value.started_at) &&
    (value.completed_at === null || timestamp(value.completed_at)) &&
    Number.isInteger(value.candidate_count) &&
    Number.isInteger(value.new_count) &&
    Number.isInteger(value.unchanged_count) &&
    Number.isInteger(value.issue_count) &&
    nullableString(value.error_code) &&
    nullableString(value.error_message)
  );
}

export function isGoogleSheetsRiskCandidate(
  value: unknown,
): value is GoogleSheetsRiskCandidate {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    nullableUuid(value.portfolio_id) &&
    nullableString(value.stream_key) &&
    nullableString(value.external_revision_id) &&
    nullableString(value.contract_version) &&
    /^[0-9a-f]{64}$/i.test(String(value.content_fingerprint)) &&
    string(value.source_url) &&
    string(value.sheet_title) &&
    Number.isInteger(value.source_row_number) &&
    [
      "PENDING",
      "READY",
      "STALE_BASELINE",
      "CONFLICT",
      "INVALID",
      "ACCEPTED",
      "REJECTED",
    ].includes(value.status as string) &&
    nullableString(value.issue) &&
    nullableString(value.author_id) &&
    nullableString(value.source_id) &&
    nullableString(value.source_reference) &&
    (value.authored_at === null || timestamp(value.authored_at)) &&
    (value.published_at === null || timestamp(value.published_at)) &&
    nullableString(value.summary) &&
    Number.isInteger(value.findings_count) &&
    (value.baseline_status === null ||
      [
        "CURRENT",
        "STALE_PORTFOLIO_STATE",
        "STALE_HOLDINGS",
        "INCOMPLETE_VALUATION",
      ].includes(value.baseline_status as string)) &&
    (value.preview_data === null || isRecord(value.preview_data)) &&
    nullableString(value.reviewer) &&
    nullableString(value.reviewer_note) &&
    nullableUuid(value.accepted_revision_id) &&
    timestamp(value.first_observed_at) &&
    timestamp(value.last_observed_at) &&
    (value.accepted_at === null || timestamp(value.accepted_at)) &&
    (value.rejected_at === null || timestamp(value.rejected_at))
  );
}

export function isGoogleSheetsRiskSyncCheck(
  value: unknown,
): value is GoogleSheetsRiskSyncCheck {
  return (
    isRecord(value) &&
    isGoogleSheetsRiskSyncRun(value.run) &&
    array(value.new_candidates, isGoogleSheetsRiskCandidate)
  );
}

export function isGoogleSheetsResearchSyncStatus(
  value: unknown,
): value is GoogleSheetsResearchSyncStatus {
  return (
    isRecord(value) &&
    typeof value.configured === "boolean" &&
    typeof value.credentials_available === "boolean" &&
    nullableString(value.spreadsheet_id) &&
    nullableString(value.spreadsheet_url) &&
    value.research_inbox_tab === "Application Research Inbox" &&
    value.thesis_inbox_tab === "Application Thesis Inbox" &&
    (value.last_run === null || isGoogleSheetsResearchSyncRun(value.last_run))
  );
}

export function isGoogleSheetsResearchConnectionTest(
  value: unknown,
): value is GoogleSheetsResearchConnectionTest {
  return (
    isRecord(value) &&
    typeof value.connected === "boolean" &&
    nullableString(value.spreadsheet_id) &&
    nullableString(value.spreadsheet_title) &&
    typeof value.research_inbox_exists === "boolean" &&
    typeof value.thesis_inbox_exists === "boolean" &&
    timestamp(value.checked_at) &&
    string(value.message)
  );
}

export function isGoogleSheetsResearchSyncRun(
  value: unknown,
): value is GoogleSheetsResearchSyncRun {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    nullableString(value.spreadsheet_id) &&
    nullableString(value.spreadsheet_title) &&
    ["SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED"].includes(
      value.status as string,
    ) &&
    timestamp(value.started_at) &&
    (value.completed_at === null || timestamp(value.completed_at)) &&
    Number.isInteger(value.candidate_count) &&
    Number.isInteger(value.new_count) &&
    Number.isInteger(value.unchanged_count) &&
    Number.isInteger(value.issue_count) &&
    nullableString(value.error_code) &&
    nullableString(value.error_message)
  );
}

export function isGoogleSheetsResearchCandidate(
  value: unknown,
): value is GoogleSheetsResearchCandidate {
  return (
    isRecord(value) &&
    uuid(value.id) &&
    ["RESEARCH", "THESIS"].includes(value.domain as string) &&
    nullableUuid(value.company_id) &&
    nullableUuid(value.security_id) &&
    nullableString(value.stream_key) &&
    nullableString(value.external_revision_id) &&
    nullableUuid(value.base_revision_id) &&
    nullableString(value.contract_version) &&
    /^[0-9a-f]{64}$/i.test(String(value.content_fingerprint)) &&
    string(value.source_url) &&
    string(value.sheet_title) &&
    Number.isInteger(value.source_row_number) &&
    nullableString(value.author_id) &&
    nullableString(value.source_id) &&
    nullableString(value.source_reference) &&
    (value.observed_at === null || timestamp(value.observed_at)) &&
    nullableString(value.rationale) &&
    Number.isInteger(value.item_count) &&
    Number.isInteger(value.evidence_count) &&
    [
      "PENDING",
      "READY",
      "CONFLICT",
      "INVALID",
      "ACCEPTED",
      "REJECTED",
    ].includes(value.status as string) &&
    nullableString(value.issue) &&
    (value.preview_data === null || isRecord(value.preview_data)) &&
    nullableString(value.reviewer) &&
    nullableString(value.reviewer_note) &&
    nullableUuid(value.accepted_research_revision_id) &&
    nullableUuid(value.accepted_thesis_revision_id) &&
    timestamp(value.first_observed_at) &&
    timestamp(value.last_observed_at) &&
    (value.accepted_at === null || timestamp(value.accepted_at)) &&
    (value.rejected_at === null || timestamp(value.rejected_at))
  );
}

export function isGoogleSheetsResearchSyncCheck(
  value: unknown,
): value is GoogleSheetsResearchSyncCheck {
  return (
    isRecord(value) &&
    isGoogleSheetsResearchSyncRun(value.run) &&
    array(value.new_candidates, isGoogleSheetsResearchCandidate)
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
      "RISK_ASSESSMENT",
      "RESEARCH_PROPOSAL",
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
