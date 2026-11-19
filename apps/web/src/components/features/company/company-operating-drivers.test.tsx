import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  OperatingDriversPanel,
  actualVsDriver,
  actualVsGuidance,
  operatingMetricPeriods,
} from "@/components/features/company/company-operating-drivers";
import type { CompanyAgentContext } from "@/lib/domain-contracts";
import { companyViewFromLocation } from "@/components/features/company/company-view-tabs";

type Actual = CompanyAgentContext["metric_observations"][number];
type Guidance = CompanyAgentContext["guidance_observations"][number];
type Driver = CompanyAgentContext["native_models"][number]["driver_projections"][number];

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
} as Actual;

const guidance = {
  id: "guidance-1",
  ...actual,
  lower_value: "4000",
  upper_value: "4200",
  midpoint_value: null,
  value_qualifier: "RANGE",
  status: "ACTIVE",
} as unknown as Guidance;

const driver = {
  id: "model-driver-1",
  ...actual,
  scenario: "BASE",
  value: "4000",
  value_qualifier: "EQ",
  forecast_year: 1,
  rationale: "Test projection supported by source",
} as Driver;

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
    expect(companyViewFromLocation("", "#management-guidance")).toBe("operating");
  });

  it("only compares exact same unit, currency, period and scope", () => {
    expect(actualVsGuidance(actual, guidance)).toBe("WITHIN");
    expect(actualVsDriver(actual, driver)).toBe("ABOVE");
    expect(actualVsGuidance({ ...actual, value: "4300" }, guidance)).toBe("ABOVE");
    expect(actualVsGuidance({ ...actual, value: "3900" }, guidance)).toBe("BELOW");
    expect(actualVsDriver({ ...actual, value: "4000" }, driver)).toBe("ON");
    expect(actualVsGuidance({ ...actual, scale: "1000" }, guidance)).toBeNull();
    expect(actualVsDriver({ ...actual, currency: "USD" }, driver)).toBeNull();
    expect(actualVsDriver({ ...actual, period_end: "2026-10-31" }, driver)).toBeNull();
    expect(actualVsGuidance({ ...actual, scope_json: { region: "USA" } }, guidance)).toBeNull();
    expect(actualVsGuidance({ ...actual, quality_status: "PROVISIONAL" }, guidance)).toBeNull();
    expect(actualVsGuidance({ ...actual, value_qualifier: "GT" }, guidance)).toBeNull();
    expect(actualVsGuidance(actual, { ...guidance, value_qualifier: "APPROX" })).toBeNull();
  });

  it("groups data by economic period instead of mixing future guidance with prior actuals", () => {
    const payload = context();
    payload.guidance_observations = [{ ...guidance, period_start: "2026-10-01", period_end: "2026-12-31" }];
    const groups = operatingMetricPeriods(payload, "uber.trips");
    expect(groups).toHaveLength(2);
    expect(groups[0].periodEnd).toBe("2026-12-31");
    expect(groups[0].actuals).toHaveLength(0);
    expect(groups[0].guidance).toHaveLength(1);
    expect(groups[1].drivers).toHaveLength(1);
  });

  it("shows source-backed actuals, guidance and accepted scenario without synthesizing values", () => {
    const html = renderToStaticMarkup(<OperatingDriversPanel context={context()} />);
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
    const html = renderToStaticMarkup(<OperatingDriversPanel context={payload} />);
    expect(html).toContain("Partial coverage or missing metric definitions");
    expect(html).toContain("No accepted operating metric definitions");
    expect(html).not.toContain("4,061");
  });
});
