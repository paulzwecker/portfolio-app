import { describe, expect, it } from "vitest";
import {
  isMarketRefreshStatus,
  type MarketRefreshRun,
} from "./domain-contracts";

const at = "2026-11-07T12:00:00Z";
const run: MarketRefreshRun = {
  run_id: "10000000-0000-4000-8000-000000000001",
  domain: "FX",
  status: "FAILED",
  last_attempt_at: at,
  finished_at: at,
  last_successful_at: null,
  attempt_count: 1,
  max_attempts: 3,
  retry_state: "COOLDOWN",
  retry_eligible_at: "2026-11-07T12:15:00Z",
  failure_code: "NETWORK_ERROR",
  failure_message: "Provider network request failed.",
  request_scope: { required_fx_pairs: [["USD", "EUR"]] },
  report: { status: "FAILED" },
  attempts: [
    {
      attempt_number: 1,
      status: "FAILED",
      started_at: at,
      finished_at: at,
      retryable: true,
      failure_code: "NETWORK_ERROR",
      failure_message: "Provider network request failed.",
    },
  ],
};
const legacy = {
  state: "PARTIAL",
  last_attempt_at: at,
  last_successful_update: at,
  market_run_id: null,
  fx_run_id: run.run_id,
  message: run.failure_message,
};

describe("Market refresh diagnostics contract", () => {
  it("preserves compatibility with a deployed API without detailed runs", () => {
    expect(isMarketRefreshStatus(legacy)).toBe(true);
    expect(isMarketRefreshStatus({ ...legacy, runs: [run] })).toBe(true);
  });

  it.each([
    { retry_state: "APPROVED" },
    { retry_eligible_at: "not a timestamp" },
    { request_scope: null },
    { report: [] },
    { attempt_count: "1" },
    { attempts: [{ ...run.attempts[0], retryable: "true" }] },
  ])("rejects malformed diagnostic fields %j", (replacement) => {
    expect(
      isMarketRefreshStatus({ ...legacy, runs: [{ ...run, ...replacement }] }),
    ).toBe(false);
  });
});
