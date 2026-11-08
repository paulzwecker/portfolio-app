"use client";

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
  const { data, error } = useResearch(
    "market-data/historical-bootstrap",
    isHistoricalBootstrapReview,
  );
  return <HistoricalBootstrapPanelContent data={data} error={error} />;
}

export function HistoricalBootstrapPanelContent({
  data,
  error,
}: {
  data?: HistoricalBootstrapReview;
  error?: string;
}) {
  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Historical bootstrap review</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {error ? (
          <p role="status">
            Historical bootstrap review is unavailable. Check the API version
            and retry.
          </p>
        ) : !data ? (
          <p>Loading historical bootstrap review…</p>
        ) : !data.run_id ? (
          <p>No historical bootstrap run has been recorded.</p>
        ) : (
          <>
            <p>
              Latest run: {data.run_status} · prepared{" "}
              {dateTime(data.prepared_at)} · checked {dateTime(data.checked_at)}
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
                {data.omitted_listing_count} additional listings are not
                reviewed in this panel.
              </p>
            )}
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
          </>
        )}
      </CardContent>
    </Card>
  );
}
