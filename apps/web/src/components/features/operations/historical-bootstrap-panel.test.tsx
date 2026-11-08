import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  isHistoricalBootstrapReview,
  isHistoricalBootstrapReconciliation,
} from "@/lib/domain-contracts";
import { HistoricalBootstrapPanelContent } from "./historical-bootstrap-panel";

describe("historical bootstrap review", () => {
  it("rejects malformed or unexplained reconciliation states", () => {
    const result = {
      run_id: "11111111-1111-4111-8111-111111111111",
      checkpoint_id: "22222222-2222-4222-8222-222222222222",
      checked_at: "2026-11-09T00:00:00Z",
      status: "MATCHED",
      issue_codes: [],
    };
    expect(isHistoricalBootstrapReconciliation(result)).toBe(true);
    expect(
      isHistoricalBootstrapReconciliation({ ...result, status: "MISMATCH" }),
    ).toBe(false);
    expect(
      isHistoricalBootstrapReconciliation({
        ...result,
        status: "MISMATCH",
        issue_codes: ["SOURCE_PAYLOAD_HASH_MISMATCH"],
      }),
    ).toBe(true);
    expect(
      isHistoricalBootstrapReconciliation({
        ...result,
        status: "MISMATCH",
        issue_codes: ["arbitrary source content"],
      }),
    ).toBe(false);
  });
  const payload = {
    run_id: "11111111-1111-4111-8111-111111111111",
    run_status: "COMPLETE",
    prepared_at: "2026-11-08T20:00:00Z",
    requested_start: "2025-01-01",
    requested_end: "2026-12-31",
    checked_at: "2026-11-09T00:00:00Z",
    listing_count: 2,
    fx_checkpoint_count: 1,
    offset: 0,
    omitted_listing_count: 1,
    listings: [
      {
        checkpoint_id: "22222222-2222-4222-8222-222222222222",
        subject_key: "NYSE:SYNTH",
        checkpoint_status: "COMPLETE",
        reason: "AVAILABLE",
        scheduled_session_review: {
          venue: "NYSE",
          schedule_id: "synthetic",
          source_url:
            "https://www.nyse.com/publicdocs/nyse/ICE_NYSE_2026_Yearly_Trading_Calendar.pdf",
          source_sha256: "a".repeat(64),
          schedule_fingerprint: "b".repeat(64),
          source_as_of: null,
          source_observed_at: "2026-11-08T18:37:45Z",
          start_date: "2026-07-02",
          end_date: "2026-07-07",
          full_selected_span_covered: true,
          scheduled_count: 3,
          absent_scheduled_dates: ["2026-07-06"],
          selected_unscheduled_dates: [],
        },
      },
    ],
  };

  it("shows bounded evidence and missing coverage honestly", () => {
    expect(isHistoricalBootstrapReview(payload)).toBe(true);
    if (!isHistoricalBootstrapReview(payload))
      throw new Error("fixture invalid");
    const html = renderToStaticMarkup(
      <HistoricalBootstrapPanelContent data={payload} />,
    );
    expect(html).toContain("1 additional listings follow this page");
    expect(html).toContain("coverage of dates outside the displayed range");
    expect(html).toContain("not confirmed missing trades");
    expect(html).toContain("FX sessions remain unassessed");
    expect(html).toContain("Requested-window schedule review unavailable");
    expect(html).toContain("synthetic");
  });

  it("displays boundary candidates and rejects conflicting schedule evidence", () => {
    const window = {
      ...payload.listings[0].scheduled_session_review,
      start_date: "2026-07-01",
      end_date: "2026-07-10",
      absent_scheduled_dates: ["2026-07-01", "2026-07-06", "2026-07-08"],
    };
    const withWindow = {
      ...payload,
      listings: [{ ...payload.listings[0], requested_window_review: window }],
    };
    expect(isHistoricalBootstrapReview(withWindow)).toBe(true);
    if (!isHistoricalBootstrapReview(withWindow))
      throw new Error("fixture invalid");
    const html = renderToStaticMarkup(
      <HistoricalBootstrapPanelContent data={withWindow} />,
    );
    expect(html).toContain("Requested-window schedule review");
    expect(html).toContain("3 scheduled dates without eligible closes");
    expect(html).toContain("Dates outside this window remain unassessed");
    expect(
      isHistoricalBootstrapReview({
        ...payload,
        listings: [
          {
            ...payload.listings[0],
            requested_window_review: { ...window, schedule_id: "different" },
          },
        ],
      }),
    ).toBe(false);
  });

  it("keeps unavailable, empty and malformed states distinct", () => {
    expect(
      renderToStaticMarkup(<HistoricalBootstrapPanelContent error="failed" />),
    ).toContain("unavailable");
    expect(
      isHistoricalBootstrapReview({ ...payload, omitted_listing_count: 0 }),
    ).toBe(false);
    expect(
      isHistoricalBootstrapReview({
        ...payload,
        listings: [
          {
            ...payload.listings[0],
            reason: "AVAILABLE",
            scheduled_session_review: null,
          },
        ],
      }),
    ).toBe(false);
    const empty = {
      ...payload,
      run_id: null,
      run_status: null,
      prepared_at: null,
      requested_start: null,
      requested_end: null,
      listing_count: 0,
      fx_checkpoint_count: 0,
      omitted_listing_count: 0,
      listings: [],
    };
    expect(isHistoricalBootstrapReview(empty)).toBe(true);
    expect(isHistoricalBootstrapReview({ ...payload, run_id: null })).toBe(
      false,
    );
    expect(isHistoricalBootstrapReview({ ...payload, offset: 30 })).toBe(false);
    expect(
      isHistoricalBootstrapReview({ ...payload, requested_start: null }),
    ).toBe(false);
    if (!isHistoricalBootstrapReview(empty)) throw new Error("fixture invalid");
    expect(
      renderToStaticMarkup(<HistoricalBootstrapPanelContent data={empty} />),
    ).toContain("No historical bootstrap run");
  });

  it("shows recorded empty response evidence without inventing warning counts", () => {
    const diagnostics = {
      failure_kind: "NO_PROVIDER_DATA",
      raw_response_count: 1,
      normalized_daily_rows: 0,
      provider_failure_count: 0,
      normalization_rejection_count: 1,
      normalization_warning_count: null,
      retryable: false,
    };
    const data = {
      ...payload,
      listings: [
        {
          checkpoint_id: "22222222-2222-4222-8222-222222222222",
          subject_key: "NYSE:SYNTH",
          checkpoint_status: "UNAVAILABLE",
          reason: "CHECKPOINT_UNAVAILABLE",
          scheduled_session_review: null,
          checkpoint_diagnostics: diagnostics,
        },
      ],
    };
    expect(isHistoricalBootstrapReview(data)).toBe(true);
    if (!isHistoricalBootstrapReview(data)) throw new Error("fixture invalid");
    const html = renderToStaticMarkup(
      <HistoricalBootstrapPanelContent data={data} />,
    );
    expect(html).toContain("Provider reported no observations");
    expect(html).toContain("Normalization warnings: Not recorded");
    expect(html).toContain("raw responses have not been reconciled");
    expect(
      isHistoricalBootstrapReview({
        ...data,
        listings: [
          {
            ...data.listings[0],
            checkpoint_diagnostics: { ...diagnostics, raw_response_count: -1 },
          },
        ],
      }),
    ).toBe(false);
  });
});
