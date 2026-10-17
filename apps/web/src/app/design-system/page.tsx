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

const stateRows = [
  { id: "fresh", label: "Canonical observation", state: "FRESH" },
  { id: "stale", label: "Historical observation", state: "STALE" },
  { id: "partial", label: "Provider coverage", state: "PARTIAL" },
  { id: "review", label: "Decision eligibility", state: "REVIEW" },
  { id: "unavailable", label: "Source mapping", state: "UNAVAILABLE" },
];

export default function DesignSystemPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <>
      <PageHeader
        eyebrow="Internal reference"
        title="Design system"
        description="Shared interface patterns and semantic states. Every sample below is illustrative presentation content, not portfolio or investment data. The default palette follows the operating system's light or dark preference."
        badge={<StatusIndicator label="Phase 11 foundation" tone="info" />}
      />

      <div className="space-y-10">
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
          <ResponsiveDataTable
            caption="Illustrative data availability states"
            rows={stateRows}
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
