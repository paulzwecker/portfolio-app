import Link from "next/link";
import { DetailDrawer } from "@/components/app/detail-drawer";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import { ExecutionPaceCompact } from "@/components/execution-pace";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DecisionOpportunity } from "@/components/features/decisions/decision-data";
import {
  dateTime,
  formatCurrency,
  formatPercent,
  statusLabel,
} from "@/lib/display";

function percentage(value: string | null) {
  return value === null ? "Unavailable" : formatPercent(value, 2);
}

export function DecisionDetailDrawer({
  opportunity,
  open,
  onOpenChange,
}: {
  opportunity: DecisionOpportunity | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <DetailDrawer
      open={open && opportunity !== null}
      onOpenChange={onOpenChange}
      title={opportunity?.company.name ?? "Decision context"}
      description="Canonical evidence behind allocation, opportunity and execution context."
    >
      {opportunity && (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">
              {opportunity.company.lifecycle ?? "Lifecycle unassigned"}
            </Badge>
            <Link
              className="text-sm text-primary underline-offset-4 hover:underline"
              href={`/company/${opportunity.company.id}`}
            >
              Company Explorer
            </Link>
            <Link
              className="text-sm text-primary underline-offset-4 hover:underline"
              href={`/company/${opportunity.company.id}#canonical-models`}
            >
              Modeling
            </Link>
          </div>

          <section aria-labelledby="decision-detail-allocation">
            <h3
              id="decision-detail-allocation"
              className="text-sm font-semibold"
            >
              Strategic allocation
            </h3>
            {opportunity.kind === "PORTFOLIO" ? (
              <dl className="mt-2 grid grid-cols-3 gap-3 rounded-lg border p-3 text-sm">
                <div>
                  <dt className="text-xs text-muted-foreground">Current</dt>
                  <dd className="mt-1 tabular-nums">
                    {percentage(opportunity.currentWeight)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Target</dt>
                  <dd className="mt-1 tabular-nums">
                    {opportunity.targetWeight === null
                      ? "No target"
                      : formatPercent(opportunity.targetWeight, 2)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Gap</dt>
                  <dd className="mt-1 tabular-nums">
                    {percentage(opportunity.allocationGap)}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">
                Watchlist company; no portfolio target or current weight is
                inferred.
              </p>
            )}
          </section>

          <section aria-labelledby="decision-detail-return">
            <h3 id="decision-detail-return" className="text-sm font-semibold">
              Opportunity and return basis
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {opportunity.asOf
                ? `Latest ranking inputs as of ${dateTime(opportunity.asOf)}.`
                : "No ranking snapshot is available."}
              {opportunity.returnCohort
                ? ` Cohort: ${statusLabel(opportunity.returnCohort)}.`
                : " No comparable return cohort is available."}
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-3 rounded-lg border p-3 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">Expected IRR</dt>
                <dd className="mt-1 tabular-nums">
                  {percentage(opportunity.expectedIrr)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Hurdle</dt>
                <dd className="mt-1 tabular-nums">
                  {percentage(opportunity.hurdle)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Expected excess
                </dt>
                <dd className="mt-1 tabular-nums">
                  {percentage(opportunity.expectedExcess)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Weighted Fair Value
                </dt>
                <dd className="mt-1 tabular-nums">
                  {formatCurrency(
                    opportunity.weightedFairValue,
                    opportunity.fairValueCurrency,
                    2,
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Weighted upside · rank time
                </dt>
                <dd className="mt-1 tabular-nums">
                  {percentage(opportunity.rankTimeUpside)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Price basis status
                </dt>
                <dd className="mt-1">
                  {statusLabel(opportunity.rankTimePriceStatus)}
                  {opportunity.rankTimePriceEffectiveAt
                    ? ` · ${dateTime(opportunity.rankTimePriceEffectiveAt)}`
                    : " · date unavailable"}
                </dd>
              </div>
            </dl>
            {opportunity.methodology ? (
              <Card className="mt-3 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">
                    {opportunity.methodology.title} · v
                    {opportunity.methodology.version}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-xs">
                  <p>
                    <span className="text-muted-foreground">Perspective:</span>{" "}
                    {statusLabel(opportunity.methodology.perspective)} ·{" "}
                    {opportunity.methodology.cash_flow_basis}
                  </p>
                  <p>
                    <span className="text-muted-foreground">Entry basis:</span>{" "}
                    {opportunity.methodology.entry_value_basis}
                  </p>
                  <p>
                    <span className="text-muted-foreground">
                      Share-price basis:
                    </span>{" "}
                    {opportunity.methodology.share_price_basis}
                  </p>
                  <p className="leading-5 text-muted-foreground">
                    {opportunity.methodology.limitation}
                  </p>
                </CardContent>
              </Card>
            ) : (
              <p className="mt-3 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                Return methodology metadata is unavailable. Do not compare this
                Expected IRR with other methodologies.
              </p>
            )}
          </section>

          <section aria-labelledby="decision-detail-quality">
            <h3 id="decision-detail-quality" className="text-sm font-semibold">
              Quality and rank eligibility
            </h3>
            <dl className="mt-2 grid grid-cols-2 gap-3 rounded-lg border p-3 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">
                  10Y Durability
                </dt>
                <dd className="mt-1">
                  {opportunity.durability === null
                    ? "Not assessed"
                    : `${opportunity.durability} / 5`}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Compounder Quality
                </dt>
                <dd className="mt-1">
                  {opportunity.compounderQuality === null
                    ? "Not assessed"
                    : `${opportunity.compounderQuality} / 5`}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  {opportunity.kind === "PORTFOLIO"
                    ? "Portfolio Rank"
                    : "Watchlist Rank"}
                </dt>
                <dd className="mt-1">
                  <StatusIndicator
                    status={opportunity.rankStatus}
                    label={
                      opportunity.rankStatus === "RANKED" &&
                      opportunity.rankPosition !== null
                        ? `Ranked #${opportunity.rankPosition}`
                        : statusLabel(opportunity.rankStatus)
                    }
                  />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Model output status
                </dt>
                <dd className="mt-1">
                  {opportunity.modelStatus
                    ? statusLabel(opportunity.modelStatus)
                    : "Unavailable"}
                </dd>
              </div>
            </dl>
            <p className="mt-2 rounded-md bg-muted/50 p-3 text-xs leading-5">
              {opportunity.rankReason}
            </p>
            {opportunity.scores
              ?.filter((item) => item.assessment?.rationale)
              .map((item) => (
                <p
                  key={item.definition.dimension}
                  className="mt-2 text-xs leading-5 text-muted-foreground"
                >
                  {statusLabel(item.definition.dimension)} rationale:{" "}
                  {item.assessment?.rationale}
                </p>
              ))}
          </section>

          {opportunity.execution ? (
            <section aria-labelledby="decision-detail-execution">
              <div className="flex items-center justify-between gap-2">
                <h3
                  id="decision-detail-execution"
                  className="text-sm font-semibold"
                >
                  Execution Pace
                </h3>
                <StatusIndicator
                  status={opportunity.execution.decision.decision_status}
                />
              </div>
              <p className="mt-2 text-sm leading-5">
                {opportunity.execution.decision.reason}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                As of {dateTime(opportunity.execution.run.as_of)} ·{" "}
                {opportunity.execution.decision.pace ?? "No pace available"}.
                This is not a trade order.
              </p>
              <ExecutionPaceCompact entry={opportunity.execution} />
            </section>
          ) : (
            <section aria-labelledby="decision-detail-execution">
              <h3
                id="decision-detail-execution"
                className="text-sm font-semibold"
              >
                Execution Pace
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">
                No Execution Pace run is available. No neutral timing signal is
                implied.
              </p>
            </section>
          )}

          {opportunity.outputs && (
            <section aria-labelledby="decision-detail-model-history">
              <h3
                id="decision-detail-model-history"
                className="text-sm font-semibold"
              >
                Current published model outputs
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Current output snapshots are distinct from the ranking inputs
                above.
              </p>
              <div className="mt-2 space-y-2">
                {opportunity.outputs.models.length === 0 ? (
                  <p className="rounded-md border border-dashed p-3 text-xs">
                    {statusLabel(opportunity.outputs.status)} · no current
                    output snapshot
                  </p>
                ) : (
                  opportunity.outputs.models.map(
                    ({ model_key, status, snapshot }) => (
                      <Card key={snapshot.id} className="shadow-none">
                        <CardContent className="space-y-2 p-3 text-xs">
                          <p className="font-medium">
                            {model_key} · {statusLabel(status)} ·{" "}
                            {snapshot.model_currency ?? "Currency unknown"}
                          </p>
                          <p>
                            Expected IRR{" "}
                            {percentage(snapshot.expected_cash_flow_irr)} ·
                            hurdle {percentage(snapshot.hurdle)} · excess{" "}
                            {percentage(snapshot.expected_excess)}
                          </p>
                          <p>
                            Weighted FV {snapshot.weighted_fv ?? "Unavailable"}{" "}
                            {snapshot.model_currency ?? ""} · upside{" "}
                            {percentage(snapshot.weighted_upside)}
                          </p>
                          <p className="text-muted-foreground">
                            Effective{" "}
                            {snapshot.effective_at
                              ? dateTime(snapshot.effective_at)
                              : "unknown"}{" "}
                            · recorded {dateTime(snapshot.recorded_at)} ·
                            contract {statusLabel(snapshot.contract_status)} ·
                            share-price basis{" "}
                            {statusLabel(snapshot.share_price_basis_status)}
                          </p>
                          <SourceReference
                            label={snapshot.source}
                            reference={
                              snapshot.source_revision_id ??
                              snapshot.snapshot_key
                            }
                          />
                          {snapshot.rationale && (
                            <p className="leading-5 text-muted-foreground">
                              {snapshot.rationale}
                            </p>
                          )}
                          {snapshot.evidence && (
                            <p className="break-words text-muted-foreground">
                              {snapshot.evidence}
                            </p>
                          )}
                        </CardContent>
                      </Card>
                    ),
                  )
                )}
              </div>
            </section>
          )}
        </div>
      )}
    </DetailDrawer>
  );
}
