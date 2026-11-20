import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  OperatingDriversPanel,
  actualVsDriver,
  actualVsGuidance,
  operatingMetricPeriods,
  operatingBaseReviewSignals,
} from "@/components/features/company/company-operating-drivers";
import type { CompanyAgentContext } from "@/lib/domain-contracts";
import { companyViewFromLocation } from "@/components/features/company/company-view-tabs";

type Actual = CompanyAgentContext["metric_observations"][number];
type Guidance = CompanyAgentContext["guidance_observations"][number];
type Driver =
  CompanyAgentContext["native_models"][number]["driver_projections"][number];

const actual = {
  id: "actual-1",
  metric_id: "uber.trips",
  period_type: "QUARTER",
  period_start: "2026-07-01",
  period_end: "2026-09-30",
  scope_json: {},
  scale: "1000000",
  currency: null,
  unit: "trips",
  value: "4061",
  value_qualifier: "EQ",
  quality_status: "VERIFIED",
  basis: "REPORTED",
  is_current: true,
  source_reference: "https://example.com/source",
  reported_at: "2026-11-04T15:00:00Z",
  recorded_at: "2026-11-04T15:05:00Z",
} as Actual;

const guidance = {
  ...actual,
  id: "guidance-1",
  lower_value: "4000",
  upper_value: "4200",
  midpoint_value: null,
  value_qualifier: "RANGE",
  status: "ACTIVE",
  recorded_at: "2026-10-15T15:00:00Z",
} as unknown as Guidance;

const driver = {
  ...actual,
  id: "model-driver-1",
  scenario: "BASE",
  value: "4000",
  value_qualifier: "EQ",
  forecast_year: 1,
  rationale: "Test projection supported by source",
  recorded_at: "2026-10-15T15:00:00Z",
} as unknown as Driver;

function context(): CompanyAgentContext {
  return {
    contract_type: "CompanyAgentContextV1",
    contract_version: "1.0.0",
    metric_definitions: [
      {
        id: "definition-1",
        metric_id: "uber.trips",
        display_name: "Trips",
        description: "Completed platform journeys",
        canonical_unit: "trips",
        canonical_scale: "1000000",
      },
    ],
    metric_observations: [actual],
    guidance_observations: [guidance],
    native_models: [
      {
        model_name: "10Y UFCF",
        accepted_revision: { revision_number: 3 },
        driver_projections: [driver],
      },
    ],
    consensus_periods: [],
    metrics_status: { status: "AVAILABLE", truncated: false },
    guidance_status: { status: "AVAILABLE", truncated: false },
    native_models_status: { status: "AVAILABLE", truncated: false },
    consensus_status: { status: "NO_DATA", truncated: false },
    consensus_provider_id: null,
    consensus_continuity_status: "NO_MAPPING",
  } as unknown as CompanyAgentContext;
}

describe("Operating KPI performance and accepted driver assumptions", () => {
  it("uses a dedicated company tab and legacy deep links", () => {
    expect(companyViewFromLocation("?view=operating", "")).toBe("operating");
    expect(companyViewFromLocation("", "#management-guidance")).toBe(
      "operating",
    );
  });

  it("only compares exact same unit, currency, period and scope", () => {
    expect(actualVsGuidance(actual, guidance)).toBe("WITHIN");
    expect(actualVsDriver(actual, driver)).toBe("ABOVE");
    expect(actualVsGuidance({ ...actual, value: "4300" }, guidance)).toBe(
      "ABOVE",
    );
    expect(actualVsGuidance({ ...actual, value: "3900" }, guidance)).toBe(
      "BELOW",
    );
    expect(actualVsDriver({ ...actual, value: "4000" }, driver)).toBe("ON");
    expect(
      actualVsDriver(
        { ...actual, scope_json: { region: "US", product: "Core" } },
        { ...driver, scope_json: { product: "Core", region: "US" } },
      ),
    ).toBe("ABOVE");
    expect(actualVsGuidance({ ...actual, scale: "1000" }, guidance)).toBeNull();
    expect(actualVsDriver({ ...actual, currency: "USD" }, driver)).toBeNull();
    expect(
      actualVsDriver({ ...actual, period_end: "2026-10-31" }, driver),
    ).toBeNull();
    expect(
      actualVsGuidance({ ...actual, scope_json: { region: "USA" } }, guidance),
    ).toBeNull();
    expect(
      actualVsGuidance({ ...actual, quality_status: "PROVISIONAL" }, guidance),
    ).toBeNull();
    expect(
      actualVsGuidance({ ...actual, value_qualifier: "GT" }, guidance),
    ).toBeNull();
    expect(
      actualVsGuidance(actual, { ...guidance, value_qualifier: "APPROX" }),
    ).toBeNull();
    expect(
      actualVsGuidance(actual, {
        ...guidance,
        recorded_at: "2026-11-05T00:00:00Z",
      }),
    ).toBeNull();
    expect(
      actualVsGuidance(actual, { ...guidance, status: "WITHDRAWN" }),
    ).toBeNull();
    expect(
      actualVsDriver(actual, {
        ...driver,
        recorded_at: "2026-11-05T00:00:00Z",
      }),
    ).toBeNull();
    expect(actualVsGuidance({ ...actual, reported_at: null }, guidance)).toBeNull();
    expect(actualVsDriver({ ...actual, reported_at: null }, driver)).toBeNull();
    expect(
      actualVsGuidance(actual, {
        ...guidance,
        issued_at: "2026-11-04T15:00:00Z",
      }),
    ).toBeNull();
    expect(
      actualVsGuidance(actual, {
        ...guidance,
        issued_at: "2026-11-04T15:01:00Z",
      }),
    ).toBeNull();
    expect(
      actualVsGuidance(actual, {
        ...guidance,
        issued_at: "2026-10-15T15:00:00Z",
        recorded_at: "2026-11-06T12:00:00Z",
      }),
    ).toBeNull();
    expect(
      actualVsGuidance(actual, { ...guidance, is_current: false }),
    ).toBeNull();

    expect(
      actualVsGuidance(
        { ...actual, value: "9007199254740993.000000000001" },
        {
          ...guidance,
          lower_value: "9007199254740993",
          upper_value: "9007199254740993.000000000002",
        },
      ),
    ).toBe("WITHIN");
    expect(
      actualVsDriver(
        { ...actual, value: "9007199254740993.000000000002" },
        { ...driver, value: "9007199254740993.000000000001" },
      ),
    ).toBe("ABOVE");
  });

  it("groups data by economic period instead of mixing future guidance with prior actuals", () => {
    const payload = context();
    payload.guidance_observations = [
      { ...guidance, period_start: "2026-10-01", period_end: "2026-12-31" },
    ];
    const groups = operatingMetricPeriods(payload, "uber.trips");
    expect(groups).toHaveLength(2);
    expect(groups[0].periodEnd).toBe("2026-12-31");
    expect(groups[0].actuals).toHaveLength(0);
    expect(groups[0].guidance).toHaveLength(1);
    expect(groups[1].drivers).toHaveLength(1);
  });

  it("prompts a review only for an unambiguous, prior, comparable BASE miss", () => {
    const payload = context();
    expect(operatingBaseReviewSignals(payload)).toMatchObject([
      {
        metricId: "uber.trips",
        metricName: "Trips",
        periodEnd: "2026-09-30",
        direction: "ABOVE",
        modelName: "10Y UFCF",
        revisionNumber: 3,
        sourceReference: "https://example.com/source",
      },
    ]);
    const html = renderToStaticMarkup(<OperatingDriversPanel context={payload} />);
    expect(html).toContain("Prior BASE assumptions to review");
    expect(html).toContain("Review Trips");
    expect(html).toContain("Verify actual disclosure");
    expect(html).toContain("not valuation changes or trading signals");

    payload.metric_observations = [
      actual,
      { ...actual, id: "actual-2", value: "3900" },
    ];
    expect(operatingBaseReviewSignals(payload)).toHaveLength(0);
    const ambiguous = renderToStaticMarkup(
      <OperatingDriversPanel context={payload} />,
    );
    expect(ambiguous).not.toContain("Actual within guidance range");
    expect(ambiguous).not.toContain("Actual above base case");
    expect(ambiguous).not.toContain("Prior BASE assumptions to review");

    payload.metric_observations = [{ ...actual, reported_at: null }];
    expect(operatingBaseReviewSignals(payload)).toHaveLength(0);
    payload.metric_observations = [actual];
    payload.native_models[0].driver_projections = [
      { ...driver, recorded_at: "2026-11-05T00:00:00Z" },
    ];
    expect(operatingBaseReviewSignals(payload)).toHaveLength(0);
  });

  it("shows source-backed actuals, guidance and accepted scenario without synthesizing values", () => {
    const html = renderToStaticMarkup(
      <OperatingDriversPanel context={context()} />,
    );
    expect(html).toContain("Operating KPIs &amp; model drivers");
    expect(html).toContain("4,061");
    expect(html).toContain("4,000");
    expect(html).toContain("BASE");
    expect(html).toContain("accepted revision 3");
    expect(html).toContain("Actual within guidance range");
    expect(html).toContain("Issuer evidence");
    expect(html).toContain("https://example.com/source");
    expect(html).toContain("No selected provider consensus available.");
  });

  it("makes incomplete coverage and empty KPIs explicit", () => {
    const payload = context();
    payload.metric_definitions = [];
    payload.metric_observations = [];
    payload.guidance_observations = [];
    payload.native_models = [];
    payload.metrics_status.truncated = true;
    const html = renderToStaticMarkup(
      <OperatingDriversPanel context={payload} />,
    );
    expect(html).toContain("Partial coverage or missing metric definitions");
    expect(html).toContain("No accepted operating metric definitions");
    expect(html).not.toContain("4,061");
  });
});
