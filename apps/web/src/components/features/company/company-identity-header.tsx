"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { DataFreshnessIndicator } from "@/components/app/data-freshness-indicator";
import { PageHeader } from "@/components/app/page-header";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PendingOrError } from "@/components/app/empty-state";
import type { CompanyDetail, ListingMarketData } from "@/lib/domain-contracts";
import { date, formatCurrency } from "@/lib/display";

type MarketState = {
  data?: ListingMarketData[];
  error?: string;
  retry: () => void;
};

export function CompanyIdentityHeader({
  detail,
  marketState,
  actions,
}: {
  detail: CompanyDetail;
  marketState: MarketState;
  actions?: ReactNode;
}) {
  const [requestedListingId, setListingId] = useState(
    () => detail.positions[0]?.listing_id ?? detail.listings[0]?.id ?? "",
  );
  const listingId = detail.listings.some(
    (listing) => listing.id === requestedListingId,
  )
    ? requestedListingId
    : (detail.positions[0]?.listing_id ?? detail.listings[0]?.id ?? "");

  const market = marketState.data?.find(
    (item) => item.listing.id === listingId,
  );
  const listing = detail.listings.find((item) => item.id === listingId);
  const quote = market?.latest;
  const currency = quote?.currency ?? listing?.currency ?? null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Link
          className="text-muted-foreground underline-offset-4 hover:text-primary hover:underline"
          href="/universe"
        >
          ← Back to universe
        </Link>
      </div>
      <PageHeader
        eyebrow="Company Explorer"
        title={detail.company.name}
        description="What do we know about this business, what do we expect, and what is it worth?"
        actions={actions}
        demo={detail.company.is_demo}
        context={
          <>
            <Badge variant={detail.company.lifecycle ? "default" : "secondary"}>
              {detail.company.lifecycle ?? "Lifecycle unassigned"}
            </Badge>
            <Badge variant="outline">
              Reporting currency ·{" "}
              {detail.company.reporting_currency ?? "Unknown"}
            </Badge>
          </>
        }
      />
      <Card className="shadow-none">
        <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
          <div className="min-w-0 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              Exact listing and quote context
            </p>
            {detail.listings.length > 0 ? (
              <label className="flex flex-wrap items-center gap-2 text-sm font-medium">
                <span className="sr-only">Select exact listing</span>
                <select
                  aria-label="Select exact listing"
                  value={listingId}
                  onChange={(event) => setListingId(event.target.value)}
                  className="h-10 max-w-full rounded-md border bg-background px-3"
                >
                  {detail.listings.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.ticker} · {item.venue} ·{" "}
                      {item.currency ?? "Currency unknown"}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <p className="text-sm text-muted-foreground">
                No listing identity is recorded.
              </p>
            )}
            {market ? (
              <DataFreshnessIndicator
                state={market.freshness}
                observedAt={quote?.observed_at}
                source={quote?.provider ?? "No quote source"}
                detail={
                  quote
                    ? `Market date ${date(quote.market_date)} · ${quote.data_quality}`
                    : "No quote for this listing"
                }
              />
            ) : marketState.error ? (
              <div className="space-y-2">
                <StatusIndicator status="UNAVAILABLE" />
                <p className="text-xs text-muted-foreground">
                  Listing quote state could not be loaded.
                </p>
              </div>
            ) : (
              <StatusIndicator
                status="REFRESHING"
                label="Loading quote context"
              />
            )}
          </div>
          <div className="min-w-0 sm:text-right">
            <p className="text-xs text-muted-foreground">
              Latest split-adjusted close · {currency ?? "Currency unknown"}
            </p>
            <p className="mt-1 break-words text-2xl font-semibold tabular-nums">
              {quote?.split_adjusted_close === null || !quote
                ? "Unavailable"
                : formatCurrency(quote.split_adjusted_close, currency, 2)}
            </p>
            {marketState.error && (
              <div className="mt-2 sm:ml-auto sm:max-w-sm">
                <PendingOrError
                  error={marketState.error}
                  retry={marketState.retry}
                />
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
