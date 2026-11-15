"use client";

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
  listingId,
  onListingChange,
  fromPortfolio,
}: {
  detail: CompanyDetail;
  marketState: MarketState;
  actions?: ReactNode;
  listingId: string;
  onListingChange: (id: string) => void;
  fromPortfolio: boolean;
}) {
  const market = marketState.data?.find(
    (item) => item.listing.id === listingId,
  );
  const listing = detail.listings.find((item) => item.id === listingId);
  const quote = market?.latest;
  const currency = quote?.currency ?? listing?.currency ?? null;
  const native =
    quote?.split_adjusted_close == null && quote?.native_close != null;
  const shownPrice = native ? quote?.native_close : quote?.split_adjusted_close;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Link
          className="text-muted-foreground underline-offset-4 hover:text-primary hover:underline"
          href={fromPortfolio ? "/portfolio#portfolio-holdings" : "/universe"}
        >
          {fromPortfolio ? "← Back to holdings" : "← Back to universe"}
        </Link>
        {fromPortfolio && (
          <Link
            href="/portfolio#portfolio-allocation"
            className="ml-auto font-medium text-primary hover:underline"
          >
            Review allocation →
          </Link>
        )}
      </div>
      <PageHeader
        eyebrow="Company Explorer"
        title={detail.company.name}
        className="mb-4"
        actions={
          actions ? (
            <details className="min-w-0 max-w-full rounded-lg border bg-card p-3 text-sm sm:max-w-lg">
              <summary className="cursor-pointer font-medium">
                Data & refresh
              </summary>
              <div className="mt-3 border-t pt-3">{actions}</div>
            </details>
          ) : undefined
        }
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
        <CardContent className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-3 gap-y-3 p-4 sm:p-5">
          <div className="min-w-0 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              Exact listing
            </p>
            {detail.listings.length > 0 ? (
              <label className="flex flex-wrap items-center gap-2 text-sm font-medium">
                <span className="sr-only">Select exact listing</span>
                <select
                  aria-label="Select exact listing"
                  value={listingId}
                  onChange={(event) => onListingChange(event.target.value)}
                  className="h-10 max-w-full rounded-md border bg-background px-2 text-xs sm:text-sm"
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
          </div>
          <div className="min-w-0 text-right">
            <p className="text-xs text-muted-foreground">
              {native ? "Unadjusted native close" : "Split-adjusted close"} ·{" "}
              {currency ?? "Unknown"}
            </p>
            <p className="mt-1 break-words text-2xl font-semibold tabular-nums">
              {shownPrice == null
                ? "Unavailable"
                : formatCurrency(shownPrice, currency, 2)}
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
          <div className="col-span-2">
            {market ? (
              <DataFreshnessIndicator
                state={
                  native
                    ? (market.native_freshness ?? "NO_DATA")
                    : market.freshness
                }
                observedAt={quote?.observed_at}
                source={quote?.provider ?? "No quote source"}
                detail={
                  quote
                    ? `Market date ${date(quote.market_date)} · ${quote.data_quality}${native ? " · Unadjusted native close" : ""}${quote.provider === "EODHD_DEMO" ? " · Indicative test-drive data" : ""}`
                    : "No quote for this listing"
                }
              />
            ) : marketState.error || marketState.data ? (
              <div className="space-y-2">
                <StatusIndicator status="UNAVAILABLE" />
                <p className="text-xs text-muted-foreground">
                  {marketState.error
                    ? "Listing quote state could not be loaded."
                    : "No quote recorded for this exact listing."}
                </p>
              </div>
            ) : (
              <StatusIndicator
                status="REFRESHING"
                label="Loading quote context"
              />
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
