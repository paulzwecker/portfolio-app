"use client";

import { use, useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DemoNotice,
  PageTitle,
  PendingOrError,
  useResearch,
} from "@/components/research-frame";
import {
  isDetail,
  isCompanyRankings,
  lifecycleStates,
  isScoreCurrents,
  isScoreHistory,
  isListingMarketDataList,
  isCompanyModelOutputsCurrent,
  isModelOutputHistory,
  isCompanyReportedFundamentals,
  scoreDimensions,
  rankingTypes,
  type RankingType,
  type ScoreCurrent,
  type ScoreDimension,
  type ScoreStatus,
  type CompanyDetail,
  type Lifecycle,
  type ModelOutputSnapshot,
  type CompanyReportedFundamentals,
  type ReportedFundamentalPeriod,
} from "@/lib/domain-contracts";
import { date, percent, quantity } from "@/lib/display";
import { CanonicalDcfExplorer } from "@/components/canonical-dcf";
import { CanonicalArchetypeExplorer } from "@/components/canonical-archetypes";
import { ModelMigrationStatus } from "@/components/model-migration-status";
import { ConsensusEstimates } from "@/components/consensus-estimates";
import { SourceDocuments } from "@/components/source-documents";

export default function CompanyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const state = useResearch(`companies/${encodeURIComponent(id)}`, isDetail);
  const detail = state.data;
  if (!detail)
    return (
      <>
        <PageTitle
          title="Company"
          description="Identity, investment lifecycle and portfolio context."
        />
        <PendingOrError {...state} />
      </>
    );

  return (
    <>
      <Link
        className="mb-5 inline-block text-xs text-muted-foreground hover:text-primary"
        href="/universe"
      >
        ← Back to universe
      </Link>
      <PageTitle
        title={detail.company.name}
        description="Company Explorer · canonical investment, market and model context"
        demo={detail.company.is_demo}
      />
      {detail.company.is_demo && <DemoNotice />}
      <div className="mb-6 space-y-4 rounded-xl border bg-card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={detail.company.lifecycle ? "default" : "secondary"}>
            {detail.company.lifecycle ?? "Lifecycle unassigned"}
          </Badge>
          <Badge variant="outline">
            Reporting currency ·{" "}
            {detail.company.reporting_currency ?? "Unknown"}
          </Badge>
          {detail.listings.map((listing) => (
            <Badge key={listing.id} variant="outline" className="max-w-full">
              {listing.ticker} · {listing.venue} ·{" "}
              {listing.currency ?? "Currency unknown"}
            </Badge>
          ))}
          {detail.listings.length === 0 && (
            <Badge variant="secondary">No listings recorded</Badge>
          )}
        </div>
        <nav
          aria-label="Company research sections"
          className="flex flex-wrap gap-2 border-t pt-4"
        >
          {[
            ["overview", "Overview"],
            ["investment-quality", "Quality & risk"],
            ["market-facts", "Market data"],
            ["reported-fundamentals", "Reported fundamentals"],
            ["source-documents", "Filings & sources"],
            ["consensus-estimates", "Consensus estimates"],
            ["canonical-models", "Model & valuation"],
            ["canonical-model-archetypes", "Other model methods"],
            ["model-migration-status", "Model migration"],
            ["model-output-history", "Imported outputs"],
            ["ranking-context", "Ranking context"],
          ].map(([target, label]) => (
            <Link
              key={target}
              href={`#${target}`}
              className="rounded-md border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
      <CompanyOverview detail={detail} lifecycleChanged={state.retry} />
      <InvestmentQuality companyId={detail.company.id} />
      <MarketFacts companyId={detail.company.id} />
      <ReportedFundamentalsPanel companyId={detail.company.id} />
      <SourceDocuments companyId={detail.company.id} />
      <ConsensusEstimates companyId={detail.company.id} />
      <CanonicalDcfExplorer
        companyId={detail.company.id}
        listings={detail.listings}
      />
      <CanonicalArchetypeExplorer
        companyId={detail.company.id}
        listings={detail.listings}
      />
      <ModelMigrationStatus companyId={detail.company.id} />
      <ModelOutputs companyId={detail.company.id} />
      <RankingPanel companyId={detail.company.id} />
    </>
  );
}

function CompanyOverview({
  detail,
  lifecycleChanged,
}: {
  detail: CompanyDetail;
  lifecycleChanged: () => void;
}) {
  const allocation = detail.portfolio_context;
  return (
    <section
      id="overview"
      aria-labelledby="company-overview-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="company-overview-title" className="text-xl font-semibold">
          Company context
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Canonical identity, explicit lifecycle and observed portfolio state.
          Holdings and targets remain independent.
        </p>
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <Card className="min-w-0 shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Identity & listings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-xs text-muted-foreground">
                Reporting currency
              </p>
              <p className="mt-1 text-sm font-medium">
                {detail.company.reporting_currency ?? "Unknown"}
              </p>
            </div>
            {detail.securities.length === 0 ? (
              <p className="border-t pt-3 text-sm text-muted-foreground">
                No securities have been recorded.
              </p>
            ) : (
              <ul className="space-y-3 border-t pt-3">
                {detail.securities.map((security) => {
                  const listings = detail.listings.filter(
                    (listing) => listing.security_id === security.id,
                  );
                  return (
                    <li key={security.id} className="min-w-0">
                      <p className="break-words text-sm font-medium">
                        {security.name}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {security.security_type.replaceAll("_", " ")} · Class{" "}
                        {security.share_class ?? "not specified"}
                      </p>
                      {security.underlying_security_id && (
                        <p className="mt-1 break-words text-xs text-muted-foreground">
                          Underlying:{" "}
                          {detail.securities.find(
                            (item) =>
                              item.id === security.underlying_security_id,
                          )?.name ?? "Unspecified"}
                          ; share conversion ratio not recorded.
                        </p>
                      )}
                      {listings.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {listings.map((listing) => (
                            <li
                              key={listing.id}
                              className="flex flex-wrap justify-between gap-x-3 gap-y-1 rounded-md bg-secondary/50 px-3 py-2 text-xs"
                            >
                              <span className="font-medium">
                                {listing.ticker} · {listing.venue}
                              </span>
                              <span className="text-muted-foreground">
                                {listing.currency ?? "Currency unknown"}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-2 text-xs text-muted-foreground">
                          No listing recorded for this security.
                        </p>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card className="min-w-0 shadow-none">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">Investment lifecycle</CardTitle>
              <Badge
                variant={detail.company.lifecycle ? "default" : "secondary"}
              >
                {detail.company.lifecycle ?? "Unassigned"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <details className="border-t pt-3">
              <summary className="cursor-pointer text-sm font-medium">
                Record a lifecycle decision
              </summary>
              <LifecycleEditor detail={detail} changed={lifecycleChanged} />
            </details>
            <details className="border-t pt-3">
              <summary className="cursor-pointer text-sm font-medium">
                Lifecycle history ({detail.lifecycle_history.length})
              </summary>
              {detail.lifecycle_history.length === 0 ? (
                <p className="mt-3 text-sm text-muted-foreground">
                  No lifecycle decision has been recorded.
                </p>
              ) : (
                <ol className="mt-4 space-y-4">
                  {detail.lifecycle_history.map((event) => (
                    <li key={event.id} className="border-l-2 pl-3">
                      <p className="text-sm font-medium">
                        {event.previous_state ?? "Unassigned"} →{" "}
                        {event.new_state}
                      </p>
                      <p className="mt-1 break-words text-sm">{event.reason}</p>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Effective {date(event.effective_at)} · Recorded{" "}
                        {date(event.recorded_at)} · {event.actor}
                      </p>
                      {event.source && (
                        <p className="mt-1 break-words text-xs text-muted-foreground">
                          Source: {event.source}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </details>
          </CardContent>
        </Card>
        <Card className="min-w-0 shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Portfolio & target</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              {detail.portfolio
                ? `${detail.portfolio.name} · ${detail.portfolio.base_currency} base`
                : "No portfolio created"}
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
              <span className="text-xs text-muted-foreground">
                Current allocation
              </span>
              <Badge
                variant={
                  allocation?.allocation_status === "VALUED"
                    ? "default"
                    : "secondary"
                }
              >
                {allocation?.allocation_status.replaceAll("_", " ") ??
                  "Unavailable"}
              </Badge>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <dt className="text-xs text-muted-foreground">
                  Strategic target
                </dt>
                <dd className="mt-1 text-xl font-semibold tabular-nums">
                  {percent(detail.target_weight)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Current weight
                </dt>
                <dd className="mt-1 text-xl font-semibold tabular-nums">
                  {allocation?.current_weight === null ||
                  allocation?.current_weight === undefined
                    ? "Unavailable"
                    : percent(allocation.current_weight)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Current market value
                </dt>
                <dd className="mt-1 break-words text-sm font-medium tabular-nums">
                  {allocation?.current_market_value === null ||
                  allocation?.current_market_value === undefined
                    ? "Unavailable"
                    : formatPrice(
                        allocation.current_market_value,
                        allocation.current_market_currency,
                      )}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Target gap</dt>
                <dd className="mt-1 text-sm font-medium tabular-nums">
                  {detail.target_weight === null
                    ? "No target"
                    : allocation?.allocation_gap === null ||
                        allocation?.allocation_gap === undefined
                      ? "Unavailable"
                      : percent(allocation.allocation_gap)}
                </dd>
              </div>
            </dl>
            <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
              Holding snapshot:{" "}
              {detail.holding_snapshot?.completeness ?? "No snapshot"}
            </p>
            {detail.positions.length > 0 ? (
              <ul className="mt-4 space-y-3 border-t pt-3">
                {detail.positions.map((position) => (
                  <li key={position.listing_id} className="min-w-0 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <strong>
                        {position.ticker} · {position.venue}
                      </strong>
                      <Badge
                        variant={
                          position.price_freshness === "FRESH"
                            ? "default"
                            : "secondary"
                        }
                      >
                        {position.price_freshness.replaceAll("_", " ")}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {quantity(position.quantity)} shares ·{" "}
                      {position.currency ?? "Currency unknown"}
                      {position.price_date
                        ? ` · Price ${date(position.price_date)}`
                        : " · No dated price"}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Native value:{" "}
                      {position.native_market_value === null
                        ? "Unavailable"
                        : formatPrice(
                            position.native_market_value,
                            position.price_currency,
                          )}
                      {" · "}Portfolio value:{" "}
                      {position.base_market_value === null
                        ? position.valuation_status === "FX_UNAVAILABLE"
                          ? "FX unavailable"
                          : "Unavailable"
                        : formatPrice(
                            position.base_market_value,
                            detail.portfolio?.base_currency ?? null,
                          )}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 border-t pt-3 text-sm text-muted-foreground">
                {detail.holding_snapshot?.completeness === "COMPLETE"
                  ? "No holding in the complete snapshot."
                  : "No holding observed; data may be incomplete."}
              </p>
            )}
            {detail.positions.length > 0 &&
              detail.positions.some(
                (position) => position.base_market_value === null,
              ) && (
                <p className="mt-3 text-xs leading-5 text-muted-foreground">
                  Portfolio-currency value is incomplete where a usable price or
                  dated FX observation is missing.
                </p>
              )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
function formatPrice(value: string | null, currency: string | null) {
  if (value === null) return "Unavailable";
  if (!currency) return quantity(value);
  try {
    return new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      maximumFractionDigits: 4,
    }).format(Number(value));
  } catch {
    return `${quantity(value)} ${currency}`;
  }
}

function rateLabel(value: string | null) {
  return value === null
    ? "Unavailable"
    : new Intl.NumberFormat("en", {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(Number(value));
}

function modelValue(value: string | null, currency: string | null) {
  if (value === null) return "Not supplied";
  if (!currency) return quantity(value);
  try {
    return new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(Number(value));
  } catch {
    return `${quantity(value)} ${currency}`;
  }
}

function modelPercent(value: string | null) {
  return value === null
    ? "Not supplied"
    : new Intl.NumberFormat("en", {
        style: "percent",
        maximumFractionDigits: 2,
      }).format(Number(value));
}

const outputLabels: Record<string, string> = {
  weighted_upside: "Weighted upside",
  expected_cash_flow_irr: "Expected cash-flow IRR",
  hurdle: "Investor hurdle",
  expected_excess: "Expected excess",
  forward_fundamental_cagr: "Forward fundamental CAGR",
};

function ModelOutputValues({ snapshot }: { snapshot: ModelOutputSnapshot }) {
  return (
    <>
      <div className="grid gap-2 sm:grid-cols-3">
        {(
          [
            ["Bear", snapshot.bear_fv, snapshot.bear_probability],
            ["Base", snapshot.base_fv, snapshot.base_probability],
            ["Bull", snapshot.bull_fv, snapshot.bull_probability],
          ] as const
        ).map(([scenario, fairValue, probability]) => (
          <div key={scenario} className="rounded-md bg-secondary/40 p-3">
            <p className="text-xs text-muted-foreground">
              {scenario} fair value
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {modelValue(fairValue, snapshot.model_currency)}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Probability: {modelPercent(probability)}
            </p>
          </div>
        ))}
      </div>
      <dl className="grid min-w-0 grid-cols-2 gap-3 border-t pt-3 sm:grid-cols-3 xl:grid-cols-5">
        <div>
          <dt className="text-[10px] leading-4 text-muted-foreground">
            Weighted fair value
          </dt>
          <dd className="mt-1 break-words text-sm font-medium tabular-nums">
            {modelValue(snapshot.weighted_fv, snapshot.model_currency)}
          </dd>
        </div>
        {Object.entries(outputLabels).map(([key, label]) => {
          const value = snapshot[key as keyof ModelOutputSnapshot];
          const formatted =
            typeof value === "string" ? modelPercent(value) : "Not supplied";
          return (
            <div key={key} className="min-w-0">
              <dt className="text-[10px] leading-4 text-muted-foreground">
                {label}
              </dt>
              <dd className="mt-1 break-words text-sm font-medium tabular-nums">
                {formatted}
              </dd>
            </div>
          );
        })}
      </dl>
    </>
  );
}

function ModelOutputs({ companyId }: { companyId: string }) {
  const current = useResearch(
    `companies/${encodeURIComponent(companyId)}/model-outputs/current`,
    isCompanyModelOutputsCurrent,
  );
  const history = useResearch(
    `companies/${encodeURIComponent(companyId)}/model-outputs/history`,
    isModelOutputHistory,
  );
  return (
    <section
      id="model-output-history"
      aria-labelledby="model-output-history-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="model-output-history-title" className="text-xl font-semibold">
          Imported model-output history
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Imported model-contract snapshots. Assumptions and calculations remain
          in the legacy modeling environment; these outputs do not set
          lifecycle, scores or targets.
        </p>
      </div>
      {!current.data ? (
        <PendingOrError {...current} />
      ) : current.data.models.length === 0 ? (
        <Card>
          <CardContent className="py-5 text-sm text-muted-foreground">
            No current model contract is published. Missing values are not zero.
            {current.data.history_count > 0 &&
              ` ${current.data.history_count} historical output snapshots remain available below.`}
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 gap-4 xl:grid-cols-2">
          {current.data.models.map(({ model_key, status, snapshot }) => (
            <Card key={model_key} className="min-w-0 shadow-none">
              <CardHeader className="pb-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-base">{model_key}</CardTitle>
                  <Badge
                    variant={status === "PUBLISHED" ? "default" : "secondary"}
                  >
                    {status.replaceAll("_", " ")}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="min-w-0 space-y-4">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="secondary">{snapshot.output_quality}</Badge>
                  <span>
                    Model currency:{" "}
                    {snapshot.model_currency ?? "Not documented"}
                  </span>
                  <span>
                    Contract {snapshot.contract_version ?? "not published"}
                  </span>
                </div>
                <ModelOutputValues snapshot={snapshot} />
                <p className="text-xs leading-5 text-muted-foreground">
                  Effective date:{" "}
                  {snapshot.effective_at
                    ? date(snapshot.effective_at)
                    : "Not supplied"}
                  {" · "}Captured {date(snapshot.recorded_at)}
                  {snapshot.model_currency === null &&
                    " · Values are shown without currency conversion."}
                </p>
                {snapshot.model_status && (
                  <p className="break-words text-xs leading-5">
                    {snapshot.model_status}
                  </p>
                )}
                {snapshot.field_issues.length > 0 && (
                  <ul className="space-y-1 text-xs text-amber-800">
                    {snapshot.field_issues.map((issue, index) => (
                      <li key={`${issue.field}-${index}`}>
                        {issue.field}: {issue.reason}
                      </li>
                    ))}
                  </ul>
                )}
                <p className="break-words border-t pt-3 text-[10px] leading-4 text-muted-foreground">
                  Source: {snapshot.source}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <details className="mt-4 rounded-lg border bg-card p-4">
        <summary className="cursor-pointer text-sm font-medium">
          Model output history ({current.data?.history_count ?? "…"})
        </summary>
        {!history.data ? (
          <div className="mt-3">
            <PendingOrError {...history} />
          </div>
        ) : history.data.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            No model-output history has been imported.
          </p>
        ) : (
          <ol className="mt-4 space-y-4">
            {history.data.map((snapshot) => (
              <li key={snapshot.id} className="min-w-0 border-l-2 pl-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="break-words text-sm font-medium">
                    {snapshot.model_key} ·{" "}
                    {snapshot.revision_type ??
                      snapshot.snapshot_kind.replaceAll("_", " ")}
                  </h3>
                  <Badge variant="secondary">{snapshot.output_quality}</Badge>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Effective:{" "}
                  {snapshot.effective_at
                    ? date(snapshot.effective_at)
                    : "Not supplied"}
                  {" · "}Recorded: {date(snapshot.recorded_at)}
                  {" · "}Currency: {snapshot.model_currency ?? "Unknown"}
                </p>
                <div className="mt-3 space-y-3">
                  <ModelOutputValues snapshot={snapshot} />
                  {snapshot.rationale && (
                    <p className="break-words text-xs leading-5">
                      {snapshot.rationale}
                    </p>
                  )}
                  {snapshot.evidence && (
                    <p className="break-words text-xs leading-5 text-muted-foreground">
                      Evidence: {snapshot.evidence}
                    </p>
                  )}
                  {snapshot.field_issues.length > 0 && (
                    <p className="text-xs text-amber-800">
                      {snapshot.field_issues.length} source data-quality
                      issue(s)
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </details>
    </section>
  );
}

const fundamentalMetricLabels: Record<string, string> = {
  REVENUE: "Revenue",
  GROSS_PROFIT: "Gross profit",
  OPERATING_INCOME: "Operating income",
  NET_INCOME: "Net income",
  CASH_AND_CASH_EQUIVALENTS: "Cash & equivalents",
  CURRENT_DEBT: "Current debt",
  NONCURRENT_DEBT: "Non-current debt",
  OPERATING_CASH_FLOW: "Operating cash flow",
  CAPITAL_EXPENDITURES: "Capital expenditures",
  DILUTED_WEIGHTED_AVERAGE_SHARES: "Diluted weighted-average shares",
};

type FundamentalPeriodFilter = "ALL" | "ANNUAL" | "QUARTERLY" | "INSTANT";

function latestFundamentalPeriods(
  data: CompanyReportedFundamentals,
  metric: string,
): ReportedFundamentalPeriod[] {
  const latest = new Map<string, ReportedFundamentalPeriod>();
  for (const period of data.periods) {
    if (period.metric !== metric) continue;
    const key = `${period.period_type}:${period.currency ?? period.unit}`;
    const prior = latest.get(key);
    if (!prior || Date.parse(period.period_end) > Date.parse(prior.period_end))
      latest.set(key, period);
  }
  return [...latest.values()].sort((left, right) => {
    const order = { ANNUAL: 0, QUARTERLY: 1, INSTANT: 2 };
    return (
      order[left.period_type] - order[right.period_type] ||
      (left.currency ?? "").localeCompare(right.currency ?? "")
    );
  });
}

function periodLabel(period: ReportedFundamentalPeriod) {
  const fiscal = period.fiscal_year
    ? `FY${period.fiscal_year}${period.fiscal_period && period.fiscal_period !== "FY" ? ` · ${period.fiscal_period}` : ""}`
    : period.period_type.replaceAll("_", " ");
  return `${fiscal} · ${new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(period.period_end))}`;
}

function ReportedFundamentalsPanel({ companyId }: { companyId: string }) {
  const [periodFilter, setPeriodFilter] =
    useState<FundamentalPeriodFilter>("ALL");
  const query = periodFilter === "ALL" ? "" : `?period_type=${periodFilter}`;
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/reported-fundamentals${query}`,
    isCompanyReportedFundamentals,
  );
  return (
    <section
      id="reported-fundamentals"
      aria-labelledby="reported-fundamentals-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2
            id="reported-fundamentals-title"
            className="text-xl font-semibold"
          >
            Reported fundamentals
          </h2>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
            Filing facts are shown as reported, with currency, source and later
            filing history. No growth, ratio or free-cash-flow calculation is
            performed here.
          </p>
        </div>
        <div
          className="flex flex-wrap gap-1"
          aria-label="Financial period filter"
        >
          {(["ALL", "ANNUAL", "QUARTERLY", "INSTANT"] as const).map((value) => (
            <Button
              key={value}
              size="sm"
              variant={periodFilter === value ? "default" : "outline"}
              aria-pressed={periodFilter === value}
              onClick={() => setPeriodFilter(value)}
            >
              {value === "ALL" ? "All periods" : value.replaceAll("_", " ")}
            </Button>
          ))}
        </div>
      </div>
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge
              variant={
                state.data.provider_identity_status === "MAPPED"
                  ? "outline"
                  : "secondary"
              }
            >
              SEC identity · {state.data.provider_identity_status.toLowerCase()}
            </Badge>
            {state.data.provider_ids.map((providerId) => (
              <Badge key={providerId} variant="outline">
                CIK {providerId}
              </Badge>
            ))}
            <span className="text-xs text-muted-foreground">
              {state.data.latest_observed_at
                ? `Last retrieved ${date(state.data.latest_observed_at)}`
                : "No provider response stored"}
            </span>
          </div>
          {state.data.provider_identity_status !== "MAPPED" && (
            <p className="mb-3 rounded-md border border-dashed p-3 text-sm leading-5 text-muted-foreground">
              An exact SEC issuer identity has not been recorded. Facts remain
              unavailable until the company-to-CIK mapping is verified.
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Object.entries(fundamentalMetricLabels).map(([metric, label]) => {
              const coverage = state.data!.coverage.find(
                (item) => item.metric === metric,
              );
              const periods = latestFundamentalPeriods(state.data!, metric);
              const history = state.data!.periods.filter(
                (item) => item.metric === metric,
              );
              return (
                <Card key={metric} className="min-w-0 shadow-none">
                  <CardHeader className="pb-2">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <CardTitle className="text-sm">{label}</CardTitle>
                      <Badge
                        variant={
                          coverage?.status === "AVAILABLE"
                            ? "outline"
                            : "secondary"
                        }
                      >
                        {coverage?.status === "NOT_IMPORTED"
                          ? "Not imported"
                          : (coverage?.status.replaceAll("_", " ") ??
                            "Unavailable")}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {periods.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No{" "}
                        {periodFilter === "ALL"
                          ? "reported fact"
                          : `${periodFilter.toLowerCase()} fact`}{" "}
                        stored.
                      </p>
                    ) : (
                      periods.map((period) => (
                        <div
                          key={`${period.period_type}:${period.currency ?? period.unit}`}
                          className="border-t pt-3 first:border-0 first:pt-0"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-xs text-muted-foreground">
                                {period.period_type.replaceAll("_", " ")} ·{" "}
                                {periodLabel(period)}
                              </p>
                              <p className="mt-1 break-words text-lg font-semibold tabular-nums">
                                {period.value === null
                                  ? "Conflicting reported values"
                                  : period.unit === "currency"
                                    ? formatPrice(period.value, period.currency)
                                    : `${quantity(period.value)} shares`}
                              </p>
                            </div>
                            {period.selection_status !== "AVAILABLE" && (
                              <Badge variant="secondary">
                                {period.selection_status.replaceAll("_", " ")}
                              </Badge>
                            )}
                          </div>
                          <p className="mt-1 break-words text-xs text-muted-foreground">
                            {period.selected_observation
                              ? `${period.selected_observation.provider_id} · filed ${period.selected_observation.filed_at ? date(period.selected_observation.filed_at) : "date unavailable"} · ${period.selected_observation.data_quality}`
                              : `${period.observations.length} source observations require reconciliation`}
                          </p>
                          <details className="mt-2 border-t pt-2">
                            <summary className="cursor-pointer text-xs font-medium">
                              Filing history ({period.observations.length})
                            </summary>
                            {period.observations.length === 0 ? (
                              <p className="mt-2 text-xs text-muted-foreground">
                                No source observations are available.
                              </p>
                            ) : (
                              <ol className="mt-3 space-y-3">
                                {period.observations.map((observation) => (
                                  <li
                                    key={observation.id}
                                    className="min-w-0 border-l-2 pl-3 text-xs"
                                  >
                                    <p className="font-medium">
                                      {observation.value}{" "}
                                      {observation.currency ?? observation.unit}
                                      {observation.currency
                                        ? ` · ${observation.unit}`
                                        : ""}
                                    </p>
                                    <p className="mt-1 text-muted-foreground">
                                      {observation.revision_context.replaceAll(
                                        "_",
                                        " ",
                                      )}{" "}
                                      · filed{" "}
                                      {observation.filed_at
                                        ? date(observation.filed_at)
                                        : "date unavailable"}
                                    </p>
                                    <p className="mt-1 text-muted-foreground">
                                      {observation.provider_id} · recorded{" "}
                                      {date(observation.recorded_at)} ·{" "}
                                      {observation.data_quality}
                                    </p>
                                    {observation.quality_reason && (
                                      <p className="mt-1 leading-5">
                                        {observation.quality_reason}
                                      </p>
                                    )}
                                    {observation.supersedes_observation_id && (
                                      <p className="mt-1 break-all text-muted-foreground">
                                        Supersedes{" "}
                                        {observation.supersedes_observation_id}
                                      </p>
                                    )}
                                    <a
                                      className="mt-1 inline-block break-all text-primary underline-offset-2 hover:underline"
                                      href={observation.source_url}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      {observation.source_concept} · filing
                                      source
                                    </a>
                                  </li>
                                ))}
                              </ol>
                            )}
                          </details>
                        </div>
                      ))
                    )}
                    {history.length > 0 && (
                      <p className="border-t pt-2 text-xs text-muted-foreground">
                        {coverage?.observation_count} retained observation(s)
                        across {history.length} period(s).
                      </p>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
          <p className="mt-3 rounded-md bg-secondary/50 p-3 text-xs leading-5 text-muted-foreground">
            Free cash flow is not imported as a reported fact: issuers use
            differing definitions. Revenue growth and other ratios are also not
            calculated from these observations.
          </p>
        </>
      )}
    </section>
  );
}

function MarketFacts({ companyId }: { companyId: string }) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/market-data?history_limit=90`,
    isListingMarketDataList,
  );
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
      {!state.data ? (
        <PendingOrError {...state} />
      ) : state.data.length === 0 ? (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            No supported exchange listing has been recorded.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {state.data.map((market) => {
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

const scoreLabels: Record<ScoreDimension, string> = {
  DURABILITY_10Y: "10Y Durability",
  COMPOUNDER_QUALITY: "Compounder Quality",
  EXECUTION: "Execution",
  RISK: "Risk",
};

const rankingLabels: Record<RankingType, string> = {
  PORTFOLIO: "Portfolio Rank",
  WATCHLIST: "Watchlist Rank",
  RESEARCH: "Research Rank",
};

function displayScore(assessment: ScoreCurrent["assessment"]) {
  if (!assessment) return "Not assessed";
  if (assessment.status !== "ASSESSED") return assessment.status;
  return `${assessment.score} / 5`;
}

function InvestmentQuality({ companyId }: { companyId: string }) {
  const current = useResearch(
    `companies/${encodeURIComponent(companyId)}/scores/current`,
    isScoreCurrents,
  );
  const history = useResearch(
    `companies/${encodeURIComponent(companyId)}/scores/history`,
    isScoreHistory,
  );
  return (
    <section
      id="investment-quality"
      aria-labelledby="investment-quality-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="investment-quality-title" className="text-xl font-semibold">
          Investment quality
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Four independent assessments. Risk rises with its score; it excludes
          valuation.
        </p>
      </div>
      {!current.data ? (
        <PendingOrError {...current} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {current.data.map((score) => {
            const earlier = history.data?.filter(
              (entry) =>
                entry.definition.id === score.definition.id &&
                entry.assessment.id !== score.assessment?.id,
            );
            return (
              <Card key={score.definition.id} className="min-w-0 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    {scoreLabels[score.definition.dimension]}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="text-2xl font-semibold tabular-nums">
                    {displayScore(score.assessment)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Scale {score.definition.minimum_score}–
                    {score.definition.maximum_score} {score.definition.units} ·{" "}
                    {score.definition.directionality === "HIGHER_IS_RISK"
                      ? "Higher means greater risk"
                      : "Higher is better"}
                  </p>
                  <p className="break-words text-xs leading-5">
                    {score.assessment?.rationale ??
                      "No assessment has been recorded for this dimension."}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Effective:{" "}
                    {score.assessment?.effective_at
                      ? date(score.assessment.effective_at)
                      : "Not recorded"}
                  </p>
                  {score.assessment && (
                    <Badge variant="secondary">{score.assessment.status}</Badge>
                  )}
                  <details className="border-t pt-3">
                    <summary className="cursor-pointer text-xs font-medium">
                      Score history (
                      {(earlier?.length ?? 0) + (score.assessment ? 1 : 0)})
                    </summary>
                    {history.error ? (
                      <div className="mt-3 space-y-2 text-xs">
                        <p role="alert">History is unavailable.</p>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={history.retry}
                        >
                          Retry history
                        </Button>
                      </div>
                    ) : !history.data ? (
                      <p className="mt-3 text-xs text-muted-foreground">
                        Loading history…
                      </p>
                    ) : history.data.filter(
                        (entry) =>
                          entry.definition.dimension ===
                          score.definition.dimension,
                      ).length === 0 ? (
                      <p className="mt-3 text-xs text-muted-foreground">
                        No historical assessments.
                      </p>
                    ) : (
                      <ol className="mt-3 space-y-3">
                        {history.data
                          .filter(
                            (entry) =>
                              entry.definition.dimension ===
                              score.definition.dimension,
                          )
                          .map((entry) => (
                            <li
                              key={entry.assessment.id}
                              className="border-l-2 pl-3 text-xs"
                            >
                              <p className="font-medium">
                                {entry.assessment.status === "ASSESSED"
                                  ? `${entry.assessment.score} / ${entry.definition.maximum_score}`
                                  : entry.assessment.status}
                              </p>
                              <p className="mt-1 text-muted-foreground">
                                Effective {date(entry.assessment.effective_at)}{" "}
                                · Recorded {date(entry.assessment.recorded_at)}{" "}
                                · {entry.assessment.actor}
                              </p>
                              <p className="mt-2 break-words leading-5">
                                {entry.assessment.rationale}
                              </p>
                              {entry.assessment.source && (
                                <p className="mt-1 break-words text-muted-foreground">
                                  Source: {entry.assessment.source}
                                </p>
                              )}
                              {entry.assessment.superseded_assessment_id && (
                                <p className="mt-1 break-all text-muted-foreground">
                                  Corrects assessment{" "}
                                  {entry.assessment.superseded_assessment_id}
                                </p>
                              )}
                            </li>
                          ))}
                      </ol>
                    )}
                  </details>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      {current.data && (
        <details className="mt-4 rounded-lg border bg-card p-4">
          <summary className="cursor-pointer text-sm font-medium">
            Record a new score assessment
          </summary>
          <ScoreEditor
            companyId={companyId}
            scores={current.data}
            changed={() => {
              current.retry();
              history.retry();
            }}
          />
        </details>
      )}
    </section>
  );
}

function RankingPanel({ companyId }: { companyId: string }) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/rankings`,
    isCompanyRankings,
  );
  return (
    <section
      id="ranking-context"
      aria-labelledby="ranking-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="ranking-title" className="text-xl font-semibold">
          Ranking snapshots
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Portfolio, Watchlist and Research ranks remain separate. A missing
          input or rank is shown explicitly and never becomes position zero.
        </p>
      </div>
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          {rankingTypes.map((type) => {
            const current = state.data!.current.find(
              (ranking) => ranking.definition.ranking_type === type,
            );
            const history = state.data!.history.filter(
              (item) => item.run.definition.ranking_type === type,
            );
            const entry = current?.entry;
            const value = !current?.run
              ? "No run recorded"
              : !entry
                ? "Not included in latest run"
                : entry.status === "RANKED"
                  ? `#${entry.position}`
                  : entry.status;
            return (
              <Card key={type} className="min-w-0 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    {rankingLabels[type]}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="text-xl font-semibold tabular-nums">{value}</p>
                  <p className="text-xs leading-5 text-muted-foreground">
                    {current?.definition.implementation_status ===
                    "NOT_MIGRATED"
                      ? "Ranking inputs are not migrated. Any stored position is a source snapshot, not a recalculated rank."
                      : current?.definition.methodology}
                  </p>
                  {current?.run && (
                    <>
                      <Badge variant="secondary">
                        Run {current.run.status} · {current.run.ranked_count}/
                        {current.run.company_count} ranked
                      </Badge>
                      {entry && entry.status !== "RANKED" && (
                        <p className="break-words text-xs leading-5">
                          {entry.reason}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        As of {date(current.run.as_of)} · Recorded{" "}
                        {date(current.run.recorded_at)} · {current.run.actor}
                      </p>
                    </>
                  )}
                  <details className="border-t pt-3">
                    <summary className="cursor-pointer text-xs font-medium">
                      Ranking history ({history.length})
                    </summary>
                    {history.length === 0 ? (
                      <p className="mt-3 text-xs text-muted-foreground">
                        No historical run contains this company.
                      </p>
                    ) : (
                      <ol className="mt-3 space-y-3">
                        {history.map(({ run, entry: historicalEntry }) => (
                          <li
                            key={historicalEntry.id}
                            className="border-l-2 pl-3 text-xs"
                          >
                            <p className="font-medium">
                              {historicalEntry.status === "RANKED"
                                ? `#${historicalEntry.position}`
                                : historicalEntry.status}
                            </p>
                            <p className="mt-1 text-muted-foreground">
                              As of {date(run.as_of)} · Recorded{" "}
                              {date(run.recorded_at)} · {run.actor}
                            </p>
                            <p className="mt-2 break-words leading-5">
                              {historicalEntry.reason}
                            </p>
                            <p className="mt-1 text-muted-foreground">
                              Run: {run.status} · Definition v
                              {run.definition.version}
                            </p>
                          </li>
                        ))}
                      </ol>
                    )}
                  </details>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ScoreEditor({
  companyId,
  scores,
  changed,
}: {
  companyId: string;
  scores: ScoreCurrent[];
  changed: () => void;
}) {
  const [dimension, setDimension] = useState<ScoreDimension>("DURABILITY_10Y");
  const [status, setStatus] = useState<ScoreStatus>("ASSESSED");
  const [score, setScore] = useState("");
  const [rationale, setRationale] = useState("");
  const [source, setSource] = useState("");
  const [effectiveAt, setEffectiveAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = scores.find(
    (item) => item.definition.dimension === dimension,
  );
  return (
    <Card className="mt-4 shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Record a new assessment</CardTitle>
        <p className="text-xs leading-5 text-muted-foreground">
          Saving creates an immutable history entry. Revisions link to the
          current assessment.
        </p>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!selected) return;
            setBusy(true);
            setError(null);
            try {
              const response = await fetch(
                `/api/research/companies/${encodeURIComponent(companyId)}/score-assessments`,
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  signal: AbortSignal.timeout(10000),
                  body: JSON.stringify({
                    dimension,
                    score: status === "ASSESSED" ? score : null,
                    status,
                    effective_at: effectiveAt
                      ? new Date(effectiveAt).toISOString()
                      : new Date().toISOString(),
                    rationale: rationale.trim(),
                    actor: "LOCAL_USER",
                    source: source.trim() || null,
                    superseded_assessment_id: selected.assessment?.id ?? null,
                  }),
                },
              );
              if (!response.ok)
                throw new Error(
                  response.status === 409
                    ? "A newer assessment exists. Reload scores before revising."
                    : "The assessment could not be saved. Check the score and try again.",
                );
              setScore("");
              setRationale("");
              setSource("");
              changed();
            } catch (failure) {
              setError(
                failure instanceof Error &&
                  failure.message.startsWith("A newer")
                  ? failure.message
                  : "The assessment could not be saved. Check the services and try again.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="block text-xs font-medium">
            Score dimension
            <select
              value={dimension}
              disabled={busy}
              onChange={(event) => {
                setDimension(event.target.value as ScoreDimension);
                setScore("");
              }}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
            >
              {scoreDimensions.map((value) => (
                <option key={value} value={value}>
                  {scoreLabels[value]}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium">
            Data-quality state
            <select
              value={status}
              disabled={busy}
              onChange={(event) => {
                const next = event.target.value as ScoreStatus;
                setStatus(next);
                if (next !== "ASSESSED") setScore("");
              }}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
            >
              {(["ASSESSED", "MISSING", "UNAVAILABLE", "INVALID"] as const).map(
                (value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="block text-xs font-medium">
            Score {status === "ASSESSED" ? "(required)" : "(leave blank)"}
            <input
              type="number"
              min={selected?.definition.minimum_score}
              max={selected?.definition.maximum_score}
              step="0.01"
              value={score}
              required={status === "ASSESSED"}
              disabled={busy || status !== "ASSESSED"}
              onChange={(event) => setScore(event.target.value)}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm tabular-nums"
            />
            <span className="mt-1 block font-normal text-muted-foreground">
              {selected?.definition.minimum_score}–
              {selected?.definition.maximum_score} ·
              {selected?.definition.directionality === "HIGHER_IS_RISK"
                ? " higher means greater risk"
                : " higher is better"}
            </span>
          </label>
          <label className="block text-xs font-medium">
            Effective at (blank uses now)
            <input
              type="datetime-local"
              value={effectiveAt}
              onChange={(event) => setEffectiveAt(event.target.value)}
              disabled={busy}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
            />
          </label>
          <label className="block text-xs font-medium sm:col-span-2">
            Rationale
            <textarea
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              required
              maxLength={4000}
              rows={3}
              disabled={busy}
              className="mt-2 block w-full rounded-md border bg-card p-3 text-sm"
            />
          </label>
          <label className="block text-xs font-medium sm:col-span-2">
            Source URL or identifier (optional)
            <input
              value={source}
              onChange={(event) => setSource(event.target.value)}
              maxLength={1000}
              disabled={busy}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            <Button disabled={busy || !rationale.trim()}>
              {busy ? "Saving…" : "Record score assessment"}
            </Button>
            <span className="text-xs text-muted-foreground">
              Actor: Local user · Definition v{selected?.definition.version}
            </span>
          </div>
          {error && (
            <div
              role="alert"
              className="space-y-2 text-xs text-destructive sm:col-span-2"
            >
              <p>{error}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={changed}
              >
                Reload scores
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

function LifecycleEditor({
  detail,
  changed,
}: {
  detail: CompanyDetail;
  changed: () => void;
}) {
  const [state, setState] = useState<Lifecycle>(
    detail.company.lifecycle ?? "CANDIDATE",
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="mt-5 space-y-3"
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError(null);
        try {
          const response = await fetch(
            `/api/research/companies/${detail.company.id}/lifecycle-transitions`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              signal: AbortSignal.timeout(10000),
              body: JSON.stringify({
                new_state: state,
                expected_event_id: detail.company.lifecycle_event_id,
                actor: "LOCAL_USER",
                reason: reason.trim(),
                effective_at: new Date().toISOString(),
              }),
            },
          );
          if (!response.ok)
            throw new Error(
              response.status === 409
                ? "Lifecycle changed or is already selected. Reload before retrying."
                : "The change could not be saved. Check the services and try again.",
            );
          setReason("");
          changed();
        } catch (failure) {
          setError(
            failure instanceof Error && failure.message.startsWith("Lifecycle")
              ? failure.message
              : "The change could not be saved. Check the services and try again.",
          );
        } finally {
          setBusy(false);
        }
      }}
    >
      <label className="block text-xs font-medium">
        New lifecycle
        <select
          disabled={busy}
          value={state}
          onChange={(e) => setState(e.target.value as Lifecycle)}
          className="mt-2 block h-10 w-full rounded-md border bg-card px-2 text-sm"
        >
          {lifecycleStates.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <label className="block text-xs font-medium">
        Decision reason
        <textarea
          disabled={busy}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          required
          maxLength={1000}
          rows={3}
          className="mt-2 block w-full rounded-md border bg-card p-2 text-sm"
        />
      </label>
      {error && (
        <div role="alert" className="space-y-2 text-xs text-destructive">
          <p>{error}</p>
          <Button type="button" variant="outline" size="sm" onClick={changed}>
            Reload company
          </Button>
        </div>
      )}
      <Button
        size="sm"
        disabled={busy || !reason.trim() || state === detail.company.lifecycle}
      >
        {busy ? "Saving…" : "Record lifecycle decision"}
      </Button>
      <p className="text-xs leading-5 text-muted-foreground">
        Explicit decision with local actor attribution. Holdings and targets
        remain independent.
      </p>
    </form>
  );
}
