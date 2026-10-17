import { useRef } from "react";
import type {
  CompanyFinancialStatements,
  FinancialStatementCell,
  FinancialStatementRow,
} from "@/lib/domain-contracts";
import { formatCompactFinancial, quantity } from "@/lib/display";
import { rowLabel, sourceLabels, unitLabel } from "./financial-series";

export function FinancialStatementsTable({
  data,
  rows,
  selected,
  onToggle,
  onInspect,
}: {
  data: CompanyFinancialStatements;
  rows: FinancialStatementRow[];
  selected: string[];
  onToggle: (id: string) => void;
  onInspect: (row: FinancialStatementRow, cell: FinancialStatementCell) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  return (
    <div>
      <p
        className="mb-2 text-xs text-muted-foreground"
        id="statement-table-help"
      >
        Select metric rows to chart. Scroll within the table for more periods.
        Select a value to inspect its evidence.
      </p>
      <div
        ref={scroller}
        tabIndex={0}
        role="region"
        aria-label="Financial statements table, scrollable periods"
        aria-describedby="statement-table-help"
        className="max-h-[620px] overflow-auto rounded-xl border bg-card outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <table className="w-full border-separate border-spacing-0 text-sm tabular-nums">
          <caption className="sr-only">
            {data.period_type === "ANNUAL" ? "Annual" : "Quarterly"} financial
            statements; metrics by fiscal period
          </caption>
          <thead className="sticky top-0 z-20">
            <tr>
              <th
                scope="col"
                className="sticky left-0 z-30 min-w-[180px] border-b bg-muted px-3 py-3 text-left text-xs font-medium sm:min-w-[240px]"
              >
                Metric / source / basis
              </th>
              {data.periods.map((period) => (
                <th
                  key={period.period_end}
                  scope="col"
                  className="min-w-[116px] border-b bg-muted px-3 py-3 text-right text-xs font-medium"
                >
                  <span className="block whitespace-nowrap">
                    {period.fiscal_year ? period.label : period.period_end}
                  </span>
                  <span className="mt-1 block text-[10px] font-normal text-muted-foreground">
                    {period.fiscal_year
                      ? period.period_end
                      : data.period_type === "ANNUAL"
                        ? "year ended"
                        : "quarter ended"}
                    {period.is_forecast ? " · forecast" : ""}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const available = row.cells.some(
                (cell) => cell.status === "AVAILABLE" && cell.value !== null,
              );
              return (
                <tr
                  key={row.id}
                  className={
                    selected.includes(row.id)
                      ? "bg-primary/[0.035]"
                      : "hover:bg-muted/30"
                  }
                >
                  <th
                    scope="row"
                    className="sticky left-0 z-10 border-b bg-card px-3 py-3 text-left font-normal shadow-[1px_0_0_0_var(--border)]"
                  >
                    <label className="flex cursor-pointer items-start gap-2.5">
                      <input
                        type="checkbox"
                        checked={selected.includes(row.id)}
                        disabled={!available && !selected.includes(row.id)}
                        onChange={() => onToggle(row.id)}
                        aria-label={`Chart ${rowLabel(row)}`}
                        className="mt-0.5 size-4 shrink-0 accent-primary focus-visible:ring-2 focus-visible:ring-ring"
                      />
                      <span className="min-w-0">
                        <span className="block text-xs font-medium sm:text-sm">
                          {row.label}
                        </span>
                        <span className="mt-1 block text-[10px] text-muted-foreground">
                          {sourceLabels[row.source_kind]}
                          {row.source_kind !== "REPORTED_ACTUAL"
                            ? ` · ${row.source_name}`
                            : ""}
                          {row.scenario ? ` · ${row.scenario}` : ""}
                        </span>
                        <span className="block text-[10px] text-muted-foreground">
                          {unitLabel(row)}
                        </span>
                      </span>
                    </label>
                    {row.availability_reason && (
                      <span className="mt-1 block max-w-[220px] text-[10px] leading-4 text-muted-foreground">
                        {row.availability_reason}
                      </span>
                    )}
                  </th>
                  {data.periods.map((period) => {
                    const cell = row.cells.find(
                      (item) => item.period_end === period.period_end,
                    );
                    return (
                      <td
                        key={period.period_end}
                        className="border-b px-2 py-2 text-right"
                      >
                        {cell ? (
                          <button
                            type="button"
                            onClick={() => onInspect(row, cell)}
                            aria-label={`${row.label}, ${period.label}, ${cell.value === null ? cell.status : `${quantity(cell.value)} ${unitLabel(row)}`}, inspect source`}
                            className={`min-h-9 w-full rounded px-1 text-right underline-offset-4 hover:bg-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${cell.value !== null && Number(cell.value) < 0 ? "text-negative" : ""}`}
                          >
                            {formatCompactFinancial(cell.value)}
                            {cell.status !== "AVAILABLE" && (
                              <span
                                className="ml-1 text-warning"
                                title={cell.reason ?? cell.status}
                              >
                                !<span className="sr-only"> {cell.status}</span>
                              </span>
                            )}
                          </button>
                        ) : (
                          <span
                            title={
                              row.availability_reason ??
                              "No observation for this period"
                            }
                            className="text-muted-foreground"
                          >
                            —<span className="sr-only"> Unavailable</span>
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
