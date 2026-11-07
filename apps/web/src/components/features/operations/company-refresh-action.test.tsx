import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GET, POST } from "@/app/api/research/[...path]/route";
import {
  isCompanyRefreshOptions,
  type CompanyRefreshOptions,
} from "@/lib/domain-contracts";
import { CompanyRefreshAction } from "./company-refresh-action";

const state = vi.hoisted(() => ({
  data: undefined as CompanyRefreshOptions | undefined,
  error: undefined as string | undefined,
  retry: () => {},
}));
vi.mock("@/hooks/use-research", () => ({ useResearch: () => state }));
const id = "11111111-1111-4111-8111-111111111111";
const held: CompanyRefreshOptions = {
  company_id: id,
  company_name: "Synthetic held issuer",
  lifecycle: null,
  eligible_job_names: ["SEC_FUNDAMENTALS", "SEC_FILINGS"],
  sec_eligibility_basis: "VERIFIED_HOLDING",
  sec_unavailable_reason: null,
  portfolio_id: id,
  holding_snapshot_id: id,
  execution_mode: "OPERATOR",
};
beforeEach(() => {
  state.data = held;
  state.error = undefined;
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

it("accepts held admission with exact snapshot proof independently of lifecycle", () => {
  for (const lifecycle of [null, "CANDIDATE", "DROP"])
    expect(isCompanyRefreshOptions({ ...held, lifecycle })).toBe(true);
});
it.each([
  { holding_snapshot_id: null },
  { portfolio_id: null },
  { eligible_job_names: ["COMPANY_REFRESH", "SEC_FILINGS"] },
  { eligible_job_names: ["SEC_FILINGS", "SEC_FILINGS"] },
  { sec_eligibility_basis: "ACTIVE_LIFECYCLE" },
  { execution_mode: "UNKNOWN" },
  { sec_eligibility_basis: null },
])("rejects inconsistent eligibility %j", (change) => {
  expect(isCompanyRefreshOptions({ ...held, ...change })).toBe(false);
});
it("shows scoped controls for a held company without inventing lifecycle", () => {
  const html = renderToStaticMarkup(<CompanyRefreshAction companyId={id} />);
  expect(html).toContain("Refresh SEC fundamentals");
  expect(html).toContain("Refresh SEC filings");
  expect(html).toContain("operator-run one-shot");
  expect(html).not.toContain("Refresh this company");
  expect(html).not.toContain('disabled=""');
});
it("preserves broad active-lifecycle action while Operations stays SEC scoped", () => {
  state.data = {
    ...held,
    lifecycle: "WATCHLIST",
    portfolio_id: null,
    holding_snapshot_id: null,
    sec_eligibility_basis: "ACTIVE_LIFECYCLE",
    eligible_job_names: ["COMPANY_REFRESH", "SEC_FUNDAMENTALS", "SEC_FILINGS"],
  };
  expect(isCompanyRefreshOptions(state.data)).toBe(true);
  expect(
    renderToStaticMarkup(<CompanyRefreshAction companyId={id} />),
  ).toContain("Refresh this company");
  expect(
    renderToStaticMarkup(<CompanyRefreshAction companyId={id} secOnly />),
  ).not.toContain("Refresh this company");
});
it("keeps disabled execution and missing eligibility fail-closed", () => {
  state.data = { ...held, execution_mode: "DISABLED" };
  let html = renderToStaticMarkup(<CompanyRefreshAction companyId={id} />);
  expect(html.match(/disabled=""/g)).toHaveLength(2);
  expect(html).toContain("operations are disabled");
  state.data = undefined;
  state.error = "Refresh eligibility failed.";
  html = renderToStaticMarkup(<CompanyRefreshAction companyId={id} />);
  expect(html.match(/disabled=""/g)).toHaveLength(2);
  expect(html).toContain("Retry refresh eligibility");
  state.data = { ...held, company_id: "22222222-2222-4222-8222-222222222222" };
  expect(
    renderToStaticMarkup(<CompanyRefreshAction companyId={id} />).match(
      /disabled=""/g,
    ),
  ).toHaveLength(2);
});
it("shows the backend's missing-holding reason", () => {
  state.data = {
    ...held,
    eligible_job_names: [],
    sec_eligibility_basis: null,
    portfolio_id: null,
    holding_snapshot_id: null,
    sec_unavailable_reason:
      "No positive verified holding supports SEC refresh.",
  };
  expect(isCompanyRefreshOptions(state.data)).toBe(true);
  const html = renderToStaticMarkup(<CompanyRefreshAction companyId={id} />);
  expect(html).toContain("No positive verified holding");
  expect(html.match(/disabled=""/g)).toHaveLength(2);
});
it("proxies eligibility only as a verified read", async () => {
  const mock = vi.fn().mockResolvedValue(Response.json(held));
  vi.stubGlobal("fetch", mock);
  const path = ["companies", id, "refresh-options"];
  const context = { params: Promise.resolve({ path }) };
  const url = `http://localhost/api/research/${path.join("/")}`;
  expect((await GET(new Request(url), context)).status).toBe(200);
  expect(
    (await POST(new Request(url, { method: "POST", body: "{}" }), context))
      .status,
  ).toBe(404);
  expect(mock).toHaveBeenCalledTimes(1);
  mock.mockResolvedValue(Response.json({ ...held, holding_snapshot_id: null }));
  expect((await GET(new Request(url), context)).status).toBe(503);
});
