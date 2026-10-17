import { describe, expect, it } from "vitest";
import type { Overview } from "@/lib/domain-contracts";
import {
  portfolioHoldingRows,
  sortPortfolioRows,
  type PortfolioHoldingRow,
} from "@/components/features/portfolio/portfolio-data";

const uuid = (value: number) =>
  `00000000-0000-4000-8000-${String(value).padStart(12, "0")}`;

function fixture(positionCount = 22): Overview {
  const companies = Array.from({ length: positionCount - 1 }, (_, index) => {
    const listingId = uuid(index + 1);
    const ticker = `T${String(index + 1).padStart(2, "0")}`;
    const position = {
      listing_id: listingId,
      security_id: uuid(100 + index),
      ticker,
      venue: index % 2 === 0 ? "NASDAQ" : "XETRA",
      currency: index % 2 === 0 ? "USD" : "EUR",
      security_name: `${ticker} common stock`,
      quantity: "2",
      latest_price: "100",
      price_date: "2026-10-15",
      price_observed_at: "2026-10-15T20:00:00Z",
      price_currency: index % 2 === 0 ? "USD" : "EUR",
      portfolio_weight: "0.04",
      fx_rate: index % 2 === 0 ? "0.92" : null,
      fx_effective_at: index % 2 === 0 ? "2026-10-15T16:00:00Z" : null,
      valuation_sync_status: "SYNCHRONOUS",
      price_freshness: index === 1 ? "STALE" : "FRESH",
      native_market_value: "200",
      base_market_value: "184",
      valuation_status: "VALUED",
    };
    return {
      company: {
        id: uuid(200 + index),
        name: `Fixture company ${String(index + 1).padStart(2, "0")}`,
      },
      positions: [position],
      current_weight: "0.04",
      current_market_value: "184",
      current_market_currency: "EUR",
      target_weight: index === 0 ? "0.05" : null,
      allocation_gap: index === 0 ? "0.01" : null,
      allocation_status: "VALUED",
    };
  });
  const standaloneId = uuid(positionCount);
  const standalone = {
    listing_id: standaloneId,
    security_id: uuid(900),
    ticker: "SPYY",
    venue: "SIX",
    currency: "USD",
    security_name: "SPDR S&P 500 ETF",
    quantity: "1",
    latest_price: "100",
    price_date: "2026-10-15",
    price_observed_at: "2026-10-15T20:00:00Z",
    price_currency: "USD",
    portfolio_weight: "0.04",
    fx_rate: "0.92",
    fx_effective_at: "2026-10-15T16:00:00Z",
    valuation_sync_status: "SYNCHRONOUS",
    price_freshness: "FRESH",
    native_market_value: "100",
    base_market_value: "92",
    valuation_status: "VALUED",
  };

  return {
    snapshot: {
      positions: [
        ...companies.flatMap((company) =>
          company.positions.map(({ listing_id, quantity }) => ({
            listing_id,
            quantity,
          })),
        ),
        { listing_id: standaloneId, quantity: standalone.quantity },
      ],
    },
    companies,
    standalone_positions: [standalone],
  } as unknown as Overview;
}

describe("Portfolio presentation data", () => {
  it("renders every accepted listing position with its exact listing identity", () => {
    const overview = fixture(22);
    const rows = portfolioHoldingRows(overview);

    expect(rows).toHaveLength(22);
    expect(rows[0]).toMatchObject({
      ticker: "T01",
      venue: "NASDAQ",
      listingCurrency: "USD",
      quantity: "2",
      latestPrice: "100",
      baseMarketValue: "184",
    });
    expect(rows[21]).toMatchObject({
      listingId: uuid(22),
      companyName: "Standalone security",
      ticker: "SPYY",
      venue: "SIX",
      listingCurrency: "USD",
    });
  });

  it("preserves stale and missing valuation states while sorting available API values", () => {
    const rows = portfolioHoldingRows(fixture());
    expect(rows[1].priceFreshness).toBe("STALE");
    expect(rows[0].targetWeight).toBe("0.05");
    expect(rows[1].targetWeight).toBeNull();

    const missing = {
      ...rows[0],
      listingId: uuid(999),
      latestPrice: null,
      baseMarketValue: null,
      portfolioWeight: null,
      priceFreshness: "NO_DATA",
      valuationStatus: "PRICE_UNAVAILABLE",
    } satisfies PortfolioHoldingRow;
    const sorted = sortPortfolioRows(
      [missing, rows[1], rows[0]],
      "value",
      "descending",
    );
    expect(sorted.map((row) => row.listingId)).toEqual([
      rows[1].listingId,
      rows[0].listingId,
      missing.listingId,
    ]);
    expect(sorted[2]).toMatchObject({
      latestPrice: null,
      baseMarketValue: null,
      portfolioWeight: null,
      valuationStatus: "PRICE_UNAVAILABLE",
    });
  });
});
