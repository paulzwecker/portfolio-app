import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { PriceHistoryAnalytics } from "@/lib/domain-contracts";
import { HistoryCoverageNotice } from "./company-historical-analysis-workspace";

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
});
