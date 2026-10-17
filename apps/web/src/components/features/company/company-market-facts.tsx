"use client";

import { Badge } from "@/components/ui/badge";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError } from "@/components/app/empty-state";
import type { ListingMarketData } from "@/lib/domain-contracts";
import { date } from "@/lib/display";

import {
  formatPrice,
  rateLabel,
} from "@/components/features/company/company-formatters";
type MarketState = {
  data?: ListingMarketData[];
  error?: string;
  retry: () => void;
};

export function MarketFacts({ marketState }: { marketState: MarketState }) {
  return (
    <section
      id="market-facts"
      aria-labelledby="market-facts-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="market-facts-title" className="text-xl font-semibold">
          Market facts
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Listing-specific quotes and split-adjusted history. These facts do not
          determine lifecycle, targets or execution.
        </p>
      </div>
      {!marketState.data ? (
        <PendingOrError error={marketState.error} retry={marketState.retry} />
      ) : marketState.data.length === 0 ? (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            No supported exchange listing has been recorded.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {marketState.data.map((market) => {
            const regime = market.price_regime;
            const history = [...market.history].reverse();
            return (
              <Card key={market.listing.id} className="min-w-0 shadow-none">
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-base">
                      {market.listing.ticker} · {market.listing.venue} ·{" "}
                      {market.listing.currency ?? "Currency unknown"}
                    </CardTitle>
                    <Badge
                      variant={
                        market.freshness === "FRESH" ? "default" : "secondary"
                      }
                    >
                      {market.freshness === "FRESH" && market.age_days !== null
                        ? `Fresh · ${market.age_days}d`
                        : market.freshness.replaceAll("_", " ")}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Latest split-adjusted close
                      </p>
                      <p className="mt-1 text-2xl font-semibold tabular-nums">
                        {formatPrice(
                          market.latest?.split_adjusted_close ?? null,
                          market.latest?.currency ??
                            market.listing.currency ??
                            null,
                        )}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {market.latest
                          ? `${date(market.latest.market_date)} · ${market.latest.provider} · ${market.latest.data_quality}`
                          : "No dated quote is available for this listing."}
                      </p>
                    </div>
                    {regime && (
                      <p className="text-right text-xs text-muted-foreground">
                        {regime.regime ??
                          regime.trend_state ??
                          "Regime unavailable"}
                        <br />
                        As of {date(regime.as_of)}
                      </p>
                    )}
                  </div>
                  <details className="border-t pt-3">
                    <summary className="cursor-pointer text-xs font-medium">
                      Price history and regime measures (90 sessions)
                    </summary>
                    <div className="mt-3 space-y-3">
                      {" "}
                      {history.length >= 2 ? (
                        <PriceSeriesChart
                          values={history
                            .map((item) => item.split_adjusted_close)
                            .filter((value): value is string => value !== null)}
                        />
                      ) : (
                        <p className="rounded-md bg-secondary/40 px-3 py-4 text-xs text-muted-foreground">
                          Price history is unavailable or too short to chart.
                        </p>
                      )}
                      <dl className="grid grid-cols-2 gap-3 border-t pt-3 sm:grid-cols-4">
                        {[
                          [
                            "20-day average",
                            regime?.dma_20
                              ? formatPrice(
                                  regime.dma_20,
                                  market.listing.currency ?? null,
                                )
                              : "Unavailable",
                          ],
                          [
                            "50-day average",
                            regime?.dma_50
                              ? formatPrice(
                                  regime.dma_50,
                                  market.listing.currency ?? null,
                                )
                              : "Unavailable",
                          ],
                          [
                            "200-day average",
                            regime?.dma_200
                              ? formatPrice(
                                  regime.dma_200,
                                  market.listing.currency ?? null,
                                )
                              : "Unavailable",
                          ],
                          [
                            "52-week drawdown",
                            rateLabel(regime?.drawdown_52w ?? null),
                          ],
                          [
                            "1-month return",
                            rateLabel(regime?.return_1m ?? null),
                          ],
                          [
                            "3-month return",
                            rateLabel(regime?.return_3m ?? null),
                          ],
                          [
                            "6-month return",
                            rateLabel(regime?.return_6m ?? null),
                          ],
                          [
                            "20-day realized volatility",
                            rateLabel(regime?.realized_vol_20d ?? null),
                          ],
                        ].map(([label, value]) => (
                          <div key={label} className="min-w-0">
                            <dt className="text-[10px] leading-4 text-muted-foreground">
                              {label}
                            </dt>
                            <dd className="mt-1 break-words text-xs font-medium tabular-nums">
                              {value}
                            </dd>
                          </div>
                        ))}
                      </dl>
                      <p className="text-xs text-muted-foreground">
                        {regime?.data_quality === "PASS"
                          ? `Trend: ${regime.trend_state ?? "Unavailable"} · Correction: ${regime.correction_state ?? "Unavailable"}`
                          : (regime?.quality_reason ??
                            "No regime snapshot is available for this listing.")}
                      </p>
                    </div>
                  </details>{" "}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}

function PriceSeriesChart({ values }: { values: string[] }) {
  const points = values.map(Number).filter(Number.isFinite);
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const spread = max - min || 1;
  const polyline = points
    .map(
      (value, index) =>
        `${(index / (points.length - 1)) * 100},${38 - ((value - min) / spread) * 34}`,
    )
    .join(" ");
  return (
    <div
      aria-label="Recent split-adjusted daily closing prices"
      role="img"
      className="rounded-md bg-secondary/30 px-2 py-3"
    >
      <svg
        viewBox="0 0 100 42"
        preserveAspectRatio="none"
        className="h-20 w-full overflow-visible text-primary"
      >
        <polyline
          points={polyline}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <p className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>Earlier</span>
        <span>Latest</span>
      </p>
    </div>
  );
}
