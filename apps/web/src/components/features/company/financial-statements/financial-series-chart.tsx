"use client";

import { useEffect, useRef, useState } from "react";
import { ChartContainer } from "@/components/app/chart-container";
import { Button } from "@/components/ui/button";
import type {
  CompanyFinancialStatements,
  FinancialStatementCell,
  FinancialStatementRow,
} from "@/lib/domain-contracts";
import { formatCompactFinancial, quantity } from "@/lib/display";
import {
  financialSegments,
  indexedFinancialSegments,
  rowLabel,
  sourceLabels,
  unitLabel,
  type FinancialComparisonMode,
} from "./financial-series";

const H = 250,
  L = 62,
  R = 18,
  T = 18,
  B = 35;
const stroke = (index: number) => `var(--chart-${(index % 5) + 1})`;
const dash = {
  REPORTED_ACTUAL: undefined,
  CONSENSUS: "7 4",
  AGENT_FORECAST: "2 4",
};

function chartText(value: unknown, fallback = "Unavailable") {
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : fallback;
}

export function FinancialSeriesChart({
  data,
  rows,
  onInspect,
  onRemove,
  comparisonMode = "SEPARATE",
}: {
  data: CompanyFinancialStatements;
  rows: FinancialStatementRow[];
  onInspect: (row: FinancialStatementRow, cell: FinancialStatementCell) => void;
  onRemove: (id: string) => void;
  comparisonMode?: FinancialComparisonMode;
}) {
  const [hover, setHover] = useState<{
    row: FinancialStatementRow;
    cell: FinancialStatementCell;
  } | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(820);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(280, entry.contentRect.width - 40)),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const W = width;
  const groups = new Map<string, FinancialStatementRow[]>();
  for (const row of rows) {
    const key =
      comparisonMode === "INDEXED"
        ? "Indexed comparison · first available = 100"
        : `${row.currency ?? "No currency"} · ${row.unit}`;
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const dates = data.periods.map((period) => Date.parse(period.period_end));
  const start = Math.min(...dates),
    end = Math.max(...dates);
  const x = (date: string) =>
    L + ((W - L - R) * (Date.parse(date) - start)) / (end - start || 1);
  return (
    <div ref={container} className="min-w-0">
      <ChartContainer
        title="Financial development"
        description={
          comparisonMode === "INDEXED"
            ? "Indexed comparison uses 100 at each series' first available observation. Actuals are solid, analyst consensus dashed and agent forecasts dotted."
            : "Select metric rows in the table. Actuals are solid, analyst consensus dashed and agent forecasts dotted. Different currencies and units use separate scales; missing windows break the line."
        }
      >
        <div
          className="mb-3 flex flex-wrap gap-1.5"
          aria-label="Selected financial series"
        >
          {rows.map((row, i) => (
            <Button
              key={row.id}
              size="sm"
              variant="outline"
              className="h-auto min-h-8 max-w-full whitespace-normal text-left text-xs"
              onClick={() => onRemove(row.id)}
              aria-label={`Remove ${rowLabel(row)} from chart`}
            >
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rounded-full"
                style={{ background: stroke(i) }}
              />
              {row.label} · {unitLabel(row)}
              {row.source_kind !== "REPORTED_ACTUAL"
                ? ` · ${row.source_name}`
                : ""}
              {row.scenario ? ` · ${row.scenario}` : ""}
              <span aria-hidden="true">×</span>
            </Button>
          ))}
        </div>
        {!rows.length && (
          <div className="grid min-h-52 place-items-center rounded-lg bg-muted/30 p-6 text-center text-sm text-muted-foreground">
            Select a metric row to explore its history.
          </div>
        )}
        {[...groups].map(([basis, series]) => {
          const basisText = chartText(basis, "Unknown unit basis");
          const plottedByRow = new Map<
            string,
            ReturnType<typeof financialSegments>
          >();
          for (const row of series) {
            plottedByRow.set(
              row.id,
              comparisonMode === "INDEXED"
                ? indexedFinancialSegments(row, data.periods, data.period_type)
                : financialSegments(row, data.periods, data.period_type),
            );
          }
          const plotted = [...plottedByRow.values()].flatMap((segments) =>
            segments.flat(),
          );
          const values = plotted.map((cell) => Number(cell.value));
          const unindexableRows =
            comparisonMode === "INDEXED"
              ? series.filter(
                  (row) =>
                    indexedFinancialSegments(
                      row,
                      data.periods,
                      data.period_type,
                    ).length === 0,
                )
              : [];
          if (!values.length)
            return (
              <p key={basisText} className="p-4 text-sm text-muted-foreground">
                {comparisonMode === "INDEXED"
                  ? "One or more selected series starts at zero or has no available observations, so it cannot be indexed. Switch to separate scales; checked values remain in the table."
                  : `No available observations for ${basisText}. Checked values remain in the table.`}
              </p>
            );
          const min = Math.min(0, ...values),
            max = Math.max(0, ...values);
          const span = max - min || 1;
          const y = (value: string) =>
            T + ((max - Number(value)) / span) * (H - T - B);
          const ticks = [min, min + span / 2, max];
          return (
            <div key={basisText} className="mb-3 min-w-0">
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                {basisText}
              </p>
              {unindexableRows.length > 0 && (
                <p className="mb-2 text-xs text-warning" role="status">
                  {unindexableRows.map((row) => row.label).join(", ")} cannot be
                  indexed from a zero or unavailable baseline; switch to
                  separate scales to inspect the raw series.
                </p>
              )}
              <svg
                viewBox={`0 0 ${W} ${H}`}
                className="h-[250px] w-full min-w-0"
                role="group"
                aria-label={`Financial series chart, ${basisText}`}
              >
                {ticks.map((tick, i) => (
                  <g key={i}>
                    <line
                      x1={L}
                      x2={W - R}
                      y1={y(String(tick))}
                      y2={y(String(tick))}
                      className="stroke-border"
                      strokeDasharray="3 5"
                    />
                    <text
                      x={L - 10}
                      y={y(String(tick)) + 4}
                      textAnchor="end"
                      className="fill-muted-foreground"
                      fontSize={11}
                    >
                      {formatCompactFinancial(String(tick), 1)}
                    </text>
                  </g>
                ))}
                {data.periods.map((p, i) =>
                  i %
                    Math.max(
                      1,
                      Math.ceil(data.periods.length / (W < 500 ? 3 : 6)),
                    ) ===
                    0 || i === data.periods.length - 1 ? (
                    <text
                      key={p.period_end}
                      x={x(p.period_end)}
                      y={H - 8}
                      textAnchor={
                        i === 0
                          ? "start"
                          : i === data.periods.length - 1
                            ? "end"
                            : "middle"
                      }
                      className="fill-muted-foreground"
                      fontSize={10}
                    >
                      {p.fiscal_year && W < 500
                        ? `${p.fiscal_period ?? "FY"} ${String(p.fiscal_year).slice(-2)}`
                        : p.fiscal_year
                          ? chartText(p.label)
                          : chartText(p.period_end)}
                    </text>
                  ) : null,
                )}
                {series.map((row) => {
                  const color = stroke(
                    rows.findIndex((item) => item.id === row.id),
                  );
                  return (
                    <g key={row.id}>
                      {(plottedByRow.get(row.id) ?? []).map((segment, i) => (
                        <path
                          key={i}
                          d={segment
                            .map(
                              (cell, j) =>
                                `${j ? "L" : "M"}${x(cell.period_end)},${y(cell.value!)}`,
                            )
                            .join(" ")}
                          fill="none"
                          stroke={color}
                          strokeWidth={2.5}
                          strokeDasharray={dash[row.source_kind]}
                          strokeLinejoin="round"
                        />
                      ))}
                      {/** The table/drawer always retain raw source values. */}
                      {(() => {
                        const plottedCells = (plottedByRow.get(row.id) ?? [])
                          .flat()
                          .reduce(
                            (map, cell) => map.set(cell.period_end, cell),
                            new Map<string, FinancialStatementCell>(),
                          );
                        return row.cells
                          .filter((cell) => {
                            const plottedCell = plottedCells.get(
                              cell.period_end,
                            );
                            return Boolean(
                              plottedCell &&
                              cell.value !== null &&
                              cell.status === "AVAILABLE",
                            );
                          })
                          .map((cell) => {
                            const plottedCell = plottedCells.get(
                              cell.period_end,
                            )!;
                            return (
                              <g
                                key={cell.period_end}
                                role="button"
                                tabIndex={0}
                                aria-label={`${rowLabel(row)}, ${cell.period_end}: ${quantity(cell.value)}. Inspect source`}
                                onMouseEnter={() => setHover({ row, cell })}
                                onFocus={() => setHover({ row, cell })}
                                onClick={() => onInspect(row, cell)}
                                onKeyDown={(event) => {
                                  if (
                                    event.key === "Enter" ||
                                    event.key === " "
                                  ) {
                                    event.preventDefault();
                                    onInspect(row, cell);
                                  }
                                }}
                                className="cursor-pointer outline-none focus-visible:stroke-ring"
                              >
                                <circle
                                  cx={x(cell.period_end)}
                                  cy={y(plottedCell.value!)}
                                  r={9}
                                  fill="transparent"
                                />
                                <circle
                                  cx={x(cell.period_end)}
                                  cy={y(plottedCell.value!)}
                                  r={3.5}
                                  fill={color}
                                  stroke="var(--card)"
                                  strokeWidth={1.5}
                                />
                                <title>
                                  {row.label} · {cell.period_end} ·{" "}
                                  {quantity(cell.value)} {unitLabel(row)} ·{" "}
                                  {sourceLabels[row.source_kind]}
                                </title>
                              </g>
                            );
                          });
                      })()}
                    </g>
                  );
                })}
              </svg>
            </div>
          );
        })}
        <div
          role="status"
          aria-live="polite"
          className="min-h-12 rounded-md bg-muted/40 px-3 py-2 text-xs leading-5"
        >
          {hover ? (
            <>
              <strong>{hover.row.label}</strong> · {hover.cell.period_end} ·{" "}
              <span className="tabular-nums">
                {quantity(hover.cell.value)} {unitLabel(hover.row)}
              </span>
              <span className="block text-muted-foreground">
                {sourceLabels[hover.row.source_kind]} · {hover.row.source_name}
                {hover.row.scenario ? ` · ${hover.row.scenario}` : ""} · select
                point for evidence
              </span>
            </>
          ) : (
            "Hover or focus a chart point for exact values. Select it to open the source history."
          )}
        </div>
      </ChartContainer>
    </div>
  );
}
