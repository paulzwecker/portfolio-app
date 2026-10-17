import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FinancialMetricSelector } from "./financial-metric-selector";

describe("financial metric selector", () => {
  it("exposes statement sections, estimates and explicit comparison modes", () => {
    const html = renderToStaticMarkup(
      <FinancialMetricSelector
        statement="INCOME_STATEMENT"
        onStatement={vi.fn()}
        sources={["REPORTED_ACTUAL", "CONSENSUS", "AGENT_FORECAST"]}
        onSource={vi.fn()}
        comparisonMode="SEPARATE"
        onComparisonMode={vi.fn()}
        canCompare
      />,
    );
    expect(html).toContain("Income Statement");
    expect(html).toContain("Estimates");
    expect(html).toContain("Growth &amp; Ratios");
    expect(html).toContain("Separate scales");
    expect(html).toContain("Indexed comparison");
    expect(html).toContain("visual trend comparison, not a return");
  });

  it("keeps indexed mode disabled until mixed bases are selected", () => {
    const html = renderToStaticMarkup(
      <FinancialMetricSelector
        statement="INCOME_STATEMENT"
        onStatement={vi.fn()}
        sources={["REPORTED_ACTUAL"]}
        onSource={vi.fn()}
        comparisonMode="SEPARATE"
        onComparisonMode={vi.fn()}
        canCompare={false}
      />,
    );
    expect(html).toContain('disabled=""');
    expect(html).toContain("Select at least two available rows");
  });
});
