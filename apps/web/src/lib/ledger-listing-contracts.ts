import { isRecord, type PortfolioLedgerAnchor } from "@/lib/domain-contracts";

export type LedgerListing = PortfolioLedgerAnchor["listings"][number];
export type LedgerListingSearchItem = LedgerListing & {
  security_name: string;
  share_class: string | null;
  company_name: string | null;
  is_demo: boolean;
};
export type LedgerListingSearch = {
  results: LedgerListingSearchItem[];
  truncated: boolean;
  unsupported_results: boolean;
};
const uuid = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
export function isLedgerListingSearch(
  value: unknown,
): value is LedgerListingSearch {
  if (
    !isRecord(value) ||
    typeof value.truncated !== "boolean" ||
    typeof value.unsupported_results !== "boolean" ||
    !Array.isArray(value.results) ||
    value.results.length > 50
  )
    return false;
  const ids = new Set<string>();
  return value.results.every((row: unknown) => {
    if (
      !isRecord(row) ||
      typeof row.listing_id !== "string" ||
      !uuid.test(row.listing_id) ||
      ids.has(row.listing_id.toLowerCase()) ||
      typeof row.security_id !== "string" ||
      !uuid.test(row.security_id) ||
      !(
        row.company_id === null ||
        (typeof row.company_id === "string" && uuid.test(row.company_id))
      ) ||
      typeof row.ticker !== "string" ||
      !row.ticker ||
      typeof row.venue !== "string" ||
      !row.venue ||
      typeof row.currency !== "string" ||
      !/^[A-Z]{3}$/.test(row.currency) ||
      !["COMMON_STOCK", "ADR", "PREFERRED", "ETF"].includes(
        row.security_type as string,
      ) ||
      (row.security_type === "ETF") !== (row.company_id === null) ||
      !(
        row.identity_source_ref === null ||
        typeof row.identity_source_ref === "string"
      ) ||
      typeof row.security_name !== "string" ||
      typeof row.is_demo !== "boolean" ||
      !(row.share_class === null || typeof row.share_class === "string") ||
      !(row.company_name === null || typeof row.company_name === "string")
    )
      return false;
    ids.add(row.listing_id.toLowerCase());
    return true;
  });
}
