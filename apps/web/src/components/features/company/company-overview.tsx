"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, ChevronDown } from "lucide-react";
import { AttentionCenter } from "@/components/attention-center";
import { EmptyState } from "@/components/app/empty-state";
import { MetricCard } from "@/components/app/metric-card";
import { MetricGroup } from "@/components/app/metric-group";
import { PageSection } from "@/components/app/page-section";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyExecutionPace,
  isCompanyInvestmentThesis,
  isCompanyModelOutputsCurrent,
  isCompanyRankings,
  isScoreCurrents,
  lifecycleStates,
  type CompanyDetail,
  type CompanyInvestmentThesis,
  type CompanyModelOutputsCurrent,
  type InvestmentThesisRevision,
  type CompanyRankings,
  type Lifecycle,
  type ScoreCurrent,
  type ScoreDimension,
} from "@/lib/domain-contracts";
import {
  date,
  dateTime,
  formatCurrency,
  formatPercent,
  quantity,
  statusLabel,
} from "@/lib/display";
import { formatPrice } from "@/components/features/company/company-formatters";

const scoreLabels: Record<ScoreDimension, string> = {
  DURABILITY_10Y: "10Y Durability",
  COMPOUNDER_QUALITY: "Compounder Quality",
  EXECUTION: "Business Execution",
  RISK: "Structural Risk",
};

const scoreDimensions: ScoreDimension[] = [
  "DURABILITY_10Y",
  "COMPOUNDER_QUALITY",
  "EXECUTION",
  "RISK",
];

function compactPercent(value: string | null | undefined) {
  return formatPercent(value ?? null, 2, "No target");
}

/** Choose an existing canonical output; never derive or fabricate a valuation in the UI. */
export function selectPrimaryModelOutput(
  value: CompanyModelOutputsCurrent | undefined,
) {
  const models = value?.models ?? [];
  return (
    models.find(
      (model) =>
        model.status === "PUBLISHED" &&
        model.snapshot.output_quality === "COMPLETE",
    ) ??
    models.find((model) => model.status === "PUBLISHED") ??
    models[0] ??
    null
  );
}

function scoreFor(
  scores: ScoreCurrent[] | undefined,
  dimension: ScoreDimension,
) {
  return scores?.find((score) => score.definition.dimension === dimension);
}

function scoreDisplay(score: ScoreCurrent | undefined) {
  if (!score?.assessment) return "Not assessed";
  if (score.assessment.status !== "ASSESSED")
    return statusLabel(score.assessment.status);
  return `${quantity(score.assessment.score)} / ${quantity(score.definition.maximum_score)}`;
}

function currentThesisRevision(value: CompanyInvestmentThesis | undefined) {
  return value?.streams[0]?.current_revision ?? null;
}

function firstClaim(
  revision: InvestmentThesisRevision | null,
  types: string[],
) {
  return (
    revision?.claims.find((claim) => types.includes(claim.claim_type)) ?? null
  );
}

function currentRankLabel(rankings: CompanyRankings | undefined, type: string) {
  const ranking = rankings?.current.find(
    (item) => item.definition.ranking_type === type,
  );
  if (!ranking?.run) return "No run";
  if (!ranking.entry) return "Unavailable";
  return ranking.entry.status === "RANKED" && ranking.entry.position
    ? `#${ranking.entry.position}`
    : statusLabel(ranking.entry.status);
}

function modelReturnLabel(model: ReturnType<typeof selectPrimaryModelOutput>) {
  if (model?.snapshot.return_methodology?.perspective === "EQUITY")
    return "Expected shareholder IRR";
  if (model?.snapshot.return_methodology?.perspective === "ENTERPRISE")
    return "Expected enterprise IRR";
  return "Expected return";
}

function modelReturnNote(model: ReturnType<typeof selectPrimaryModelOutput>) {
  if (!model) return "No accepted model output";
  if (model.snapshot.expected_cash_flow_irr === null)
    return "No expected return recorded";
  return model.snapshot.return_methodology?.title ?? "Return basis unavailable";
}

export function CompanyOverview({
  detail,
  lifecycleChanged,
}: {
  detail: CompanyDetail;
  lifecycleChanged: () => void;
}) {
  const companyId = detail.company.id;
  const allocation = detail.portfolio_context;
  const scores = useResearch(
    `companies/${encodeURIComponent(companyId)}/scores/current`,
    isScoreCurrents,
  );
  const thesis = useResearch(
    `companies/${encodeURIComponent(companyId)}/thesis`,
    isCompanyInvestmentThesis,
  );
  const models = useResearch(
    `companies/${encodeURIComponent(companyId)}/model-outputs/current`,
    isCompanyModelOutputsCurrent,
  );
  const rankings = useResearch(
    `companies/${encodeURIComponent(companyId)}/rankings`,
    isCompanyRankings,
  );
  const execution = useResearch(
    `companies/${encodeURIComponent(companyId)}/execution-pace`,
    isCompanyExecutionPace,
  );

  const model = selectPrimaryModelOutput(models.data);
  const revision = currentThesisRevision(thesis.data);
  const advantage = firstClaim(revision, [
    "COMPETITIVE_ADVANTAGE",
    "DURABILITY",
  ]);
  const growth = firstClaim(revision, ["GROWTH_DRIVER"]);
  const riskClaim = firstClaim(revision, ["PRINCIPAL_RISK", "THESIS_BREAKER"]);
  const openQuestion = firstClaim(revision, ["UNRESOLVED_QUESTION"]);
  const pace = execution.data?.current?.decision;
  const paceStatus = pace?.decision_status ?? "UNAVAILABLE";
  const portfolioRank = currentRankLabel(rankings.data, "PORTFOLIO");
  const watchlistRank = currentRankLabel(rankings.data, "WATCHLIST");
  const researchRank = currentRankLabel(rankings.data, "RESEARCH");
  const thesisCoverageStatus = revision
    ? "AVAILABLE"
    : thesis.error || thesis.data
      ? "UNAVAILABLE"
      : "REFRESHING";
  const thesisCoverageLabel = revision
    ? "Accepted thesis"
    : thesis.error
      ? "Thesis unavailable"
      : thesis.data
        ? "No accepted thesis"
        : "Thesis loading";

  return (
    <section
      id="overview"
      aria-labelledby="company-overview-title"
      className="space-y-6 scroll-mt-5"
    >
      <PageSection
        id="company-overview-title"
        title="Investment summary"
        description="What matters most about this business now, which evidence supports it, and where to investigate next."
      >
        <MetricGroup label="Current investment summary" columns={4}>
          <MetricCard
            label="Lifecycle"
            value={
              <Badge
                variant={detail.company.lifecycle ? "default" : "secondary"}
              >
                {detail.company.lifecycle ?? "Unassigned"}
              </Badge>
            }
            note="Explicit investment state"
          />
          <MetricCard
            label="Portfolio position"
            value={
              allocation?.current_weight === null ||
              allocation?.current_weight === undefined
                ? "Not held"
                : compactPercent(allocation.current_weight)
            }
            note={
              detail.target_weight === null
                ? "No strategic target recorded"
                : `Target ${compactPercent(detail.target_weight)} · gap ${compactPercent(allocation?.allocation_gap)}`
            }
          />
          <MetricCard
            label={modelReturnLabel(model)}
            value={compactPercent(model?.snapshot.expected_cash_flow_irr)}
            note={modelReturnNote(model)}
            tone={model ? "default" : "warning"}
          />
          <MetricCard
            label="Decision state"
            value={pace?.pace ?? paceStatus}
            note={`Portfolio ${portfolioRank} · Watchlist ${watchlistRank} · Research ${researchRank}`}
            tone={
              pace?.decision_status === "AVAILABLE" ? "positive" : "warning"
            }
          />
        </MetricGroup>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">Coverage</span>
          <StatusIndicator
            status={thesisCoverageStatus}
            label={thesisCoverageLabel}
          />
          <StatusIndicator
            status={
              models.data?.status ??
              (models.error ? "UNAVAILABLE" : "REFRESHING")
            }
            label={`Model ${statusLabel(models.data?.status ?? (models.error ? "UNAVAILABLE" : "REFRESHING"))}`}
          />
          <StatusIndicator
            status={
              scores.data
                ? "AVAILABLE"
                : scores.error
                  ? "UNAVAILABLE"
                  : "REFRESHING"
            }
            label={
              scores.data
                ? "Quality assessments"
                : scores.error
                  ? "Scores unavailable"
                  : "Scores loading"
            }
          />
          <StatusIndicator
            status={allocation?.allocation_status ?? "UNAVAILABLE"}
            label={
              allocation
                ? statusLabel(allocation.allocation_status)
                : "Portfolio context unavailable"
            }
          />
        </div>
      </PageSection>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Card className="min-w-0 shadow-none">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 pb-3">
            <div>
              <CardTitle className="text-base">Investment case</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                Accepted thesis, strongest support and the most important open
                question.
              </p>
            </div>
            {revision ? (
              <StatusIndicator
                status={revision.confidence}
                label={`${statusLabel(revision.confidence)} confidence`}
              />
            ) : null}
          </CardHeader>
          <CardContent className="space-y-4">
            {revision?.thesis_statement ? (
              <p className="max-w-3xl text-base leading-7">
                {revision.thesis_statement}
              </p>
            ) : thesis.error ? (
              <EmptyState
                title="Thesis unavailable"
                description="The accepted thesis could not be verified. Review the Research & Evidence view before drawing an investment conclusion."
              />
            ) : !thesis.data ? (
              <p role="status" className="text-sm text-muted-foreground">
                Loading accepted thesis…
              </p>
            ) : (
              <EmptyState
                title="No accepted thesis revision"
                description="Missing thesis state is not a neutral investment conclusion. Start with Research & Evidence."
              />
            )}
            <div className="grid gap-3 border-t pt-4 sm:grid-cols-2">
              <InsightRow
                label="Strongest advantage"
                claim={advantage}
                empty="No structured advantage recorded."
              />
              <InsightRow
                label="Growth & reinvestment"
                claim={growth}
                empty="No structured growth driver recorded."
              />
              <InsightRow
                label="Principal risk / thesis breaker"
                claim={riskClaim}
                empty="No structured risk recorded."
                tone="warning"
              />
              <InsightRow
                label="Open research question"
                claim={openQuestion}
                empty="No unresolved question recorded."
                tone="warning"
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
              <span>
                {revision
                  ? `Observed ${dateTime(revision.observed_at)} · recorded ${dateTime(revision.recorded_at)}`
                  : "No accepted thesis timestamp available"}
              </span>
              <OverviewLink
                href={`/company/${companyId}?view=thesis`}
                label="Review thesis & evidence"
              />
            </div>
          </CardContent>
        </Card>

        <Card className="min-w-0 shadow-none">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 pb-3">
            <div>
              <CardTitle className="text-base">Valuation context</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                The accepted output and its method, without recomputing values
                in the browser.
              </p>
            </div>
            {model && (
              <StatusIndicator
                status={model.status}
                label={statusLabel(model.status)}
              />
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {model ? (
              <>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">
                    {model.snapshot.model_key}
                  </span>
                  <span>·</span>
                  <span>
                    {model.snapshot.return_methodology?.title ??
                      "Methodology unavailable"}
                  </span>
                  <span>·</span>
                  <span>
                    {model.snapshot.model_currency ?? "Currency unknown"}
                  </span>
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                  <ModelMetric
                    label="Bear fair value"
                    value={formatCurrency(
                      model.snapshot.bear_fv,
                      model.snapshot.model_currency,
                    )}
                  />
                  <ModelMetric
                    label="Base fair value"
                    value={formatCurrency(
                      model.snapshot.base_fv,
                      model.snapshot.model_currency,
                    )}
                  />
                  <ModelMetric
                    label="Bull fair value"
                    value={formatCurrency(
                      model.snapshot.bull_fv,
                      model.snapshot.model_currency,
                    )}
                  />
                  <ModelMetric
                    label="Weighted fair value"
                    value={formatCurrency(
                      model.snapshot.weighted_fv,
                      model.snapshot.model_currency,
                    )}
                  />
                  <ModelMetric
                    label="Expected excess"
                    value={compactPercent(model.snapshot.expected_excess)}
                  />
                  <ModelMetric
                    label="Hurdle"
                    value={compactPercent(model.snapshot.hurdle)}
                  />
                  <ModelMetric
                    label="Forward fundamental CAGR"
                    value={compactPercent(
                      model.snapshot.forward_fundamental_cagr,
                    )}
                  />
                </dl>
                <p className="border-t pt-3 text-xs leading-5 text-muted-foreground">
                  {model.snapshot.output_quality === "COMPLETE"
                    ? `Output recorded ${dateTime(model.snapshot.recorded_at)}. Fair value is a valuation reference, not a future price forecast.`
                    : (model.snapshot.notes ??
                      "Output is partial; unavailable fields remain explicit.")}
                </p>
              </>
            ) : models.error ? (
              <EmptyState
                title="Valuation unavailable"
                description="No verified accepted model output is available for this company."
                actions={
                  <Button size="sm" variant="outline" onClick={models.retry}>
                    Retry
                  </Button>
                }
              />
            ) : models.data ? (
              <EmptyState
                title="No accepted model output"
                description={`The canonical model response is ${statusLabel(models.data.status)}. Open Valuation to review supported model families or the migration state.`}
                actions={
                  <Button size="sm" variant="outline" onClick={models.retry}>
                    Retry
                  </Button>
                }
              />
            ) : (
              <p role="status" className="text-sm text-muted-foreground">
                Loading accepted model output…
              </p>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
              <span>
                {model?.snapshot.rationale ??
                  "Model rationale is available in the valuation workspace."}
              </span>
              <OverviewLink
                href={`/company/${companyId}?view=valuation`}
                label="Open valuation"
              />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card className="min-w-0 shadow-none">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 pb-3">
            <div>
              <CardTitle className="text-base">Business assessment</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                Independent quality dimensions; Risk excludes valuation and
                higher means more risk.
              </p>
            </div>
            <OverviewLink
              href={`/company/${companyId}?view=thesis`}
              label="Inspect assessments"
            />
          </CardHeader>
          <CardContent>
            {scores.data ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {scoreDimensions.map((dimension) => {
                  const score = scoreFor(scores.data, dimension);
                  return (
                    <div
                      key={dimension}
                      className="rounded-md border bg-muted/20 p-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-medium">
                          {scoreLabels[dimension]}
                        </span>
                        <StatusIndicator
                          status={score?.assessment?.status ?? "UNAVAILABLE"}
                        />
                      </div>
                      <p className="mt-2 text-lg font-semibold tabular-nums">
                        {scoreDisplay(score)}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {score?.assessment?.rationale ??
                          "No rationale recorded for this dimension."}
                      </p>
                    </div>
                  );
                })}
              </div>
            ) : scores.error ? (
              <EmptyState
                title="Quality assessments unavailable"
                description="The four independent score dimensions could not be verified."
                actions={
                  <Button size="sm" variant="outline" onClick={scores.retry}>
                    Retry
                  </Button>
                }
              />
            ) : (
              <p role="status" className="text-sm text-muted-foreground">
                Loading independent assessments…
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="min-w-0 shadow-none">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 pb-3">
            <div>
              <CardTitle className="text-base">Portfolio context</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                Current mark-to-market and long-term target architecture stay
                separate.
              </p>
            </div>
            <OverviewLink href="/portfolio" label="Open portfolio" />
          </CardHeader>
          <CardContent className="space-y-4">
            {detail.portfolio && allocation ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{detail.portfolio.name}</Badge>
                  <StatusIndicator status={allocation.allocation_status} />
                  {detail.holding_snapshot && (
                    <Badge variant="secondary">
                      Holdings {detail.holding_snapshot.completeness}
                    </Badge>
                  )}
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-4 text-sm">
                  <ModelMetric
                    label="Current weight"
                    value={compactPercent(allocation.current_weight)}
                  />
                  <ModelMetric
                    label="Strategic target"
                    value={compactPercent(detail.target_weight)}
                  />
                  <ModelMetric
                    label="Allocation gap"
                    value={
                      detail.target_weight === null
                        ? "No target"
                        : compactPercent(allocation.allocation_gap)
                    }
                  />
                  <ModelMetric
                    label="Current market value"
                    value={formatPrice(
                      allocation.current_market_value,
                      allocation.current_market_currency,
                    )}
                  />
                </dl>
                <p className="border-t pt-3 text-xs leading-5 text-muted-foreground">
                  {detail.positions.length > 0
                    ? `${detail.positions.length} exact listing position${detail.positions.length === 1 ? "" : "s"} · ${detail.positions.filter((position) => position.price_freshness !== "FRESH").length} with non-fresh price state.`
                    : "No position is present in the latest holdings snapshot."}
                </p>
              </>
            ) : (
              <EmptyState
                title="No current portfolio context"
                description="This company is not linked to a valued portfolio snapshot. Lifecycle and target state remain independent."
              />
            )}
          </CardContent>
        </Card>
      </div>

      <PageSection
        title="Explore next"
        description="Move from the summary to the canonical evidence or decision context that needs your attention."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <ExploreCard
            href={`/company/${companyId}?view=financials`}
            title="Financial performance"
            description="Reported actuals and available forecasts."
          />
          <ExploreCard
            href={`/company/${companyId}?view=valuation`}
            title="Valuation & scenarios"
            description="Assumptions, scenarios and return basis."
          />
          <ExploreCard
            href={`/company/${companyId}?view=thesis`}
            title="Thesis & quality"
            description="Claims, scores, risks and breakers."
          />
          <ExploreCard
            href={`/company/${companyId}?view=research`}
            title="Research & evidence"
            description="Filings, source context and open work."
          />
          <ExploreCard
            href={`/company/${companyId}?view=history`}
            title="Historical changes"
            description="Prices, expectations and decisions over time."
          />
        </div>
      </PageSection>

      <details className="group rounded-xl border bg-card">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4 text-sm font-semibold [&::-webkit-details-marker]:hidden">
          <span>Identity, lifecycle & holding evidence</span>
          <ChevronDown
            aria-hidden="true"
            className="size-4 shrink-0 transition-transform group-open:rotate-180"
          />
        </summary>
        <div className="grid items-start gap-4 border-t p-4 lg:grid-cols-3">
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
                <CardTitle className="text-base">
                  Investment lifecycle
                </CardTitle>
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
                        <p className="mt-1 break-words text-sm">
                          {event.reason}
                        </p>
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
              <CardTitle className="text-base">Holding evidence</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">
                Snapshot:{" "}
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
                        <StatusIndicator status={position.price_freshness} />
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
                            )}{" "}
                        · Portfolio value:{" "}
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
                    Portfolio-currency value is incomplete where a usable price
                    or dated FX observation is missing.
                  </p>
                )}
            </CardContent>
          </Card>
        </div>
      </details>

      <div id="attention" className="scroll-mt-5">
        <AttentionCenter companyId={companyId} compact />
      </div>
    </section>
  );
}

function ModelMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative" | "default";
}) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd
        className={`mt-1 font-medium tabular-nums ${tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}

function InsightRow({
  label,
  claim,
  empty,
  tone = "default",
}: {
  label: string;
  claim: { statement: string; confidence: string } | null;
  empty: string;
  tone?: "default" | "warning";
}) {
  return (
    <div
      className={`min-w-0 rounded-md border p-3 ${tone === "warning" ? "border-warning/30 bg-warning/5" : "bg-muted/20"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium">{label}</span>
        {claim && <StatusIndicator status={claim.confidence} />}
      </div>
      <p
        className={`mt-2 text-sm leading-5 ${claim ? "" : "text-muted-foreground"}`}
      >
        {claim?.statement ?? empty}
      </p>
    </div>
  );
}

function OverviewLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
    >
      {label}
      <ArrowRight aria-hidden="true" className="size-3.5" />
    </Link>
  );
}

function ExploreCard({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-lg border bg-card p-4 transition-colors hover:border-primary/50 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="flex items-start justify-between gap-2 text-sm font-semibold">
        <span>{title}</span>
        <ArrowRight
          aria-hidden="true"
          className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
        />
      </span>
      <span className="mt-2 block text-xs leading-5 text-muted-foreground">
        {description}
      </span>
    </Link>
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
