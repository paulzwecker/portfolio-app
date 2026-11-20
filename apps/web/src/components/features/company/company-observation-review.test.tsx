import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ObservationProposalReview } from "@/components/features/company/company-observation-review";
import {
  isObservationProposalRead,
  isObservationProposalList,
  isObservationProposalPreviewRead,
  isObservationProposalDecisionRead,
} from "@/lib/domain-contracts";

const id = "11111111-1111-4111-8111-111111111111";
const item = {
  metric_key: "synthetic.trips",
  source_reference: "https://example.com/disclosure",
};
const proposal = {
  id,
  producer_id: "synthetic-agent",
  content_fingerprint: "a".repeat(64),
  status: "PENDING",
  proposal: {
    contract_type: "KPIObservationBatchV1",
    contract_version: "1.0.0",
    company_id: id,
    external_batch_id: "synthetic-q3",
    authored_at: "2026-11-19T12:00:00Z",
    rationale: "Reviewed synthetic source and quarterly actual.",
    items: [item],
  },
  preview_fingerprint: null,
  accepted_record_ids: [],
  issue: null,
  decision_note: null,
  reviewer_id: null,
  submitted_at: "2026-11-19T12:00:00Z",
  reviewed_at: null,
};

describe("Canonical operating observation reviewer contracts", () => {
  it("recognizes typed source-backed candidates and rejects malformed replies", () => {
    expect(isObservationProposalRead(proposal)).toBe(true);
    expect(isObservationProposalList([proposal])).toBe(true);
    expect(
      isObservationProposalRead({
        ...proposal,
        proposal: {
          ...proposal.proposal,
          items: [{ ...item, source_reference: "http://insecure.example" }],
        },
      }),
    ).toBe(false);
    expect(
      isObservationProposalRead({
        ...proposal,
        proposal: { ...proposal.proposal, company_id: "wrong" },
      }),
    ).toBe(false);
  });

  it("requires a valid deterministic fingerprint to enable acceptance", () => {
    const preview = {
      proposal_id: id,
      status: "READY",
      changes: [
        {
          row_index: 0,
          metric_key: "synthetic.trips",
          operation: "CREATE",
          previous_id: null,
        },
      ],
      issues: [],
      preview_fingerprint: "b".repeat(64),
    };
    expect(isObservationProposalPreviewRead(preview)).toBe(true);
    expect(
      isObservationProposalPreviewRead({
        ...preview,
        preview_fingerprint: "wrong",
      }),
    ).toBe(false);
    expect(
      isObservationProposalDecisionRead({ status: "ACCEPTED", proposal }),
    ).toBe(true);
    expect(
      isObservationProposalDecisionRead({ status: "AUTO_ACCEPT", proposal }),
    ).toBe(false);
  });

  it("does not present a write button before a reviewer queue is loaded", () => {
    const html = renderToStaticMarkup(
      <ObservationProposalReview companyId={id} />,
    );
    expect(html).toContain("Operating data proposals");
    expect(html).toContain("Loading the review queue");
    expect(html).not.toContain("Accept reviewed facts");
    expect(html).not.toContain("Confirm acceptance");
  });
});
