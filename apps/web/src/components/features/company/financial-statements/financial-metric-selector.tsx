import { Button } from "@/components/ui/button";
import { sourceLabels, type FinancialComparisonMode } from "./financial-series";

export const statementLabels = {
  INCOME_STATEMENT: "Income Statement",
  BALANCE_SHEET: "Balance Sheet",
  CASH_FLOW_STATEMENT: "Cash Flow Statement",
  ESTIMATES: "Estimates",
  GROWTH_RATIOS: "Growth & Ratios",
} as const;
export type Statement = keyof typeof statementLabels;
export type FinancialSourceKind = keyof typeof sourceLabels;

export function FinancialMetricSelector({
  statement,
  onStatement,
  sources,
  onSource,
  comparisonMode,
  onComparisonMode,
  canCompare,
}: {
  statement: Statement;
  onStatement: (value: Statement) => void;
  sources: FinancialSourceKind[];
  onSource: (value: FinancialSourceKind) => void;
  comparisonMode: FinancialComparisonMode;
  onComparisonMode: (value: FinancialComparisonMode) => void;
  canCompare: boolean;
}) {
  return (
    <div className="space-y-4 rounded-xl border bg-muted/20 p-3 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Explore statements
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Choose a section, then select rows in the table to update the chart.
          </p>
        </div>
        <div
          role="group"
          aria-label="Financial chart comparison mode"
          className="flex flex-wrap gap-1"
        >
          <span className="mr-1 self-center text-[11px] text-muted-foreground">
            Chart scale
          </span>
          {(
            [
              ["SEPARATE", "Separate scales"],
              ["INDEXED", "Indexed comparison"],
            ] as const
          ).map(([value, label]) => (
            <Button
              key={value}
              size="sm"
              variant={comparisonMode === value ? "default" : "outline"}
              aria-pressed={comparisonMode === value}
              disabled={value === "INDEXED" && !canCompare}
              title={
                value === "INDEXED" && !canCompare
                  ? "Select at least two available rows with different units or scales"
                  : undefined
              }
              onClick={() => onComparisonMode(value)}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>
      <div
        role="group"
        aria-label="Financial statement category"
        className="flex gap-1 overflow-x-auto pb-1"
      >
        {(Object.entries(statementLabels) as [Statement, string][]).map(
          ([value, label]) => (
            <Button
              key={value}
              size="sm"
              variant={statement === value ? "default" : "outline"}
              aria-pressed={statement === value}
              title={
                value === "GROWTH_RATIOS"
                  ? "No canonical growth or ratio observations are available yet"
                  : undefined
              }
              onClick={() => onStatement(value)}
            >
              {label}
            </Button>
          ),
        )}
      </div>
      <div
        role="group"
        aria-label="Financial source visibility"
        className="flex flex-wrap gap-x-5 gap-y-2 border-t pt-3"
      >
        {(Object.entries(sourceLabels) as [FinancialSourceKind, string][]).map(
          ([value, label]) => (
            <label key={value} className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={sources.includes(value)}
                onChange={() => onSource(value)}
                className="size-4 accent-primary"
              />
              {label}
            </label>
          ),
        )}
      </div>
      <p className="text-[11px] leading-4 text-muted-foreground">
        Indexed comparison sets each selected series to 100 at its first
        available observation. It is a visual trend comparison, not a return or
        growth calculation. Exact source values stay in the table.
      </p>
    </div>
  );
}
