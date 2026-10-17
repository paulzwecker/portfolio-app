import { describe, expect, it } from "vitest";
import {
  buildHistoricalTimelineEvents,
  comparableExpectationPoints,
  expectedReturnLabel,
  filterByHistoricalRange,
} from "./company-historical-analysis-workspace";
import type { ExpectedReturnHistoryPoint } from "@/lib/domain-contracts";

const point = (overrides: Partial<ExpectedReturnHistoryPoint> = {}) =>
  ({
    point_id: "point-1",
    source_kind: "NATIVE_MODEL_REVISION",
    event_status: "DATED",
    effective_at: "2026-10-15T12:00:00Z",
    recorded_at: "2026-10-15T12:01:00Z",
    series_id: "native:model-1",
    model_key: "MODEL-1",
    model_id: null,
    revision_id: null,
    revision_number: 1,
    model_type: "UFCF_DCF_10Y_FADE",
    methodology_version: "ufcf-v1",
    model_label: "Operating DCF",
    model_currency: "USD",
    currency_status: "DOCUMENTED",
    valuation_listing_id: "listing-1",
    valuation_ticker: "EXM",
    valuation_venue: "NASDAQ",
    valuation_listing_currency: "USD",
    is_current_at_cutoff: true,
    output_status: "COMPLETE",
    output_quality: "COMPLETE",
    contract_status: null,
    return_semantics: "NATIVE_METHOD_OUTPUT",
    return_methodology: null,
    return_methodology_status: "CLASSIFIED",
    share_price_basis_status: "CAPTURED",
    actor: "LOCAL_USER",
    source_actor: null,
    revision_source: "web",
    revision_type: null,
    bear_fv: "80",
    base_fv: "100",
    bull_fv: "120",
    bear_probability: "0.2",
    base_probability: "0.6",
    bull_probability: "0.2",
    weighted_fv: "100",
    weighted_upside: "0.2",
    expected_cash_flow_irr: "0.15",
    hurdle: "0.1",
    expected_excess: "0.05",
    forward_fundamental_cagr: "0.1",
    market_price: {
      status: "AVAILABLE",
      listing_id: "listing-1",
      ticker: "EXM",
      venue: "NASDAQ",
      listing_currency: "USD",
      quote: "83",
      quote_currency: "USD",
      model_reference_price: null,
      model_currency: "USD",
      effective_at: "2026-10-15T11:00:00Z",
      observed_at: "2026-10-15T11:01:00Z",
      recorded_at: "2026-10-15T11:02:00Z",
      provider: "fixture",
      adjustment_basis: "SPLIT_ADJUSTED",
      observation_id: null,
      source_ref: "fixture",
      reason: null,
    },
    estimate_context: {
      status: "UNAVAILABLE",
      provider_id: null,
      periods: [],
    },
    source: "fixture",
    source_revision_id: null,
    rationale: "Test point",
    evidence: null,
    ...overrides,
  }) as ExpectedReturnHistoryPoint;

describe("company historical analysis", () => {
  it("keeps historical return labels aligned with the canonical perspective", () => {
    expect(expectedReturnLabel("EQUITY")).toBe("Expected shareholder return");
    expect(expectedReturnLabel("ENTERPRISE")).toBe(
      "Expected enterprise return",
    );
    expect(expectedReturnLabel("UNCLASSIFIED")).toBe("Expected return");
  });

  it("filters dated records by the latest available record while retaining undated records", () => {
    const values = [
      { id: "old", date: "2025-01-01T00:00:00Z" },
      { id: "new", date: "2026-10-15T00:00:00Z" },
      { id: "unknown", date: null },
    ];
    expect(
      filterByHistoricalRange(values, "1Y", (value) => value.date).map(
        (value) => value.id,
      ),
    ).toEqual(["new", "unknown"]);
    expect(
      filterByHistoricalRange(values, "ALL", (value) => value.date),
    ).toHaveLength(3);
  });

  it("only compares fair value with a same-listing, same-currency price known by the model event", () => {
    const compatible = point();
    const laterPrice = point({
      point_id: "later",
      market_price: {
        ...compatible.market_price,
        effective_at: "2026-10-16T12:00:00Z",
      },
    });
    const wrongCurrency = point({
      point_id: "currency",
      market_price: { ...compatible.market_price, quote_currency: "EUR" },
    });
    expect(
      comparableExpectationPoints([compatible, laterPrice, wrongCurrency]),
    ).toEqual([compatible]);
  });

  it("does not use an accepted model reference price when no canonical quote is available", () => {
    const missingQuote = point({
      market_price: {
        ...point().market_price,
        quote: null,
        model_reference_price: "83",
        status: "NO_DATA",
      },
    });
    expect(comparableExpectationPoints([missingQuote])).toEqual([]);
  });

  it("builds separate model, estimate, ranking, execution and thesis events", () => {
    const events = buildHistoricalTimelineEvents({
      expectedReturn: {
        company_id: "company-1",
        as_of: "2026-10-17",
        known_at: "2026-10-17T12:00:00Z",
        status: "AVAILABLE",
        history: [point()],
        current_calculations: [],
      },
      momentum: {
        company_id: "company-1",
        methodology_version: "momentum-v1",
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
        provider_id: null,
        latest_snapshot_date: null,
        as_of: "2026-10-17",
        known_at: null,
        reason: "No estimate history",
        periods: [],
      },
    });
    expect(events.map((event) => event.kind)).toEqual(["ESTIMATE", "MODEL"]);
    expect(events[1].detail).toContain("Native method output");
  });
});
