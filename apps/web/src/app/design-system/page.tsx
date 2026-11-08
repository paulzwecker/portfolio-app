"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ChartContainer } from "@/components/app/chart-container";
import { DataFreshnessIndicator } from "@/components/app/data-freshness-indicator";
import { DetailDrawer } from "@/components/app/detail-drawer";
import { EmptyState } from "@/components/app/empty-state";
import { LoadingSkeleton } from "@/components/app/loading-skeleton";
import { MetricCard } from "@/components/app/metric-card";
import { MetricGroup } from "@/components/app/metric-group";
import { PageHeader } from "@/components/app/page-header";
import { PageSection } from "@/components/app/page-section";
import { ResponsiveDataTable } from "@/components/app/responsive-data-table";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import { TableSearch } from "@/components/app/table-search";

const stateRows = [
  { id: "fresh", label: "Canonical observation", state: "FRESH" },
  { id: "stale", label: "Historical observation", state: "STALE" },
  { id: "partial", label: "Provider coverage", state: "PARTIAL" },
  { id: "review", label: "Decision eligibility", state: "REVIEW" },
  { id: "unavailable", label: "Source mapping", state: "UNAVAILABLE" },
];

export default function DesignSystemPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const filteredRows = stateRows.filter((row) =>
    `${row.label} ${row.state}`
      .toLowerCase()
      .includes(search.trim().toLowerCase()),
  );

  return (
    <>
      <PageHeader
        eyebrow="Internal reference"
        title="Design system"
        description="Reusable patterns for clear, accessible investment work. Every example is illustrative; no portfolio data is loaded here. Choose light, dark or system appearance in the header."
        badge={<StatusIndicator label="Shared foundation" tone="info" />}
      />

      <div className="space-y-10">
        <PageSection
          title="Foundations"
          description="Cool neutral surfaces, a warm action color and teal information accents. Meaning is never conveyed through color alone."
        >
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {[
              ["Action", "bg-primary"],
              ["Information", "bg-info"],
              ["Surface", "bg-card"],
              ["Background", "bg-background"],
              ["Text", "bg-foreground"],
              ["Border", "bg-border"],
            ].map(([label, color]) => (
              <div key={label} className="rounded-lg border bg-card p-2.5">
                <div
                  aria-hidden="true"
                  className={`h-16 rounded-md border ${color}`}
                />
                <p className="mt-2 text-xs font-medium">{label}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            Spacing uses a 4, 8, 12, 16, 24 and 32 px rhythm. Tabular numerals
            keep financial comparisons aligned.
          </p>
        </PageSection>

        <PageSection
          title="Controls"
          description="Actions, labels, focus and disabled states stay visible without relying on hover."
        >
          <div className="flex flex-wrap gap-2 rounded-lg border bg-card p-4">
            <Button type="button" onClick={() => setDrawerOpen(true)}>
              Primary action
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setSearch("")}
            >
              Outline action
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDrawerOpen(true)}
            >
              Quiet action
            </Button>
            <Button type="button" disabled>
              Unavailable
            </Button>
          </div>
        </PageSection>
        <PageSection
          title="Semantic states"
          description="State is communicated in text and icon as well as color. A decision review state is not a negative return."
        >
          <div className="flex flex-wrap gap-2">
            <StatusIndicator status="AVAILABLE" />
            <StatusIndicator status="STALE" />
            <StatusIndicator status="PARTIAL" />
            <StatusIndicator status="REVIEW" />
            <StatusIndicator status="UNAVAILABLE" />
            <StatusIndicator status="FAILED" />
          </div>
          <div className="mt-4">
            <DataFreshnessIndicator
              state="STALE"
              source="Illustrative source state"
              detail="No observation timestamp supplied"
            />
          </div>
        </PageSection>

        <PageSection
          title="Metrics and surfaces"
          description="The sample deliberately contains no fabricated financial values. Callers supply canonical values, currency, basis and availability."
        >
          <MetricGroup label="Illustrative metric states" columns={3}>
            <MetricCard
              label="Current portfolio value"
              value="Unavailable"
              note="No portfolio response is used on this page."
            />
            <MetricCard
              label="Expected return"
              value="Not comparable"
              note="Return methodology and share-price basis must be present."
              tone="warning"
            />
            <MetricCard
              label="Data quality"
              value="Review"
              note="Missing data is not shown as zero or neutral."
              tone="warning"
            />
          </MetricGroup>
        </PageSection>

        <PageSection
          title="Table, provenance and chart framing"
          description="Wide data keeps semantic table markup; narrow screens receive labeled row cards rather than page-wide horizontal overflow."
        >
          <div className="mb-3">
            <TableSearch
              label="Search illustrative states"
              placeholder="Search labels or states"
              value={search}
              onChange={setSearch}
              resultCount={filteredRows.length}
              totalCount={stateRows.length}
            />
          </div>
          <ResponsiveDataTable
            caption="Illustrative data availability states"
            rows={filteredRows}
            getRowKey={(row) => row.id}
            columns={[
              { id: "input", header: "Input", render: (row) => row.label },
              {
                id: "state",
                header: "State",
                render: (row) => <StatusIndicator status={row.state} />,
              },
            ]}
          />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <SourceReference
              label="Source record"
              reference="identifier present · URL unavailable"
            />
            <span className="text-xs text-muted-foreground">
              Source links are rendered only when a canonical URL is supplied.
            </span>
          </div>
          <div className="mt-4">
            <ChartContainer
              title="Historical series"
              description="A chart container carries context and source information; the feature owns its data and chart implementation."
              source="No observation series supplied"
            >
              <EmptyState
                title="No chart data available"
                description="No historical observations are connected to this internal reference."
              />
            </ChartContainer>
          </div>
          <div className="mt-4">
            <ChartContainer
              title="Example observations"
              description="Illustrative monthly counts; a missing observation creates a gap, not zero."
              source="Synthetic example"
            >
              <svg
                viewBox="0 0 480 150"
                role="img"
                aria-label="Example observations: January 3, February 5, March missing, April 4"
                className="w-full rounded-md border bg-muted/40 p-2"
              >
                <path
                  d="M35 120 H450 M35 30 H450 M35 75 H450"
                  fill="none"
                  stroke="var(--border)"
                  strokeDasharray="4 4"
                />
                <path
                  d="M45 93 L170 48 M420 70"
                  fill="none"
                  stroke="var(--chart-1)"
                  strokeWidth="3"
                />
                <circle cx="45" cy="93" r="4" fill="var(--chart-1)" />
                <circle cx="170" cy="48" r="4" fill="var(--chart-1)" />
                <circle cx="420" cy="70" r="4" fill="var(--chart-1)" />
                <g fill="var(--muted-foreground)" fontSize="12">
                  <text x="35" y="143">
                    Jan
                  </text>
                  <text x="160" y="143">
                    Feb
                  </text>
                  <text x="280" y="143">
                    Mar
                  </text>
                  <text x="410" y="143">
                    Apr
                  </text>
                </g>
              </svg>
              <details className="mt-3 border-t pt-3 text-sm">
                <summary className="cursor-pointer font-medium text-info">
                  View chart data
                </summary>
                <p className="mt-2 text-muted-foreground">
                  January: 3 · February: 5 · March: unavailable · April: 4
                </p>
              </details>
            </ChartContainer>
          </div>
        </PageSection>

        <PageSection
          title="Loading, empty and error patterns"
          description="Loading is announced, empty data has a precise explanation, and errors expose a retry action."
        >
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-xl border bg-card p-4">
              <h3 className="mb-3 text-sm font-semibold">Loading</h3>
              <div role="status" aria-live="polite">
                <span className="sr-only">Loading market data</span>
                <LoadingSkeleton lines={3} label="Loading market data" />
              </div>
            </div>
            <EmptyState
              title="No observations"
              description="No records are available for this selected source and period."
            />
            <EmptyState
              title="Refresh needs attention"
              description="The source is temporarily unavailable. Previously observed facts remain unchanged."
              actions={
                <Button variant="outline" size="sm">
                  Retry
                </Button>
              }
            />
          </div>
        </PageSection>

        <PageSection
          title="Detail drawer"
          description="Use a drawer for focused row context. Long review and authoring tasks remain on a route."
          actions={
            <Button onClick={() => setDrawerOpen(true)}>Open details</Button>
          }
        >
          <p className="text-sm text-muted-foreground">
            Open with the keyboard or pointer; Escape and the close control
            return focus to the invoking button.
          </p>
        </PageSection>
      </div>

      <DetailDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        title="Observation details"
        description="Illustrative provenance panel"
      >
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">Source</dt>
            <dd className="mt-1">Identifier supplied; URL unavailable</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Observation time</dt>
            <dd className="mt-1">Unavailable</dd>
          </div>
        </dl>
      </DetailDrawer>
    </>
  );
}
