import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GET, POST } from "@/app/api/research/[...path]/route";
import {
  isCompanySecCoverage,
  type CompanySecCoverage,
} from "@/lib/domain-contracts";
import { SecCoverageDetails } from "./company-sec-coverage";

const id = "11111111-1111-4111-8111-111111111111";
const data: CompanySecCoverage = {
  company_id: id,
  company_name: "Synthetic issuer",
  mapping_status: "MAPPED",
  cik: "0000000001",
  provider_company_name: "Synthetic Holdings Inc.",
  identity_evidence_url: "https://www.sec.gov/edgar/browse/?CIK=1",
  fundamentals: {
    record_count: 1,
    data_check_count: 0,
    latest_period_end: "2023-12-31",
    latest_filed_at: "2024-02-10",
    latest_retrieved_at: "2026-10-19T10:00:00Z",
    latest_recorded_at: "2026-10-19T10:01:00Z",
    bootstrap: null,
  },
  filings: {
    record_count: 0,
    data_check_count: 0,
    latest_period_end: null,
    latest_filed_at: null,
    latest_retrieved_at: null,
    latest_recorded_at: null,
    bootstrap: {
      checkpoint_id: id,
      run_id: id,
      status: "FAILED",
      prepared_at: "2026-10-19T10:00:00Z",
      started_at: "2026-10-19T10:00:00Z",
      finished_at: "2026-10-19T10:01:00Z",
      failure_code: "SEC_NETWORK_ERROR",
      retryable: true,
      next_attempt_at: "2026-10-19T10:01:05Z",
      provider_request_count: 1,
    },
  },
  metrics_present: ["REVENUE"],
  metrics_missing: [
    "GROSS_PROFIT",
    "OPERATING_INCOME",
    "NET_INCOME",
    "CASH_AND_CASH_EQUIVALENTS",
    "CURRENT_DEBT",
    "NONCURRENT_DEBT",
    "OPERATING_CASH_FLOW",
    "CAPITAL_EXPENDITURES",
    "DILUTED_WEIGHTED_AVERAGE_SHARES",
  ],
};

beforeEach(() => {
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_ACCESS_TOKEN", "");
  vi.stubEnv("WEB_ACCESS_USERNAME", "");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("Company SEC coverage", () => {
  it("validates exact coverage types and rejects incomplete metric inventories", () => {
    expect(isCompanySecCoverage(data)).toBe(true);
    expect(isCompanySecCoverage({ ...data, metrics_missing: [] })).toBe(false);
    expect(
      isCompanySecCoverage({
        ...data,
        metrics_present: ["REVENUE", "REVENUE"],
      }),
    ).toBe(false);
    expect(
      isCompanySecCoverage({
        ...data,
        fundamentals: { ...data.fundamentals, record_count: "1" },
      }),
    ).toBe(false);
    expect(
      isCompanySecCoverage({
        ...data,
        fundamentals: { ...data.fundamentals, record_count: -1 },
      }),
    ).toBe(false);
    expect(
      isCompanySecCoverage({
        ...data,
        identity_evidence_url: "javascript:invalid",
      }),
    ).toBe(false);
    expect(
      isCompanySecCoverage({
        ...data,
        identity_evidence_url: "https://example.test/?CIK=1",
      }),
    ).toBe(false);
    expect(
      isCompanySecCoverage({
        ...data,
        identity_evidence_url: "https://fixture:synthetic@sec.gov/?CIK=1",
      }),
    ).toBe(false);
  });
  it("separates period, filing and retrieval dates and retains failure details", () => {
    const html = renderToStaticMarkup(<SecCoverageDetails data={data} />);
    expect(html).toContain("Latest economic period end");
    expect(html).toContain("Latest filing date");
    expect(html).toContain("Latest retained retrieval");
    expect(html).toContain("2023");
    expect(html).toContain("2026");
    expect(html).toContain("SEC_NETWORK_ERROR");
    expect(html).toContain("Next attempt after");
    expect(html).not.toContain("Fresh");
  });
  it("keeps absent coverage and missing identity explicit", () => {
    const html = renderToStaticMarkup(
      <SecCoverageDetails
        data={{
          ...data,
          mapping_status: "UNMAPPED",
          cik: null,
          provider_company_name: null,
          identity_evidence_url: null,
        }}
      />,
    );
    expect(html).toContain("reviewed SEC CIK mapping is required");
    expect(html).toContain("Not retained");
    expect(html).toContain("Missing concepts remain unavailable");
    expect(html).not.toContain("SEC identity evidence</");
  });
  it("proxies the typed read and rejects writes to the coverage endpoint", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json(data));
    vi.stubGlobal("fetch", fetch);
    const path = ["companies", id, "sec-coverage"];
    const context = { params: Promise.resolve({ path }) };
    const result = await GET(
      new Request(`http://localhost/api/research/${path.join("/")}`),
      context,
    );
    expect(result.status).toBe(200);
    expect(await result.json()).toEqual(data);
    expect(fetch.mock.calls[0][1].cache).toBe("no-store");
    const rejected = await POST(
      new Request(`http://localhost/api/research/${path.join("/")}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }),
      context,
    );
    expect(rejected.status).toBe(404);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
