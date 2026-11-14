import type { CompanyDetail } from "@/lib/domain-contracts";
import type { CompanyView } from "./company-view-tabs";

/** Only canonical company/listing identity and a known portfolio origin enter links. */
export function companyResearchHref(
  companyId: string,
  options: {
    listingId?: string | null;
    fromPortfolio?: boolean;
    view?: CompanyView;
  } = {},
) {
  const query = new URLSearchParams();
  if (options.view) query.set("view", options.view);
  if (options.listingId) query.set("listing", options.listingId);
  if (options.fromPortfolio) query.set("from", "portfolio");
  return `/company/${encodeURIComponent(companyId)}${query.size ? `?${query}` : ""}`;
}

export function selectedCompanyListing(
  detail: CompanyDetail,
  requested: string | null,
) {
  if (detail.listings.some((listing) => listing.id === requested))
    return requested!;
  const held = detail.positions.find((position) =>
    detail.listings.some((listing) => listing.id === position.listing_id),
  );
  return held?.listing_id ?? detail.listings[0]?.id ?? "";
}
