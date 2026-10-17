import { describe, expect, it } from "vitest";
import type {
  FinancialStatementColumn,
  FinancialStatementRow,
} from "@/lib/domain-contracts";
import {
  financialSegments,
  indexedFinancialSegments,
  rowLabel,
} from "./financial-series";

const columns = (ends: string[]): FinancialStatementColumn[] =>
  ends.map((period_end, index) => ({
    period_end,
    label: `FY${2022 + index}`,
    fiscal_year: 2022 + index,
    fiscal_period: "FY",
    is_forecast: false,
  }));

const row = (cells: unknown[]) =>
  ({
    id: "REPORTED_ACTUAL::REVENUE::USD::currency",
    metric: "REVENUE",
    label: "Revenue",
    statement: "INCOME_STATEMENT",
    source_kind: "REPORTED_ACTUAL",
    source_name: "Reported actuals",
    scenario: null,
    currency: "USD",
    unit: "currency",
    availability_reason: null,
    cells,
  }) as unknown as FinancialStatementRow;

describe("financial statement series geometry", () => {
  it("breaks a line for missing or quality-checked cells", () => {
    const periods = columns([
      "2022-12-31",
      "2023-12-31",
      "2024-12-31",
      "2025-12-31",
    ]);
    const series = row([
      {
        period_end: "2022-12-31",
        value: "10",
        status: "AVAILABLE",
      },
      {
        period_end: "2023-12-31",
        value: null,
        status: "UNAVAILABLE",
      },
      {
        period_end: "2024-12-31",
        value: "20",
        status: "DATA_CHECK",
      },
      {
        period_end: "2025-12-31",
        value: "30",
        status: "AVAILABLE",
      },
    ]);
    expect(financialSegments(series, periods, "ANNUAL")).toEqual([
      [series.cells[0]],
      [series.cells[3]],
    ]);
  });

  it("breaks long quarterly gaps instead of drawing across missing history", () => {
    const periods = columns([
      "2024-03-31",
      "2024-06-30",
      "2025-03-31",
      "2025-06-30",
    ]);
    const series = row(
      periods.map((period) => ({
        period_end: period.period_end,
        value: "10",
        status: "AVAILABLE",
      })),
    );
    expect(
      financialSegments(series, periods, "QUARTERLY").map((x) => x.length),
    ).toEqual([2, 2]);
  });

  it("keeps zero and negative observations as valid values", () => {
    const periods = columns(["2025-12-31"]);
    const series = row([
      { period_end: "2025-12-31", value: "0", status: "AVAILABLE" },
    ]);
    expect(financialSegments(series, periods, "ANNUAL")).toEqual([
      [series.cells[0]],
    ]);
    expect(rowLabel(series)).toContain("Revenue · Reported actuals · USD");
  });

  it("indexes compatible chart geometry without changing source values", () => {
    const periods = columns(["2024-12-31", "2025-12-31"]);
    const series = row([
      { period_end: "2024-12-31", value: "50", status: "AVAILABLE" },
      { period_end: "2025-12-31", value: "75", status: "AVAILABLE" },
    ]);
    const indexed = indexedFinancialSegments(series, periods, "ANNUAL");
    expect(indexed.flat().map((cell) => cell.value)).toEqual(["100", "150"]);
    expect(series.cells.map((cell) => cell.value)).toEqual(["50", "75"]);
  });

  it("does not fabricate an indexed baseline from a zero observation", () => {
    const periods = columns(["2024-12-31", "2025-12-31"]);
    const series = row([
      { period_end: "2024-12-31", value: "0", status: "AVAILABLE" },
      { period_end: "2025-12-31", value: "10", status: "AVAILABLE" },
    ]);
    expect(indexedFinancialSegments(series, periods, "ANNUAL")).toEqual([]);
  });
});
