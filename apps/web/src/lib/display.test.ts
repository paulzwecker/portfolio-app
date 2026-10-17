import { describe, expect, it } from "vitest";
import {
  dateOnly,
  dateTime,
  formatCompactFinancial,
  formatCurrency,
  formatMetric,
  formatNumber,
  formatPercent,
  marketDate,
  percent,
  quantity,
  statusLabel,
} from "@/lib/display";

describe("shared display formatting", () => {
  it("keeps missing values distinct from numeric zero", () => {
    expect(formatCurrency(null, "USD")).toBe("Unavailable");
    expect(formatNumber(null)).toBe("Unavailable");
    expect(formatPercent(null)).toBe("No target");
    expect(formatCurrency("0", "USD")).toBe("$0.00");
  });

  it("formats currency and falls back without discarding the currency code", () => {
    expect(formatCurrency("1234.567", "EUR", 2)).toBe("€1,234.57");
    expect(formatCurrency("12.500", "US", 2)).toBe("12.5 US");
    expect(formatCurrency("12.500", null, 2)).toBe("12.5");
  });

  it("preserves configurable precision for rates and reported metrics", () => {
    expect(formatPercent("0.123456", 2)).toBe("12.35%");
    expect(percent("0.000000000001")).not.toBe("0%");
    expect(formatMetric("1.2300", { unit: "shares" })).toBe("1.23 shares");
    expect(formatMetric(null, { missing: "Not supplied" })).toBe(
      "Not supplied",
    );
    expect(quantity("12.340000")).toBe("12.34");
    expect(formatCompactFinancial("0")).toBe("0");
    expect(formatCompactFinancial("-1234000")).toContain("(");
    expect(formatCompactFinancial(null)).toBe("—");
  });

  it("keeps date-only market values in UTC while timestamps use the viewer timezone", () => {
    expect(marketDate("2026-10-16T00:00:00Z")).toBe(
      dateOnly("2026-10-16T00:00:00Z", "UTC"),
    );
    expect(dateTime("2026-10-16T08:30:00Z")).not.toBe("Unknown time");
    expect(dateTime(null)).toBe("Unknown time");
  });

  it("uses one readable status label convention", () => {
    expect(statusLabel("DATA_CHECK")).toBe("DATA CHECK");
    expect(statusLabel(undefined)).toBe("Unavailable");
  });
});
