import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import { GET, POST } from "@/app/api/research/[...path]/route";
import { isMarketBootstrapScopePreview } from "@/lib/domain-contracts";
import { MarketScopePreview } from "./market-scope-preview";

const preview = {
  status: "READY",
  checked_at: "2024-12-01T12:00:00Z",
  provider_id: "YAHOO_FINANCE",
  provider_schema_version: "yahoo-chart-v8",
  crosswalk_sha256: "a".repeat(64),
  target_environment: "production",
  date_window: { start: "2024-02-01", end: "2024-11-30" },
  listing_scope: "held and active listings",
  holdings_snapshot: {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    portfolio_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    completeness: "COMPLETE",
    effective_at: "2024-01-20T10:00:00Z",
    recorded_at: "2024-01-20T10:00:00Z",
  },
  company_scope: null,
  canonical_import_readiness: {
    ready: true,
    status: "RECONCILED",
    run_id: "11111111-1111-4111-8111-111111111111",
    bootstrap_status: "APPLIED_WITH_GAPS",
    reconciliation_status: "MATCHED",
    source_gap_count: 12,
    recorded_at: "2024-01-20T10:30:00Z",
  },
  listing_priority_counts: { HELD: 3, PORTFOLIO: 0, WATCHLIST: 0, OTHER: 0 },
  selected_listing_count: 3,
  listing_review: Array.from({ length: 3 }, (_, index) => ({
    listing_id: `11111111-1111-4111-8111-${String(index + 1).padStart(12, "0")}`,
    security_id: `22222222-2222-4222-8222-${String(index + 1).padStart(12, "0")}`,
    company_id: null,
    company_name: null,
    ticker: `SYN${index + 1}`,
    venue: "NASDAQ",
    currency: "USD",
    security_type: "ETF",
    priority: "HELD",
    held_quantity: "2.5000000000",
    mapping_verified: true,
    provider_symbol: `SYN${index + 1}`,
  })),
  omitted_listing_count: 0,
  verified_listing_mapping_count: 3,
  unresolved_listings: [],
  portfolio_base_currency: "EUR",
  required_fx_pairs: ["GBP/EUR", "USD/EUR"],
  allowlisted_fx_pairs: ["GBP/EUR", "USD/EUR"],
  unmapped_fx_pairs: [],
  provider_requests_planned: 5,
  database_writes: 0,
  provider_requests: 0,
  lifecycle_counts: { PORTFOLIO: 0, WATCHLIST: 0 },
};
const context = {
  params: Promise.resolve({ path: ["market-data", "bootstrap-scope"] }),
};

beforeEach(() => {
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_ACCESS_TOKEN", "");
  vi.stubEnv("WEB_ACCESS_USERNAME", "");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "");
});

it("renders a labeled, read-only scope review", () => {
  const html = renderToStaticMarkup(<MarketScopePreview />);
  expect(html).toContain("Review historical data scope");
  expect(html).toContain('for="market-scope-start"');
  expect(html).toContain('for="market-scope-end"');
  expect(html).toContain("does not fetch prices or prepare a run");
});

it("rejects malformed or internally inconsistent previews", () => {
  expect(isMarketBootstrapScopePreview(preview)).toBe(true);
  expect(
    isMarketBootstrapScopePreview({
      ...preview,
      listing_review: [
        { ...preview.listing_review[0], held_quantity: "0.0000000000" },
        { ...preview.listing_review[1], held_quantity: "0.0000000001" },
        { ...preview.listing_review[2], held_quantity: null },
        ...preview.listing_review.slice(3),
      ],
    }),
  ).toBe(true);
  expect(
    isMarketBootstrapScopePreview({ ...preview, provider_requests: 1 }),
  ).toBe(false);
  expect(
    isMarketBootstrapScopePreview({ ...preview, selected_listing_count: 4 }),
  ).toBe(false);
  expect(
    isMarketBootstrapScopePreview({
      ...preview,
      listing_review: preview.listing_review.slice(1),
    }),
  ).toBe(false);
  expect(
    isMarketBootstrapScopePreview({
      ...preview,
      listing_review: [
        ...preview.listing_review.slice(0, 2),
        preview.listing_review[0],
      ],
    }),
  ).toBe(false);
  expect(
    isMarketBootstrapScopePreview({
      ...preview,
      listing_review: [
        {
          ...preview.listing_review[0],
          mapping_verified: false,
          provider_symbol: null,
        },
        ...preview.listing_review.slice(1),
      ],
    }),
  ).toBe(false);
  expect(
    isMarketBootstrapScopePreview({
      ...preview,
      listing_review: preview.listing_review.slice(0, 2),
      omitted_listing_count: 1,
    }),
  ).toBe(true);
  expect(
    isMarketBootstrapScopePreview({
      ...preview,
      canonical_import_readiness: null,
    }),
  ).toBe(false);
  expect(
    isMarketBootstrapScopePreview({
      ...preview,
      status: "READY",
      unmapped_fx_pairs: ["USD/EUR"],
    }),
  ).toBe(false);
});

it("forwards exactly one date window, requires a matching response and denies writes", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json(preview));
  vi.stubGlobal("fetch", fetcher);
  const url =
    "http://localhost/api/research/market-data/bootstrap-scope?start_date=2024-02-01&end_date=2024-11-30";
  const response = await GET(new Request(url), context);
  expect(response.status).toBe(200);
  expect((fetcher.mock.calls[0][0] as URL).searchParams.toString()).toBe(
    "start_date=2024-02-01&end_date=2024-11-30",
  );
  const duplicate = await GET(
    new Request(url + "&start_date=2024-02-02"),
    context,
  );
  expect(duplicate.status).toBe(400);
  fetcher.mockResolvedValueOnce(
    Response.json({
      ...preview,
      date_window: { start: "2024-02-02", end: "2024-11-30" },
    }),
  );
  expect((await GET(new Request(url), context)).status).toBe(503);
  expect(
    (await POST(new Request(url, { method: "POST" }), context)).status,
  ).toBe(404);
});
