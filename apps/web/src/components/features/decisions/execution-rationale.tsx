import { ArrowUpRight, CircleAlert, Clock3 } from "lucide-react";
import Link from "next/link";
import { PageSection } from "@/components/app/page-section";
import { StatusIndicator } from "@/components/app/status-indicator";
import {
  ExecutionPaceCompact,
  executionPaceLabel,
} from "@/components/execution-pace";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { date, formatPercent, statusLabel } from "@/lib/display";
import type {
  CompanyPortfolioContext,
  UniverseExecutionPaceSummary,
} from "@/lib/domain-contracts";

export function ExecutionRationale({
  rows,
  paceRows,
  onSelect,
}: {
  rows: CompanyPortfolioContext[];
  paceRows: UniverseExecutionPaceSummary[] | undefined;
  onSelect: (companyId: string) => void;
}) {
  const decisions = rows.map((row) => ({
    row,
    entry:
      paceRows?.find((item) => item.company.id === row.company.id)?.decision ??
      null,
  }));

  return (
    <PageSection
      id="decision-execution"
      title="Execution Pace"
      description="Timing context for moving toward accepted strategic targets. Pace states are not trade orders, order sizes, or target changes."
    >
      {decisions.length === 0 ? (
        <Card className="shadow-none">
          <CardContent className="py-6 text-sm text-muted-foreground">
            No Portfolio company rows are available for execution review.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {decisions.map(({ row, entry }) => {
            const decision = entry?.decision;
            const blockers = decision?.input_snapshot.context_notes ?? [];
            return (
              <Card
                key={row.company.id}
                className="min-w-0 shadow-none"
                data-decision-status={decision?.decision_status ?? "NO_RUN"}
              >
                <CardContent className="space-y-3 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <Button
                        variant="link"
                        size="sm"
                        className="h-auto justify-start truncate p-0 font-semibold"
                        onClick={() => onSelect(row.company.id)}
                        aria-label={`Inspect ${row.company.name} execution rationale`}
                      >
                        {row.company.name}
                      </Button>
                      <p className="text-xs text-muted-foreground">
                        {row.positions.length > 0
                          ? "Held position"
                          : "No held position"}
                        {row.target_weight === null
                          ? " · target not set"
                          : ` · target ${formatPercent(row.target_weight, 2, "No target", "en")}`}
                      </p>
                    </div>
                    {decision ? (
                      <StatusIndicator
                        label={
                          decision.pace
                            ? `${statusLabel(decision.decision_status)} · ${executionPaceLabel(decision.pace)}`
                            : statusLabel(decision.decision_status)
                        }
                        status={decision.decision_status}
                      />
                    ) : (
                      <StatusIndicator
                        label="No run recorded"
                        status="UNAVAILABLE"
                      />
                    )}
                  </div>

                  {decision ? (
                    <>
                      <p className="text-sm leading-5">{decision.reason}</p>
                      <p className="text-xs text-muted-foreground">
                        Run as of {date(entry.run.as_of)} · recorded{" "}
                        {date(entry.run.recorded_at)}
                      </p>
                      {decision.decision_status === "REVIEW" && (
                        <div
                          role="status"
                          className="rounded-md border border-warning/35 bg-warning/10 p-3 text-xs text-warning"
                        >
                          <p className="flex items-center gap-1.5 font-medium">
                            <CircleAlert
                              aria-hidden="true"
                              className="size-3.5"
                            />
                            Review required; no timing pace is available.
                          </p>
                          {blockers.length > 0 && (
                            <ul className="mt-2 list-disc space-y-1 pl-4">
                              {blockers.map((blocker) => (
                                <li key={blocker}>{blocker}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                      <details className="rounded-md border bg-secondary/20 px-3 py-2">
                        <summary className="cursor-pointer text-xs font-medium">
                          Inspect evidence and input snapshot
                        </summary>
                        <ExecutionPaceCompact entry={entry} />
                      </details>
                    </>
                  ) : (
                    <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                      No Execution Pace history is recorded. Missing history is
                      not a neutral timing signal.
                    </p>
                  )}
                  <div className="flex flex-wrap gap-3 border-t pt-3 text-xs">
                    <Link
                      href={`/company/${row.company.id}#execution-pace`}
                      className="inline-flex min-h-8 items-center gap-1 text-primary hover:underline"
                    >
                      Company evidence{" "}
                      <ArrowUpRight aria-hidden="true" className="size-3.5" />
                    </Link>
                    <span className="inline-flex min-h-8 items-center gap-1 text-muted-foreground">
                      <Clock3 aria-hidden="true" className="size-3.5" />
                      {decision
                        ? statusLabel(
                            decision.input_snapshot.holdings_freshness,
                          )
                        : "No input snapshot"}{" "}
                      holdings
                    </span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </PageSection>
  );
}
