import { describe, expect, it } from "vitest";
import {
  isCompany,
  isDetail,
  isCompanyRankings,
  isOverview,
  isListingMarketData,
  isUniverseRankingSummary,
  isModelOutputSnapshot,
  isFinancialModelOutputs,
  isFinancialModelContract,
  isFinancialModelContractPreview,
  isFinancialModelCalculationPreview,
  isAdditionalModelPortableContractResponse,
  isAdditionalModelContractPreview,
  isExtendedFinancialModels,
  isCompanyFinancialModelMigration,
  isCompanyReportedFundamentals,
  isCompanyConsensusEstimates,
  isCompanyEstimateMomentum,
  isCompanyTemporalAlignment,
  isCompanyExpectedReturnHistory,
  isCompanyExpectedReturnAttribution,
  isPortfolioRankInputSnapshot,
  isResearchRankInputSnapshot,
  isCompanySourceDocuments,
  isReportedFundamentalDefinitions,
  isCompanyExecutionPace,
  isUniverseExecutionPaceSummary,
  isAttentionFeed,
} from "@/lib/domain-contracts";
import { percent, quantity } from "@/lib/display";

const id = "11111111-1111-4111-8111-111111111111";
const executionPaceSnapshot = {
  context_version: "execution-pace-inputs-v1",
  lifecycle: "PORTFOLIO",
  target_revision_id: id,
  target_effective_at: "2026-10-05T00:00:00Z",
  holding_snapshot_id: id,
  holding_effective_at: "2026-10-05T00:00:00Z",
  allocation_status: "VALUED",
  current_weight: "0.02",
  target_weight: "0.05",
  allocation_gap: "0.03",
  model_source_kind: "IMPORTED_CURRENT_CONTRACT",
  model_source_id: id,
  model_revision_id: null,
  model_output_snapshot_id: id,
  model_key: "P-EXAMPLE",
  return_semantics: "LEGACY_NORMALIZED_FIELD",
  model_effective_at: "2026-10-05T00:00:00Z",
  model_recorded_at: "2026-10-05T00:00:00Z",
  model_currency: "USD",
  model_output_quality: "COMPLETE",
  model_contract_status: "PASS",
  model_review_flag: "PASS",
  expected_irr: "0.18",
  hurdle: "0.09",
  valuation_listing_id: id,
  valuation_ticker: "EXM",
  valuation_venue: "NASDAQ",
  valuation_currency: "USD",
  price_observation_id: id,
  price_market_date: "2026-10-05T00:00:00Z",
  price_recorded_at: "2026-10-05T00:00:00Z",
  price_currency: "USD",
  price: "100",
  price_provider: "YAHOO_FINANCE",
  price_quality: "PASS",
  price_freshness: "FRESH",
  model_price_status: "AVAILABLE",
  model_price_effective_at: "2026-10-05T00:00:00Z",
  model_price_observation_id: id,
  model_reference_price: "100",
  model_price_currency: "USD",
  weighted_fair_value: "130",
  weighted_upside: "0.3",
  valuation_zone: "DEEP_DISCOUNT",
  valuation_range_ratio: "0.8",
  estimate_momentum_availability: "AVAILABLE",
  estimate_momentum_direction: "POSITIVE",
  estimate_momentum_freshness: "FRESH",
  estimate_momentum_quality: "PASS",
  estimate_provider_id: "primary_estimates",
  estimate_latest_snapshot_date: "2026-10-05",
  estimate_momentum_reason: null,
  price_regime_source_ref: "regime:example",
  price_regime_as_of: "2026-10-05T00:00:00Z",
  price_regime_quality: "PASS",
  price_regime_raw: "DEEP CORRECTION",
  price_regime: "DEEP CORR",
  price_regime_freshness: "FRESH",
  context_notes: [],
};
const executionPaceRun = {
  id,
  portfolio_id: id,
  as_of: "2026-10-05T00:00:00Z",
  recorded_at: "2026-10-05T00:00:00Z",
  methodology_version: "legacy-execution-pace-v1",
  status: "PARTIAL",
  actor: "LOCAL_USER",
  reason: "Periodic review.",
  source: "web",
  company_count: 1,
  available_count: 0,
  review_count: 1,
  unavailable_count: 0,
  not_applicable_count: 0,
};
const executionPaceHistoryEntry = {
  run: executionPaceRun,
  decision: {
    id: "22222222-2222-4222-8222-222222222222",
    run_id: id,
    company_id: id,
    target_revision_id: id,
    holding_snapshot_id: id,
    model_revision_id: null,
    model_output_snapshot_id: id,
    price_observation_id: id,
    decision_status: "REVIEW",
    pace: null,
    reason: "Estimate history is insufficient.",
    input_snapshot: {
      ...executionPaceSnapshot,
      estimate_momentum_availability: "INSUFFICIENT_HISTORY",
      estimate_momentum_direction: null,
      estimate_momentum_freshness: "NO_DATA",
      estimate_momentum_quality: "NO_DATA",
      estimate_latest_snapshot_date: null,
    },
  },
};
const fundamentalMetrics = [
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
const missingReportedFundamentals = {
  company_id: id,
  provider_identity_status: "UNMAPPED",
  provider_ids: [],
  coverage: fundamentalMetrics.map((metric, index) => ({
    metric,
    statement:
      index < 4 || index === 9
        ? "INCOME_STATEMENT"
        : index < 7
          ? "BALANCE_SHEET"
          : "CASH_FLOW_STATEMENT",
    observation_count: 0,
    latest_period_end: null,
    status: "NOT_IMPORTED",
  })),
  periods: [],
  as_of: null,
  known_at: null,
  latest_observed_at: null,
};

describe("reported fundamentals contracts", () => {
  it("keeps unmapped and not-imported facts explicitly missing", () => {
    expect(isCompanyReportedFundamentals(missingReportedFundamentals)).toBe(
      true,
    );
    expect(
      missingReportedFundamentals.coverage.every(
        (item) =>
          item.status === "NOT_IMPORTED" && item.latest_period_end === null,
      ),
    ).toBe(true);
  });

  it("identifies free cash flow as derived instead of a reported fact", () => {
    expect(
      isReportedFundamentalDefinitions([
        {
          metric: "FREE_CASH_FLOW",
          statement: null,
          display_name: "Free cash flow",
          canonical_unit: "currency",
          evidence_type: "DERIVED_ANALYTIC",
          description: "Not stored as a reported fact.",
        },
      ]),
    ).toBe(true);
  });
});

describe("Execution Pace contracts", () => {
  it("preserves review and no-run states without treating them as neutral", () => {
    expect(
      isCompanyExecutionPace({
        company_id: id,
        current: executionPaceHistoryEntry,
        history: [executionPaceHistoryEntry],
      }),
    ).toBe(true);
    expect(
      isCompanyExecutionPace({ company_id: id, current: null, history: [] }),
    ).toBe(true);
    expect(
      isUniverseExecutionPaceSummary([
        { company, decision: executionPaceHistoryEntry },
        { company, decision: null },
      ]),
    ).toBe(true);
  });

  it("rejects a result that claims availability without an explicit pace", () => {
    const malformed = structuredClone(executionPaceHistoryEntry);
    malformed.decision.decision_status = "AVAILABLE";
    expect(
      isCompanyExecutionPace({
        company_id: id,
        current: malformed,
        history: [malformed],
      }),
    ).toBe(false);
  });
});

describe("expected-return history contract", () => {
  it("accepts an explicit absence without manufacturing a historical value", () => {
    const noHistory = {
      company_id: id,
      as_of: "2026-10-05",
      known_at: "2026-10-05T12:00:00Z",
      status: "NO_HISTORY",
      history: [],
    };
    expect(isCompanyExpectedReturnHistory(noHistory)).toBe(true);
    expect(
      isCompanyExpectedReturnHistory({
        ...noHistory,
        status: "AVAILABLE",
        history: null,
      }),
    ).toBe(false);
  });

  it("keeps imported output-only history distinct from undated native state", () => {
    const undated = {
      point_id: "imported:fixture",
      source_kind: "IMPORTED_LEGACY_REVISION",
      event_status: "EFFECTIVE_DATE_UNKNOWN",
      effective_at: null,
      recorded_at: "2026-10-05T12:00:00Z",
      series_id: "legacy:P-EXAMPLE",
      model_key: "P-EXAMPLE",
      model_id: null,
      revision_id: null,
      revision_number: null,
      model_type: null,
      methodology_version: null,
      model_label: "P-EXAMPLE",
      model_currency: null,
      currency_status: "UNKNOWN",
      valuation_listing_id: null,
      valuation_ticker: null,
      valuation_venue: null,
      valuation_listing_currency: null,
      is_current_at_cutoff: false,
      output_status: "COMPLETE",
      output_quality: "COMPLETE",
      contract_status: "PASS",
      return_semantics: "LEGACY_NORMALIZED_FIELD",
      actor: "IMPORT",
      source_actor: "Workbook researcher",
      revision_source: "Workbook",
      revision_type: "Periodic review",
      bear_fv: null,
      base_fv: null,
      bull_fv: null,
      bear_probability: null,
      base_probability: null,
      bull_probability: null,
      weighted_fv: null,
      weighted_upside: null,
      expected_cash_flow_irr: null,
      hurdle: null,
      expected_excess: null,
      forward_fundamental_cagr: null,
      market_price: {
        status: "UNDATED",
        listing_id: null,
        ticker: null,
        venue: null,
        listing_currency: null,
        quote: null,
        quote_currency: null,
        model_reference_price: null,
        model_currency: null,
        effective_at: null,
        observed_at: null,
        recorded_at: null,
        provider: null,
        adjustment_basis: null,
        observation_id: null,
        source_ref: null,
        reason: "The source snapshot has no effective timestamp.",
      },
      estimate_context: {
        status: "UNDATED",
        provider_id: null,
        periods: [],
      },
      source: "Workbook",
      source_revision_id: "legacy-revision",
      rationale: null,
      evidence: null,
    };
    expect(
      isCompanyExpectedReturnHistory({
        company_id: id,
        as_of: "2026-10-05",
        known_at: "2026-10-05T12:00:00Z",
        status: "PARTIAL",
        history: [undated],
      }),
    ).toBe(true);
  });

  it("preserves null Expected IRR when attribution endpoints are missing", () => {
    const state = {
      point_id: "native:fixture",
      source_kind: "NATIVE_MODEL_REVISION",
      effective_at: "2026-10-01T12:00:00Z",
      recorded_at: "2026-10-01T12:00:00Z",
      series_id: "native:model",
      model_id: id,
      revision_id: id,
      revision_number: 1,
      model_type: "UFCF_DCF_10Y_FADE",
      methodology_version: "fixture-v1",
      return_semantics: "NATIVE_METHOD_OUTPUT",
      model_currency: "USD",
      expected_cash_flow_irr: null,
      hurdle: "0.09",
      expected_excess: null,
      bear_fv: "10",
      base_fv: "20",
      bull_fv: "30",
      bear_probability: "0.2",
      base_probability: "0.6",
      bull_probability: "0.2",
      weighted_fv: "20",
      market_price: {
        status: "NO_DATA",
        listing_id: null,
        ticker: null,
        venue: null,
        listing_currency: null,
        quote: null,
        quote_currency: null,
        model_reference_price: null,
        model_currency: "USD",
        effective_at: null,
        observed_at: null,
        recorded_at: null,
        provider: null,
        adjustment_basis: null,
        observation_id: null,
        source_ref: null,
        reason: "No price captured.",
      },
      estimate_context: {
        status: "NO_OBSERVATIONS",
        provider_id: null,
        periods: [],
      },
      source: "test",
      source_revision_id: null,
      rationale: "test fixture",
    };
    const missing = {
      company_id: id,
      status: "MISSING_RETURN",
      method: "UNAVAILABLE",
      prior: state,
      current: { ...state, point_id: "native:fixture-2", revision_number: 2 },
      expected_irr_change: null,
      drivers: [],
      residual: null,
      residual_reason: "A model endpoint has no return.",
      context_changes: {
        weighted_fv: "0",
        bear_fv: null,
        base_fv: null,
        bull_fv: null,
        bear_probability: null,
        base_probability: null,
        bull_probability: null,
        hurdle: null,
        expected_excess: null,
      },
      estimate_context_note: "Estimates remain contextual.",
    };
    expect(isCompanyExpectedReturnAttribution(missing)).toBe(true);
    expect(
      isCompanyExpectedReturnAttribution({
        ...missing,
        expected_irr_change: "0",
      }),
    ).toBe(false);
    const attributed = {
      ...missing,
      status: "ATTRIBUTED",
      method: "SYMMETRIC_COUNTERFACTUAL_SHAPLEY",
      expected_irr_change: "0.02",
      drivers: [
        ["MARKET_PRICE", "Market price", "-0.01"],
        ["SCENARIO_PROBABILITIES", "Probabilities", "0.005"],
        ["REQUIRED_RETURN_ASSUMPTIONS", "Required return", "0.01"],
        ["MODEL_ASSUMPTIONS", "Model assumptions", "0.015"],
      ].map(([code, label, effect]) => ({
        code,
        label,
        effect,
        explanation: "Fixture driver.",
      })),
      residual: "0",
      residual_reason: null,
    };
    expect(isCompanyExpectedReturnAttribution(attributed)).toBe(true);
  });
});

describe("active ranking input snapshot contracts", () => {
  it("keeps Portfolio Rank missing fields null and explicit", () => {
    const score = {
      score: null,
      status: "MISSING",
      assessment_id: null,
      effective_at: null,
      recorded_at: null,
      source: null,
    };
    const missingPortfolioInputs = {
      context_version: "portfolio-rank-inputs-v1",
      score_formula: "LEGACY_IRR_FIRST_ALLOCATION_V1",
      portfolio_score: null,
      current_weight: null,
      target_weight: null,
      target_minus_current_gap: null,
      lifecycle: "PORTFOLIO",
      allocation_status: "FX_UNAVAILABLE",
      holding_snapshot_id: id,
      holding_effective_at: "2026-10-06T12:00:00Z",
      target_revision_id: id,
      target_effective_at: "2026-10-06T12:00:00Z",
      expected_irr: null,
      expected_excess: null,
      hurdle: null,
      bear_fair_value: null,
      weighted_fair_value: null,
      bull_fair_value: null,
      valuation_uncertainty: null,
      durability_10y: score,
      compounder_quality: score,
      execution: score,
      risk: score,
      model_source: null,
      score_contributions: {
        target_underweight: null,
        expected_irr: null,
        durability_10y: null,
        compounder_quality: null,
        execution: null,
        risk: null,
        valuation_uncertainty_penalty: null,
        negative_expected_excess_penalty: null,
      },
      context_note: "Missing scores are not zero.",
    };
    expect(isPortfolioRankInputSnapshot(missingPortfolioInputs)).toBe(true);
    expect(
      isPortfolioRankInputSnapshot({
        ...missingPortfolioInputs,
        portfolio_score: "0",
      }),
    ).toBe(true);
  });

  it("accepts an explicit Research Rank missing-input state without an invented key", () => {
    expect(
      isResearchRankInputSnapshot({
        context_version: "research-rank-inputs-v1",
        lifecycle: "CANDIDATE",
        candidate_tier: null,
        priority_seed: null,
        legacy_default_priority_seed: null,
        used_legacy_default: false,
        sort_key: null,
        input_quality: "MISSING",
        source_digest: null,
        bucket_source_ref: null,
        priority_seed_source_ref: null,
        context_note: "Candidate tier has not been imported.",
      }),
    ).toBe(true);
    expect(
      isResearchRankInputSnapshot({
        context_version: "research-rank-inputs-v1",
        lifecycle: "CANDIDATE",
        candidate_tier: "LOW",
        priority_seed: null,
        legacy_default_priority_seed: "50000",
        used_legacy_default: true,
        sort_key: "50000",
        input_quality: "AVAILABLE",
        source_digest: null,
        bucket_source_ref: "Workbook!C12",
        priority_seed_source_ref: null,
        context_note: "The documented source fallback was used.",
      }),
    ).toBe(true);
  });
});

describe("consensus estimate contracts", () => {
  const empty = {
    company_id: id,
    continuity_status: "NO_MAPPING",
    selected_provider_id: null,
    as_of: null,
    known_at: null,
    providers: [],
  };

  it("keeps missing consensus explicit instead of converting it to zero", () => {
    expect(isCompanyConsensusEstimates(empty)).toBe(true);
    expect(
      isCompanyConsensusEstimates({ ...empty, selected_provider_id: "fake" }),
    ).toBe(false);
  });

  it("accepts a flagged legacy baseline with unknown period, currency and coverage", () => {
    const observation = {
      id,
      company_id: id,
      listing_id: null,
      provider_mapping_id: id,
      provider_id: "legacy_workbook_estimates",
      metric: "REVENUE",
      period_type: "ANNUAL",
      forecast_period: "FY+1",
      period_end: null,
      value: "120.5",
      low_value: null,
      high_value: null,
      analyst_count: null,
      currency: null,
      unit: "CURRENCY",
      snapshot_date: "2026-09-12",
      observed_at: null,
      recorded_at: "2026-10-05T12:00:00Z",
      source_record_id: "EXPL:4:REVENUE:FY+1",
      source_ref: "workbook#Estimate History!D4",
      revision_context: "LEGACY_BASELINE",
      data_quality: "DATA_CHECK",
      quality_reason: "Currency and absolute fiscal period are unknown.",
      supersedes_observation_id: null,
    };
    const period = {
      metric: "REVENUE",
      period_type: "ANNUAL",
      forecast_period: "FY+1",
      period_end: null,
      currency: null,
      unit: "CURRENCY",
      current_observation: observation,
      history: [observation],
    };
    expect(
      isCompanyConsensusEstimates({
        ...empty,
        continuity_status: "FALLBACK_SELECTED",
        selected_provider_id: "legacy_workbook_estimates",
        providers: [
          {
            provider_id: "legacy_workbook_estimates",
            provider_symbol: "EXPL",
            role: "FALLBACK",
            priority: 1000,
            selected: true,
            mapping_status: "SELECTED",
            currency: null,
            currency_evidence_source: null,
            identity_evidence_source: "sha256:source#Estimate History",
            effective_from: "2026-09-12T00:00:00Z",
            freshness: "DATA_CHECK",
            latest_snapshot_date: "2026-09-12",
            latest_observed_at: null,
            observation_count: 1,
            missing_metrics: ["EPS"],
            periods: [period],
          },
        ],
      }),
    ).toBe(true);
  });
});

describe("temporal alignment contracts", () => {
  const emptyValue = {
    status: "NO_MATCHING_FISCAL_PERIOD",
    value: null,
    currency: null,
    unit: null,
    source_name: null,
    source_reference: null,
    source_observation_id: null,
    period_end: null,
    effective_at: null,
    observed_at: null,
    recorded_at: null,
    data_quality: null,
    quality_reason: null,
    low_value: null,
    high_value: null,
    analyst_count: null,
  };

  it("accepts explicit unavailable values without treating them as zero", () => {
    expect(
      isCompanyTemporalAlignment({
        company_id: id,
        metric: "REVENUE",
        fiscal_year: 2027,
        as_of: "2026-10-05",
        forecast_known_at: "2026-10-05T23:59:59.999999Z",
        outcome_known_at: "2026-10-05T23:59:59Z",
        horizon_days: 365,
        fiscal_year_mapping_basis: "NO_EXPLICIT_MODEL_FISCAL_YEAR_ANCHOR",
        comparison_status: "NO_MODEL_FORECAST",
        model_forecasts: [],
        consensus: emptyValue,
        actual: { ...emptyValue, status: "NOT_REPORTED" },
      }),
    ).toBe(true);
  });

  it("preserves a reported zero and rejects malformed point-in-time cutoffs", () => {
    const valid = {
      company_id: id,
      metric: "REVENUE",
      fiscal_year: 2027,
      as_of: "2026-10-05",
      forecast_known_at: "2026-10-05T23:59:59.999999Z",
      outcome_known_at: "2026-10-05T23:59:59Z",
      horizon_days: 365,
      fiscal_year_mapping_basis: "EXPLICIT_FIXTURE",
      comparison_status: "INCOMPLETE",
      model_forecasts: [],
      consensus: emptyValue,
      actual: { ...emptyValue, status: "NOT_REPORTED" },
    };
    expect(
      isCompanyTemporalAlignment({
        ...valid,
        actual: { ...valid.actual, value: "0" },
      }),
    ).toBe(true);
    expect(
      isCompanyTemporalAlignment({
        ...valid,
        forecast_known_at: "not-a-timestamp",
      }),
    ).toBe(false);
  });
});

describe("source document contracts", () => {
  it("accepts explicit unmapped and no-document coverage", () => {
    expect(
      isCompanySourceDocuments({
        company_id: id,
        sec_identity_status: "UNMAPPED",
        source_count: 0,
        as_of: null,
        known_at: null,
        documents: [],
      }),
    ).toBe(true);
  });

  it("requires secure source links and preserves retrieval and amendment metadata", () => {
    const document = {
      id,
      company_id: id,
      security_id: null,
      batch_id: null,
      provider_id: "company_source",
      source_name: "Issuer relations",
      source_jurisdiction: "GB",
      external_identifier: "annual-report-2025",
      document_type: "ANNUAL_REPORT",
      source_form: null,
      title: "Annual report 2025",
      reporting_period: "FY 2025",
      fiscal_year: 2025,
      fiscal_period: "FY",
      period_end: "2025-12-31",
      filed_at: null,
      published_at: "2026-02-20",
      canonical_url: "https://ir.example.test/reports/2025.pdf",
      retrieved_at: null,
      recorded_at: "2026-10-05T12:00:00Z",
      is_amendment: false,
      amends_document_id: null,
      supersedes_document_id: null,
      data_quality: "PASS",
      quality_reason: null,
      actor: "LOCAL_USER",
    };
    expect(
      isCompanySourceDocuments({
        company_id: id,
        sec_identity_status: "MAPPED",
        source_count: 1,
        as_of: null,
        known_at: null,
        documents: [document],
      }),
    ).toBe(true);
    expect(
      isCompanySourceDocuments({
        company_id: id,
        sec_identity_status: "MAPPED",
        source_count: 1,
        as_of: null,
        known_at: null,
        documents: [
          { ...document, canonical_url: "http://ir.example.test/report.pdf" },
        ],
      }),
    ).toBe(false);
  });
});
const modelOutput = {
  id,
  company_id: id,
  model_key: "P-EXAMPLE",
  snapshot_key: "CONTRACT:source-fingerprint",
  snapshot_kind: "CURRENT_CONTRACT",
  contract_version: "v1",
  contract_status: "PASS",
  output_quality: "PARTIAL",
  model_currency: null,
  currency_status: "UNKNOWN",
  currency_source_ref: null,
  model_status: null,
  effective_at: null,
  recorded_at: "2026-10-05T00:00:00Z",
  actor: "IMPORT",
  source: "Portfolio_Watchlist.xlsx:P-EXAMPLE!AZ3:BA20",
  source_revision_id: null,
  revision_source: null,
  revision_type: null,
  source_actor: null,
  rationale: null,
  evidence: null,
  notes: null,
  field_issues: [],
  bear_fv: "0",
  base_fv: null,
  bull_fv: null,
  bear_probability: null,
  base_probability: null,
  bull_probability: null,
  weighted_fv: null,
  weighted_upside: null,
  expected_cash_flow_irr: null,
  hurdle: null,
  expected_excess: null,
  forward_fundamental_cagr: null,
};
export const company = {
  id,
  name: "Example",
  reporting_currency: null,
  is_demo: true,
  created_at: "2026-10-04T00:00:00Z",
  lifecycle: null,
  lifecycle_event_id: null,
};
export const overview = {
  portfolio: {
    id,
    name: "Example portfolio",
    base_currency: "EUR",
    created_at: company.created_at,
    is_demo: true,
  },
  snapshot: null,
  target_revision: null,
  valuation_status: "NO_HOLDING_SNAPSHOT",
  base_market_value: null,
  valuation_currency: "EUR",
  cash_valuations: [],
  valuation_gaps: [],
  standalone_positions: [],
  companies: [
    {
      company,
      positions: [],
      target_weight: null,
      current_market_value: null,
      current_market_currency: null,
      current_weight: null,
      allocation_gap: null,
      allocation_status: "PORTFOLIO_TOTAL_UNAVAILABLE",
    },
  ],
};
const companyDetail = {
  company,
  securities: [],
  listings: [],
  lifecycle_history: [],
  portfolio: overview.portfolio,
  portfolio_context: overview.companies[0],
  holding_snapshot: null,
  positions: [],
  target_weight: null,
  target_revision_id: null,
};

const rankTypes = ["PORTFOLIO", "WATCHLIST", "RESEARCH"] as const;
const rankingCompany = { ...company, lifecycle: "WATCHLIST" as const };
const rankingCurrent = rankTypes.map((ranking_type, index) => {
  const definition = {
    id: `22222222-2222-4222-8222-22222222222${index}`,
    ranking_type,
    version: ranking_type === "WATCHLIST" ? 3 : 2,
    title: `${ranking_type} Rank`,
    methodology: "Documented, separate ranking methodology.",
    population_rule: "Explicit domain population.",
    required_inputs: "Domain-specific canonical inputs.",
    source_reference: "reference/workbook/Portfolio_Watchlist.xlsx",
    implementation_status: "READY",
    effective_from: company.created_at,
    status: "ACTIVE",
    recorded_at: company.created_at,
  };
  const run = {
    id: `33333333-3333-4333-8333-33333333333${index}`,
    definition,
    as_of: company.created_at,
    recorded_at: company.created_at,
    status: "PARTIAL",
    actor: "SYSTEM",
    reason: "Snapshot records input availability.",
    source: "fictional-test",
    company_count: 1,
    ranked_count: 0,
  };
  const entry = {
    id: `44444444-4444-4444-8444-44444444444${index}`,
    run_id: run.id,
    company_id: id,
    position: null,
    status: index === 1 ? "DATA_CHECK" : "INPUTS_UNAVAILABLE",
    reason: "Required ranking inputs are unavailable.",
  };
  return { definition, run, entry };
});
const companyRankings = {
  current: rankingCurrent,
  history: rankingCurrent.map(({ run, entry }) => ({ run, entry })),
};

describe("domain display integrity", () => {
  it("preserves native, output-only, unsupported and missing model states", () => {
    const item = {
      model_key: "P-EXAMPLE",
      company_name: "Example",
      canonical_ticker: "EX",
      lifecycle: "PORTFOLIO",
      methodology_family: "UFCF_DCF_10Y_FADE",
      model_currency: "USD",
      inventory_status: "READY_FOR_NATIVE_IMPORT",
      representation_status: "NATIVE_EDITABLE",
      output_snapshot_available: false,
      output_contract_status: "PASS",
      native_model_id: id,
      native_revision_number: 1,
      parity_status: "PARITY_PASS",
      projections_compared: 30,
      projections_passed: 30,
      outputs_compared: 22,
      outputs_passed: 22,
      blockers: [],
      legacy_return_semantics: "Legacy enterprise cash-flow return.",
    };
    const result = {
      company_id: id,
      inventory_available: true,
      models: [item],
    };
    expect(isCompanyFinancialModelMigration(result)).toBe(true);
    for (const status of [
      "IMPORTED_OUTPUT_ONLY",
      "UNSUPPORTED_LEGACY",
      "LEGACY_ONLY",
      "NOT_IMPORTED",
      "NATIVE_WITH_PARITY_ISSUE",
    ]) {
      expect(
        isCompanyFinancialModelMigration({
          ...result,
          models: [
            {
              ...item,
              representation_status: status,
              native_model_id: status.startsWith("NATIVE") ? id : null,
              native_revision_number: status.startsWith("NATIVE") ? 1 : null,
            },
          ],
        }),
      ).toBe(true);
    }
    expect(
      isCompanyFinancialModelMigration({
        ...result,
        models: [{ ...item, native_revision_number: 0 }],
      }),
    ).toBe(false);
    expect(
      isCompanyFinancialModelMigration({
        ...result,
        models: [{ ...item, output_snapshot_available: null }],
      }),
    ).toBe(false);
  });

  it("retains unknown quantities and exactly observed zero and large decimal quantities", () => {
    expect(quantity(null)).toBe("Unknown");
    expect(quantity("0.0000000000")).toBe("0");
    expect(quantity("123456789012345678.1234567890")).toBe(
      "123456789012345678.123456789",
    );
    expect(percent(null)).toBe("No target");
    expect(percent("0.000000000000")).toBe("0%");
    expect(percent("0.000000000001")).not.toBe("0%");
  });
  it("allows an identity without lifecycle and refuses an invented lifecycle value", () => {
    expect(isCompany(company)).toBe(true);
    expect(isCompany({ ...company, lifecycle: "OWNED" })).toBe(false);
  });
  it("accepts explicit missing valuation fields and preserves a zero target", () => {
    expect(isOverview(overview)).toBe(true);
    expect(
      isOverview({
        ...overview,
        companies: [{ ...overview.companies[0], target_weight: "0" }],
      }),
    ).toBe(true);
  });
  it("retains backend-emitted company allocation and missing coverage states", () => {
    expect(isDetail(companyDetail)).toBe(true);
    expect(
      isDetail({
        ...companyDetail,
        portfolio_context: {
          ...companyDetail.portfolio_context,
          current_weight: "0",
          allocation_gap: "0",
          allocation_status: "VALUED",
        },
      }),
    ).toBe(true);
    expect(
      isDetail({
        ...companyDetail,
        portfolio_context: {
          ...companyDetail.portfolio_context,
          current_weight: undefined,
        },
      }),
    ).toBe(false);
    expect(
      isDetail({ ...companyDetail, portfolio_context: null, portfolio: null }),
    ).toBe(true);
  });
  it("accepts signed backend allocation gaps without changing their sign", () => {
    const allocation = {
      ...overview.companies[0],
      target_weight: "0.15",
      current_market_value: "20",
      current_market_currency: "EUR",
      current_weight: "0.2",
      allocation_gap: "-0.05",
      allocation_status: "VALUED",
    };
    expect(
      isOverview({
        ...overview,
        valuation_status: "VALUED",
        base_market_value: "100",
        companies: [allocation],
      }),
    ).toBe(true);
    expect(
      isDetail({
        ...companyDetail,
        target_weight: allocation.target_weight,
        portfolio_context: allocation,
      }),
    ).toBe(true);
  });
  it("rejects an omitted current market weight while accepting explicit zero", () => {
    expect(
      isOverview({
        ...overview,
        companies: [{ ...overview.companies[0], current_weight: undefined }],
      }),
    ).toBe(false);
    expect(
      isOverview({
        ...overview,
        valuation_status: "VALUED",
        base_market_value: "100",
        companies: [
          {
            ...overview.companies[0],
            current_market_value: "0",
            current_market_currency: "EUR",
            current_weight: "0",
            allocation_status: "VALUED",
          },
        ],
      }),
    ).toBe(true);
  });
  it("keeps missing and stale listing prices explicit instead of numeric", () => {
    const missingListing = {
      id,
      security_id: id,
      ticker: "EXAMPLE",
      venue: "NYSE",
      currency: "USD",
      is_demo: false,
    };
    expect(
      isListingMarketData({
        listing: missingListing,
        latest: null,
        freshness: "NO_DATA",
        age_days: null,
        price_regime: null,
        history: [],
      }),
    ).toBe(true);
    expect(
      isListingMarketData({
        listing: missingListing,
        latest: null,
        freshness: "FRESH",
        age_days: 0,
        price_regime: null,
        history: [],
      }),
    ).toBe(false);
  });
  it("preserves separate explicit ranking states without inventing a rank", () => {
    expect(isCompanyRankings(companyRankings)).toBe(true);
    expect(
      isUniverseRankingSummary([
        { company: rankingCompany, rankings: rankingCurrent },
      ]),
    ).toBe(true);
    const fabricatedZero = {
      ...companyRankings,
      current: companyRankings.current.map((ranking, index) =>
        index === 0
          ? {
              ...ranking,
              entry: { ...ranking.entry, status: "RANKED", position: 0 },
            }
          : ranking,
      ),
    };
    expect(isCompanyRankings(fabricatedZero)).toBe(false);
  });
  it("accepts Watchlist Rank data-checks with source and missing-score context", () => {
    const run = companyRankings.current.find(
      (item) => item.definition.ranking_type === "WATCHLIST",
    );
    if (!run?.run || !run.entry)
      throw new Error("ranking fixture is incomplete");
    const entry = {
      ...run.entry,
      status: "DATA_CHECK",
      position: null,
      reason: "Native and legacy return semantics are not mixed.",
      input_snapshot: {
        context_version: "watchlist-rank-inputs-v1",
        expected_irr: "0.12",
        return_semantics: "LEGACY_NORMALIZED_FIELD",
        return_source: {
          source_kind: "IMPORTED_CURRENT_CONTRACT",
          record_id: id,
          model_id: null,
          revision_id: null,
          revision_number: null,
          model_key: "P-EXAMPLE",
          model_type: null,
          methodology_version: null,
          contract_version: "1.0.0",
          source_revision_id: "legacy-1",
          source: "Workbook fixture",
          effective_at: null,
          recorded_at: company.created_at,
          effective_time_status: "UNKNOWN",
          model_currency: "USD",
          currency_status: "DOCUMENTED",
          output_quality: "COMPLETE",
          contract_status: "PASS",
          price_status: null,
          price_effective_at: null,
          price_observation_id: null,
          listing_id: id,
          listing_ticker: "EX",
          listing_venue: "TEST-X",
          migration_status: null,
        },
        durability_10y: {
          score: null,
          status: "NOT_ASSESSED",
          assessment_id: null,
          effective_at: null,
          recorded_at: null,
          rationale: null,
          source: null,
        },
        compounder_quality: {
          score: null,
          status: "NOT_ASSESSED",
          assessment_id: null,
          effective_at: null,
          recorded_at: null,
          rationale: null,
          source: null,
        },
        forward_fundamental_cagr: null,
        weighted_fair_value: "20",
        hurdle: "0.09",
        expected_excess: "0.03",
        decision_context: "QUALITY_GATE_THRESHOLDS_NOT_DOCUMENTED",
        context_note: "Missing context remains explicit.",
      },
    };
    const withContext = {
      ...companyRankings,
      current: companyRankings.current.map((item) =>
        item.definition.ranking_type === "WATCHLIST"
          ? { ...item, entry }
          : item,
      ),
      history: companyRankings.history.map((item) =>
        item.run.definition.ranking_type === "WATCHLIST"
          ? { ...item, entry }
          : item,
      ),
    };
    expect(isCompanyRankings(withContext)).toBe(true);
  });
  it("keeps a real zero model output distinct from an unavailable output", () => {
    expect(isModelOutputSnapshot(modelOutput)).toBe(true);
    expect(isModelOutputSnapshot({ ...modelOutput, bear_fv: null })).toBe(true);
    expect(isModelOutputSnapshot({ ...modelOutput, bear_fv: undefined })).toBe(
      false,
    );
  });
  it("keeps price-dependent model outputs unavailable without a fresh comparable quote", () => {
    const partial = {
      id,
      revision_id: id,
      status: "PARTIAL",
      model_currency: "USD",
      price_observation_id: null,
      current_price: null,
      price_effective_at: null,
      price_status: "NO_DATA",
      price_unavailable_reason: "No listing price observation is available.",
      irr_unavailable_reason: "No listing price observation is available.",
      bear_fv: "10",
      base_fv: "20",
      bull_fv: "30",
      bear_probability: "0.2",
      base_probability: "0.6",
      bull_probability: "0.2",
      weighted_fv: "20",
      weighted_upside: null,
      expected_cash_flow_irr: null,
      hurdle: "0.09",
      expected_excess: null,
      forward_fundamental_cagr: null,
    };
    expect(isFinancialModelOutputs(partial)).toBe(true);
    expect(
      isFinancialModelOutputs({
        ...partial,
        status: "COMPLETE",
        weighted_upside: "0.1",
      }),
    ).toBe(false);
  });

  it("accepts a portable model contract, rejects unsupported versions and preserves missing quote state", () => {
    const revisionId = "22222222-2222-4222-8222-222222222222";
    const scenarioIds = [
      "33333333-3333-4333-8333-333333333331",
      "33333333-3333-4333-8333-333333333332",
      "33333333-3333-4333-8333-333333333333",
    ];
    const output = {
      id: "44444444-4444-4444-8444-444444444444",
      revision_id: revisionId,
      status: "PARTIAL",
      model_currency: "USD",
      price_observation_id: null,
      current_price: null,
      price_effective_at: null,
      price_status: "NO_DATA",
      price_unavailable_reason: "No comparable quote is available.",
      irr_unavailable_reason: "No comparable quote is available.",
      bear_fv: "10",
      base_fv: "20",
      bull_fv: "30",
      bear_probability: "0.2",
      base_probability: "0.6",
      bull_probability: "0.2",
      weighted_fv: "20",
      weighted_upside: null,
      expected_cash_flow_irr: null,
      hurdle: "0.09",
      expected_excess: null,
      forward_fundamental_cagr: null,
    };
    const contract = {
      contract_version: "1.0.0",
      exported_at: "2026-10-05T00:00:00Z",
      model: {
        model_id: "66666666-6666-4666-8666-666666666666",
        company_id: id,
        model_type: "UFCF_DCF_10Y_FADE",
        model_name: "Example DCF",
        valuation_listing_id: "77777777-7777-4777-8777-777777777777",
        valuation_listing: {
          id: "77777777-7777-4777-8777-777777777777",
          security_id: "88888888-8888-4888-8888-888888888888",
          venue: "NASDAQ",
          ticker: "EXM",
          currency: "USD",
          is_demo: true,
        },
        model_currency: "USD",
        source_model_key: null,
      },
      base_revision: {
        revision_id: revisionId,
        revision_number: 1,
        methodology_version: "ufcf-dcf-fade-v1",
      },
      candidate_revision: {
        source_revision_id: "google-sheets:example-1",
        actor: "IMPORT",
        source: "Google Sheets portable contract",
        rationale: "Reviewed the scenario assumptions.",
        effective_at: "2026-10-05T00:00:00Z",
        base: {
          base_revenue: "100",
          base_ebit_margin: "0.2",
          base_tax_rate: "0.25",
          base_da_to_revenue: "0.03",
          base_capex_to_revenue: "0.02",
          base_nwc_to_revenue: "0.04",
          net_cash_debt: "-5",
          diluted_shares: "10",
        },
        scenarios: (["BEAR", "BASE", "BULL"] as const).map((scenario) => ({
          scenario,
          probability: scenario === "BASE" ? "0.6" : "0.2",
          terminal_growth: "0.025",
          year10_ufcf_growth: "0.04",
          rationale: `${scenario} case`,
          years: Array.from({ length: 5 }, (_, index) => ({
            forecast_year: index + 1,
            revenue_growth: "0.1",
            ebit_margin: "0.2",
            tax_rate: "0.25",
            da_to_revenue: "0.03",
            capex_to_revenue: "0.02",
            nwc_to_revenue: "0.04",
            discount_rate: "0.09",
          })),
        })),
      },
      base_calculation: {
        revision_id: revisionId,
        outputs: output,
        projections: scenarioIds.flatMap((scenario_id) =>
          Array.from({ length: 10 }, (_, index) => {
            const forecast_year = index + 1;
            const detailed = forecast_year <= 5;
            return {
              id: "55555555-5555-4555-8555-555555555555",
              scenario_id,
              forecast_year,
              revenue: detailed ? "100" : null,
              ebit: detailed ? "20" : null,
              nopat: detailed ? "15" : null,
              depreciation_amortization: detailed ? "3" : null,
              capex: detailed ? "2" : null,
              net_working_capital: detailed ? "4" : null,
              change_in_nwc: detailed ? "1" : null,
              unlevered_free_cash_flow: "15",
              revenue_growth: "0.1",
              discount_rate: "0.09",
              discount_factor: "0.65",
              present_value_ufcf: "10",
              terminal_value: forecast_year === 10 ? "100" : null,
            };
          }),
        ),
      },
    };

    expect(isFinancialModelContract(contract)).toBe(true);
    expect(
      isFinancialModelContract({ ...contract, contract_version: "2.0.0" }),
    ).toBe(false);
    const invalidEdit = structuredClone(contract);
    invalidEdit.candidate_revision.scenarios[1].years[0].revenue_growth = "NaN";
    expect(isFinancialModelContract(invalidEdit)).toBe(false);
  });

  it("keeps a portable-contract conflict and unavailable outputs explicit", () => {
    const summary = {
      status: "PARTIAL",
      model_currency: "USD",
      price_status: "NO_DATA",
      current_price: null,
      price_effective_at: null,
      price_unavailable_reason: "No comparable quote is available.",
      bear_fv: "10",
      base_fv: "20",
      bull_fv: "30",
      weighted_fv: "20",
      weighted_upside: null,
      expected_cash_flow_irr: null,
      hurdle: "0.09",
      expected_excess: null,
      irr_unavailable_reason: "No comparable quote is available.",
    };
    expect(
      isFinancialModelContractPreview({
        status: "CONFLICT",
        model_id: id,
        base_revision_id: id,
        current_revision_id: "22222222-2222-4222-8222-222222222222",
        current_revision_number: 2,
        source_revision_id: "google-sheets:example-1",
        actor: "IMPORT",
        source: "Google Sheets portable contract",
        effective_at: "2026-10-05T00:00:00Z",
        proposed_revision_number: null,
        already_imported_revision_id: null,
        reason: "The application has advanced.",
        changes: [],
        output_changes: [],
        current_outputs: summary,
        calculated_outputs: null,
      }),
    ).toBe(true);
  });

  it("validates draft calculations, explicit missing outputs, and all scenario projections", () => {
    const outputs = {
      status: "PARTIAL",
      model_currency: "USD",
      price_observation_id: null,
      current_price: null,
      price_effective_at: null,
      price_status: "NO_DATA",
      price_unavailable_reason: "No comparable quote is available.",
      irr_unavailable_reason: "A fresh comparable price is required.",
      bear_fv: "10",
      base_fv: "20",
      bull_fv: "30",
      bear_probability: "0.2",
      base_probability: "0.6",
      bull_probability: "0.2",
      weighted_fv: "20",
      weighted_upside: null,
      expected_cash_flow_irr: null,
      hurdle: "0.09",
      expected_excess: null,
      forward_fundamental_cagr: null,
    };
    const projections = (["BEAR", "BASE", "BULL"] as const).flatMap(
      (scenario) =>
        Array.from({ length: 10 }, (_, index) => {
          const forecast_year = index + 1;
          const detailed = forecast_year <= 5;
          return {
            scenario,
            forecast_year,
            revenue: detailed ? "110" : null,
            ebit: detailed ? "22" : null,
            nopat: detailed ? "16.5" : null,
            depreciation_amortization: detailed ? "3.3" : null,
            capex: detailed ? "2.2" : null,
            net_working_capital: detailed ? "4.4" : null,
            change_in_nwc: detailed ? "0.4" : null,
            unlevered_free_cash_flow: "17.2",
            revenue_growth: "0.1",
            discount_rate: "0.09",
            discount_factor: "0.65",
            present_value_ufcf: "11.18",
            terminal_value: forecast_year === 10 ? "100" : null,
          };
        }),
    );
    const preview = {
      model_id: id,
      base_revision_id: id,
      current_revision_id: id,
      current_revision_number: 1,
      model_currency: "USD",
      outputs,
      projections,
    };

    expect(isFinancialModelCalculationPreview(preview)).toBe(true);
    expect(
      isFinancialModelCalculationPreview({
        ...preview,
        model_id: null,
      }),
    ).toBe(false);
    expect(
      isFinancialModelCalculationPreview({
        ...preview,
        projections: projections.slice(1),
      }),
    ).toBe(false);
    expect(
      isFinancialModelCalculationPreview({
        ...preview,
        outputs: { ...outputs, weighted_upside: "missing" },
      }),
    ).toBe(false);
  });

  it("validates method-specific v2 contracts and preserves unavailable return outputs", () => {
    const ownerInput = {
      base: {
        base_revenue: "6.153",
        net_cash: "1.713",
        diluted_shares: "0.596",
      },
      scenarios: (["BEAR", "BASE", "BULL"] as const).map((scenario) => ({
        scenario,
        probability: scenario === "BASE" ? "0.6" : "0.2",
        required_return: "0.1",
        terminal_growth: "0.03",
        rationale: `${scenario} case`,
        years: Array.from({ length: 10 }, (_, index) => ({
          forecast_year: index + 1,
          revenue_growth: "0.1",
          owner_cash_flow_margin: "0.05",
        })),
      })),
    };
    const contract = {
      contract_version: "2.0.0",
      exported_at: "2026-10-05T00:00:00Z",
      model_id: id,
      company_id: id,
      model_type: "OWNER_CASH_FLOW_10Y",
      model_name: "Example owner cash flow",
      valuation_listing_id: id,
      model_currency: "USD",
      source_model_key: "W-TOST",
      base_revision_id: id,
      base_revision_number: 1,
      candidate_revision: {
        source_revision_id: "sheet-1",
        actor: "IMPORT",
        source: "Google Sheets v2",
        rationale: "Reviewed the owner-cash-flow assumptions.",
        effective_at: "2026-10-05T00:00:00Z",
        owner_cash_flow: ownerInput,
        residual_income: null,
      },
    };
    expect(isAdditionalModelPortableContractResponse(contract)).toBe(true);
    const invalid = structuredClone(contract);
    invalid.candidate_revision.owner_cash_flow.scenarios[0].years.pop();
    expect(isAdditionalModelPortableContractResponse(invalid)).toBe(false);

    const partialOutputs = {
      status: "PARTIAL",
      model_currency: "USD",
      price_observation_id: null,
      current_price: null,
      price_effective_at: null,
      price_status: "NO_DATA",
      price_unavailable_reason: "No comparable listing price is available.",
      irr_unavailable_reason: "No comparable listing price is available.",
      bear_fv: "16.29",
      base_fv: "42.98",
      bull_fv: "125.57",
      bear_probability: "0.2",
      base_probability: "0.6",
      bull_probability: "0.2",
      weighted_fv: "54.16",
      weighted_upside: null,
      expected_cash_flow_irr: null,
      hurdle: "0.0975",
      expected_excess: null,
      forward_fundamental_cagr: null,
    };
    expect(
      isAdditionalModelContractPreview({
        status: "READY",
        model_id: id,
        base_revision_id: id,
        current_revision_id: id,
        current_revision_number: 1,
        source_revision_id: "sheet-1",
        changes: [
          {
            path: "owner_cash_flow.base.base_revenue",
            previous: "6.1",
            proposed: "6.2",
          },
        ],
        output_changes: [],
        current_outputs: partialOutputs,
        calculated_outputs: partialOutputs,
        reason: null,
      }),
    ).toBe(true);
    expect(isExtendedFinancialModels([])).toBe(true);
  });

  it("keeps missing Estimate Momentum explicit instead of accepting a neutral score", () => {
    const missingSignal = {
      company_id: id,
      methodology_version: "legacy-estimate-momentum-v2-partial-1",
      availability: "INSUFFICIENT_HISTORY",
      direction: null,
      raw_score: null,
      confidence_adjusted_score: null,
      confidence: "0",
      confidence_band: "NO_DATA",
      coverage_fraction: "0",
      coverage_count: 0,
      coverage_total: 20,
      freshness: "NO_DATA",
      data_quality: "NO_DATA",
      provider_id: "fmp_estimates",
      latest_snapshot_date: null,
      as_of: "2026-10-05",
      known_at: null,
      reason:
        "No same-provider point-in-time reference comparison is available.",
      periods: [],
    };
    expect(isCompanyEstimateMomentum(missingSignal)).toBe(true);
    expect(
      isCompanyEstimateMomentum({ ...missingSignal, direction: "NEUTRAL" }),
    ).toBe(false);
    expect(
      isCompanyEstimateMomentum({ ...missingSignal, raw_score: "0" }),
    ).toBe(false);
  });

  it("accepts an undated attention review without coercing missing values", () => {
    const event = {
      id: "model_output_coverage:missing",
      company_id: id,
      company_name: "Example business",
      lifecycle: "PORTFOLIO",
      event_type: "DATA_QUALITY",
      severity: "LOW",
      status: "REVIEW",
      title: "No complete normalized model output",
      explanation: "No model output is available.",
      effective_at: null,
      time_precision: "UNKNOWN",
      recorded_at: null,
      source_domain: "model_output_coverage",
      source_id: "missing",
      source_reference: null,
      href: `/company/${id}`,
      prior_value: null,
      current_value: null,
      unit: null,
    };
    expect(
      isAttentionFeed({
        as_of: "2026-10-05T12:00:00Z",
        lookback_days: 30,
        total: 1,
        events: [event],
      }),
    ).toBe(true);
    expect(
      isAttentionFeed({
        as_of: "2026-10-05T12:00:00Z",
        lookback_days: 30,
        total: 1,
        events: [
          {
            ...event,
            effective_at: "2026-10-05T12:00:00Z",
            time_precision: "UNKNOWN",
          },
        ],
      }),
    ).toBe(false);
  });
});
