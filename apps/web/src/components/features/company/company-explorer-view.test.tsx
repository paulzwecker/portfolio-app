import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  CompanyViewTabs,
  companyViewFromLocation,
} from "@/components/features/company/company-view-tabs";
import {
  compareThesisRevisions,
  reportedFactPeriodLabel,
  thesisClaimGroupLabel,
  thesisEvidenceCounts,
} from "@/components/features/company/company-investment-thesis";
import type {
  InvestmentThesisClaim,
  InvestmentThesisRevision,
} from "@/lib/domain-contracts";
import { FinancialOutputComparison } from "@/components/features/modeling/financial-output-comparison";

describe("Company Explorer view contracts", () => {
  it("routes legacy section links into their focused company views", () => {
    expect(companyViewFromLocation("", "#canonical-models")).toBe("valuation");
    expect(companyViewFromLocation("", "#source-documents")).toBe("research");
    expect(companyViewFromLocation("", "#reported-fundamentals")).toBe(
      "financials",
    );
    expect(companyViewFromLocation("?view=history", "#canonical-models")).toBe(
      "history",
    );
    expect(companyViewFromLocation("?view=unknown", "")).toBe("overview");
  });

  it("exposes an accessible tablist with selected state and panel connection", () => {
    const html = renderToStaticMarkup(
      <CompanyViewTabs value="financials" onChange={() => undefined} />,
    );
    expect(html).toContain('role="tablist"');
    expect(html).toContain('aria-label="Company research views"');
    expect(html).toContain('id="company-tab-financials"');
    expect(html).toContain('aria-selected="true"');
    expect(html).toContain('aria-controls="company-view-panel"');
  });

  it("labels linked actuals without duplicating fiscal-year markers", () => {
    expect(reportedFactPeriodLabel(2024, "FY")).toBe("FY2024");
    expect(reportedFactPeriodLabel(2024, "Q2")).toBe("FY2024 · Q2");
    expect(reportedFactPeriodLabel(null, null)).toBe("Period unavailable");
  });

  it("keeps thesis claim categories and evidence relationships explicit", () => {
    const claim = {
      id: "00000000-0000-0000-0000-000000000001",
      claim_key: "renewal-economics",
      claim_type: "COMPETITIVE_ADVANTAGE",
      status: "UNDER_REVIEW",
      statement: "Renewals may reinforce switching costs.",
      confidence: "MEDIUM",
      uncertainty: "Cohort data is incomplete.",
      evidence: [
        {
          id: "00000000-0000-0000-0000-000000000002",
          relationship: "SUPPORTS",
        },
        {
          id: "00000000-0000-0000-0000-000000000003",
          relationship: "CONTRADICTS",
        },
        {
          id: "00000000-0000-0000-0000-000000000004",
          relationship: "CONTEXT",
        },
      ],
    } as InvestmentThesisClaim;
    expect(thesisClaimGroupLabel(claim.claim_type)).toBe(
      "Advantage & durability",
    );
    expect(thesisEvidenceCounts(claim)).toEqual({
      supporting: 1,
      contradicting: 1,
      context: 1,
    });
  });

  it("shows append-only thesis revision deltas by stable claim key", () => {
    const base = {
      id: "00000000-0000-0000-0000-000000000001",
      claims: [
        {
          id: "00000000-0000-0000-0000-000000000011",
          claim_key: "durability",
          claim_type: "DURABILITY",
          status: "ACTIVE",
          statement: "Durability is supported.",
          confidence: "MEDIUM",
          uncertainty: null,
          evidence: [],
        },
      ],
    } as unknown as InvestmentThesisRevision;
    const next = {
      ...base,
      id: "00000000-0000-0000-0000-000000000002",
      claims: [
        { ...base.claims[0], statement: "Durability remains supported." },
        {
          ...base.claims[0],
          id: "00000000-0000-0000-0000-000000000012",
          claim_key: "open-question",
          claim_type: "UNRESOLVED_QUESTION",
          statement: "Can retention remain stable?",
        },
      ],
    } as unknown as InvestmentThesisRevision;
    const delta = compareThesisRevisions(next, base);
    expect(delta.changed).toHaveLength(1);
    expect(delta.added).toHaveLength(1);
    expect(delta.removed).toHaveLength(0);
    expect(delta.unchanged).toBe(0);

    const evidenceRevision = {
      ...base,
      id: "00000000-0000-0000-0000-000000000003",
      claims: [
        {
          ...base.claims[0],
          evidence: [
            {
              id: "00000000-0000-0000-0000-000000000013",
              relationship: "SUPPORTS",
              source_name: "Issuer filing",
            },
          ],
        },
      ],
    } as unknown as InvestmentThesisRevision;
    const evidenceDelta = compareThesisRevisions(evidenceRevision, base);
    expect(evidenceDelta.changed).toHaveLength(0);
    expect(evidenceDelta.evidenceChanged).toHaveLength(1);
  });

  it("uses one normalized output presentation for the supported model families", () => {
    const output = {
      bear_fv: "70",
      base_fv: "100",
      bull_fv: "130",
      weighted_fv: "100",
      weighted_upside: "0.1",
      expected_cash_flow_irr: null,
      hurdle: "0.12",
      expected_excess: null,
    } as const;
    const html = renderToStaticMarkup(
      <FinancialOutputComparison
        output={output}
        previous={{ ...output, base_fv: "95" }}
        currency="USD"
      />,
    );
    expect(html).toContain("Bear fair value");
    expect(html).toContain("$70.00");
    expect(html).toContain("$95.00");
    expect(html).toContain("Changed");
    expect(html).toContain("No target");
    expect(html).toContain("No target");
  });
});
