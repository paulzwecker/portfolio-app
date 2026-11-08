import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { dateOnly } from "@/lib/display";
import type {
  ListingMarketData,
  PriceHistoryAnalytics,
} from "@/lib/domain-contracts";
import {
  HistoryCoverageNotice,
  HistorySourceReview,
  PriceObservationReview,
  PriceHistoryChart,
  filterPriceObservations,
} from "./company-historical-analysis-workspace";

describe("historical market coverage notice", () => {
  it("warns that a long sparse history is not proof of complete sessions", () => {
    const analytics = {
      session_coverage: "NOT_ASSESSED",
      distinct_market_dates: 2,
      first_market_date: "2024-01-01",
      max_calendar_gap_days: 366,
    } as PriceHistoryAnalytics;
    const html = renderToStaticMarkup(
      <HistoryCoverageNotice analytics={analytics} />,
    );
    expect(html).toContain("coverage has not been assessed");
    expect(html).toContain("may span missing sessions");
    expect(html).toContain("2 distinct market dates");
    expect(html).toContain("largest calendar gap 366 days");
    expect(html).toContain("weekends and holidays");
  });

  it("keeps older API responses unknown and represents explicit zero", () => {
    const legacy = renderToStaticMarkup(
      <HistoryCoverageNotice analytics={{} as PriceHistoryAnalytics} />,
    );
    expect(legacy).toContain("coverage has not been assessed");
    expect(legacy).not.toContain("0 distinct market dates");
    const empty = renderToStaticMarkup(
      <HistoryCoverageNotice
        analytics={{ distinct_market_dates: 0 } as PriceHistoryAnalytics}
      />,
    );
    expect(empty).toContain("0 distinct market dates");
  });

  it("hides the chart and explains incompatible inputs", () => {
    const analytics = {
      input_issues: ["MULTIPLE_SOURCE_STREAMS", "DUPLICATE_MARKET_DATE"],
    } as PriceHistoryAnalytics;
    const notice = renderToStaticMarkup(
      <HistoryCoverageNotice analytics={analytics} />,
    );
    expect(notice).toContain("different provider, symbol or currency");
    expect(notice).toContain("duplicate market dates");
    const chart = renderToStaticMarkup(
      <PriceHistoryChart
        market={{ analytics } as ListingMarketData}
        observations={[]}
      />,
    );
    expect(chart).toContain("Price series needs review");
    expect(chart).not.toContain('role="img"');
  });

  it("discloses the source streams and duplicate dates without inventing prices", () => {
    const analytics = {
      input_issues: ["MULTIPLE_SOURCE_STREAMS", "DUPLICATE_MARKET_DATE"],
      source_streams: [
        {
          provider: "Example",
          provider_symbol: "EXM.X",
          currency: "EUR",
          observation_count: 2,
          first_market_date: "2026-01-01",
          last_market_date: "2026-01-03",
        },
        {
          provider: "Other",
          provider_symbol: "EXM",
          currency: "EUR",
          observation_count: 1,
          first_market_date: "2026-01-03",
          last_market_date: "2026-01-03",
        },
      ],
      duplicate_market_dates: ["2026-01-03"],
    } as PriceHistoryAnalytics;
    const html = renderToStaticMarkup(
      <HistorySourceReview analytics={analytics} />,
    );
    expect(html).toContain("Review conflicting history inputs");
    expect(html).toContain("Example");
    expect(html).toContain("EXM.X");
    expect(html).toContain("2 recorded closes");
    expect(html).toContain("Duplicate market dates");
    expect(html).toContain("other provider records may exist");
    expect(
      renderToStaticMarkup(
        <HistorySourceReview
          analytics={
            {
              input_issues: ["MULTIPLE_SOURCE_STREAMS"],
            } as PriceHistoryAnalytics
          }
        />,
      ),
    ).toBe("");
  });

  it("explains differing and unavailable adjustment evidence", () => {
    const analytics = {
      input_issues: [
        "ADJUSTMENT_BASIS_MISMATCH",
        "ADJUSTMENT_BASIS_UNVERIFIED",
      ],
      source_streams: [
        {
          provider: "Example",
          provider_symbol: "EXM",
          currency: "EUR",
          adjustment_basis: "Split adjusted",
          observation_count: 1,
          first_market_date: "2026-01-01",
          last_market_date: "2026-01-01",
        },
        {
          provider: "Example",
          provider_symbol: "EXM",
          currency: "EUR",
          adjustment_basis: null,
          observation_count: 1,
          first_market_date: "2026-01-02",
          last_market_date: "2026-01-02",
        },
      ],
    } as PriceHistoryAnalytics;
    const notice = renderToStaticMarkup(
      <HistoryCoverageNotice analytics={analytics} />,
    );
    const review = renderToStaticMarkup(
      <HistorySourceReview analytics={analytics} />,
    );
    expect(notice).toContain("price adjustment descriptions differ");
    expect(notice).toContain("price adjustment description is unavailable");
    expect(review).toContain("Split adjusted");
    expect(review).toContain("Adjustment: Unavailable");
  });

  it("shows the bounded published schedule as review evidence, not confirmed missing trades", () => {
    const analytics = {
      scheduled_session_review: {
        venue: "NYSE",
        schedule_id: "NYSE-2026-asof-2025-12-10-observed-2026-11-08-v1",
        source_url:
          "https://www.nyse.com/publicdocs/nyse/ICE_NYSE_2026_Yearly_Trading_Calendar.pdf",
        source_as_of: "2025-12-10",
        source_observed_at: "2026-11-08T18:37:45.016120Z",
        source_sha256:
          "70f5577eb43e60a9dbbecaae3cec23d0f02028c05c7f175013bb3e97816d394f",
        start_date: "2026-07-02",
        end_date: "2026-07-07",
        full_selected_span_covered: false,
        scheduled_count: 3,
        absent_scheduled_dates: ["2026-07-06"],
        selected_unscheduled_dates: ["2026-07-03"],
      },
    } as PriceHistoryAnalytics;
    const html = renderToStaticMarkup(
      <HistoryCoverageNotice analytics={analytics} />,
    );
    expect(html).toContain("1 without selected closes");
    expect(html).toContain("covers only part of the selected date span");
    expect(html).toContain("not a confirmed missing trade");
    expect(html).toContain(dateOnly("2026-07-06"));
    expect(html).toContain(dateOnly("2026-07-03"));
  });

  it("labels Nasdaq evidence without inventing a calendar as-of date", () => {
    const analytics = {
      status: "PARTIAL",
      methodology_version: "fixture",
      observation_count: 2,
      as_of: null,
      session_coverage: "NOT_ASSESSED",
      daily_return: null,
      dma_20: null,
      dma_50: null,
      dma_200: null,
      high_52w: null,
      drawdown_52w: null,
      price_return_1m: null,
      price_return_3m: null,
      price_return_6m: null,
      realized_vol_20d: null,
      trend_state: null,
      correction_state: null,
      scheduled_session_review: {
        venue: "NASDAQ",
        schedule_id: "NASDAQ-2026-observed-2026-11-08-v1",
        source_url: "https://nasdaqtrader.com/Trader.aspx?id=Calendar",
        source_sha256:
          "33e2c294b3959430f9b4edbbbb0e6c5ed832ca6da30a3ea0de53748857e6698f",
        source_as_of: null,
        source_observed_at: "2026-11-08T18:37:45.961889Z",
        start_date: "2026-07-02",
        end_date: "2026-07-07",
        full_selected_span_covered: true,
        scheduled_count: 3,
        absent_scheduled_dates: ["2026-07-06"],
        selected_unscheduled_dates: [],
      },
    } satisfies PriceHistoryAnalytics;
    const html = renderToStaticMarkup(
      <HistoryCoverageNotice analytics={analytics} />,
    );
    expect(html).toContain("Review scheduled NASDAQ dates");
    expect(html).toContain("Calendar as-of date:");
    expect(html).toContain("not stated");
    expect(html).toContain("Published NASDAQ calendar");
  });

  it("filters all returned observations and keeps exact close text", () => {
    const observations = Array.from({ length: 75 }, (_, index) => ({
      id: String(index),
      market_date: new Date(Date.UTC(2026, 9, 4 - index * 2)).toISOString(),
      observed_at: null,
      recorded_at: "2026-10-04T00:00:00Z",
      split_adjusted_close:
        index === 74 ? "41.1234567890" : index === 73 ? null : "0.0000000000",
      provider: index === 74 ? "Alternate" : "Primary",
      provider_symbol: index === 74 ? "EXPL.A" : "EXPL",
      currency: "USD",
      data_quality: "PASS",
      adjustment_basis: "split adjusted",
      source_ref: "fixture",
    })) as ListingMarketData["history"];
    expect(filterPriceObservations(observations, "  expl.a  ")).toEqual([
      observations[74],
    ]);
    expect(filterPriceObservations(observations, "usd")).toHaveLength(75);
    expect(
      filterPriceObservations(
        observations,
        observations[74].market_date.slice(0, 10),
      ),
    ).toEqual([observations[74]]);
    expect(filterPriceObservations(observations, "missing")).toEqual([]);
    const html = renderToStaticMarkup(
      <PriceObservationReview observations={observations} />,
    );
    expect(html).toContain("75 of 75 rows shown");
    expect(html).toContain("41.1234567890 USD");
    expect(html).toContain("0.0000000000 USD");
    expect(html).toContain("Unavailable");
    expect(html).toContain("split adjusted");
  });
});
