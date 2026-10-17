import { DataFreshnessIndicator } from "@/components/app/data-freshness-indicator";
import { MetricCard } from "@/components/app/metric-card";
import { PageSection } from "@/components/app/page-section";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { sortedByWeight } from "@/components/features/portfolio/decision-components";
import type { Overview } from "@/lib/domain-contracts";
import { dateTime, statusLabel } from "@/lib/display";
import {
  countNote,
  currency,
  percent,
  portfolioCoverageTone,
  type PortfolioHoldingRow,
} from "@/components/features/portfolio/portfolio-data";

export function PortfolioOverviewSection({
  overview,
  rows,
}: {
  overview: Overview;
  rows: PortfolioHoldingRow[];
}) {
  const largest = sortedByWeight(overview.companies).find(
    (company) => company.current_weight !== null,
  );
  const cashCount = overview.snapshot?.cash_positions.length ?? 0;
  const missingTargets = overview.companies.filter(
    (company) =>
      company.company.lifecycle === "PORTFOLIO" &&
      company.target_weight === null,
  );
  const staleHolding = overview.holdings_freshness === "STALE";
  const unresolvedCount = overview.valuation_gaps.length;

  return (
    <PageSection
      id="portfolio-overview"
      title="Portfolio at a glance"
      description="Current mark-to-market uses the latest accepted holdings with eligible listing prices and dated FX. It is not historical portfolio performance."
    >
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label={`Current value · ${overview.valuation_currency}`}
          value={currency(
            overview.base_market_value,
            overview.valuation_currency,
          )}
          note={
            overview.valuation_status === "VALUED"
              ? `Market valuation as of ${dateTime(overview.valuation_as_of)}`
              : `Portfolio total ${statusLabel(overview.valuation_status).toLowerCase()}`
          }
        />
        <MetricCard
          label="Security positions"
          value={String(overview.snapshot?.positions.length ?? rows.length)}
          note={
            overview.snapshot
              ? `Positions as of ${dateTime(overview.snapshot.effective_at)}`
              : "No accepted holdings snapshot"
          }
        />
        <MetricCard
          label="Cash exposure"
          value={
            cashCount > 0
              ? countNote(cashCount, "currency")
              : "No cash recorded"
          }
          note={
            cashCount > 0
              ? "Balances are shown by original currency below; no unsupported total is inferred."
              : "Cash balances are not present in the accepted snapshot."
          }
        />
        <MetricCard
          label="Largest company exposure"
          value={largest?.company.name ?? "Unavailable"}
          note={
            largest
              ? `${percent(largest.current_weight)} of valued portfolio · ${currency(largest.current_market_value, largest.current_market_currency)}`
              : "Comparable company weights are unavailable."
          }
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <Card className="shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Data timing and completeness
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <DataFreshnessIndicator
              state={
                overview.holdings_freshness ??
                (overview.snapshot ? "UNKNOWN" : "NO_DATA")
              }
              observedAt={overview.snapshot?.effective_at}
              source="Holdings confirmation"
              detail={
                overview.holdings_age_days === undefined ||
                overview.holdings_age_days === null
                  ? "Age unknown"
                  : `${overview.holdings_age_days} days old`
              }
            />
            <DataFreshnessIndicator
              state={overview.market_data_through ? "AVAILABLE" : "UNAVAILABLE"}
              observedAt={overview.market_data_through}
              source="Market data through"
            />
            <DataFreshnessIndicator
              state={overview.fx_data_through ? "AVAILABLE" : "UNAVAILABLE"}
              observedAt={overview.fx_data_through}
              source="FX data through"
            />
            <div className="flex flex-wrap items-center gap-2 border-t pt-3 text-xs text-muted-foreground">
              <StatusIndicator
                status={overview.valuation_status}
                tone={portfolioCoverageTone(overview.valuation_status)}
              />
              <span>{statusLabel(overview.valuation_mode)}</span>
              {overview.snapshot && (
                <span>
                  Snapshot recorded {dateTime(overview.snapshot.recorded_at)}
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Portfolio exceptions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!overview.snapshot && (
              <p className="rounded-md border border-warning/35 bg-warning/10 p-3 text-warning">
                No accepted holdings snapshot is available. Position quantities,
                value and weights remain unavailable.
              </p>
            )}
            {staleHolding && (
              <p className="rounded-md border border-warning/35 bg-warning/10 p-3 text-warning">
                {overview.holdings_age_days === null ||
                overview.holdings_age_days === undefined
                  ? "Holdings confirmation age is unknown."
                  : `Holdings confirmation is ${overview.holdings_age_days} days old.`}{" "}
                Current marks may be useful for context, while rank and
                Execution Pace can remain in review.
              </p>
            )}
            {missingTargets.length > 0 && (
              <div className="rounded-md border p-3">
                <p className="font-medium">
                  Strategic targets need investor review
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  No target is inferred for{" "}
                  {missingTargets.map((item) => item.company.name).join(", ")}.
                </p>
              </div>
            )}
            {unresolvedCount > 0 && (
              <div className="rounded-md border p-3">
                <p className="font-medium">
                  {unresolvedCount} valuation input
                  {unresolvedCount === 1 ? "" : "s"} unresolved
                </p>
                <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
                  {overview.valuation_gaps.slice(0, 4).map((gap) => (
                    <li
                      key={`${gap.identity}-${gap.reason}`}
                      className="flex justify-between gap-2"
                    >
                      <span>{gap.identity}</span>
                      <span className="text-right">
                        {statusLabel(gap.reason)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {!staleHolding &&
              missingTargets.length === 0 &&
              unresolvedCount === 0 && (
                <p className="text-xs text-muted-foreground">
                  No portfolio-specific valuation or target exception was
                  returned.
                </p>
              )}
            <p className="text-xs text-muted-foreground">
              {
                rows.filter(
                  (row) =>
                    row.priceFreshness !== "FRESH" ||
                    row.valuationStatus !== "VALUED",
                ).length
              }{" "}
              listing marks need freshness or valuation review.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {(overview.snapshot?.cash_positions ?? []).map((cash) => {
          const valuation = overview.cash_valuations.find(
            (item) => item.currency === cash.currency,
          );
          return (
            <MetricCard
              key={cash.currency}
              label={`${cash.currency} cash`}
              value={currency(cash.balance, cash.currency)}
              note={
                valuation?.valuation_status === "VALUED"
                  ? `${currency(valuation.base_market_value, overview.valuation_currency)} at portfolio valuation · weight ${percent(valuation.portfolio_weight ?? null)}`
                  : `Base-currency value ${statusLabel(valuation?.valuation_status ?? "UNAVAILABLE").toLowerCase()}`
              }
            />
          );
        })}
      </div>

      <details className="rounded-xl border bg-card p-4">
        <summary className="cursor-pointer text-sm font-semibold">
          Valuation and holdings audit details
        </summary>
        <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2 xl:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">Valuation basis</dt>
            <dd className="mt-1 font-medium">
              {statusLabel(overview.valuation_mode)} · as of{" "}
              {dateTime(overview.valuation_as_of)}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Holdings snapshot</dt>
            <dd className="mt-1 break-all font-mono">
              {overview.snapshot?.id ?? "No accepted snapshot"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Snapshot actor / source</dt>
            <dd className="mt-1">
              {overview.snapshot
                ? `${statusLabel(overview.snapshot.actor)} · ${overview.snapshot.source ?? "Source not recorded"}`
                : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Snapshot reason</dt>
            <dd className="mt-1">
              {overview.snapshot?.reason ?? "No snapshot rationale recorded"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">
              Snapshot effective / recorded
            </dt>
            <dd className="mt-1">
              {overview.snapshot
                ? `${dateTime(overview.snapshot.effective_at)} / ${dateTime(overview.snapshot.recorded_at)}`
                : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Accepted target revision</dt>
            <dd className="mt-1 break-all font-mono">
              {overview.target_revision?.id ?? "No accepted target revision"}
              {overview.target_revision && (
                <span className="mt-1 block font-sans text-muted-foreground">
                  recorded {dateTime(overview.target_revision.recorded_at)}
                </span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Market / FX data through</dt>
            <dd className="mt-1">
              {dateTime(overview.market_data_through)} /{" "}
              {dateTime(overview.fx_data_through)}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Quote provider provenance</dt>
            <dd className="mt-1 text-muted-foreground">
              Provider identity is not part of the portfolio overview contract.
              Listing quote details are available through the company
              market-data view and Operations.
            </dd>
          </div>
        </dl>
      </details>
    </PageSection>
  );
}
