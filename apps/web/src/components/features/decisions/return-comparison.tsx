"use client";

import { useMemo, useState } from "react";
import { PageSection } from "@/components/app/page-section";
import {
  ResponsiveDataTable,
  type ResponsiveColumn,
} from "@/components/app/responsive-data-table";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  date,
  formatCurrency,
  formatPercent,
  statusLabel,
} from "@/lib/display";
import type { DecisionOpportunity } from "@/components/features/decisions/decision-data";

function metric(value: string | null, missing = "Unavailable") {
  return value === null ? missing : formatPercent(value, 2, missing);
}

export function groupByReturnCohort(rows: DecisionOpportunity[]) {
  const cohorts = new Map<string, DecisionOpportunity[]>();
  const unclassified: DecisionOpportunity[] = [];
  for (const row of rows) {
    if (!row.returnCohort) {
      unclassified.push(row);
      continue;
    }
    cohorts.set(row.returnCohort, [
      ...(cohorts.get(row.returnCohort) ?? []),
      row,
    ]);
  }
  return { cohorts: [...cohorts.entries()], unclassified };
}

function rankLabel(row: DecisionOpportunity) {
  return row.rankStatus === "RANKED" && row.rankPosition !== null
    ? `#${row.rankPosition}`
    : statusLabel(row.rankStatus);
}

export function ReturnComparison({
  title,
  description,
  rows,
  onSelect,
}: {
  title: string;
  description: string;
  rows: DecisionOpportunity[];
  onSelect: (companyId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filteredRows = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return rows;
    return rows.filter((row) =>
      [
        row.company.name,
        row.returnCohort,
        row.methodology?.title,
        row.rankStatus,
      ]
        .filter(Boolean)
        .some((value) => value?.toLocaleLowerCase().includes(normalized)),
    );
  }, [query, rows]);
  const groups = groupByReturnCohort(filteredRows);
  const columns: ResponsiveColumn<DecisionOpportunity>[] = [
    {
      id: "company",
      header: "Company / rank",
      className: "w-[24%]",
      render: (row) => (
        <div className="min-w-0">
          <Button
            variant="link"
            size="sm"
            className="h-auto max-w-full justify-start truncate p-0 font-semibold"
            onClick={() => onSelect(row.company.id)}
            aria-label={`Inspect ${row.company.name} decision context`}
          >
            {row.company.name}
          </Button>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusIndicator
              label={rankLabel(row)}
              status={
                row.rankStatus === "RANKED" ? "AVAILABLE" : row.rankStatus
              }
            />
            {row.asOf && (
              <span className="text-[10px] text-muted-foreground">
                Run {date(row.asOf)}
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      id: "returns",
      header: "Expected return · rank snapshot",
      render: (row) => (
        <div className="space-y-1 tabular-nums">
          <p>IRR {metric(row.expectedIrr)}</p>
          <p className="text-xs text-muted-foreground">
            Hurdle {metric(row.hurdle)} · excess {metric(row.expectedExcess)}
          </p>
        </div>
      ),
    },
    {
      id: "fair-value",
      header: "Fair-value context · rank time",
      render: (row) => (
        <div className="space-y-1 tabular-nums">
          <p>
            {formatCurrency(row.weightedFairValue, row.fairValueCurrency, 2)}
          </p>
          <p className="text-xs">Upside {metric(row.rankTimeUpside)}</p>
          <p className="text-xs text-muted-foreground">
            {row.fairValueCurrency ?? "Currency unknown"} · price{" "}
            {statusLabel(row.rankTimePriceStatus)}
          </p>
        </div>
      ),
    },
    {
      id: "quality",
      header: "Quality gate context",
      render: (row) => (
        <div className="space-y-1 text-xs">
          <p>
            10Y durability ·{" "}
            {row.durability === null ? "Not assessed" : `${row.durability} / 5`}
          </p>
          <p>
            Compounder quality ·{" "}
            {row.compounderQuality === null
              ? "Not assessed"
              : `${row.compounderQuality} / 5`}
          </p>
          <p className="text-muted-foreground">
            Model{" "}
            {row.modelStatus ? statusLabel(row.modelStatus) : "unavailable"}
          </p>
        </div>
      ),
    },
    {
      id: "portfolio-fit",
      header: "Current allocation context",
      render: (row) =>
        row.kind === "WATCHLIST" ? (
          <span className="text-xs text-muted-foreground">
            Watchlist · no target context
          </span>
        ) : (
          <div className="space-y-1 text-xs tabular-nums">
            <p>
              {metric(row.currentWeight)} →{" "}
              {metric(row.targetWeight, "No target")}
            </p>
            <p className="text-muted-foreground">
              Gap {metric(row.allocationGap)}
            </p>
          </div>
        ),
    },
  ];

  return (
    <PageSection title={title} description={description}>
      <label className="block max-w-sm text-xs font-medium">
        Filter companies or cohorts
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Company, methodology, or rank state"
          className="mt-1.5 h-10 w-full rounded-md border bg-background px-3 text-sm"
        />
      </label>
      {groups.cohorts.length === 0 && groups.unclassified.length === 0 ? (
        <Card className="shadow-none">
          <CardContent className="py-6 text-sm text-muted-foreground">
            No company rows match this filter.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {groups.cohorts.map(([cohort, cohortRows]) => (
            <section
              key={cohort}
              aria-label={`Comparable return cohort ${cohort}`}
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">
                  Comparable cohort · {statusLabel(cohort)}
                </h3>
                <span className="text-xs text-muted-foreground">
                  {cohortRows.length} companies · rank values as of each run
                </span>
              </div>
              <ResponsiveDataTable
                caption={`${title}: ${statusLabel(cohort)}`}
                rows={cohortRows}
                getRowKey={(row) => row.company.id}
                columns={columns}
              />
            </section>
          ))}
          {groups.unclassified.length > 0 && (
            <section aria-label="Returns without a comparability cohort">
              <div className="mb-2 rounded-lg border border-warning/35 bg-warning/10 px-4 py-3">
                <h3 className="text-sm font-semibold">
                  No comparable return cohort
                </h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  These entries remain visible for diagnosis. The application
                  has not supplied a valid comparison cohort, so their returns
                  are not presented as directly comparable to one another or to
                  classified methodologies.
                </p>
              </div>
              <ResponsiveDataTable
                caption={`${title}: no comparable cohort`}
                rows={groups.unclassified}
                getRowKey={(row) => row.company.id}
                columns={columns}
              />
            </section>
          )}
        </div>
      )}
    </PageSection>
  );
}
