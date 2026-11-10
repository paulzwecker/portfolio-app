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
import { CompanySecCoveragePanel } from "../company-sec-coverage";
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
  const periodEnds = new Set(
    (data?.periods ?? []).map((period) => period.period_end),
  );
  const chartable = (row: FinancialStatementRow) =>
    row.cells.some(
      (cell) =>
        periodEnds.has(cell.period_end) &&
        cell.status === "AVAILABLE" &&
        cell.value !== null,
    );
  const defaultRows = allRows.filter(
    (row) => row.source_kind === "REPORTED_ACTUAL" && chartable(row),
  );
  const preferredRows = defaultRows.filter((row) =>
    ["REVENUE", "OPERATING_INCOME"].includes(row.metric),
  );
  const fallbackRows = defaultRows.length
    ? defaultRows
    : allRows.filter(chartable);
  const selected =
    selection ??
    (preferredRows.length ? preferredRows : fallbackRows)
      .map((row) => row.id)
      .slice(0, 2);
  const hasAlignedCells = allRows.some((row) =>
    row.cells.some((cell) => periodEnds.has(cell.period_end)),
  );
  const chartAvailable = allRows
    .filter((row) => sources.includes(row.source_kind))
    .some(chartable);
  const visibleRows = allRows.filter((row) => {
    if (!sources.includes(row.source_kind)) return false;
    if (statement === "ESTIMATES") return row.source_kind !== "REPORTED_ACTUAL";
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
    (row) => row.source_kind === "REPORTED_ACTUAL" && chartable(row),
  ).length;
  const forecastRows = allRows.filter(
    (row) =>
      row.source_kind !== "REPORTED_ACTUAL" &&
      row.cells.some((cell) => periodEnds.has(cell.period_end)),
  ).length;
  const qualityCheckedCells = allRows.reduce(
    (count, row) =>
      count +
      row.cells.filter(
        (cell) =>
          periodEnds.has(cell.period_end) && cell.status !== "AVAILABLE",
      ).length,
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
        description={
          chartAvailable
            ? "Explore reported performance and separately identified forecasts. Select metric rows to chart; select a value to inspect the original evidence."
            : "Explore reported performance and separately identified forecasts. Review sources and coverage for the available evidence."
        }
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
        {!cutoff && <CompanySecCoveragePanel companyId={companyId} />}
        {cutoff && (
          <p role="note" className="text-sm text-warning">
            Historical issuer attribution has not been verified for this cutoff.
            Review source identities before relying on reported values.
          </p>
        )}
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
              {hasAlignedCells && (
                <span>
                  Latest reported observation{" "}
                  {dateTime(data.latest_observed_at)}
                </span>
              )}
            </div>
            {hasAlignedCells && (
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
            )}
            {!data.periods.length && (
              <EmptyState
                title="No aligned financial periods"
                description="No eligible facts or forecasts are known at this cutoff. Sources & alignment explains missing coverage; no values are substituted."
              />
            )}
            {data.periods.length > 0 && !hasAlignedCells && (
              <EmptyState
                title="No financial statement rows"
                description="No eligible facts or forecasts are available in these periods. Sources & alignment explains missing coverage."
              />
            )}
            {hasAlignedCells && (
              <>
                {chartAvailable && (
                  <FinancialSeriesChart
                    key={`${periodType}:${range}:${cutoff}`}
                    data={data}
                    rows={chartRows}
                    onInspect={inspect}
                    onRemove={toggle}
                    comparisonMode={comparisonMode}
                  />
                )}
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
                  chartAvailable={chartAvailable}
                />
                {chartAvailable && (
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span>
                      {selected.length} of 6 chart series selected · select a
                      row in the table to add it above
                    </span>
                    {comparisonMode === "INDEXED" && (
                      <span className="font-medium text-primary">
                        Indexed view · 100 at each series start
                      </span>
                    )}
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  {allRows.some(
                    (row) =>
                      row.source_kind === "CONSENSUS" &&
                      row.cells.some((cell) => periodEnds.has(cell.period_end)),
                  )
                    ? "Consensus uses the selected provider only."
                    : "No eligible aligned analyst consensus."}{" "}
                  {allRows.some(
                    (row) =>
                      row.source_kind === "AGENT_FORECAST" &&
                      row.cells.some((cell) => periodEnds.has(cell.period_end)),
                  )
                    ? "Agent forecasts retain separate author/scenario rows."
                    : "No eligible aligned agent forecasts."}{" "}
                  Model projections require a verified fiscal anchor; inspect
                  their mapping status in Sources & alignment.
                </p>
                {notice && (
                  <p role="status" className="text-sm text-warning">
                    {notice}
                  </p>
                )}
                {visibleRows.length ? (
                  <FinancialStatementsTable
                    data={data}
                    rows={visibleRows}
                    selected={selected}
                    onToggle={toggle}
                    onInspect={inspect}
                    chartAvailable={chartAvailable}
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
                  Parentheses indicate negative values; — means unavailable. No
                  FX conversion, derived ratios, missing quarters or inferred
                  forecasts are calculated here. Accepted model projections
                  remain in Valuation until a verified fiscal anchor is
                  available.
                </p>
              </>
            )}
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
