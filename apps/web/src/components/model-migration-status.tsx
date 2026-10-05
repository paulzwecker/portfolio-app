"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError, useResearch } from "@/components/research-frame";
import {
  isCompanyFinancialModelMigration,
  type CompanyFinancialModelMigrationItem,
} from "@/lib/domain-contracts";

const representationLabels: Record<string, string> = {
  NATIVE_EDITABLE: "Native · editable",
  NATIVE_WITH_PARITY_ISSUE: "Native · parity issue",
  IMPORTED_OUTPUT_ONLY: "Imported outputs only",
  UNSUPPORTED_LEGACY: "Unsupported legacy method",
  LEGACY_ONLY: "Legacy only",
  NOT_IMPORTED: "Not imported",
};

function ParityCount({
  label,
  compared,
  passed,
}: {
  label: string;
  compared: number | null;
  passed: number | null;
}) {
  if (compared === null || passed === null) return null;
  return (
    <span>
      {label}: {passed}/{compared} matched
    </span>
  );
}

function ModelMigrationCard({
  model,
}: {
  model: CompanyFinancialModelMigrationItem;
}) {
  const native = model.native_model_id !== null;
  const parityPassed = model.parity_status === "PARITY_PASS";
  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="space-y-2 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">
            {model.model_key} · {model.company_name}
          </CardTitle>
          <Badge
            variant={
              model.representation_status === "NATIVE_EDITABLE"
                ? "default"
                : "secondary"
            }
          >
            {representationLabels[model.representation_status]}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <Badge variant="outline">{model.lifecycle}</Badge>
          <Badge variant="outline">
            {model.canonical_ticker ?? "Ticker unresolved"}
          </Badge>
          <Badge variant="outline">
            {model.model_currency ?? "Currency unresolved"}
          </Badge>
          <span>{model.methodology_family.replaceAll("_", " ")}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-xs leading-5">
        {native ? (
          <>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span>
                Accepted native revision {model.native_revision_number ?? "—"}
              </span>
              <Badge variant={parityPassed ? "default" : "secondary"}>
                {model.parity_status?.replaceAll("_", " ") ??
                  "Parity not recorded"}
              </Badge>
              <ParityCount
                label="Projections"
                compared={model.projections_compared}
                passed={model.projections_passed}
              />
              <ParityCount
                label="Outputs"
                compared={model.outputs_compared}
                passed={model.outputs_passed}
              />
            </div>
            <p className="text-muted-foreground">
              The accepted assumptions recalculate in the application. Current
              valuation outputs still depend on canonical market-data freshness.
            </p>
          </>
        ) : (
          <p className="text-muted-foreground">
            {model.output_snapshot_available
              ? `A normalized legacy output snapshot is available (${model.output_contract_status}); assumptions are not editable in the application yet.`
              : `No normalized output snapshot is available (${model.output_contract_status}).`}
          </p>
        )}
        {model.blockers.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-amber-800 dark:text-amber-300">
            {model.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        )}
        {model.legacy_return_semantics && (
          <details className="rounded-md border px-3 py-2">
            <summary className="cursor-pointer font-medium">
              Legacy return-method note
            </summary>
            <p className="mt-2 text-muted-foreground">
              {model.legacy_return_semantics}
            </p>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

export function ModelMigrationStatus({ companyId }: { companyId: string }) {
  const status = useResearch(
    `companies/${encodeURIComponent(companyId)}/model-migration-status`,
    isCompanyFinancialModelMigration,
  );
  return (
    <section
      id="model-migration-status"
      aria-labelledby="model-migration-status-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="model-migration-status-title" className="text-xl font-semibold">
          Model migration status
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Distinguishes native editable assumptions from imported legacy outputs
          and methods that still need migration work.
        </p>
      </div>
      {!status.data ? (
        <PendingOrError {...status} />
      ) : !status.data.inventory_available ? (
        <Card>
          <CardContent className="py-5 text-sm text-muted-foreground">
            The reviewed migration inventory is unavailable in this
            installation.
          </CardContent>
        </Card>
      ) : status.data.models.length === 0 ? (
        <Card>
          <CardContent className="py-5 text-sm text-muted-foreground">
            No legacy model tab is mapped to this company. Missing models remain
            explicit and are not inferred from a ticker match.
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 gap-4 xl:grid-cols-2">
          {status.data.models.map((model) => (
            <ModelMigrationCard key={model.model_key} model={model} />
          ))}
        </div>
      )}
    </section>
  );
}
