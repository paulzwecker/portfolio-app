import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
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
