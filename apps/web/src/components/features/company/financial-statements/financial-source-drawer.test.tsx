import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { ConsensusEstimateObservation } from "@/lib/domain-contracts";
import { ConsensusSource } from "./financial-source-drawer";

// Fictional values; authentic provider captures never enter this repository.
const observation: ConsensusEstimateObservation = {
  id: "11111111-1111-4111-8111-111111111111",
  company_id: "22222222-2222-4222-8222-222222222222",
  listing_id: null,
  provider_mapping_id: "33333333-3333-4333-8333-333333333333",
  provider_id: "eodhd_demo_estimates",
  metric: "REVENUE",
  period_type: "ANNUAL",
  forecast_period: "FY2027",
  period_end: "2027-12-31",
  value: "120",
  low_value: "100",
  high_value: "140",
  analyst_count: 12,
  currency: "USD",
  unit: "CURRENCY",
  snapshot_date: "2026-11-15",
  observed_at: "2026-11-15T00:00:00Z",
  recorded_at: "2026-11-15T01:00:00Z",
  source_record_id: "FICTIONAL:annual",
  source_ref: "https://example.invalid/fictional-estimates#FY2027",
  revision_context: "SNAPSHOT",
  data_quality: "PASS",
  quality_reason: null,
  supersedes_observation_id: null,
};

it("shows the genuine range, coverage, fiscal identity and source timestamp separately", () => {
  const html = renderToStaticMarkup(<ConsensusSource item={observation} />);
  expect(html).toContain(
    "EODHD demo · private evaluation · REVENUE · FY2027 · ends 2027-12-31",
  );
  expect(html).toContain("Analyst range: 100 – 140 USD");
  expect(html).toContain("12 analysts · snapshot 2026-11-15 · SNAPSHOT");
  expect(html).toContain("Observed");
  expect(html).toContain("recorded");
  expect(html).toContain(
    'href="https://example.invalid/fictional-estimates#FY2027"',
  );
});

it("keeps missing ranges and coverage unavailable instead of substituting zero", () => {
  const html = renderToStaticMarkup(
    <ConsensusSource
      item={{
        ...observation,
        low_value: null,
        high_value: null,
        analyst_count: null,
      }}
    />,
  );
  expect(html).toContain("Analyst range: Unavailable – Unavailable USD");
  expect(html).toContain("Unknown analysts");
  expect(html).not.toContain("0 analysts");
});

it("retains a source-supported zero and EPS comparability warning", () => {
  const html = renderToStaticMarkup(
    <ConsensusSource
      item={{
        ...observation,
        metric: "EPS",
        value: "0",
        low_value: "-1",
        high_value: "1",
        unit: "CURRENCY_PER_SHARE",
        data_quality: "DATA_CHECK",
        quality_reason: "EPS accounting basis is not independently verified.",
      }}
    />,
  );
  expect(html).toContain("0 USD");
  expect(html).toContain("Analyst range: -1 – 1 USD / share");
  expect(html).toContain("EPS accounting basis is not independently verified.");
});
