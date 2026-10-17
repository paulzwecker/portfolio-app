"use client";

import { useState } from "react";
import { PageSection } from "@/components/app/page-section";
import { PendingOrError, EmptyState } from "@/components/app/empty-state";
import { MetricCard } from "@/components/app/metric-card";
import { MetricGroup } from "@/components/app/metric-group";
import { Button } from "@/components/ui/button";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyFinancialStatements,
  type FinancialStatementCell,
  type FinancialStatementRow,
} from "@/lib/domain-contracts";
import { dateTime, statusLabel } from "@/lib/display";
import { FinancialPeriodControls } from "./financial-period-controls";
import {
  FinancialMetricSelector,
  type FinancialSourceKind,
  type Statement,
} from "./financial-metric-selector";
import type { FinancialComparisonMode } from "./financial-series";
import { FinancialStatementsTable } from "./financial-statements-table";
import { FinancialSeriesChart } from "./financial-series-chart";
import {
  FinancialSourceDrawer,
  type FinancialCellSelection,
} from "./financial-source-drawer";

const order = [
  "REVENUE",
  "GROSS_PROFIT",
  "OPERATING_INCOME",
  "NET_INCOME",
  "EPS",
  "EBIT",
  "EBITDA",
  "DILUTED_WEIGHTED_AVERAGE_SHARES",
  "DILUTED_SHARES",
  "CASH_AND_CASH_EQUIVALENTS",
  "CURRENT_DEBT",
  "NONCURRENT_DEBT",
  "OPERATING_CASH_FLOW",
  "CAPITAL_EXPENDITURES",
  "FREE_CASH_FLOW",
];

export function FinancialStatementsWorkspace({
  companyId,
}: {
  companyId: string;
}) {
  const [periodType, setPeriodType] = useState<"ANNUAL" | "QUARTERLY">(
    "ANNUAL",
  );
  const [range, setRange] = useState(10);
  const [cutoff, setCutoff] = useState("");
  const [statement, setStatement] = useState<Statement>("INCOME_STATEMENT");
  const [sources, setSources] = useState<FinancialSourceKind[]>([
    "REPORTED_ACTUAL",
    "CONSENSUS",
    "AGENT_FORECAST",
  ]);
  const [comparisonMode, setComparisonMode] =
    useState<FinancialComparisonMode>("SEPARATE");
  const [selection, setSelection] = useState<string[] | null>(null);
  const [inspected, setInspected] = useState<FinancialCellSelection | null>(
    null,
  );
  const [drawer, setDrawer] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const params = new URLSearchParams({
    period_type: periodType,
    period_limit: String(range),
  });
  if (cutoff) {
    params.set("as_of", cutoff);
    params.set("known_at", `${cutoff}T23:59:59.999Z`);
  }
  const state = useResearch(
    `companies/${companyId}/financial-statements?${params}`,
    isCompanyFinancialStatements,
  );
  const data = state.data;
  const allRows = (data?.rows ?? [])
    .slice()
    .sort(
      (a, b) =>
        order.indexOf(a.metric) - order.indexOf(b.metric) ||
        a.source_kind.localeCompare(b.source_kind) ||
        a.id.localeCompare(b.id),
    );
  const selected =
    selection ??
    allRows
      .filter(
        (row) =>
          row.source_kind === "REPORTED_ACTUAL" &&
          ["REVENUE", "OPERATING_INCOME"].includes(row.metric) &&
          row.cells.some((cell) => cell.status === "AVAILABLE"),
      )
      .map((row) => row.id)
      .slice(0, 2);
  const visibleRows = allRows.filter((row) => {
    if (!sources.includes(row.source_kind)) return false;
    if (statement === "ESTIMATES") return row.source_kind !== "REPORTED_ACTUAL";
    if (statement === "GROWTH_RATIOS") return false;
    return row.statement === statement;
  });
  const chartRows = allRows.filter(
    (row) => selected.includes(row.id) && sources.includes(row.source_kind),
  );
  const chartBases = new Set(
    chartRows.map((row) => `${row.currency ?? "unknown"}:${row.unit}`),
  );
  const canCompare = chartRows.length > 1 && chartBases.size > 1;
  const availableActualRows = allRows.filter(
    (row) =>
      row.source_kind === "REPORTED_ACTUAL" &&
      row.cells.some(
        (cell) => cell.status === "AVAILABLE" && cell.value !== null,
      ),
  ).length;
  const forecastRows = allRows.filter(
    (row) => row.source_kind !== "REPORTED_ACTUAL",
  ).length;
  const qualityCheckedCells = allRows.reduce(
    (count, row) =>
      count + row.cells.filter((cell) => cell.status !== "AVAILABLE").length,
    0,
  );
  const toggle = (id: string) => {
    setNotice(null);
    if (!selected.includes(id) && selected.length >= 6) {
      setNotice(
        "Select up to six series. Remove a selected metric before adding another.",
      );
      return;
    }
    setSelection(
      selected.includes(id)
        ? selected.filter((item) => item !== id)
        : [...selected, id],
    );
  };
  const inspect = (
    row: FinancialStatementRow,
    cell: FinancialStatementCell,
  ) => {
    setInspected({ rowId: row.id, periodEnd: cell.period_end });
    setDrawer(true);
  };
  return (
    <section id="reported-fundamentals" className="scroll-mt-5">
      <PageSection
        title="Financial statements"
        description="Explore reported performance and separately identified forecasts. Select metric rows to chart; select a value to inspect the original evidence."
        actions={
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setInspected(null);
              setDrawer(true);
            }}
            disabled={!data}
          >
            Sources & alignment
          </Button>
        }
      >
        <span
          id="consensus-estimates"
          className="scroll-mt-5"
          aria-hidden="true"
        />
        <span
          id="research-forecasts"
          className="scroll-mt-5"
          aria-hidden="true"
        />
        <FinancialPeriodControls
          periodType={periodType}
          onPeriodType={(value) => {
            setPeriodType(value);
            setRange(value === "ANNUAL" ? 10 : 16);
          }}
          range={range}
          onRange={setRange}
          cutoff={cutoff}
          onCutoff={setCutoff}
        />
        <p className="text-xs leading-4 text-muted-foreground">
          Columns use the reported period end. Fiscal-year and quarter labels
          appear only when the canonical filing evidence supports them; an
          ambiguous period stays date-only.
        </p>
        {!data ? (
          <PendingOrError {...state} />
        ) : (
          <>
            <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
              <span>
                {cutoff
                  ? `Known in the app by ${cutoff} · publication cutoff also applied`
                  : "Latest known filings and accepted research"}
              </span>
              <span>
                Latest reported observation {dateTime(data.latest_observed_at)}
              </span>
            </div>
            <MetricGroup label="Financial statement coverage" columns={4}>
              <MetricCard
                label="Timeline columns"
                value={data.periods.length}
                note={`${periodType === "ANNUAL" ? "Annual" : "Quarterly"} view · ${range} period limit`}
              />
              <MetricCard
                label="Reported rows"
                value={availableActualRows}
                note="Rows with at least one eligible reported value"
              />
              <MetricCard
                label="Forward rows"
                value={forecastRows}
                note="Consensus and agent forecasts remain separate"
              />
              <MetricCard
                label="Quality checks"
                value={qualityCheckedCells}
                note={
                  qualityCheckedCells
                    ? "Inspect flagged cells for source context"
                    : "No flagged cells in this period window"
                }
                tone={qualityCheckedCells ? "warning" : "default"}
              />
            </MetricGroup>
            {!data.periods.length && (
              <EmptyState
                title="No aligned financial periods"
                description="No eligible facts or forecasts are known at this cutoff. Sources & alignment explains missing coverage; no values are substituted."
              />
            )}
            <FinancialSeriesChart
              key={`${periodType}:${range}:${cutoff}`}
              data={data}
              rows={chartRows}
              onInspect={inspect}
              onRemove={toggle}
              comparisonMode={comparisonMode}
            />
            <FinancialMetricSelector
              statement={statement}
              onStatement={setStatement}
              sources={sources}
              onSource={(kind) =>
                setSources(
                  sources.includes(kind)
                    ? sources.filter((item) => item !== kind)
                    : [...sources, kind],
                )
              }
              comparisonMode={comparisonMode}
              onComparisonMode={setComparisonMode}
              canCompare={canCompare}
            />
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>
                {selected.length} of 6 chart series selected · select a row in
                the table to add it above
              </span>
              {comparisonMode === "INDEXED" && (
                <span className="font-medium text-primary">
                  Indexed view · 100 at each series start
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {data.rows.filter((row) => row.source_kind === "CONSENSUS").length
                ? "Consensus uses the selected provider only."
                : "No eligible aligned analyst consensus."}{" "}
              {data.rows.some((row) => row.source_kind === "AGENT_FORECAST")
                ? "Agent forecasts retain separate author/scenario rows."
                : "No eligible aligned agent forecasts."}{" "}
              Model projections require a verified fiscal anchor; inspect their
              mapping status in Sources & alignment.
            </p>
            {notice && (
              <p role="status" className="text-sm text-warning">
                {notice}
              </p>
            )}
            {statement === "GROWTH_RATIOS" ? (
              <EmptyState
                title="Growth & ratios are unavailable"
                description="The canonical API does not yet publish derived growth or ratio observations. Reported facts remain available in the statement tabs; nothing is calculated or substituted in the browser."
              />
            ) : visibleRows.length ? (
              <FinancialStatementsTable
                data={data}
                rows={visibleRows}
                selected={selected}
                onToggle={toggle}
                onInspect={inspect}
              />
            ) : (
              <EmptyState
                title={
                  statement === "ESTIMATES"
                    ? "No aligned estimates"
                    : `No ${statusLabel(statement).toLowerCase()} rows`
                }
                description="No canonical observations are available for this section and source filter. Open Sources & alignment for the precise coverage reason."
                actions={
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setInspected(null);
                      setDrawer(true);
                    }}
                  >
                    Inspect coverage
                  </Button>
                }
              />
            )}
            <p className="text-xs text-muted-foreground">
              Compact values retain their original currency and units.
              Parentheses indicate negative values; — means unavailable. No FX
              conversion, derived ratios, missing quarters or inferred forecasts
              are calculated here. Accepted model projections remain in
              Valuation until a verified fiscal anchor is available.
            </p>
            <FinancialSourceDrawer
              data={data}
              selection={inspected}
              open={drawer}
              onOpenChange={setDrawer}
            />
          </>
        )}
      </PageSection>
    </section>
  );
}
