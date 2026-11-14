import { afterEach, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { JobStatus } from "@/components/app/job-status";
import type { OperationalJobRequest } from "@/lib/domain-contracts";
import {
  hasCompletedRefresh,
  ManualRefreshPanel,
  requestEligibleSecRefresh,
  requestUniverseRefresh,
} from "./manual-refresh-panel";

function receipt(
  jobName: OperationalJobRequest["job_name"] = "SEC_FILINGS",
): OperationalJobRequest {
  return {
    id:
      jobName === "SEC_FILINGS"
        ? "11111111-1111-4111-8111-111111111111"
        : "22222222-2222-4222-8222-222222222222",
    job_name: jobName,
    scope_kind: "ACTIVE_UNIVERSE",
    company_id: null,
    company_name: null,
    lifecycle: null,
    requested_by: "LOCAL_USER",
    status: "QUEUED",
    requested_at: "2026-11-14T01:00:00Z",
    started_at: null,
    finished_at: null,
    next_attempt_at: null,
    attempt_count: 0,
    retry_of_id: null,
    affected_domains: [
      jobName === "SEC_FILINGS" ? "SOURCE_DOCUMENTS" : "REPORTED_FUNDAMENTALS",
    ],
    scope_detail: { scope_kind: "ACTIVE_UNIVERSE" },
    result: {},
    error_code: null,
    error_message: null,
    retry_available: false,
    deduplicated: false,
    cooldown_until: "2026-11-14T01:15:00Z",
    attempts: [],
  };
}

afterEach(() => vi.unstubAllGlobals());

it("queues only two existing SEC domains and records the first before requesting the second", async () => {
  const recorded: OperationalJobRequest[] = [];
  const fetcher = vi.fn(async (_url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      job_name: recorded.length === 0 ? "SEC_FILINGS" : "SEC_FUNDAMENTALS",
      scope_kind: "ACTIVE_UNIVERSE",
    });
    return Response.json(receipt(body.job_name), { status: 202 });
  });
  vi.stubGlobal("fetch", fetcher);
  await requestEligibleSecRefresh((item) => recorded.push(item));
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(recorded.map((item) => item.id)).toEqual([
    receipt().id,
    receipt("SEC_FUNDAMENTALS").id,
  ]);
});

it("retains a confirmed filings receipt when the fundamentals submission fails", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(receipt(), { status: 202 }))
    .mockResolvedValueOnce(
      Response.json(
        { detail: "Queue is at its bounded limit." },
        { status: 409 },
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  const recorded: OperationalJobRequest[] = [];
  await expect(
    requestEligibleSecRefresh((item) => recorded.push(item)),
  ).rejects.toThrow("The filings receipt remains below");
  expect(recorded).toEqual([receipt()]);
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it("does not queue fundamentals after an unconfirmed filings submission", async () => {
  const fetcher = vi
    .fn()
    .mockRejectedValue(new Error("Connection interrupted"));
  vi.stubGlobal("fetch", fetcher);
  const record = vi.fn();
  await expect(requestEligibleSecRefresh(record)).rejects.toThrow(
    "fundamentals were not requested",
  );
  expect(record).not.toHaveBeenCalled();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it.each([
  { job_name: "SEC_FUNDAMENTALS" },
  { scope_kind: "COMPANY", company_id: "33333333-3333-4333-8333-333333333333" },
])("rejects a valid but mismatched request receipt: %j", async (change) => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json({ ...receipt(), ...change })),
  );
  await expect(requestUniverseRefresh("SEC_FILINGS")).rejects.toThrow(
    "did not match the requested scope",
  );
});

it("accepts the server's deduplicated durable identity", async () => {
  const existing = { ...receipt(), deduplicated: true };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(existing)));
  expect(await requestUniverseRefresh("SEC_FILINGS")).toEqual(existing);
});

it("invalidates only observed terminal transitions, including partial and failed results", () => {
  const job = receipt();
  const active = new Set([job.id]);
  expect(
    hasCompletedRefresh(new Set(), [{ ...job, status: "SUCCEEDED" }]),
  ).toBe(false);
  expect(hasCompletedRefresh(active, [{ ...job, status: "RUNNING" }])).toBe(
    false,
  );
  expect(hasCompletedRefresh(active, [])).toBe(false);
  for (const status of ["SUCCEEDED", "PARTIAL", "FAILED", "BLOCKED"] as const)
    expect(hasCompletedRefresh(active, [{ ...job, status }])).toBe(true);
  expect(
    hasCompletedRefresh(active, [
      { ...receipt("SEC_FUNDAMENTALS"), status: "SUCCEEDED" },
    ]),
  ).toBe(false);
});

it("discloses bounded SEC-only scope and retains disabled execution", () => {
  const html = renderToStaticMarkup(
    <ManualRefreshPanel workerEnabled={false} manualRunnerEnabled={false} />,
  );
  expect(html).toContain("Refresh eligible SEC data");
  expect(html).toContain("limited to 30 issuers");
  expect(html).toContain("five historical files per attempt");
  expect(html).toContain("Creates two durable requests");
  expect(html).toContain("Manual operations are disabled in this environment.");
  const button = html
    .match(/<button\b[\s\S]*?<\/button>/g)
    ?.find((item) => item.includes("Refresh eligible SEC data"));
  expect(button).toContain('disabled=""');
});

it("keeps durable identity and source coverage failures inspectable in the shared job card", () => {
  const job = receipt();
  job.status = "PARTIAL";
  job.error_message = "One issuer response is incomplete.";
  job.attempts = [
    {
      id: "44444444-4444-4444-8444-444444444444",
      attempt_number: 1,
      step_name: "SEC_FILINGS",
      status: "PARTIAL",
      affected_domains: ["SOURCE_DOCUMENTS"],
      started_at: "2026-11-14T01:00:01Z",
      finished_at: "2026-11-14T01:00:05Z",
      result: { status: "PARTIAL", report: { skipped_company_count: 1 } },
      error_code: null,
      error_message: null,
    },
  ];
  const html = renderToStaticMarkup(<JobStatus job={job} />);
  expect(html).toContain(job.id);
  expect(html).toContain("SEC EDGAR");
  expect(html).toContain("One issuer response is incomplete.");
  expect(html).toContain("skipped_company_count");
  expect(html).toContain("does not imply complete financial history");
});
