"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { PageSection } from "@/components/app/page-section";
import { ResponsiveDataTable } from "@/components/app/responsive-data-table";
import { TableSearch } from "@/components/app/table-search";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HoldingsConfirmation } from "@/components/features/portfolio/holdings-confirmation";
import { ValuationFxEvidence } from "@/components/features/portfolio/valuation-fx-evidence";
import type { Overview } from "@/lib/domain-contracts";
import { dateTime, marketDate, quantity, statusLabel } from "@/lib/display";
import {
  countNote,
  currency,
  percent,
  type PortfolioHoldingRow,
  type SortDirection,
  type SortKey,
  sortPortfolioRows,
} from "@/components/features/portfolio/portfolio-data";

export function PortfolioHoldingsSection({
  overview,
  rows,
  onConfirmed,
}: {
  overview: Overview;
  rows: PortfolioHoldingRow[];
  onConfirmed: () => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("value");
  const [direction, setDirection] = useState<SortDirection>("descending");
  const [search, setSearch] = useState("");
  const sortedRows = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    const filtered = query
      ? rows.filter((row) =>
          [
            row.companyName,
            row.securityName,
            row.ticker,
            row.venue,
            row.listingCurrency,
            row.listingId,
          ].some((value) => value?.toLocaleLowerCase().includes(query)),
        )
      : rows;
    return sortPortfolioRows(filtered, sortKey, direction);
  }, [rows, sortKey, direction, search]);
  const columns = [
    {
      id: "identity",
      header: "Company / exact listing",
      className: "w-[31%]",
      render: (row: PortfolioHoldingRow) => (
        <div className="min-w-0">
          {row.companyId ? (
            <Link
              href={`/company/${row.companyId}`}
              className="font-medium hover:text-primary"
            >
              {row.companyName}
            </Link>
          ) : (
            <span className="font-medium">{row.companyName}</span>
          )}
          <p className="mt-0.5 text-xs text-muted-foreground">
            {row.securityName}
          </p>
          <p className="mt-0.5 break-all text-xs text-muted-foreground">
            {row.ticker && row.venue
              ? `${row.ticker} · ${row.venue} · ${row.listingCurrency ?? "Currency unknown"}`
              : "Listing identity unavailable"}
          </p>
          <p className="mt-0.5 break-all font-mono text-[10px] text-muted-foreground">
            Listing {row.listingId}
          </p>
          {row.priceDate && (
            <p className="mt-1 text-[10px] text-muted-foreground">
              Price date {marketDate(row.priceDate)} · quote observed{" "}
              {row.priceObservedAt
                ? dateTime(row.priceObservedAt)
                : "time unknown"}{" "}
              · {statusLabel(row.priceFreshness)}
              {row.valuationSyncStatus === "NON_SYNCHRONOUS"
                ? " · FX and quote observation times differ"
                : ""}
            </p>
          )}
        </div>
      ),
    },
    {
      id: "quantity",
      header: "Quantity",
      className: "w-[12%] text-right tabular-nums",
      render: (row: PortfolioHoldingRow) => quantity(row.quantity),
    },
    {
      id: "price",
      header: "Market price",
      className: "w-[15%] text-right tabular-nums",
      render: (row: PortfolioHoldingRow) =>
        currency(row.latestPrice, row.priceCurrency),
    },
    {
      id: "value",
      header: `Market value · ${overview.valuation_currency}`,
      className: "w-[16%] text-right tabular-nums",
      render: (row: PortfolioHoldingRow) => (
        <div>
          {currency(row.baseMarketValue, overview.valuation_currency)}
          {row.valuationStatus !== "VALUED" && (
            <div className="mt-1 space-y-1 text-xs text-muted-foreground">
              <p>{statusLabel(row.valuationStatus)}</p>
              {row.valuationStatus === "PRICE_UNAVAILABLE" && row.companyId && (
                <Link
                  href={`/company/${row.companyId}?view=history`}
                  aria-label={`Review company prices, from ${row.ticker ?? "listing"} ${row.venue ?? row.listingId}`}
                  className="inline-block text-primary underline underline-offset-2"
                >
                  Review company prices
                </Link>
              )}
              {(row.valuationStatus === "FX_UNAVAILABLE" ||
                (row.valuationStatus === "PRICE_UNAVAILABLE" &&
                  !row.companyId)) && (
                <Link
                  href="/operations#market-data-refresh"
                  aria-label={`Review global price and FX status, from ${row.ticker ?? "listing"} ${row.venue ?? row.listingId}`}
                  className="inline-block text-primary underline underline-offset-2"
                >
                  Review global price and FX status
                </Link>
              )}
              {row.valuationStatus === "QUANTITY_UNAVAILABLE" && (
                <a
                  href={
                    overview.holdings_authority?.source === "ACCEPTED_LEDGER"
                      ? "/portfolio/ledger"
                      : "#holdings-confirmation"
                  }
                  aria-label={`Review ${overview.holdings_authority?.source === "ACCEPTED_LEDGER" ? "ledger" : "holdings"} for ${row.ticker ?? "listing"} ${row.venue ?? row.listingId}`}
                  className="inline-block text-primary underline underline-offset-2"
                >
                  {overview.holdings_authority?.source === "ACCEPTED_LEDGER"
                    ? "Review ledger"
                    : "Review holdings"}
                </a>
              )}
            </div>
          )}
          <details className="mt-1 text-xs text-muted-foreground">
            <summary
              aria-label={`FX details for ${row.ticker ?? "listing"} ${row.venue ?? row.listingId}`}
              className="cursor-pointer"
            >
              FX details
            </summary>
            <div className="mt-1 break-words">
              <ValuationFxEvidence
                sourceCurrency={row.listingCurrency}
                targetCurrency={overview.valuation_currency}
                rate={row.fxRate}
                effectiveAt={row.fxEffectiveAt}
                syncStatus={row.valuationSyncStatus}
              />
            </div>
          </details>
        </div>
      ),
    },
    {
      id: "weight",
      header: "Listing weight",
      className: "w-[12%] text-right tabular-nums",
      render: (row: PortfolioHoldingRow) => percent(row.portfolioWeight),
    },
    {
      id: "target",
      header: "Company target / gap",
      className: "w-[14%] text-right tabular-nums",
      render: (row: PortfolioHoldingRow) => (
        <span>
          {row.companyId ? (
            <>
              <span>{percent(row.targetWeight)}</span>
              <span className="block text-xs text-muted-foreground">
                Gap {percent(row.allocationGap)}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground">No company target</span>
          )}
        </span>
      ),
    },
  ];

  return (
    <PageSection
      id="portfolio-holdings"
      title="Holdings"
      description="Accepted quantities remain distinct from current market marks and strategic targets. Values and weights are API-supplied; missing inputs stay explicit."
      actions={
        <a
          href="#holdings-confirmation"
          className="inline-flex min-h-9 items-center rounded-md border px-3 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Review holdings
        </a>
      }
    >
      <Card className="shadow-none">
        <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle className="text-base">Current positions</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {countNote(rows.length, "listing position")} · listing identity
              includes venue, currency and canonical ID. Targets and gaps apply
              to the company, not an individual listing.
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Sort by</span>
            <select
              aria-label="Sort holdings by"
              value={sortKey}
              onChange={(event) => setSortKey(event.target.value as SortKey)}
              className="h-9 max-w-48 rounded-md border bg-background px-2 text-sm"
            >
              <option value="value">Market value</option>
              <option value="weight">Current weight</option>
              <option value="company">Company</option>
              <option value="quantity">Quantity</option>
              <option value="price">Market price</option>
            </select>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label={`Sort ${direction === "descending" ? "ascending" : "descending"}`}
              onClick={() =>
                setDirection((current) =>
                  current === "descending" ? "ascending" : "descending",
                )
              }
            >
              {direction === "descending" ? "↓" : "↑"}
            </Button>
          </label>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="mb-3">
            <TableSearch
              label="Find a position"
              placeholder="Company, ticker, venue or currency"
              value={search}
              onChange={setSearch}
              resultCount={sortedRows.length}
              totalCount={rows.length}
            />
          </div>
          <ResponsiveDataTable
            caption="Portfolio holdings and current valuation"
            rows={sortedRows}
            columns={columns}
            getRowKey={(row) => row.listingId}
          />
        </CardContent>
      </Card>

      <div id="holdings-confirmation" className="scroll-mt-6">
        <HoldingsConfirmation
          key={overview.snapshot?.id ?? "no-snapshot"}
          id="holdings-confirmation-details"
          overview={overview}
          onSaved={onConfirmed}
        />
      </div>
    </PageSection>
  );
}
