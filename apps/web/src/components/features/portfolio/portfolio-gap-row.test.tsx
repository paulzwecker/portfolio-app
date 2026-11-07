import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GapRow } from "./decision-components";
import type { CompanyPortfolioContext } from "@/lib/domain-contracts";

const row: CompanyPortfolioContext = {
  company: {
    id: "10000000-0000-4000-8000-000000000001",
    name: "A long company name for a narrow allocation card",
    reporting_currency: "USD",
    is_demo: false,
    created_at: "2026-11-07T12:00:00Z",
    lifecycle: null,
    lifecycle_event_id: null,
  },
  positions: [],
  current_weight: "0.707466949649000000000",
  target_weight: "0.5",
  allocation_gap: "-0.207466949649000000000",
  allocation_status: "VALUED",
  current_market_value: "277.15",
  current_market_currency: "EUR",
};

describe("Strategic allocation gap display", () => {
  it("keeps the company visible and exposes original precision", () => {
    const html = renderToStaticMarkup(<GapRow row={row} />);
    expect(html).toContain(row.company.name);
    expect(html).toContain("block break-words");
    expect(html).toContain("70.75%");
    expect(html).toContain("-20.75 pp");
    expect(html).toContain("Exact current weight 0.707466949649000000000");
  });
  it("retains explicit zero weights", () => {
    const html = renderToStaticMarkup(
      <GapRow
        row={{
          ...row,
          current_weight: "0",
          target_weight: "0",
          allocation_gap: "0",
        }}
      />,
    );
    expect(html).toContain("0%");
    expect(html).toContain("0 pp");
    expect(html).not.toContain("No target");
  });
  it("keeps absent inputs unavailable", () => {
    const html = renderToStaticMarkup(
      <GapRow
        row={{
          ...row,
          current_weight: null,
          target_weight: null,
          allocation_gap: null,
          allocation_status: "PRICE_COVERAGE_INCOMPLETE",
        }}
      />,
    );
    expect(html).toContain("No target");
    expect(html).toContain("Unavailable");
    expect(html).not.toContain("0%");
  });
});
