"use client";

import { useState } from "react";
import { DataFreshnessIndicator } from "@/components/app/data-freshness-indicator";
import { DemoNotice } from "@/components/app/demo-notice";
import { PendingOrError } from "@/components/app/empty-state";
import { MetricCard } from "@/components/app/metric-card";
import { MetricGroup } from "@/components/app/metric-group";
import { PageHeader } from "@/components/app/page-header";
import { StatusIndicator } from "@/components/app/status-indicator";
import { AllocationComparison } from "@/components/features/decisions/allocation-comparison";
import { DecisionDetailDrawer } from "@/components/features/decisions/decision-detail-drawer";
import {
  allocationCompanies,
  portfolioOpportunity,
  watchlistOpportunity,
} from "@/components/features/decisions/decision-data";
import { ExecutionRationale } from "@/components/features/decisions/execution-rationale";
import { ReturnComparison } from "@/components/features/decisions/return-comparison";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  isOverview,
  isReturnMethodologies,
  isUniverseExecutionPaceSummary,
  isUniverseModelOutputSummary,
  isUniverseRankingSummary,
  isUniverseScoreSummary,
  type ReturnComparabilityRule,
} from "@/lib/domain-contracts";
import { dateTime, formatCurrency, statusLabel } from "@/lib/display";

function ReturnPolicy({ rules }: { rules: ReturnComparabilityRule[] }) {
  return (
    <details className="rounded-lg border bg-card p-4">
      <summary className="cursor-pointer text-sm font-semibold">
        Return methodology and cross-method policy
      </summary>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        Cohorts below come from canonical ranking inputs. A cross-method rule
        describes the domain policy; it does not make two observed returns
        comparable when listing, currency, dates or share-price bases are
        unresolved.
      </p>
      {rules.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">
          No comparability rules were returned.
        </p>
      ) : (
        <ul className="mt-3 divide-y text-xs">
          {rules.map((rule) => (
            <li
              key={`${rule.left_methodology}-${rule.right_methodology}`}
              className="grid gap-1 py-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:gap-4"
            >
              <span>
                {statusLabel(rule.left_methodology)} ↔{" "}
                {statusLabel(rule.right_methodology)}
              </span>
              <span className="font-medium">{statusLabel(rule.status)}</span>
              <span className="text-muted-foreground sm:col-span-2">
                {rule.rationale}
              </span>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

export function DecisionsWorkspace({ id }: { id: string }) {
  const overviewView = useResearch(`portfolios/${id}/overview`, isOverview);
  const rankingView = useResearch(
    "universe/ranking-summary",
    isUniverseRankingSummary,
  );
  const paceView = useResearch(
    "universe/execution-pace-summary",
    isUniverseExecutionPaceSummary,
  );
  const modelView = useResearch(
    "universe/model-output-summary",
    isUniverseModelOutputSummary,
  );
  const scoreView = useResearch(
    "universe/score-summary",
    isUniverseScoreSummary,
  );
  const returnMethodsView = useResearch(
    "return-methodologies",
    isReturnMethodologies,
  );
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(
    null,
  );
  const overview = overviewView.data;

  if (!overview) {
    return (
      <>
        <PageHeader
          title="Decisions"
          description="Review strategic allocation, comparable opportunity context, and portfolio timing evidence."
        />
        <PendingOrError error={overviewView.error} retry={overviewView.retry} />
      </>
    );
  }

  const companies = allocationCompanies(overview);
  const portfolioOpportunities = companies.map((row) =>
    portfolioOpportunity(
      row,
      rankingView.data?.find((item) => item.company.id === row.company.id),
      modelView.data?.find((item) => item.company.id === row.company.id),
      scoreView.data?.find((item) => item.company.id === row.company.id),
      paceView.data?.find((item) => item.company.id === row.company.id),
      rankingView.data !== undefined,
    ),
  );
  const watchlistOpportunities = (rankingView.data ?? [])
    .filter((item) => item.company.lifecycle === "WATCHLIST")
    .map((item) =>
      watchlistOpportunity(
        item,
        modelView.data?.find((model) => model.company.id === item.company.id),
        scoreView.data?.find((score) => score.company.id === item.company.id),
        paceView.data?.find((pace) => pace.company.id === item.company.id),
        rankingView.data !== undefined,
      ),
    );
  const allOpportunities = [
    ...portfolioOpportunities,
    ...watchlistOpportunities,
  ];
  const selectedOpportunity =
    allOpportunities.find((item) => item.company.id === selectedCompanyId) ??
    null;
  const serviceIssues = [
    rankingView.error ? "rank summary" : null,
    paceView.error ? "Execution Pace" : null,
    modelView.error ? "model outputs" : null,
    scoreView.error ? "quality assessments" : null,
    returnMethodsView.error ? "return methodology policy" : null,
  ].filter((item): item is string => item !== null);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Decisions"
        description="What deserves investigation or investor review? Compare accepted portfolio architecture, method-aware opportunity inputs, and recorded execution timing without turning them into trade instructions."
        demo={overview.portfolio.is_demo}
        badge={<StatusIndicator status={overview.valuation_status} />}
        context={
          <>
            <Badge variant="secondary">{overview.portfolio.name}</Badge>
            <Badge variant="outline">
              Base currency · {overview.valuation_currency}
            </Badge>
            <DataFreshnessIndicator
              state={overview.holdings_freshness}
              detail="holdings baseline"
            />
          </>
        }
      />
      {overview.portfolio.is_demo && <DemoNotice />}

      <MetricGroup label="Decision baseline" columns={3}>
        <MetricCard
          label="Current mark-to-market"
          value={
            overview.valuation_status === "VALUED"
              ? formatCurrency(
                  overview.base_market_value,
                  overview.valuation_currency,
                )
              : statusLabel(overview.valuation_status)
          }
          note={
            overview.valuation_as_of
              ? `Market valuation as of ${dateTime(overview.valuation_as_of)}`
              : "Valuation time unavailable"
          }
        />
        <MetricCard
          label="Holdings confirmation"
          value={statusLabel(overview.holdings_freshness)}
          note={
            overview.snapshot
              ? `${overview.snapshot.completeness} snapshot · ${dateTime(overview.snapshot.effective_at)}`
              : "No accepted holdings baseline"
          }
          tone={overview.holdings_freshness === "STALE" ? "warning" : "default"}
        />
        <MetricCard
          label="Strategic target revision"
          value={overview.target_revision ? "Accepted" : "Unavailable"}
          note={
            overview.target_revision
              ? `Recorded ${dateTime(overview.target_revision.recorded_at)}`
              : "No accepted target architecture"
          }
        />
      </MetricGroup>

      <nav
        aria-label="Decision sections"
        className="flex flex-wrap gap-2 border-b pb-3 text-sm"
      >
        <a
          href="#decision-allocation"
          className="rounded-md px-3 py-2 hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          Allocation
        </a>
        <a
          href="#decision-opportunity"
          className="rounded-md px-3 py-2 hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          Opportunity
        </a>
        <a
          href="#decision-execution"
          className="rounded-md px-3 py-2 hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          Execution
        </a>
      </nav>

      {serviceIssues.length > 0 && (
        <Card
          role="status"
          className="border-warning/35 bg-warning/10 shadow-none"
        >
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-warning">
              Some decision evidence is unavailable: {serviceIssues.join(", ")}.
              Missing context remains unavailable; it is not treated as zero or
              neutral.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                rankingView.retry();
                paceView.retry();
                modelView.retry();
                scoreView.retry();
                returnMethodsView.retry();
              }}
            >
              Retry decision context
            </Button>
          </CardContent>
        </Card>
      )}

      <AllocationComparison
        overview={overview}
        rows={companies}
        onSelect={setSelectedCompanyId}
      />

      <section id="decision-opportunity" className="scroll-mt-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Opportunity</h2>
          <p className="mt-1 max-w-3xl text-sm leading-5 text-muted-foreground">
            Returns are shown from the latest immutable rank-input snapshots,
            with each run date and canonical comparability cohort. Unclassified
            returns are isolated. Portfolio Rank and Watchlist Rank remain
            separate concepts.
          </p>
        </div>
        {returnMethodsView.data && (
          <ReturnPolicy rules={returnMethodsView.data.rules} />
        )}
        <ReturnComparison
          title="Portfolio Rank"
          description="Incremental-capital context for current Portfolio companies. Current weights and target gaps are shown separately from the rank-time inputs."
          rows={portfolioOpportunities}
          onSelect={setSelectedCompanyId}
        />
        <ReturnComparison
          title="Watchlist Rank"
          description="Valuation opportunity among explicit Watchlist companies. Watchlist entries have no current portfolio target or weight."
          rows={watchlistOpportunities}
          onSelect={setSelectedCompanyId}
        />
      </section>

      <ExecutionRationale
        rows={companies}
        paceRows={paceView.data}
        onSelect={setSelectedCompanyId}
      />

      <details className="rounded-lg border bg-card p-4">
        <summary className="cursor-pointer text-sm font-semibold">
          Allocation and decision provenance
        </summary>
        <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Holdings snapshot</dt>
            <dd className="mt-1 break-all">
              {overview.snapshot?.id ?? "Unavailable"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Target revision</dt>
            <dd className="mt-1 break-all">
              {overview.target_revision?.id ?? "Unavailable"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Valuation basis</dt>
            <dd className="mt-1">
              {statusLabel(overview.valuation_mode)} ·{" "}
              {dateTime(overview.valuation_as_of)}
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
            <dt className="text-muted-foreground">Allocation status</dt>
            <dd className="mt-1">{statusLabel(overview.valuation_status)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Decision history</dt>
            <dd className="mt-1">
              Latest rank and Execution Pace records are immutable; this page is
              read-only.
            </dd>
          </div>
        </dl>
      </details>

      <DecisionDetailDrawer
        opportunity={selectedOpportunity}
        open={selectedOpportunity !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedCompanyId(null);
        }}
      />
    </div>
  );
}
