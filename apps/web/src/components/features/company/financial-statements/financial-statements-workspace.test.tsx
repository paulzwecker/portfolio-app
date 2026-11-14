import { beforeEach, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FinancialStatementsWorkspace } from "./financial-statements-workspace";

const state = vi.hoisted(() => ({
  data: undefined as unknown,
  error: undefined,
  retry: () => {},
}));
vi.mock("@/hooks/use-research", () => ({ useResearch: () => state }));
vi.mock("../company-sec-coverage", () => ({
  CompanySecCoveragePanel: () => <div>SEC coverage remains accessible</div>,
}));
vi.mock("./financial-source-drawer", () => ({
  FinancialSourceDrawer: () => null,
}));
vi.mock("./financial-series-chart", () => ({
  FinancialSeriesChart: ({ rows }: { rows: { label: string }[] }) => (
    <div>Chart is available: {rows.map((item) => item.label).join(", ")}</div>
  ),
}));

const period = {
  period_end: "2025-12-31",
  label: "FY2025",
  fiscal_year: 2025,
  fiscal_period: "FY",
  is_forecast: false,
};
const row = (status: string, value: string | null) => ({
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
  cells: [
    {
      period_end: period.period_end,
      status,
      value,
      reason: "Evidence requires review",
      selected_source_id: null,
      source_ids: [],
    },
  ],
});
const base = {
  company_id: "11111111-1111-4111-8111-111111111111",
  period_type: "ANNUAL",
  latest_observed_at: null,
  periods: [] as unknown[],
  rows: [] as unknown[],
};

beforeEach(() => {
  state.data = { ...base, periods: [], rows: [] };
});

it("keeps coverage and evidence access while hiding empty charts and selectors", () => {
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("No aligned financial periods");
  expect(html).toContain("SEC coverage remains accessible");
  expect(html).toContain("Sources &amp; alignment");
  expect(html).not.toContain("Chart is available");
  expect(html).not.toContain("Financial statement category");
  expect(html).not.toContain("Select a metric row");
  expect(html).not.toContain("Select metric rows to chart");
  expect(html).not.toContain("Financial statement coverage");
});

it("treats canonical placeholder-only rows as empty without hiding coverage", () => {
  state.data = {
    ...base,
    periods: [],
    rows: [
      {
        ...row("UNAVAILABLE", null),
        cells: [],
        availability_reason:
          "No eligible reported observation in this period view.",
      },
    ],
  };
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("No aligned financial periods");
  expect(html).toContain("Sources &amp; alignment");
  expect(html).toContain("SEC coverage remains accessible");
  expect(html).not.toContain("Financial statement category");
  expect(html).not.toContain("Financial statement coverage");
  expect(html).not.toContain("Chart is available");
});

it("retains conflicting evidence in the table without offering a chart", () => {
  state.data = { ...base, periods: [period], rows: [row("DATA_CHECK", null)] };
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("Revenue");
  expect(html).toContain("DATA_CHECK, inspect source");
  expect(html).toContain("Sources &amp; alignment");
  expect(html).not.toContain("Chart is available");
  expect(html).not.toContain("Financial chart comparison mode");
  expect(html).not.toContain("Chart Revenue");
});

it("announces a quality warning even when the source value is retained", () => {
  state.data = { ...base, periods: [period], rows: [row("DATA_CHECK", "10")] };
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("Revenue, FY2025, 10 USD, DATA_CHECK, inspect source");
  expect(html).not.toContain("Chart is available");
});

it("shows chart controls for a real zero value in an aligned period", () => {
  state.data = { ...base, periods: [period], rows: [row("AVAILABLE", "0")] };
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("Chart is available");
  expect(html).toContain("Financial chart comparison mode");
  expect(html).toContain("Chart Revenue");
  expect(html).not.toContain("Growth &amp; Ratios");
});

it("does not chart an observation without its aligned period", () => {
  state.data = { ...base, periods: [], rows: [row("AVAILABLE", "10")] };
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("No aligned financial periods");
  expect(html).toContain("Sources &amp; alignment");
  expect(html).not.toContain("Chart is available");
});

it("charts an available reported metric when the preferred defaults are absent", () => {
  state.data = {
    ...base,
    periods: [period],
    rows: [
      { ...row("AVAILABLE", "0"), metric: "NET_INCOME", label: "Net income" },
    ],
  };
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("Chart is available: Net income");
});

it("defaults to an eligible forecast when no reported metric can be charted", () => {
  state.data = {
    ...base,
    periods: [period],
    rows: [{ ...row("AVAILABLE", "10"), source_kind: "CONSENSUS" }],
  };
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("Chart is available: Revenue");
});

it("does not claim an out-of-window forecast is aligned or chartable", () => {
  state.data = {
    ...base,
    periods: [period],
    rows: [
      row("AVAILABLE", "10"),
      {
        ...row("AVAILABLE", "20"),
        id: "old-forecast",
        source_kind: "CONSENSUS",
        cells: [
          { ...row("AVAILABLE", "20").cells[0], period_end: "2024-12-31" },
        ],
      },
    ],
  };
  const html = renderToStaticMarkup(
    <FinancialStatementsWorkspace companyId={base.company_id} />,
  );
  expect(html).toContain("No eligible aligned analyst consensus.");
  expect(html).not.toContain("Consensus uses the selected provider only.");
  expect(html).toMatch(/Forward rows<\/[^>]+>.*?>0<\/[^>]+>/);
  expect(html).toMatch(/<input[^>]*disabled=""[^>]*aria-label="Chart Revenue/);
});
