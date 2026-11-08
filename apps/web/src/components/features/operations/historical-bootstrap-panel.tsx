"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  isHistoricalBootstrapReview,
  type HistoricalBootstrapReview,
} from "@/lib/domain-contracts";
import { dateOnly, dateTime } from "@/lib/display";

const reasonLabels = {
  AVAILABLE: "Schedule review available",
  CHECKPOINT_NOT_COMPLETE: "Checkpoint is not complete",
  IDENTITY_CHANGED: "Listing identity needs review",
  LISTING_CURRENCY_UNAVAILABLE: "Listing currency is unavailable",
  BATCH_UNVERIFIED: "Batch identity is unavailable or inconsistent",
  NO_DAILY_CLOSES: "No eligible 2026 daily closes in this batch",
  NO_SCHEDULE: "No reviewed schedule for these dates or venue",
  DATE_LIMIT_EXCEEDED: "Date limit exceeded; review the source separately",
} as const;

export function HistoricalBootstrapPanel() {
  const [page, setPage] = useState<{ runId: string; offset: number } | null>(
    null,
  );
  const { data, error, retry } = useResearch(
    page
      ? `market-data/historical-bootstrap?run_id=${encodeURIComponent(page.runId)}&offset=${page.offset}`
      : "market-data/historical-bootstrap",
    isHistoricalBootstrapReview,
  );
  return (
    <HistoricalBootstrapPanelContent
      data={data}
      error={error}
      onPage={(runId, offset) => setPage({ runId, offset })}
      onLatest={() => {
        if (page) setPage(null);
        else retry();
      }}
    />
  );
}

export function HistoricalBootstrapPanelContent({
  data,
  error,
  onPage,
  onLatest,
}: {
  data?: HistoricalBootstrapReview;
  error?: string;
  onPage?: (runId: string, offset: number) => void;
  onLatest?: () => void;
}) {
  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Historical bootstrap review</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {error ? (
          <div role="status">
            <p>
              Historical bootstrap review is unavailable. Check the API version
              and retry.
            </p>
            {onLatest && (
              <Button variant="outline" onClick={onLatest}>
                Load latest run
              </Button>
            )}
          </div>
        ) : !data ? (
          <p>Loading historical bootstrap review…</p>
        ) : !data.run_id ? (
          <p>No historical bootstrap run has been recorded.</p>
        ) : (
          <>
            <p>
              Run: {data.run_status} · prepared {dateTime(data.prepared_at)} ·
              checked {dateTime(data.checked_at)}
            </p>
            <p>
              Requested{" "}
              {data.requested_start
                ? dateOnly(data.requested_start)
                : "Unavailable"}{" "}
              –{" "}
              {data.requested_end
                ? dateOnly(data.requested_end)
                : "Unavailable"}{" "}
              · {data.listing_count} listing checkpoints ·{" "}
              {data.fx_checkpoint_count} FX checkpoints
            </p>
            <p className="text-muted-foreground">
              Review uses eligible stored batch dates within 2026, between the
              first and last returned close. It does not establish coverage of
              the full requested window, reconcile provider payloads, or verify
              unscheduled closures and security halts. FX sessions remain
              unassessed.
            </p>
            {data.omitted_listing_count > 0 && (
              <p>
                {data.omitted_listing_count} additional listings follow this
                page.
              </p>
            )}
            <p className="text-muted-foreground">
              Each page is checked independently; the run is pinned, but its
              data may change between requests.
            </p>
            <div className="space-y-2">
              {data.listings.map((row) => (
                <details
                  key={row.subject_key}
                  className="rounded-md border px-3 py-2"
                >
                  <summary className="cursor-pointer font-medium break-words">
                    {row.subject_key} · {reasonLabels[row.reason]}
                  </summary>
                  <p className="mt-2 text-muted-foreground">
                    Checkpoint: {row.checkpoint_status}
                  </p>
                  {row.scheduled_session_review && (
                    <div className="mt-2 space-y-1 text-muted-foreground">
                      <p>
                        {row.scheduled_session_review.venue}:{" "}
                        {dateOnly(row.scheduled_session_review.start_date)} –{" "}
                        {dateOnly(row.scheduled_session_review.end_date)} ·{" "}
                        {row.scheduled_session_review.scheduled_count} scheduled
                        dates
                      </p>
                      <p>
                        Dates without selected closes:{" "}
                        {
                          row.scheduled_session_review.absent_scheduled_dates
                            .length
                        }
                        ; selected closes outside schedule:{" "}
                        {
                          row.scheduled_session_review
                            .selected_unscheduled_dates.length
                        }
                        . These are review candidates, not confirmed missing
                        trades.
                      </p>
                      {row.scheduled_session_review.absent_scheduled_dates
                        .length > 0 && (
                        <p className="break-words">
                          {row.scheduled_session_review.absent_scheduled_dates
                            .map((day) => dateOnly(day))
                            .join(", ")}
                        </p>
                      )}
                      {row.scheduled_session_review.selected_unscheduled_dates
                        .length > 0 && (
                        <p className="break-words">
                          Outside schedule:{" "}
                          {row.scheduled_session_review.selected_unscheduled_dates
                            .map((day) => dateOnly(day))
                            .join(", ")}
                        </p>
                      )}
                      <p className="break-all">
                        Schedule: {row.scheduled_session_review.schedule_id} ·
                        SHA-256:{" "}
                        {row.scheduled_session_review.schedule_fingerprint ??
                          "Unavailable"}
                      </p>
                    </div>
                  )}
                </details>
              ))}
            </div>
            {onPage && (
              <div
                className="flex flex-wrap items-center gap-2"
                aria-label="Historical bootstrap pages"
              >
                <Button
                  variant="outline"
                  disabled={data.offset === 0}
                  onClick={() =>
                    onPage(data.run_id!, Math.max(0, data.offset - 30))
                  }
                >
                  Previous listings
                </Button>
                <span>
                  Showing {data.listings.length ? data.offset + 1 : 0}–
                  {data.offset + data.listings.length} of {data.listing_count}
                </span>
                <Button
                  variant="outline"
                  disabled={
                    data.omitted_listing_count === 0 || data.offset + 30 > 10000
                  }
                  onClick={() => onPage(data.run_id!, data.offset + 30)}
                >
                  Next listings
                </Button>
                <Button variant="ghost" onClick={onLatest}>
                  Latest run
                </Button>
              </div>
            )}
            {data.omitted_listing_count > 0 && data.offset + 30 > 10000 && (
              <p>
                Further listings exceed the page limit; review a smaller scoped
                run.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
