import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { isHistoricalBootstrapReview } from "@/lib/domain-contracts";
import { HistoricalBootstrapPanelContent } from "./historical-bootstrap-panel";

describe("historical bootstrap review", () => {
  const payload = {
    run_id: "11111111-1111-4111-8111-111111111111",
    run_status: "COMPLETE",
    prepared_at: "2026-11-08T20:00:00Z",
    requested_start: "2025-01-01",
    requested_end: "2026-12-31",
    checked_at: "2026-11-09T00:00:00Z",
    listing_count: 2,
    fx_checkpoint_count: 1,
    omitted_listing_count: 1,
    listings: [
      {
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
    expect(html).toContain("1 additional listings are not reviewed");
    expect(html).toContain(
      "does not establish coverage of the full requested window",
    );
    expect(html).toContain("not confirmed missing trades");
    expect(html).toContain("FX sessions remain unassessed");
    expect(html).toContain("synthetic");
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
    expect(
      isHistoricalBootstrapReview({ ...payload, requested_start: null }),
    ).toBe(false);
    if (!isHistoricalBootstrapReview(empty)) throw new Error("fixture invalid");
    expect(
      renderToStaticMarkup(<HistoricalBootstrapPanelContent data={empty} />),
    ).toContain("No historical bootstrap run");
  });
});
