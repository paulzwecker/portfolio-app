import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { portfolioFixture, iso } from "../../../../e2e/fixtures/portfolio";
import { isOverview } from "@/lib/domain-contracts";
import { HoldingsConfirmation } from "./holdings-confirmation";

const publicationId = "30000000-0000-4000-8000-000000000001";
function owned() {
  const view = portfolioFixture();
  if (!view.snapshot) throw new Error("Synthetic snapshot required");
  view.snapshot.source = `portfolio-ledger-publication-v1:${publicationId}`;
  view.snapshot.actor = "LOCAL_USER";
  view.holdings_authority = {
    source: "ACCEPTED_LEDGER",
    publication_id: publicationId,
    opening_snapshot_id: "40000000-0000-4000-8000-000000000001",
    cutover_at: iso,
  };
  return view;
}
it("preserves ordinary snapshot display and validates explicit ledger ownership", () => {
  expect(isOverview(portfolioFixture())).toBe(true);
  expect(isOverview(owned())).toBe(true);
});
it.each(["source", "publication", "cutoff", "actor", "snapshot"])(
  "rejects contradictory holdings authority %s",
  (field) => {
    const view = owned();
    if (field === "source")
      Object.assign(view.holdings_authority!, { source: "UNKNOWN" });
    if (field === "publication")
      view.holdings_authority!.publication_id =
        "50000000-0000-4000-8000-000000000001";
    if (field === "cutoff") view.holdings_authority!.cutover_at = null;
    if (field === "actor") view.snapshot!.actor = "IMPORT";
    if (field === "snapshot") view.snapshot = null;
    expect(isOverview(view)).toBe(false);
  },
);
it("requires observed ownership metadata to have no ledger publication fields", () => {
  const view = portfolioFixture();
  view.holdings_authority = {
    source: "OBSERVED_SNAPSHOT",
    publication_id: null,
    opening_snapshot_id: null,
    cutover_at: null,
  };
  expect(isOverview(view)).toBe(true);
  view.holdings_authority.publication_id = publicationId;
  expect(isOverview(view)).toBe(false);
});
it("replaces manual snapshot editing with ledger provenance and history navigation", () => {
  const html = renderToStaticMarkup(
    <HoldingsConfirmation overview={owned()} onSaved={() => {}} />,
  );
  expect(html).toContain("Ledger-owned holdings");
  expect(html).toContain(publicationId);
  expect(html).toContain('href="/portfolio/ledger"');
  expect(html).not.toContain("<input");
  expect(html).not.toContain("<textarea");
});

it("requires ownership evidence for a publication-labelled snapshot", () => {
  const view = owned();
  view.holdings_authority = null;
  expect(isOverview(view)).toBe(false);
});
