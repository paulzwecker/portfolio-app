"use client";

import Link from "next/link";
import { useState } from "react";
import { useResearch } from "@/components/research-frame";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { isAttentionFeed, isUniverse } from "@/lib/domain-contracts";

const eventTypes = [
  ["", "All event types"],
  ["MODEL_REVISION", "Model revision"],
  ["MODEL_OUTPUT_IMPORT", "Imported model output"],
  ["EXPECTED_IRR_CHANGE", "Expected IRR change"],
  ["CONSENSUS_REVISION", "Consensus revision"],
  ["NEW_FILING", "New filing"],
  ["PRICE_MOVE", "Large price move"],
  ["RANK_CHANGE", "Rank change"],
  ["EXECUTION_PACE_CHANGE", "Execution Pace change"],
  ["DATA_QUALITY", "Data quality"],
] as const;

function eventDate(value: string | null, precision: string, fallback?: string) {
  if (!value)
    return fallback
      ? `Current status · checked ${new Date(fallback).toLocaleDateString()}`
      : "Current status";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return "Date unavailable";
  return precision === "DATE"
    ? parsed.toLocaleDateString()
    : parsed.toLocaleString();
}

export function AttentionCenter({
  companyId,
  compact = false,
}: {
  companyId?: string;
  compact?: boolean;
}) {
  const universe = useResearch("universe", isUniverse);
  const params = new URLSearchParams();
  if (companyId) params.set("company_id", companyId);
  const [companyFilter, setCompanyFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [lifecycleFilter, setLifecycleFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  if (companyFilter && !companyId) params.set("company_id", companyFilter);
  if (typeFilter) params.set("event_type", typeFilter);
  if (lifecycleFilter) params.set("lifecycle", lifecycleFilter);
  if (severityFilter) params.set("severity", severityFilter);
  if (statusFilter) params.set("status", statusFilter);
  params.set("lookback_days", "30");
  params.set("limit", compact ? "5" : "100");
  const path = `attention?${params.toString()}`;
  const state = useResearch(path, isAttentionFeed);
  const events = state.data?.events ?? [];

  return (
    <section aria-labelledby={compact ? undefined : "attention-title"}>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle
              id={compact ? undefined : "attention-title"}
              className="text-lg"
            >
              {compact ? "Needs attention" : "Attention Center"}
            </CardTitle>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">
              Material changes and current review states from canonical records.
              {state.data
                ? ` · ${state.data.total} items in the current view`
                : ""}
            </p>
          </div>
          {compact && (
            <Button asChild size="sm" variant="outline">
              <Link href="/attention">Open feed</Link>
            </Button>
          )}
        </CardHeader>
        {!compact && (
          <div className="grid gap-2 px-6 pb-4 sm:grid-cols-2 lg:grid-cols-5">
            {!companyId && (
              <label className="text-xs text-muted-foreground">
                Company
                <select
                  aria-label="Filter by company"
                  className="mt-1 block h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
                  value={companyFilter}
                  onChange={(event) => setCompanyFilter(event.target.value)}
                >
                  <option value="">All companies</option>
                  {(universe.data ?? []).map((company) => (
                    <option key={company.id} value={company.id}>
                      {company.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <FilterSelect
              label="Event type"
              value={typeFilter}
              onChange={setTypeFilter}
              options={eventTypes}
            />
            <FilterSelect
              label="Lifecycle"
              value={lifecycleFilter}
              onChange={setLifecycleFilter}
              options={[
                ["", "All lifecycles"],
                ["PORTFOLIO", "Portfolio"],
                ["WATCHLIST", "Watchlist"],
                ["CANDIDATE", "Candidate"],
                ["DROP", "Drop"],
              ]}
            />
            <FilterSelect
              label="Severity"
              value={severityFilter}
              onChange={setSeverityFilter}
              options={[
                ["", "All severity"],
                ["HIGH", "High"],
                ["MEDIUM", "Medium"],
                ["LOW", "Low"],
              ]}
            />
            <FilterSelect
              label="Status"
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                ["", "All status"],
                ["REVIEW", "Review"],
                ["INFORMATIONAL", "Informational"],
              ]}
            />
          </div>
        )}
        <CardContent className="space-y-3">
          {state.error ? (
            <p role="alert" className="rounded-md border p-4 text-sm">
              Attention data is unavailable. Retry after checking the API.
            </p>
          ) : !state.data ? (
            <p role="status" className="py-4 text-sm text-muted-foreground">
              Loading recent changes
            </p>
          ) : events.length === 0 ? (
            <p className="rounded-md border border-dashed p-5 text-sm text-muted-foreground">
              Nothing meets the current attention rules and filters.
            </p>
          ) : (
            events.map((item) => (
              <article
                key={item.id}
                className="grid gap-3 rounded-lg border p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:p-4"
              >
                <div className="min-w-0">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold">{item.title}</h3>
                    <Badge
                      variant={
                        item.severity === "HIGH" ? "destructive" : "secondary"
                      }
                    >
                      {item.severity.toLowerCase()}
                    </Badge>
                    {item.status === "REVIEW" && (
                      <Badge variant="outline">Review</Badge>
                    )}
                    <Badge variant="outline">
                      {item.lifecycle ?? "Lifecycle unknown"}
                    </Badge>
                  </div>
                  <p className="text-xs leading-5 text-muted-foreground">
                    {item.company_name
                      ? `${item.company_name} · `
                      : "Portfolio · "}
                    {eventDate(
                      item.effective_at,
                      item.time_precision,
                      state.data?.as_of,
                    )}
                    {item.recorded_at
                      ? ` · recorded ${new Date(item.recorded_at).toLocaleString()}`
                      : " · recorded time unavailable"}
                  </p>
                  <p className="mt-2 text-sm leading-5">{item.explanation}</p>
                  {(item.prior_value || item.current_value) && (
                    <p className="mt-2 text-xs font-medium tabular-nums">
                      {item.prior_value ?? "Unavailable"} →{" "}
                      {item.current_value ?? "Unavailable"}
                      {item.unit ? ` ${item.unit}` : ""}
                    </p>
                  )}
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Source: {item.source_domain}
                    {item.source_id ? ` · ${item.source_id}` : ""}
                  </p>
                </div>
                <div className="flex items-start gap-2 sm:flex-col sm:items-end">
                  {item.href && (
                    <Button asChild size="sm" variant="outline">
                      <Link href={item.href}>Company detail</Link>
                    </Button>
                  )}
                  {item.source_reference?.startsWith("https://") && (
                    <Button asChild size="sm" variant="ghost">
                      <a
                        href={item.source_reference}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Source record
                      </a>
                    </Button>
                  )}
                </div>
              </article>
            ))
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: ReadonlyArray<readonly [string, string]>;
}) {
  return (
    <label className="text-xs text-muted-foreground">
      {label}
      <select
        aria-label={`Filter by ${label.toLowerCase()}`}
        className="mt-1 block h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map(([key, title]) => (
          <option key={key} value={key}>
            {title}
          </option>
        ))}
      </select>
    </label>
  );
}
