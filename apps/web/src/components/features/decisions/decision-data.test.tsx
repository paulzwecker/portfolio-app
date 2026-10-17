import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  allocationPresence,
  type DecisionOpportunity,
} from "@/components/features/decisions/decision-data";
import {
  ReturnComparison,
  groupByReturnCohort,
} from "@/components/features/decisions/return-comparison";
import type { CompanyPortfolioContext, Overview } from "@/lib/domain-contracts";

const company = {
  id: "10000000-0000-4000-8000-000000000001",
  name: "Example Co",
  reporting_currency: "USD",
  is_demo: false,
  created_at: "2026-10-01T00:00:00Z",
  lifecycle: "PORTFOLIO",
  lifecycle_event_id: null,
};

function allocationRow({
  positions = [],
  target_weight = null,
}: {
  positions?: CompanyPortfolioContext["positions"];
  target_weight?: string | null;
} = {}) {
  return {
    company,
    positions,
    target_weight,
    current_market_value: null,
    current_market_currency: "EUR",
    current_weight: null,
    allocation_gap: null,
    allocation_status: "PORTFOLIO_TOTAL_UNAVAILABLE",
  } as CompanyPortfolioContext;
}

function overview({
  completeness = "COMPLETE",
}: {
  completeness?: "COMPLETE" | "PARTIAL" | "UNAVAILABLE";
} = {}) {
  return {
    snapshot: completeness === "UNAVAILABLE" ? null : { completeness },
  } as Overview;
}

function opportunity({
  id,
  cohort,
  expectedIrr = null,
  targetWeight = null,
}: {
  id: string;
  cohort: string | null;
  expectedIrr?: string | null;
  targetWeight?: string | null;
}) {
  return {
    company: { ...company, id, name: `Company ${id.slice(-1)}` },
    ranking: undefined,
    kind: "PORTFOLIO",
    rankPosition: null,
    rankStatus: "DATA_CHECK",
    rankReason: "A source input needs review.",
    asOf: "2026-10-15T12:00:00Z",
    returnCohort: cohort,
    methodology: null,
    expectedIrr,
    hurdle: null,
    expectedExcess: null,
    weightedFairValue: null,
    fairValueCurrency: null,
    durability: null,
    compounderQuality: null,
    currentWeight: null,
    targetWeight,
    allocationGap: null,
    modelStatus: null,
    outputs: undefined,
    scores: undefined,
    execution: null,
  } as DecisionOpportunity;
}

describe("decision comparison presentation", () => {
  it("distinguishes held zero-target positions, target-only rows, and unconfirmed holdings", () => {
    const held = allocationRow({
      positions: [
        {
          listing_id: "20000000-0000-4000-8000-000000000001",
        } as CompanyPortfolioContext["positions"][number],
      ],
      target_weight: "0",
    });
    const targetOnly = allocationRow({ target_weight: "0.05" });

    expect(allocationPresence(held, overview())).toBe("HELD");
    expect(allocationPresence(targetOnly, overview())).toBe("TARGET_ONLY");
    expect(
      allocationPresence(
        allocationRow(),
        overview({ completeness: "PARTIAL" }),
      ),
    ).toBe("HOLDINGS_UNCONFIRMED");
  });

  it("keeps distinct methodology cohorts separate and isolates unclassified returns", () => {
    const rows = [
      opportunity({
        id: "10000000-0000-4000-8000-000000000001",
        cohort: "UFCF_EQUITY",
      }),
      opportunity({
        id: "10000000-0000-4000-8000-000000000002",
        cohort: "OWNER_CASH_EQUITY",
      }),
      opportunity({ id: "10000000-0000-4000-8000-000000000003", cohort: null }),
    ];
    const groups = groupByReturnCohort(rows);

    expect(groups.cohorts.map(([cohort]) => cohort)).toEqual([
      "UFCF_EQUITY",
      "OWNER_CASH_EQUITY",
    ]);
    expect(groups.unclassified).toHaveLength(1);
  });

  it("keeps missing IRR and missing target explicit in the comparison view", () => {
    const html = renderToStaticMarkup(
      <ReturnComparison
        title="Portfolio Rank"
        description="Rank snapshot context."
        rows={[
          opportunity({
            id: "10000000-0000-4000-8000-000000000001",
            cohort: null,
            expectedIrr: null,
            targetWeight: null,
          }),
        ]}
        onSelect={() => undefined}
      />,
    );

    expect(html).toContain("No comparable return cohort");
    expect(html).toContain("IRR Unavailable");
    expect(html).toContain("No target");
    expect(html).not.toContain("IRR 0%");
  });
});
