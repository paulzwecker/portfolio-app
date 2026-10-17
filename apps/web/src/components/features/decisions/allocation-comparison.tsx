import { Button } from "@/components/ui/button";
import { ResponsiveDataTable } from "@/components/app/responsive-data-table";
import { PageSection } from "@/components/app/page-section";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Card, CardContent } from "@/components/ui/card";
import {
  dateTime,
  formatCurrency,
  formatPercent,
  quantity,
  statusLabel,
} from "@/lib/display";
import type { CompanyPortfolioContext, Overview } from "@/lib/domain-contracts";
import {
  allocationPresence,
  type AllocationPresence,
} from "@/components/features/decisions/decision-data";

const presenceLabels: Record<AllocationPresence, string> = {
  HELD: "Held position",
  TARGET_ONLY: "Target only",
  NO_POSITION: "No position or target",
  HOLDINGS_UNCONFIRMED: "Position unconfirmed",
};

function barWidth(value: string | null) {
  if (value === null) return "0%";
  const percentage = Number(value) * 100;
  if (!Number.isFinite(percentage)) return "0%";
  return `${Math.max(0, Math.min(100, percentage))}%`;
}

function WeightCell({
  value,
  missing,
  label,
  target = false,
}: {
  value: string | null;
  missing: string;
  label: string;
  target?: boolean;
}) {
  return (
    <div className="min-w-24">
      <p className="tabular-nums">
        {value === null ? missing : formatPercent(value, 2, missing)}
      </p>
      {value === null ? (
        <div className="mt-1 h-1.5 rounded-full bg-muted" aria-hidden="true" />
      ) : Number(value) === 0 ? (
        <div
          className="mt-1 h-1.5 border-l-2 border-primary"
          aria-hidden="true"
        />
      ) : (
        <div
          className="mt-1 h-1.5 rounded-full bg-primary/20"
          aria-hidden="true"
        >
          <div
            className={`h-full rounded-full ${target ? "bg-chart-2" : "bg-primary"}`}
            style={{ width: barWidth(value) }}
          />
        </div>
      )}
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function AllocationComparison({
  overview,
  rows,
  onSelect,
}: {
  overview: Overview;
  rows: CompanyPortfolioContext[];
  onSelect: (companyId: string) => void;
}) {
  const columns = [
    {
      id: "company",
      header: "Company",
      className: "w-[27%]",
      render: (row: CompanyPortfolioContext) => (
        <div className="min-w-0">
          <Button
            variant="link"
            size="sm"
            className="h-auto max-w-full justify-start truncate p-0 font-medium"
            onClick={() => onSelect(row.company.id)}
            aria-label={`Inspect ${row.company.name} decision context`}
          >
            {row.company.name}
          </Button>
          <p className="text-[11px] text-muted-foreground">
            {row.company.lifecycle ?? "Lifecycle unassigned"}
          </p>
        </div>
      ),
    },
    {
      id: "presence",
      header: "Portfolio status",
      render: (row: CompanyPortfolioContext) => {
        const presence = allocationPresence(row, overview);
        return (
          <StatusIndicator
            label={presenceLabels[presence]}
            status={presence === "HELD" ? "AVAILABLE" : presence}
          />
        );
      },
    },
    {
      id: "current",
      header: "Current weight",
      render: (row: CompanyPortfolioContext) => (
        <WeightCell
          value={row.current_weight}
          missing={statusLabel(row.allocation_status)}
          label="Current portfolio weight"
        />
      ),
    },
    {
      id: "target",
      header: "Strategic target",
      render: (row: CompanyPortfolioContext) => (
        <WeightCell
          value={row.target_weight}
          missing="No target"
          label="Strategic target weight"
          target
        />
      ),
    },
    {
      id: "gap",
      header: "Allocation gap",
      className: "w-[16%]",
      render: (row: CompanyPortfolioContext) =>
        row.allocation_gap === null ? (
          <span className="text-muted-foreground">Unavailable</span>
        ) : (
          <span className="font-medium tabular-nums">
            {formatPercent(row.allocation_gap, 2)}
          </span>
        ),
    },
  ];

  return (
    <PageSection
      id="decision-allocation"
      title="Allocation"
      description="Canonical current weights and accepted strategic targets are shown on the same 0–100% scale. A gap is context for investor review, not an order or suggested trade."
    >
      {overview.holdings_freshness === "STALE" && (
        <div
          role="status"
          className="rounded-lg border border-warning/35 bg-warning/10 px-4 py-3 text-sm text-warning"
        >
          Holdings confirmation is stale
          {overview.holdings_age_days !== null &&
          overview.holdings_age_days !== undefined
            ? ` (${overview.holdings_age_days} days old)`
            : " (age unknown)"}
          . Current marks may be useful for context; gaps and decisions retain
          their availability states.
        </div>
      )}
      {overview.snapshot?.completeness === "PARTIAL" && (
        <div
          role="status"
          className="rounded-lg border border-warning/35 bg-warning/10 px-4 py-3 text-sm text-warning"
        >
          Holdings snapshot is partial: {overview.snapshot.reason}. Missing
          positions remain unconfirmed and are not treated as zero.
        </div>
      )}
      {overview.valuation_status !== "VALUED" && (
        <div
          role="status"
          className="rounded-lg border border-warning/35 bg-warning/10 px-4 py-3 text-sm text-warning"
        >
          Current portfolio valuation is{" "}
          {statusLabel(overview.valuation_status)}. The allocation view retains
          API-provided missing weights and gaps.
        </div>
      )}
      <ResponsiveDataTable
        caption="Current versus strategic allocation"
        rows={rows}
        getRowKey={(row) => row.company.id}
        columns={columns}
      />
      <div className="grid gap-3 lg:grid-cols-2">
        <section
          aria-labelledby="issuer-concentration-title"
          className="space-y-2"
        >
          <h3 id="issuer-concentration-title" className="text-sm font-semibold">
            Issuer concentration
          </h3>
          {(() => {
            const largest = rows
              .filter((row) => row.current_weight !== null)
              .sort(
                (left, right) =>
                  Number(right.current_weight) - Number(left.current_weight),
              )[0];
            return largest ? (
              <Card className="shadow-none">
                <CardContent className="p-4">
                  <p className="text-xl font-semibold tabular-nums">
                    {formatPercent(largest.current_weight, 2)}
                  </p>
                  <p className="text-sm">{largest.company.name}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Largest API-reported company weight. Sector, geographic and
                    look-through concentration are not calculated here.
                  </p>
                </CardContent>
              </Card>
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                Issuer concentration is unavailable until current weights are
                available.
              </p>
            );
          })()}
        </section>
        <section aria-labelledby="funding-context-title" className="space-y-2">
          <h3 id="funding-context-title" className="text-sm font-semibold">
            Cash and funding context
          </h3>
          {overview.cash_valuations.length === 0 ? (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              No cash balance is present in the accepted holdings snapshot.
            </p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {overview.cash_valuations.map((cash) => (
                <Card key={cash.currency} className="shadow-none">
                  <CardContent className="space-y-2 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium">{cash.currency} cash</p>
                      <StatusIndicator status={cash.valuation_status} />
                    </div>
                    <dl className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <dt className="text-muted-foreground">Balance</dt>
                        <dd className="mt-1 tabular-nums">
                          {formatCurrency(cash.balance, cash.currency, 2)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">
                          Base-currency mark
                        </dt>
                        <dd className="mt-1 tabular-nums">
                          {formatCurrency(
                            cash.base_market_value,
                            overview.valuation_currency,
                            2,
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">
                          Current weight
                        </dt>
                        <dd className="mt-1 tabular-nums">
                          {cash.portfolio_weight === null ||
                          cash.portfolio_weight === undefined
                            ? "Unavailable"
                            : formatPercent(cash.portfolio_weight, 2)}
                        </dd>
                      </div>
                      {cash.fx_rate !== null && cash.fx_rate !== undefined && (
                        <div>
                          <dt className="text-muted-foreground">FX rate</dt>
                          <dd className="mt-1 tabular-nums">
                            {quantity(cash.fx_rate)} · effective{" "}
                            {dateTime(cash.fx_effective_at)}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Cash is shown as available funding context; no amount is allocated
            to a company and no trade is recommended.
          </p>
        </section>
      </div>
      {overview.standalone_positions.length > 0 && (
        <section
          aria-labelledby="standalone-exposure-title"
          className="space-y-2"
        >
          <h3 id="standalone-exposure-title" className="text-sm font-semibold">
            Standalone securities
          </h3>
          <p className="text-xs text-muted-foreground">
            These accepted positions do not have company strategic targets in
            this view.
          </p>
          <ResponsiveDataTable
            caption="Standalone security allocation context"
            rows={overview.standalone_positions}
            getRowKey={(position) => position.listing_id}
            columns={[
              {
                id: "listing",
                header: "Exact listing",
                render: (position) => (
                  <span className="font-medium">
                    {position.ticker} · {position.venue} ·{" "}
                    {position.currency ?? "currency unknown"}
                  </span>
                ),
              },
              {
                id: "quantity",
                header: "Quantity",
                render: (position) => quantity(position.quantity),
              },
              {
                id: "weight",
                header: "Current weight",
                render: (position) =>
                  position.portfolio_weight === null ||
                  position.portfolio_weight === undefined
                    ? "Unavailable"
                    : formatPercent(position.portfolio_weight, 2),
              },
              {
                id: "value",
                header: "Base value",
                render: (position) =>
                  formatCurrency(
                    position.base_market_value,
                    overview.valuation_currency,
                    2,
                  ),
              },
              {
                id: "quality",
                header: "Valuation state",
                render: (position) => statusLabel(position.valuation_status),
              },
            ]}
          />
        </section>
      )}
      <p className="text-xs text-muted-foreground">
        Current holdings snapshot:{" "}
        {overview.snapshot?.effective_at ?? "Unavailable"}
        {overview.target_revision
          ? ` · accepted target revision ${overview.target_revision.id}`
          : " · no accepted strategic target revision"}
      </p>
    </PageSection>
  );
}
