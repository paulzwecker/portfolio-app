import { describe, expect, it } from "vitest";
import {
  buildResearchActivity,
  filterResearchActivity,
  researchActivityIsRecent,
  type ResearchActivityItem,
} from "./company-research-evidence-workspace";

const now = new Date("2026-10-17T12:00:00Z");

function item(
  overrides: Partial<ResearchActivityItem> = {},
): ResearchActivityItem {
  return {
    id: "item",
    category: "FILINGS",
    title: "Item",
    summary: "Summary",
    effectiveAt: "2026-10-16T12:00:00Z",
    recordedAt: "2026-10-16T12:01:00Z",
    sourceLabel: "Reported source",
    sourceUrl: null,
    status: "PASS",
    detail: { kind: "DOCUMENT", document: {} as never },
    ...overrides,
  };
}

describe("company research evidence activity", () => {
  it("keeps undated evidence visible in the all-dates view but excludes it from a bounded recency window", () => {
    expect(
      researchActivityIsRecent(
        item({ effectiveAt: null, recordedAt: null }),
        null,
        now,
      ),
    ).toBe(true);
    expect(
      researchActivityIsRecent(
        item({ effectiveAt: null, recordedAt: null }),
        30,
        now,
      ),
    ).toBe(false);
  });

  it("filters by evidence category and orders effective records newest first", () => {
    const records = [
      item({ id: "old", effectiveAt: "2026-09-01T12:00:00Z" }),
      item({
        id: "risk",
        category: "RISKS",
        effectiveAt: "2026-10-17T08:00:00Z",
      }),
      item({ id: "new", effectiveAt: "2026-10-17T10:00:00Z" }),
    ];
    expect(
      filterResearchActivity(records, "FILINGS", "ALL", now).map((x) => x.id),
    ).toEqual(["new", "old"]);
    expect(
      filterResearchActivity(records, "RISKS", "ALL", now).map((x) => x.id),
    ).toEqual(["risk"]);
    expect(
      filterResearchActivity(records, "ALL", "30", now).map((x) => x.id),
    ).toEqual(["new", "risk"]);
  });

  it("builds separate activity records for reported sources, interpretations, accepted risks and triggers", () => {
    const activity = buildResearchActivity({
      documents: [
        {
          id: "11111111-1111-4111-8111-111111111111",
          title: "Annual report",
          document_type: "ANNUAL_REPORT",
          source_name: "Issuer",
          filed_at: "2026-10-10",
          published_at: "2026-10-10",
          recorded_at: "2026-10-11T00:00:00Z",
          canonical_url: "https://issuer.example/report",
          data_quality: "PASS",
        } as never,
      ],
      researchRevisions: [
        {
          id: "22222222-2222-4222-8222-222222222222",
          revision_number: 1,
          stream_key: "agent",
          rationale: "Interpretation",
          observed_at: "2026-10-09T00:00:00Z",
          recorded_at: "2026-10-09T01:00:00Z",
          source_reference: "https://sheets.example/revision",
          status: "PUBLISHED",
        } as never,
      ],
      riskRevisions: [
        {
          id: "33333333-3333-4333-8333-333333333333",
          revision_number: 1,
          summary: "Risk",
          accepted_at: "2026-10-08T00:00:00Z",
          recorded_at: "2026-10-08T01:00:00Z",
          source_reference: "https://sheets.example/risk",
          findings: [],
          baseline_status_at_accept: "CURRENT",
        } as never,
      ],
      triggers: [
        {
          id: "44444444-4444-4444-8444-444444444444",
          title: "New filing",
          reason: "Review it",
          effective_at: "2026-10-07T00:00:00Z",
          source_recorded_at: "2026-10-07T01:00:00Z",
          detected_at: "2026-10-07T01:00:00Z",
          processing_state: "OPEN",
          source_reference: "https://issuer.example/filing",
        } as never,
      ],
    });
    expect(activity.map((record) => record.category)).toEqual([
      "FILINGS",
      "RESEARCH",
      "RISKS",
      "TRIGGERS",
    ]);
    expect(activity.map((record) => record.sourceLabel)).toEqual([
      "Reported source",
      "Research interpretation",
      "Accepted qualitative risk",
      "Deterministic evidence trigger",
    ]);
  });
});
