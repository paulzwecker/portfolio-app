import {
  isRecord,
  type PortfolioLedgerAnchor,
  type PortfolioLedgerPreview,
} from "@/lib/domain-contracts";
import type { LedgerReviewFile } from "./portfolio-ledger-data";

export { isLedgerListingSearch } from "@/lib/ledger-listing-contracts";
export type {
  LedgerListing,
  LedgerListingSearch,
  LedgerListingSearchItem,
} from "@/lib/ledger-listing-contracts";
import type { LedgerListing } from "@/lib/ledger-listing-contracts";
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
