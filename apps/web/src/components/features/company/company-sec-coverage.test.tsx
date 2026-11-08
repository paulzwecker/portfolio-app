import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GET, POST } from "@/app/api/research/[...path]/route";
import {
  isCompanySecCoverage,
  type CompanySecCoverage,
} from "@/lib/domain-contracts";
import {
  CompanySecCoveragePanel,
  SecCoverageDetails,
} from "./company-sec-coverage";

const coverageState = vi.hoisted(() => ({
  data: null as CompanySecCoverage | null,
}));
vi.mock("@/hooks/use-research", () => ({ useResearch: () => coverageState }));

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

const refresh: NonNullable<CompanySecCoverage["fundamentals"]["refresh"]> = {
  run_id: id,
  attempt_id: id,
  request_id: id,
  trigger: "MANUAL",
  batch_status: "PARTIAL",
  requested_at: "2026-11-07T09:00:00Z",
  started_at: "2026-11-07T09:01:00Z",
  finished_at: "2026-11-07T09:02:00Z",
  attempt_count: 1,
  retryable: false,
  failure_code: null,
  scope_company_count: 3,
  mapped_company_count: 2,
  issuer_outcome: "REPORTED",
  source_record_count: 12,
};

function withRefresh(value: unknown) {
  return { ...data, fundamentals: { ...data.fundamentals, refresh: value } };
}

beforeEach(() => {
  coverageState.data = null;
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
  it("retains older identity warnings beside a newer matched execution", () => {
    const matched = { status: "MATCHED" as const, frozen_cik: "0000000001" };
    const changed = { status: "CHANGED" as const, frozen_cik: "0000000002" };
    coverageState.data = {
      ...data,
      filings: {
        ...data.filings,
        refresh: { ...refresh, identity: matched },
        bootstrap: {
          ...data.filings.bootstrap!,
          status: "COMPLETE",
          identity: changed,
        },
      },
    };
    const newerRefresh = renderToStaticMarkup(
      <CompanySecCoveragePanel companyId={id} />,
    ).split("<dialog")[0];
    expect(newerRefresh).toContain("Other recorded bootstrap:");
    expect(newerRefresh).toContain(
      "issuer details changed since this bootstrap",
    );
    coverageState.data = {
      ...data,
      filings: {
        ...data.filings,
        refresh: {
          ...refresh,
          requested_at: "2026-10-18T09:00:00Z",
          started_at: "2026-10-18T09:00:00Z",
          finished_at: "2026-10-18T09:01:00Z",
          identity: changed,
        },
        bootstrap: {
          ...data.filings.bootstrap!,
          status: "COMPLETE",
          identity: matched,
        },
      },
    };
    const newerBootstrap = renderToStaticMarkup(
      <CompanySecCoveragePanel companyId={id} />,
    ).split("<dialog")[0];
    expect(newerBootstrap).toContain("Other recorded refresh:");
    expect(newerBootstrap).toContain(
      "issuer details changed since this refresh",
    );
  });
  it("surfaces a changed bootstrap issuer even when its checkpoint completed", () => {
    const bootstrap = {
      ...data.filings.bootstrap!,
      status: "COMPLETE" as const,
      identity: { status: "CHANGED" as const, frozen_cik: "0000000002" },
    };
    coverageState.data = { ...data, filings: { ...data.filings, bootstrap } };
    expect(isCompanySecCoverage(coverageState.data)).toBe(true);
    const panel = renderToStaticMarkup(
      <CompanySecCoveragePanel companyId={id} />,
    );
    expect(panel).toContain("Filings bootstrap");
    expect(panel).toContain("issuer details changed since this bootstrap");
    const details = renderToStaticMarkup(
      <SecCoverageDetails data={coverageState.data} />,
    );
    expect(details).toContain("Frozen bootstrap CIK 0000000002");
    expect(details).toContain(
      "historical, not evidence for the current identity",
    );
  });
  it("handles old and malformed bootstrap identity evidence conservatively", () => {
    expect(isCompanySecCoverage(data)).toBe(true);
    const bad = {
      ...data,
      filings: {
        ...data.filings,
        bootstrap: {
          ...data.filings.bootstrap!,
          identity: { status: "MATCHED", frozen_cik: null },
        },
      },
    };
    expect(isCompanySecCoverage(bad)).toBe(false);
    coverageState.data = data;
    expect(
      renderToStaticMarkup(<CompanySecCoveragePanel companyId={id} />),
    ).toContain("bootstrap issuer identity could not be verified");
  });
  it("keeps a newer bootstrap warning visible over older incremental success", () => {
    coverageState.data = {
      ...data,
      filings: {
        ...data.filings,
        refresh: {
          ...refresh,
          batch_status: "COMPLETE",
          requested_at: "2026-10-18T09:00:00Z",
          started_at: "2026-10-18T09:00:00Z",
          finished_at: "2026-10-18T09:01:00Z",
        },
      },
    };
    const html = renderToStaticMarkup(
      <CompanySecCoveragePanel companyId={id} />,
    );
    expect(html).toContain("Filings bootstrap");
    expect(html).toContain("SEC_NETWORK_ERROR");
    expect(html).not.toContain("Filings refresh batch");
  });
  it("replaces an older bootstrap warning with a newer incremental result", () => {
    coverageState.data = { ...data, filings: { ...data.filings, refresh } };
    const html = renderToStaticMarkup(
      <CompanySecCoveragePanel companyId={id} />,
    );
    expect(html).toContain("Filings refresh batch");
    expect(html).not.toContain("Filings bootstrap");
    expect(html.split("<dialog")[0]).not.toContain("SEC_NETWORK_ERROR");
    expect(html).toContain("SEC_NETWORK_ERROR");
  });
  it("accepts old coverage and typed refresh attribution independently of batch status", () => {
    expect(isCompanySecCoverage(data)).toBe(true);
    expect(isCompanySecCoverage(withRefresh(refresh))).toBe(true);
    expect(isCompanySecCoverage(withRefresh(null))).toBe(true);
    expect(
      isCompanySecCoverage(
        withRefresh({
          ...refresh,
          issuer_outcome: "NOT_REPORTED",
          source_record_count: null,
        }),
      ),
    ).toBe(true);
  });
  it("distinguishes frozen issuer identities and rejects contradictory evidence", () => {
    for (const status of ["MATCHED", "CHANGED", "CURRENT_UNAVAILABLE"]) {
      expect(
        isCompanySecCoverage(
          withRefresh({
            ...refresh,
            identity: { status, frozen_cik: "0000000001" },
          }),
        ),
      ).toBe(true);
      expect(
        isCompanySecCoverage(
          withRefresh({ ...refresh, identity: { status, frozen_cik: null } }),
        ),
      ).toBe(false);
    }
    for (const status of ["UNMAPPED_IN_SCOPE", "UNVERIFIED"]) {
      expect(
        isCompanySecCoverage(
          withRefresh({ ...refresh, identity: { status, frozen_cik: null } }),
        ),
      ).toBe(true);
      expect(
        isCompanySecCoverage(
          withRefresh({
            ...refresh,
            identity: { status, frozen_cik: "0000000001" },
          }),
        ),
      ).toBe(false);
    }
    expect(
      isCompanySecCoverage(
        withRefresh({
          ...refresh,
          identity: { status: "MATCHED", frozen_cik: "bad" },
        }),
      ),
    ).toBe(false);
  });
  it("warns when a refresh belongs to a different reviewed issuer identity", () => {
    const changed = {
      ...refresh,
      identity: { status: "CHANGED" as const, frozen_cik: "0000000002" },
    };
    coverageState.data = {
      ...data,
      fundamentals: { ...data.fundamentals, refresh: changed },
    };
    const panel = renderToStaticMarkup(
      <CompanySecCoveragePanel companyId={id} />,
    );
    expect(panel).toContain(
      "Issuer mapping or recorded issuer details changed since this refresh",
    );
    const detail = renderToStaticMarkup(
      <SecCoverageDetails data={coverageState.data} />,
    );
    expect(detail).toContain("Frozen refresh CIK 0000000002");
    expect(detail).toContain(
      "historical, not evidence for the current identity",
    );
  });
  it("keeps older API refreshes explicitly unverified", () => {
    coverageState.data = {
      ...data,
      fundamentals: { ...data.fundamentals, refresh },
    };
    expect(
      renderToStaticMarkup(<CompanySecCoveragePanel companyId={id} />),
    ).toContain("issuer identity could not be verified");
    const matched = {
      ...refresh,
      identity: { status: "MATCHED" as const, frozen_cik: "0000000001" },
    };
    expect(
      renderToStaticMarkup(
        <SecCoverageDetails
          data={{
            ...data,
            fundamentals: { ...data.fundamentals, refresh: matched },
          }}
        />,
      ),
    ).toContain("freshness is separate");
  });
  it.each([
    { ...refresh, scope_company_count: 0 },
    { ...refresh, mapped_company_count: 4 },
    { ...refresh, attempt_count: 4 },
    { ...refresh, batch_status: "ACCEPTED" },
    { ...refresh, issuer_outcome: "NOT_REPORTED" },
    { ...refresh, issuer_outcome: "UNAVAILABLE", source_record_count: null },
    { ...refresh, source_record_count: true },
    { ...refresh, request_id: "invalid" },
    { ...refresh, finished_at: "invalid" },
  ])(
    "rejects invalid refresh fields or unsupported attribution %#",
    (value) => {
      expect(isCompanySecCoverage(withRefresh(value))).toBe(false);
    },
  );
  it("labels issuer evidence separately from batch partials and bootstrap history", () => {
    const html = renderToStaticMarkup(
      <SecCoverageDetails
        data={{ ...data, fundamentals: { ...data.fundamentals, refresh } }}
      />,
    );
    expect(html).toContain("Source response reported");
    expect(html).toContain("Source facts in result");
    expect(html).toContain("3 companies in frozen scope");
    expect(html).toContain("2 mapped SEC issuers");
    expect(html).toContain("Latest incremental refresh");
    expect(html).toContain("Latest bootstrap checkpoint");
  });
  it("keeps rolled-back and unattributed results missing beside retained evidence", () => {
    const html = renderToStaticMarkup(
      <SecCoverageDetails
        data={{
          ...data,
          fundamentals: {
            ...data.fundamentals,
            refresh: {
              ...refresh,
              batch_status: "FAILED",
              issuer_outcome: "NOT_REPORTED",
              source_record_count: null,
              failure_code: "NETWORK_ERROR",
              retryable: true,
            },
          },
        }}
      />,
    );
    expect(html).toContain("No issuer-specific result recorded");
    expect(html).toContain("Retained records");
    expect(html).toContain("NETWORK_ERROR");
    expect(html).toContain("Last recorded attempt is retryable");
    expect(html).not.toContain("Source facts in result");
  });
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
  it("validates exhaustive recorded CIK counts and warns about retained facts", () => {
    const counts = { matching_cik: 0, other_cik: 1, unverified: 0 };
    const withCounts = { ...data, fundamental_identity_counts: counts };
    expect(isCompanySecCoverage(withCounts)).toBe(true);
    expect(
      isCompanySecCoverage({
        ...data,
        fundamental_identity_counts: { ...counts, other_cik: 2 },
      }),
    ).toBe(false);
    expect(
      isCompanySecCoverage({
        ...data,
        fundamental_identity_counts: { ...counts, unverified: -1 },
      }),
    ).toBe(false);
    coverageState.data = withCounts;
    const panel = renderToStaticMarkup(
      <CompanySecCoveragePanel companyId={id} />,
    );
    expect(panel).toContain("Financial statements may include them");
    const details = renderToStaticMarkup(
      <SecCoverageDetails data={withCounts} />,
    );
    expect(details).toContain("Recorded issuer CIK on retained facts");
    expect(details).toContain("They do not verify source bytes");
  });
  it("does not imply attribution is checked when coverage is absent or from an older API", () => {
    coverageState.data = null;
    expect(
      renderToStaticMarkup(<CompanySecCoveragePanel companyId={id} />),
    ).toContain("Retained issuer attribution has not been checked");
    coverageState.data = data;
    expect(
      renderToStaticMarkup(<CompanySecCoveragePanel companyId={id} />),
    ).toContain("This API version does not report retained issuer attribution");
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
