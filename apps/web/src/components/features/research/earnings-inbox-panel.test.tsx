import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { EarningsInboxPanel } from "./earnings-inbox-panel";

vi.mock("@/hooks/use-research", () => ({
  useResearch: (path: string) => ({
    data:
      path === "portfolios"
        ? [{ id: "p", name: "Portfolio" }]
        : {
            snapshot_id: "s",
            effective_at: "2026-10-01T12:00:00Z",
            listing_count: 2,
            modeled_count: 1,
            rows: [
              {
                listing_id: "l",
                company_id: "c",
                company: "Issuer",
                listing: "TEST:A",
                title: "Quarterly results",
                url: "https://issuer.test/q3",
                outcome: "ACCEPTED",
                passage: "Sales grew.",
                proposal_id: "proposal",
                revision_number: 2,
                irr_before: "0.14",
                irr_after: "0.15",
                impact_bps: "100",
                crosses_hurdle: true,
                decision_note: "Accepted the revised assumption.",
              },
              {
                listing_id: "etf",
                company_id: null,
                listing: "TEST:ETF",
                url: null,
                revision_number: null,
              },
            ],
          },
  }),
}));

it("shows cited decisions, same-price hurdle crossings, and issuerless coverage", () => {
  const html = renderToStaticMarkup(<EarningsInboxPanel />);
  expect(html).toContain("Sales grew.");
  expect(html).toContain("14.00% → 15.00%");
  expect(html).toContain("Crosses 15% hurdle");
  expect(html).toContain("Accepted the revised assumption.");
  expect(html).toContain("proposal=proposal#model-proposals-title");
  expect(html).toContain("TEST:ETF");
  expect(html).not.toContain("/company/null");
});

it("offers the earnings release check from the holdings inbox", () => {
  const html = renderToStaticMarkup(<EarningsInboxPanel />);
  expect(html).toContain("Check for new releases");
  expect(html).toContain("Issuer release drafts");
});
