import { describe, expect, it } from "vitest";
import {
  formatRatioValue,
  scenarioWidth,
} from "@/components/features/company/company-valuation-workspace";

describe("Company valuation workspace presentation", () => {
  it("keeps valuation percentages readable while preserving missing state", () => {
    expect(formatRatioValue("0.127970006925")).toBe("12.8%");
    expect(formatRatioValue("0")).toBe("0%");
    expect(formatRatioValue(null)).toBe("Unavailable");
  });

  it("uses probabilities only for scenario visual width and clamps malformed extremes", () => {
    expect(scenarioWidth("0.6125")).toBeCloseTo(61.25);
    expect(scenarioWidth("1.2")).toBe(100);
    expect(scenarioWidth("-0.2")).toBe(0);
    expect(scenarioWidth(null)).toBe(0);
  });
});
