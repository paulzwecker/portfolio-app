"use client";

import { Badge } from "@/components/ui/badge";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError } from "@/components/app/empty-state";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyModelOutputsCurrent,
  isModelOutputHistory,
  type ModelOutputSnapshot,
} from "@/lib/domain-contracts";
import { date } from "@/lib/display";

import {
  modelPercent,
  modelValue,
} from "@/components/features/company/company-formatters";
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

export function ModelOutputs({ companyId }: { companyId: string }) {
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
