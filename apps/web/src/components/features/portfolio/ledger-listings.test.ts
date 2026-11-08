import { expect, it } from "vitest";
import { ledgerAnchor, ledgerReport } from "../../../../e2e/fixtures/ledger";
import { inspectLedgerFile } from "./portfolio-ledger-data";
import {
  isLedgerListingSearch,
  ledgerAvailableListings,
  selectedListingsMatchPreview,
} from "./ledger-listings";

const other = {
  ...ledgerAnchor.listings[0],
  listing_id: "99999999-9999-4999-8999-999999999999",
  ticker: "OTHER",
  venue: "NYSE",
  currency: "USD",
  security_id: "77777777-7777-4777-8777-777777777777",
  security_type: "COMMON_STOCK",
  company_id: "88888888-8888-4888-8888-888888888888",
};
const result = {
  results: [
    {
      ...other,
      security_name: "Synthetic common",
      share_class: null,
      company_name: "Synthetic issuer",
      is_demo: false,
    },
  ],
  truncated: false,
  unsupported_results: false,
};
it("validates bounded exact listing search response shape, demo flag and omissions", () => {
  expect(isLedgerListingSearch(result)).toBe(true);
  expect(
    isLedgerListingSearch({ ...result, unsupported_results: undefined }),
  ).toBe(false);
  expect(
    isLedgerListingSearch({
      ...result,
      results: [{ ...result.results[0], is_demo: undefined }],
    }),
  ).toBe(false);
  expect(
    isLedgerListingSearch({
      ...result,
      results: [result.results[0], result.results[0]],
    }),
  ).toBe(false);
  expect(
    isLedgerListingSearch({
      ...result,
      results: [{ ...result.results[0], security_type: "UNKNOWN" }],
    }),
  ).toBe(false);
  expect(
    isLedgerListingSearch({
      ...result,
      results: [{ ...result.results[0], company_id: null }],
    }),
  ).toBe(false);
  expect(
    isLedgerListingSearch({
      ...result,
      results: [{ ...result.results[0], security_type: "ETF" }],
    }),
  ).toBe(false);
});
it("keeps anchor immutable and refuses changed identity for the same listing", () => {
  expect(ledgerAvailableListings(ledgerAnchor, [other])).toEqual([
    ledgerAnchor.listings[0],
    other,
  ]);
  expect(ledgerAnchor.listings).toHaveLength(1);
  expect(() =>
    ledgerAvailableListings(ledgerAnchor, [
      { ...ledgerAnchor.listings[0], currency: "EUR" },
    ]),
  ).toThrow(/identity changed/);
});
it("requires every used selected identity to match the preview but ignores unused search results", () => {
  const file = inspectLedgerFile(
    JSON.stringify({
      contract_version: "portfolio-ledger-preview-v2",
      anchor_snapshot_id: ledgerAnchor.snapshot.id,
      anchor_sha256: ledgerAnchor.anchor_sha256,
      as_of: "2026-01-31T00:00:00Z",
      accounts: [],
      activity: [{ listing_id: other.listing_id }],
      ending_statement: null,
    }),
    "synthetic.json",
  );
  const report = ledgerReport();
  report.consumed_listings = [other];
  expect(selectedListingsMatchPreview(file, [other], report)).toBe(true);
  report.consumed_listings = [{ ...other, identity_source_ref: "different" }];
  expect(selectedListingsMatchPreview(file, [other], report)).toBe(false);
  report.consumed_listings = [];
  expect(selectedListingsMatchPreview(file, [other], report)).toBe(false);
  expect(
    selectedListingsMatchPreview(file, [ledgerAnchor.listings[0]], report),
  ).toBe(false);
  expect(selectedListingsMatchPreview(file, [], report)).toBe(false);
  report.consumed_listings = [other];
  expect(selectedListingsMatchPreview(file, [], report)).toBe(true);
});
