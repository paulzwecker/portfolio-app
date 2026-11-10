"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  ResponsiveDataTable,
  type ResponsiveColumn,
} from "@/components/app/responsive-data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  isMarketBootstrapScopePreview,
  type MarketBootstrapScopePreview,
} from "@/lib/domain-contracts";
import { dateTime } from "@/lib/display";

type ScopeListing = MarketBootstrapScopePreview["listing_review"][number];
const listingColumns: ResponsiveColumn<ScopeListing>[] = [
  {
    id: "listing",
    header: "Listing",
    render: (row) => (
      <>
        <p className="font-medium">
          {row.company_name ?? "Standalone security"}
        </p>
        <p>
          {row.ticker} · {row.venue} · {row.currency ?? "Currency unavailable"}
        </p>
        <p className="text-muted-foreground">
          {row.security_type.replaceAll("_", " ")}
        </p>
        <details className="mt-1 text-xs text-muted-foreground">
          <summary
            className="cursor-pointer"
            aria-label={`Canonical IDs for ${row.ticker} on ${row.venue}`}
          >
            Canonical IDs
          </summary>
          <p className="break-all">Listing: {row.listing_id}</p>
          <p className="break-all">Security: {row.security_id}</p>
          {row.company_id && (
            <p className="break-all">Company: {row.company_id}</p>
          )}
        </details>
      </>
    ),
  },
  {
    id: "priority",
    header: "Selected as",
    render: (row) =>
      row.priority === "HELD"
        ? `HELD · quantity ${row.held_quantity ?? "unknown"}`
        : row.priority,
  },
  {
    id: "provider",
    header: "Provider mapping",
    render: (row) =>
      row.mapping_verified
        ? `Verified: ${row.provider_symbol}`
        : "Needs review",
  },
];

export function MarketScopePreview() {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [submitted, setSubmitted] = useState<{
    start: string;
    end: string;
  } | null>(null);
  const [invalid, setInvalid] = useState(false);
  const path = submitted
    ? `market-data/bootstrap-scope?start_date=${submitted.start}&end_date=${submitted.end}`
    : "market-data/bootstrap-scope";
  const { data, error, retry } = useResearch(
    path,
    isMarketBootstrapScopePreview,
    0,
    !!submitted,
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!start || !end || start > end) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    if (submitted?.start === start && submitted.end === end) retry();
    else setSubmitted({ start, end });
  }

  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle role="heading" aria-level={2} className="text-base">
          Review historical data scope
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          Review held, Portfolio and Watchlist listings and required currency
          pairs for a proposed window. This reads current mappings only; it does
          not fetch prices or prepare a run.
        </p>
        <form className="flex flex-wrap items-end gap-3" onSubmit={submit}>
          <label className="grid gap-1" htmlFor="market-scope-start">
            Start date
            <input
              id="market-scope-start"
              type="date"
              required
              value={start}
              onChange={(event) => {
                setStart(event.target.value);
                setSubmitted(null);
                setInvalid(false);
                retry();
              }}
              className="rounded-md border bg-background px-3 py-2"
            />
          </label>
          <label className="grid gap-1" htmlFor="market-scope-end">
            End date
            <input
              id="market-scope-end"
              type="date"
              required
              value={end}
              onChange={(event) => {
                setEnd(event.target.value);
                setSubmitted(null);
                setInvalid(false);
                retry();
              }}
              className="rounded-md border bg-background px-3 py-2"
            />
          </label>
          <Button type="submit" variant="outline">
            Review scope
          </Button>
        </form>
        {invalid && (
          <p role="alert">Choose a start date on or before the end date.</p>
        )}
        {submitted && !data && !error && (
          <p role="status">Checking current scope…</p>
        )}
        {error && (
          <p role="status">
            Scope review is unavailable. Check the dates and API, then retry.
          </p>
        )}
        {data && (
          <div role="status" className="space-y-2">
            <p className="font-medium">
              {data.status === "READY"
                ? data.holdings_snapshot?.completeness === "COMPLETE"
                  ? "Mappings ready for review"
                  : "Mappings available; holdings need review"
                : "Scope needs review"}{" "}
              · checked {dateTime(data.checked_at)}
            </p>
            <p>
              {data.date_window.start} to {data.date_window.end} · configured{" "}
              {data.target_environment} environment
            </p>
            {data.holdings_snapshot ? (
              <p>
                Holdings snapshot: {data.holdings_snapshot.completeness} ·
                effective {dateTime(data.holdings_snapshot.effective_at)} ·
                recorded {dateTime(data.holdings_snapshot.recorded_at)} ·
                portfolio {data.holdings_snapshot.portfolio_id}
              </p>
            ) : (
              <p
                role="alert"
                className="rounded-lg border border-warning/35 bg-warning/10 px-3 py-2 text-warning"
              >
                No holdings snapshot is available; the held scope cannot be
                established.
              </p>
            )}
            {data.holdings_snapshot &&
              data.holdings_snapshot.completeness !== "COMPLETE" && (
                <p
                  role="alert"
                  className="rounded-lg border border-warning/35 bg-warning/10 px-3 py-2 text-warning"
                >
                  The holdings snapshot is incomplete or unavailable; the
                  selected listings cannot establish a complete held scope.
                </p>
              )}
            <p className="text-muted-foreground">
              The selection includes every recorded position, including zero and
              unknown quantities. Confirm the intended holdings separately.
            </p>
            <p>
              Provider: {data.provider_id} · {data.provider_schema_version} ·
              mapping SHA-256:{" "}
              <span className="break-all">{data.crosswalk_sha256}</span>
            </p>
            <p>
              {data.selected_listing_count} selected listings (
              {data.listing_priority_counts.HELD} held,{" "}
              {data.listing_priority_counts.PORTFOLIO} Portfolio,{" "}
              {data.listing_priority_counts.WATCHLIST} Watchlist,{" "}
              {data.listing_priority_counts.OTHER} other) ·{" "}
              {data.verified_listing_mapping_count} verified mappings
            </p>
            <p>
              Required FX:{" "}
              {data.required_fx_pairs.length
                ? data.required_fx_pairs.join(", ")
                : "None identified"}{" "}
              · {data.provider_requests_planned} planned provider scopes
            </p>
            {data.unresolved_listings.length > 0 && (
              <p>
                {data.unresolved_listings.length} listing mappings need review.
              </p>
            )}
            {data.unmapped_fx_pairs.length > 0 && (
              <p>Unmapped FX: {data.unmapped_fx_pairs.join(", ")}</p>
            )}
            {data.canonical_import_readiness && (
              <p>
                Canonical receipt:{" "}
                {data.canonical_import_readiness.status.replaceAll("_", " ")} ·
                source gaps:{" "}
                {data.canonical_import_readiness.source_gap_count ??
                  "Not recorded"}
              </p>
            )}
            {data.omitted_listing_count > 0 && (
              <p
                role="alert"
                className="rounded-lg border border-warning/35 bg-warning/10 px-3 py-2 text-warning"
              >
                {data.omitted_listing_count} selected listings are not shown.
                Stop and obtain a separate read-only listing inventory before
                using the guarded operator preview.
              </p>
            )}
            {data.listing_review.length > 0 && (
              <details className="space-y-3">
                <summary className="cursor-pointer font-medium">
                  Review {data.listing_review.length} selected listings
                </summary>
                <ResponsiveDataTable
                  caption="Selected market-data listings"
                  columns={listingColumns}
                  rows={data.listing_review}
                  getRowKey={(row) => row.listing_id}
                />
              </details>
            )}
            <p className="text-muted-foreground">
              Held listings use the most recent snapshot across portfolios; cash
              FX requirements use the first-created portfolio. Review both if
              more than one portfolio exists. This review does not verify the
              database target, provider permission or recovery, establish data
              availability, or authorize ingestion. Planned scopes are not a
              limit on retry requests. The selection can change; use the guarded
              operator preview and confirm exact identities before any write.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
