import type { Overview } from "@/lib/domain-contracts";
import { formatCurrency, formatPercent } from "@/lib/display";

export type SortKey = "company" | "quantity" | "price" | "value" | "weight";
export type SortDirection = "ascending" | "descending";

export type PortfolioHoldingRow = {
  listingId: string;
  companyId: string | null;
  companyName: string;
  securityName: string;
  ticker: string | null;
  venue: string | null;
  listingCurrency: string | null;
  quantity: string | null;
  latestPrice: string | null;
  priceCurrency: string | null;
  priceDate: string | null;
  priceObservedAt: string | null;
  priceFreshness: string;
  valuationStatus: string;
  valuationSyncStatus: string;
  baseMarketValue: string | null;
  portfolioWeight: string | null;
  targetWeight: string | null;
  allocationGap: string | null;
  allocationStatus: string | null;
};

/** Join accepted snapshot rows to canonical listing valuation context by listing ID. */
export function portfolioHoldingRows(
  overview: Overview,
): PortfolioHoldingRow[] {
  const contexts = [
    ...overview.companies.flatMap((company) =>
      company.positions.map((position) => ({
        company,
        position,
      })),
    ),
    ...overview.standalone_positions.map((position) => ({
      company: null,
      position,
    })),
  ];
  const contextByListing = new Map(
    contexts.map(({ company, position }) => [
      position.listing_id,
      { company, position },
    ]),
  );

  return (overview.snapshot?.positions ?? []).map((snapshotPosition) => {
    const context = contextByListing.get(snapshotPosition.listing_id);
    const position = context?.position;
    return {
      listingId: snapshotPosition.listing_id,
      companyId: context?.company?.company.id ?? null,
      companyName: context
        ? (context.company?.company.name ?? "Standalone security")
        : "Unresolved company",
      securityName: position?.security_name ?? "Unresolved security",
      ticker: position?.ticker ?? null,
      venue: position?.venue ?? null,
      listingCurrency: position?.currency ?? null,
      quantity: snapshotPosition.quantity,
      latestPrice: position?.latest_price ?? null,
      priceCurrency: position?.price_currency ?? null,
      priceDate: position?.price_date ?? null,
      priceObservedAt: position?.price_observed_at ?? null,
      priceFreshness: position?.price_freshness ?? "NO_DATA",
      valuationStatus: position?.valuation_status ?? "PRICE_UNAVAILABLE",
      valuationSyncStatus: position?.valuation_sync_status ?? "UNAVAILABLE",
      baseMarketValue: position?.base_market_value ?? null,
      portfolioWeight:
        context?.company?.current_weight ?? position?.portfolio_weight ?? null,
      targetWeight: context?.company?.target_weight ?? null,
      allocationGap: context?.company?.allocation_gap ?? null,
      allocationStatus: context?.company?.allocation_status ?? null,
    };
  });
}

export function nullableNumber(value: string | null) {
  if (value === null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function sortPortfolioRows(
  rows: PortfolioHoldingRow[],
  sortKey: SortKey,
  direction: SortDirection,
) {
  const multiplier = direction === "ascending" ? 1 : -1;
  return [...rows].sort((left, right) => {
    if (sortKey === "company") {
      return (
        multiplier *
        left.companyName.localeCompare(right.companyName, undefined, {
          sensitivity: "base",
        })
      );
    }
    const field = {
      quantity: [left.quantity, right.quantity],
      price: [left.latestPrice, right.latestPrice],
      value: [left.baseMarketValue, right.baseMarketValue],
      weight: [left.portfolioWeight, right.portfolioWeight],
    }[sortKey];
    const leftValue = nullableNumber(field[0]);
    const rightValue = nullableNumber(field[1]);
    if (leftValue === null) return rightValue === null ? 0 : 1;
    if (rightValue === null) return -1;
    return multiplier * (leftValue - rightValue);
  });
}

export function currency(value: string | null, code: string | null) {
  return formatCurrency(value, code, 2, "Unavailable");
}

export function percent(value: string | null) {
  return formatPercent(value, 2, "Unavailable");
}

export function countNote(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function portfolioCoverageTone(status: string) {
  if (status === "VALUED") return "positive" as const;
  if (status.startsWith("INCOMPLETE")) return "warning" as const;
  return "neutral" as const;
}
