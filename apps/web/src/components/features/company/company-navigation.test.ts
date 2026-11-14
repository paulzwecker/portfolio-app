import { describe, expect, it } from "vitest";
import {
  companyResearchHref,
  selectedCompanyListing,
} from "./company-navigation";
import type { CompanyDetail } from "@/lib/domain-contracts";
const detail = {
  listings: [{ id: "first" }, { id: "held" }],
  positions: [{ listing_id: "held" }],
} as CompanyDetail;
describe("research listing navigation", () => {
  it("defaults to a held identity and honors another canonical listing", () => {
    expect(selectedCompanyListing(detail, null)).toBe("held");
    expect(selectedCompanyListing(detail, "first")).toBe("first");
    expect(selectedCompanyListing(detail, "foreign-company-listing")).toBe(
      "held",
    );
    expect(
      selectedCompanyListing(
        { ...detail, listings: [], positions: [] },
        "held",
      ),
    ).toBe("");
  });
  it("keeps company, listing and portfolio origin across research views without accepting a return URL", () => {
    const url = new URL(
      companyResearchHref("company", {
        listingId: "held",
        fromPortfolio: true,
        view: "history",
      }),
      "https://example.test",
    );
    expect(url.pathname).toBe("/company/company");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      listing: "held",
      from: "portfolio",
      view: "history",
    });
    expect(companyResearchHref("company")).toBe("/company/company");
  });
});
