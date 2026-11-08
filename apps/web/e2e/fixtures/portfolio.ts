import type { Overview } from "../../src/lib/domain-contracts";

export const portfolioId = "10000000-0000-4000-8000-000000000001";
export const iso = "2026-10-16T12:00:00Z";
const uuid = (value: number) =>
  `20000000-0000-4000-8000-${String(value).padStart(12, "0")}`;

export function portfolioFixture(): Overview {
  const companies = Array.from({ length: 21 }, (_, index) => {
    const listingId = uuid(index + 1);
    const securityId = uuid(index + 101);
    const currency = index % 2 === 0 ? "EUR" : "USD";
    const baseValue = currency === "EUR" ? 100 : 92;
    const ticker = `T${String(index + 1).padStart(2, "0")}`;
    const position = {
      listing_id: listingId,
      security_id: securityId,
      ticker,
      venue: currency === "EUR" ? "XETRA" : "NASDAQ",
      currency,
      security_name: `${ticker} common stock`,
      quantity: "1",
      latest_price: "100",
      price_date: "2026-10-15T00:00:00Z",
      price_observed_at: "2026-10-15T20:00:00Z",
      price_currency: currency,
      portfolio_weight: "0.04",
      fx_rate: currency === "USD" ? "0.92" : null,
      fx_effective_at: currency === "USD" ? "2026-10-15T16:00:00Z" : null,
      valuation_sync_status:
        currency === "USD" ? "NON_SYNCHRONOUS" : "NOT_REQUIRED",
      price_freshness: index === 1 ? "STALE" : "FRESH",
      native_market_value: "100",
      base_market_value: String(baseValue),
      valuation_status: "VALUED",
    };
    const company = {
      id: uuid(index + 201),
      name: `Fixture issuer ${String(index + 1).padStart(2, "0")}`,
      reporting_currency: currency,
      is_demo: false,
      created_at: "2026-01-01T00:00:00Z",
      lifecycle: "PORTFOLIO",
      lifecycle_event_id: null,
    };
    return {
      company,
      positions: [position],
      target_weight: index === 0 ? "0.05" : null,
      current_market_value: String(baseValue),
      current_market_currency: "EUR",
      current_weight: "0.04",
      allocation_gap: index === 0 ? "0.01" : null,
      allocation_status: "VALUED",
    };
  });

  const standaloneListingId = uuid(22);
  const standalone = {
    listing_id: standaloneListingId,
    security_id: uuid(901),
    ticker: "SPYY",
    venue: "XETRA",
    currency: "EUR",
    security_name: "SPDR MSCI ACWI UCITS ETF",
    quantity: "1",
    latest_price: "100",
    price_date: "2026-10-15T00:00:00Z",
    price_observed_at: "2026-10-15T20:00:00Z",
    price_currency: "EUR",
    portfolio_weight: "0.04",
    fx_rate: null,
    fx_effective_at: null,
    valuation_sync_status: "NOT_REQUIRED",
    price_freshness: "FRESH",
    native_market_value: "100",
    base_market_value: "100",
    valuation_status: "VALUED",
  };
  const totalValue =
    companies.reduce(
      (total, company) => total + Number(company.current_market_value),
      0,
    ) +
    100 +
    50 +
    92;

  // Synthetic API fixture weights reconcile with its explicit cash and security marks.
  for (const company of companies) {
    company.current_weight = String(
      Number(company.current_market_value) / totalValue,
    );
    company.positions[0].portfolio_weight = company.current_weight;
    company.allocation_gap =
      company.target_weight === null
        ? null
        : String(
            Number(company.target_weight) - Number(company.current_weight),
          );
  }
  standalone.portfolio_weight = String(100 / totalValue);

  return {
    portfolio: {
      id: portfolioId,
      name: "Primary Portfolio",
      base_currency: "EUR",
      created_at: "2026-01-01T00:00:00Z",
      is_demo: false,
    },
    snapshot: {
      id: uuid(990),
      portfolio_id: portfolioId,
      completeness: "COMPLETE",
      positions: [
        ...companies.map((company) => ({
          listing_id: company.positions[0].listing_id,
          quantity: "1",
        })),
        { listing_id: standaloneListingId, quantity: "1" },
      ],
      cash_positions: [
        { currency: "EUR", balance: "50" },
        { currency: "USD", balance: "100" },
      ],
      actor: "IMPORT",
      reason: "Read-only browser fixture.",
      source: "portfolio-experience-test",
      effective_at: "2026-10-10T12:00:00Z",
      recorded_at: "2026-10-10T12:00:00Z",
    },
    target_revision: {
      id: uuid(991),
      portfolio_id: portfolioId,
      status: "ACCEPTED",
      allocations: [{ company_id: companies[0].company.id, weight: "0.05" }],
      actor: "IMPORT",
      reason:
        "One target is explicit; remaining targets are intentionally absent.",
      source: "portfolio-experience-test",
      effective_at: "2026-10-01T12:00:00Z",
      recorded_at: "2026-10-01T12:00:00Z",
      accepted_at: "2026-10-01T12:00:00Z",
      invested_weight: "0.05",
      strategic_cash_weight: "0.95",
    },
    companies,
    standalone_positions: [standalone],
    cash_valuations: [
      {
        currency: "EUR",
        balance: "50",
        base_market_value: "50",
        portfolio_weight: String(50 / totalValue),
        valuation_status: "VALUED",
      },
      {
        currency: "USD",
        balance: "100",
        base_market_value: "92",
        fx_rate: "0.92",
        fx_effective_at: "2026-10-15T16:00:00Z",
        portfolio_weight: String(92 / totalValue),
        valuation_status: "VALUED",
      },
    ],
    valuation_gaps: [],
    valuation_status: "VALUED",
    valuation_mode: "CURRENT_MARK_TO_MARKET",
    valuation_as_of: iso,
    market_data_through: "2026-10-15T20:00:00Z",
    fx_data_through: "2026-10-15T16:00:00Z",
    holdings_age_days: 6,
    holdings_freshness: "STALE",
    base_market_value: String(totalValue),
    valuation_currency: "EUR",
  } as unknown as Overview;
}
