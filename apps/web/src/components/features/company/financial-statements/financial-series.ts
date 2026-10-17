import type {
  FinancialStatementCell,
  FinancialStatementColumn,
  FinancialStatementRow,
} from "@/lib/domain-contracts";

export const sourceLabels = {
  REPORTED_ACTUAL: "Reported actuals",
  CONSENSUS: "Analyst consensus",
  AGENT_FORECAST: "Agent forecast",
} as const;

export type FinancialComparisonMode = "SEPARATE" | "INDEXED";

export function unitLabel(
  row: Pick<FinancialStatementRow, "currency" | "unit">,
) {
  const basis =
    row.currency ?? (row.unit === "shares" ? "shares" : "currency unknown");
  return row.unit === "currency_per_share" ? `${basis} / share` : basis;
}

export function rowLabel(row: FinancialStatementRow) {
  return `${row.label} · ${row.source_name}${row.scenario ? ` · ${row.scenario}` : ""} · ${unitLabel(row)}`;
}

/** Plot geometry only. Missing/checked values and missing reporting windows break the path. */
export function financialSegments(
  row: FinancialStatementRow,
  columns: FinancialStatementColumn[],
  periodType: "ANNUAL" | "QUARTERLY",
) {
  const segments: FinancialStatementCell[][] = [];
  let current: FinancialStatementCell[] = [];
  for (const column of columns) {
    const cell = row.cells.find(
      (item) => item.period_end === column.period_end,
    );
    if (
      !cell ||
      cell.value === null ||
      cell.status !== "AVAILABLE" ||
      !Number.isFinite(Number(cell.value))
    ) {
      if (current.length) segments.push(current);
      current = [];
      continue;
    }
    const previous = current.at(-1);
    const days = previous
      ? (Date.parse(cell.period_end) - Date.parse(previous.period_end)) /
        86400000
      : 0;
    if (days > (periodType === "ANNUAL" ? 400 : 120)) {
      if (current.length) segments.push(current);
      current = [];
    }
    current.push(cell);
  }
  if (current.length) segments.push(current);
  return segments;
}

/**
 * Presentation-only indexed geometry for comparing values with different
 * currencies, units or scales. The source values remain unchanged in the
 * table and evidence drawer. A zero first observation cannot be indexed
 * honestly, so the series is omitted from this mode and remains available in
 * separate-scale mode.
 */
export function indexedFinancialSegments(
  row: FinancialStatementRow,
  columns: FinancialStatementColumn[],
  periodType: "ANNUAL" | "QUARTERLY",
) {
  const sourceSegments = financialSegments(row, columns, periodType);
  const first = sourceSegments.flat().find((cell) => cell.value !== null);
  const baseline = first ? Number(first.value) : NaN;
  if (!Number.isFinite(baseline) || baseline === 0) return [];
  return sourceSegments.map((segment) =>
    segment.map((cell) => ({
      ...cell,
      value: String((Number(cell.value) / baseline) * 100),
    })),
  );
}
