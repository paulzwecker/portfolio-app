import Link from "next/link";
import { ChartContainer } from "@/components/app/chart-container";
import { EmptyState } from "@/components/app/empty-state";
import { PageSection } from "@/components/app/page-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  GapRow,
  sortedByGap,
} from "@/components/features/portfolio/decision-components";
import type { Overview } from "@/lib/domain-contracts";
import { dateTime, statusLabel } from "@/lib/display";
import {
  currency,
  nullableNumber,
  percent,
} from "@/components/features/portfolio/portfolio-data";

type ExposureItem = {
  key: string;
  name: string;
  detail: string;
  weight: string | null;
  value: string | null;
  currency: string | null;
  status: string;
  href?: string;
};

function percentWidth(value: string | null) {
  const parsed = nullableNumber(value);
  if (parsed === null || parsed < 0) return undefined;
  return `${Math.min(100, parsed * 100)}%`;
}

function allocationItems(overview: Overview): ExposureItem[] {
  const companies: ExposureItem[] = overview.companies.map((row) => ({
    key: `company-${row.company.id}`,
    name: row.company.name,
    detail:
      row.positions
        .map((position) => `${position.ticker} · ${position.venue}`)
        .join(", ") || "No listing context",
    weight: row.current_weight,
    value: row.current_market_value,
    currency: row.current_market_currency,
    status: row.allocation_status,
    href: `/company/${row.company.id}`,
  }));
  const standalone: ExposureItem[] = overview.standalone_positions.map(
    (position) => ({
      key: `listing-${position.listing_id}`,
      name: position.security_name,
      detail: `${position.ticker} · ${position.venue} · ${position.currency ?? "Currency unknown"}`,
      weight: position.portfolio_weight ?? null,
      value: position.base_market_value,
      currency: overview.valuation_currency,
      status: position.valuation_status,
    }),
  );
  const cash: ExposureItem[] = overview.cash_valuations.map((item) => ({
    key: `cash-${item.currency}`,
    name: `${item.currency} cash`,
    detail:
      item.balance === null
        ? "Balance unavailable"
        : currency(item.balance, item.currency),
    weight: item.portfolio_weight ?? null,
    value: item.base_market_value,
    currency: overview.valuation_currency,
    status: item.valuation_status,
  }));
  return [...companies, ...standalone, ...cash].sort((left, right) => {
    const a = nullableNumber(left.weight);
    const b = nullableNumber(right.weight);
    if (a === null) return b === null ? left.name.localeCompare(right.name) : 1;
    if (b === null) return -1;
    return b - a;
  });
}

export function PortfolioAllocationSection({
  overview,
}: {
  overview: Overview;
}) {
  const items = allocationItems(overview);
  const gaps = sortedByGap(overview.companies).filter(
    (row) => row.allocation_gap !== null,
  );
  return (
    <PageSection
      id="portfolio-allocation"
      title="Allocation and exposure"
      description="Current allocation and target gaps use canonical API values. This view does not recommend trades or change strategic targets."
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(280px,0.7fr)]">
        <ChartContainer
          title="Current composition"
          description="Company, standalone listing and cash weights from the current priced portfolio overview. Missing weights are not plotted as zero."
          source={`Base currency · ${overview.valuation_currency}`}
        >
          <div
            className="mb-4 flex flex-wrap items-center gap-2"
            role="group"
            aria-label="Exposure classification"
          >
            <span className="mr-1 text-xs font-medium text-muted-foreground">
              Group by
            </span>
            <Badge>Company and cash</Badge>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled
              title="Canonical sector classification coverage is incomplete"
            >
              Sector · unavailable
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled
              title="Canonical geographic classification coverage is incomplete"
            >
              Geography · unavailable
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled
              title="Canonical business-model classification coverage is incomplete"
            >
              Business model · unavailable
            </Button>
          </div>
          {items.length === 0 ? (
            <EmptyState
              title="Portfolio composition unavailable"
              description="No current company, standalone listing or cash weight was returned by the portfolio overview."
            />
          ) : (
            <div className="space-y-3">
              {items.map((item) => {
                const width = percentWidth(item.weight);
                return (
                  <div
                    key={item.key}
                    className="grid gap-1.5 sm:grid-cols-[minmax(125px,0.75fr)_minmax(0,1.5fr)_auto] sm:items-center sm:gap-3"
                  >
                    <div className="min-w-0">
                      {item.href ? (
                        <Link
                          href={item.href}
                          className="block truncate text-sm font-medium hover:text-primary"
                        >
                          {item.name}
                        </Link>
                      ) : (
                        <span className="block truncate text-sm font-medium">
                          {item.name}
                        </span>
                      )}
                      <span className="block truncate text-xs text-muted-foreground">
                        {item.detail}
                      </span>
                    </div>
                    <div
                      className="h-2.5 overflow-hidden rounded-full bg-muted"
                      aria-hidden="true"
                    >
                      {width && (
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width }}
                        />
                      )}
                    </div>
                    <span className="text-right text-sm tabular-nums">
                      {percent(item.weight)}
                    </span>
                    {item.weight === null && (
                      <span className="text-xs text-muted-foreground sm:col-start-2">
                        {statusLabel(item.status)} · weight unavailable
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div className="mt-4 border-t pt-3 text-xs text-muted-foreground">
            Missing classifications remain unavailable. Bars represent only
            API-provided weights; they are not normalized in the browser.
          </div>
        </ChartContainer>

        <div className="space-y-4">
          <Card className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Largest strategic gaps</CardTitle>
              <p className="text-xs text-muted-foreground">
                Positive target-minus-current gap means below target; no target
                is inferred.
              </p>
            </CardHeader>
            <CardContent className="space-y-1">
              {gaps.length === 0 ? (
                <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                  {overview.target_revision
                    ? "Allocation gaps are unavailable until the holdings and valuation inputs are comparable."
                    : "No accepted strategic target revision."}
                </p>
              ) : (
                gaps
                  .slice(0, 6)
                  .map((row) => <GapRow key={row.company.id} row={row} />)
              )}
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Cash by original currency
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {(overview.snapshot?.cash_positions ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No cash balances are present in the accepted holdings
                  snapshot.
                </p>
              ) : (
                (overview.snapshot?.cash_positions ?? []).map((cash) => {
                  const valuation = overview.cash_valuations.find(
                    (item) => item.currency === cash.currency,
                  );
                  return (
                    <div
                      key={cash.currency}
                      className="flex flex-wrap items-start justify-between gap-2 border-b pb-2 last:border-0 last:pb-0"
                    >
                      <div>
                        <p className="text-sm font-medium">
                          {currency(cash.balance, cash.currency)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Original balance · {cash.currency}
                        </p>
                      </div>
                      <div className="text-right text-sm tabular-nums">
                        {valuation?.valuation_status === "VALUED"
                          ? currency(
                              valuation.base_market_value,
                              overview.valuation_currency,
                            )
                          : statusLabel(
                              valuation?.valuation_status ?? "UNAVAILABLE",
                            )}
                        <p className="text-xs text-muted-foreground">
                          Weight {percent(valuation?.portfolio_weight ?? null)}
                        </p>
                      </div>
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Strategic target architecture
              </CardTitle>
            </CardHeader>
            <CardContent>
              {overview.target_revision ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Invested target
                      </p>
                      <p className="mt-1 text-lg font-semibold tabular-nums">
                        {percent(overview.target_revision.invested_weight)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Strategic cash
                      </p>
                      <p className="mt-1 text-lg font-semibold tabular-nums">
                        {percent(
                          overview.target_revision.strategic_cash_weight,
                        )}
                      </p>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Accepted{" "}
                    {dateTime(
                      overview.target_revision.accepted_at ??
                        overview.target_revision.recorded_at,
                    )}
                  </p>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No accepted strategic target revision is available.
                </p>
              )}
            </CardContent>
          </Card>
          {overview.target_revision && (
            <p className="rounded-md border bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
              Accepted target revision {overview.target_revision.id} · recorded{" "}
              {dateTime(overview.target_revision.recorded_at)}. Target cash{" "}
              {percent(overview.target_revision.strategic_cash_weight)}.
            </p>
          )}
        </div>
      </div>
    </PageSection>
  );
}

export function PortfolioPerformanceSection() {
  return (
    <PageSection
      id="portfolio-performance"
      title="Performance"
      description="Portfolio returns require reliable cash-flow and dated valuation history."
    >
      <EmptyState
        title="Historical portfolio performance is unavailable"
        description="The application does not yet have complete transaction and cash-flow history to calculate portfolio performance. Current holdings multiplied by historical prices would be a hypothetical price series, not realized portfolio performance, so it is not shown here."
      />
    </PageSection>
  );
}
