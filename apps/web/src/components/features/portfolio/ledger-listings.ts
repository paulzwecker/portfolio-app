import {
  isRecord,
  type PortfolioLedgerAnchor,
  type PortfolioLedgerPreview,
} from "@/lib/domain-contracts";
import type { LedgerReviewFile } from "./portfolio-ledger-data";

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
const keys: (keyof LedgerListing)[] = [
  "listing_id",
  "security_id",
  "company_id",
  "ticker",
  "venue",
  "currency",
  "security_type",
  "identity_source_ref",
];
export const sameLedgerListing = (a: LedgerListing, b: LedgerListing) =>
  keys.every((key) => a[key] === b[key]);
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
/** Never modify anchor identities; reject inconsistent repeated identity snapshots. */
export function ledgerAvailableListings(
  anchor: PortfolioLedgerAnchor,
  extra: readonly LedgerListing[] = [],
): LedgerListing[] {
  const items = new Map(
    anchor.listings.map((row) => [row.listing_id.toLowerCase(), row]),
  );
  for (const row of extra) {
    const id = row.listing_id.toLowerCase();
    const previous = items.get(id);
    if (previous && !sameLedgerListing(previous, row))
      throw new Error(
        "Listing identity changed. Reload the anchor and review the source before retrying.",
      );
    items.set(id, previous ?? row);
  }
  return [...items.values()];
}
/** Lookup results consulted by the user must still match identities used in the preview. */
export function selectedListingsMatchPreview(
  file: LedgerReviewFile,
  expected: readonly LedgerListing[],
  report: PortfolioLedgerPreview,
): boolean {
  const packet: unknown = JSON.parse(file.text);
  if (!isRecord(packet)) return false;
  const ids = new Set<string>();
  function collect(rows: unknown) {
    if (!Array.isArray(rows)) return;
    for (const row of rows) {
      if (!isRecord(row)) continue;
      if (typeof row.listing_id === "string")
        ids.add(row.listing_id.toLowerCase());
      if (
        isRecord(row.destination) &&
        typeof row.destination.listing_id === "string"
      )
        ids.add(row.destination.listing_id.toLowerCase());
      if (Array.isArray(row.positions)) collect(row.positions);
    }
  }
  collect(packet.accounts);
  collect(packet.activity);
  if (isRecord(packet.ending_statement))
    collect(packet.ending_statement.accounts);
  if (
    [...ids].some(
      (id) =>
        !report.consumed_listings.some(
          (row) => row.listing_id.toLowerCase() === id,
        ),
    )
  )
    return false;
  return expected
    .filter((row) => ids.has(row.listing_id.toLowerCase()))
    .every((row) => {
      const actual = report.consumed_listings.find(
        (item) =>
          item.listing_id.toLowerCase() === row.listing_id.toLowerCase(),
      );
      return actual !== undefined && sameLedgerListing(row, actual);
    });
}
