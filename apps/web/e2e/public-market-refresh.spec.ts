import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  isOverview,
  isListingMarketDataList,
} from "../src/lib/domain-contracts";
import { formatCurrency } from "../src/lib/display";

test.skip(
  process.env.E2E_PUBLIC_MARKET_REFRESH_API !== "1" ||
    process.env.E2E_MANAGED_PRODUCTION_SERVER === "1",
  "Requires a fresh isolated public-market API and reviewed private real-source recordings.",
);
// Demo source content and screenshots must stay private; no trace uploads.
test.use({ trace: "off", screenshot: "off", video: "off" });

type Metadata = {
  scenario: string;
  schema: string;
  company_id: string;
  listing_id: string;
  portfolio_id: string;
  provider_fixture: string;
  counts: Record<string, number>;
  offline_transport_calls: number;
  protected_state_sha256: string;
  worker_errors: string[];
  expected: {
    initial_prices: number;
    initial_fx: number;
    final_prices: number;
    final_fx: number;
    price: string;
    portfolio_eur: string;
    position_eur: string;
  };
};
function decimal(value: string) {
  return value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

test("recorded official FX and demo prices refresh into native charts and EUR valuation", async ({
  page,
  request,
}, info) => {
  test.setTimeout(120_000);
  const api = `http://127.0.0.1:${process.env.BROWSER_API_PORT}`;
  expect(process.env.API_BASE_URL).toBe(api);
  expect(new URL(String(info.project.use.baseURL)).hostname).toBe("127.0.0.1");
  const privateRoot = process.env.PUBLIC_MARKET_ARTIFACT_DIR;
  if (
    !privateRoot ||
    !path.isAbsolute(privateRoot) ||
    !path.relative(path.resolve("../.."), privateRoot).startsWith("..")
  )
    throw new Error(
      "An absolute private artifact directory outside the repository is required",
    );
  await mkdir(privateRoot, { recursive: true });
  const artifact = (name: string) =>
    path.join(privateRoot, `${info.project.name}-${name}`);
  const read = async (): Promise<Metadata> => {
    const response = await request.get(`${api}/__test/fixture`);
    expect(response.status()).toBe(200);
    return response.json();
  };
  const control = async (
    paused: boolean,
    phase = "initial",
    scheduled = false,
  ) => {
    const response = await request.post(`${api}/__test/refresh-control`, {
      data: { paused, phase, scheduled },
    });
    expect(response.status()).toBe(200);
    return response.json() as Promise<Metadata>;
  };
  const before = await read();
  expect(before.scenario).toBe("public-market-refresh");
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  expect(before.provider_fixture).toBe("recorded-real-public-market-v1");
  expect(before.counts.price_observations).toBe(0);
  expect(before.counts.fx_observations).toBe(0);
  const errors: string[] = [];
  const writes: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (r) => {
    if (r.url().includes("/api/research/") && r.method() !== "GET")
      writes.push(new URL(r.url()).pathname);
  });
  await page.goto("/operations#manual-refresh");
  await page.getByLabel("Appearance").selectOption("light");
  const accepted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/operations/job-requests") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Market prices and FX", exact: true })
    .click();
  const acceptedResponse = await accepted;
  expect(acceptedResponse.status()).toBe(202);
  const job = await acceptedResponse.json();
  expect(job.job_name).toBe("MARKET_AND_FX");
  expect(job.scope_kind).toBe("ACTIVE_UNIVERSE");
  expect(job.status).toBe("QUEUED");
  expect((await read()).offline_transport_calls).toBe(0);
  await page.goto(`/company/${before.company_id}?view=history`);
  await page.goto("/operations#manual-refresh");
  await page.reload();
  const manual = page.getByRole("region", {
    name: "Manual refresh",
    exact: true,
  });
  await expect(
    manual.getByText("QUEUED", { exact: true }).first(),
  ).toBeVisible();
  await control(false);
  await expect
    .poll(
      async () => {
        const response = await request.get(
          `${api}/v1/operations/job-requests/${job.id}`,
        );
        return (await response.json()).status;
      },
      { timeout: 45000 },
    )
    .toMatch(/^(SUCCEEDED|PARTIAL)$/);
  await expect(manual.getByText(/^(SUCCEEDED|PARTIAL)$/).first()).toBeVisible();
  const initial = await read();
  expect(initial.counts.price_observations).toBe(
    before.expected.initial_prices,
  );
  expect(initial.counts.fx_observations).toBe(before.expected.initial_fx);
  expect(initial.offline_transport_calls).toBe(4);
  expect(initial.protected_state_sha256).toBe(before.protected_state_sha256);
  await control(true);
  await page.goto(`/company/${before.company_id}?view=history`);
  await expect(
    page.getByRole("img", { name: "Exact-listing price history for AMZN" }),
  ).toBeVisible();
  await expect(
    page.getByText(/EODHD test-drive data is indicative/),
  ).toBeVisible();
  await expect(page.getByText(/Unadjusted native close/).first()).toBeVisible();
  await expect(
    page.getByText(/This chart is not a comparable return series/),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: artifact("native-history-light.png"),
    fullPage: true,
    animations: "disabled",
    scale: "css",
  });
  await page.getByLabel("Appearance").selectOption("dark");
  await page.screenshot({
    path: artifact("native-history-dark.png"),
    fullPage: true,
    animations: "disabled",
    scale: "css",
  });
  const stale = await (
    await request.get(`${api}/v1/portfolios/${before.portfolio_id}/overview`)
  ).json();
  expect(stale.base_market_value).toBeNull();
  const scheduled = await control(true, "incremental", true);
  expect(scheduled.counts.price_observations).toBe(
    before.expected.final_prices,
  );
  expect(scheduled.counts.fx_observations).toBe(before.expected.final_fx);
  expect(scheduled.offline_transport_calls).toBe(8);
  const market = await (
    await request.get(
      `${api}/v1/companies/${before.company_id}/market-data?history_limit=252`,
    )
  ).json();
  expect(isListingMarketDataList(market)).toBe(true);
  if (!isListingMarketDataList(market))
    throw new Error("Market contract failed");
  expect(market[0].native_freshness).toBe("FRESH");
  expect(market[0].history).toHaveLength(0);
  expect(market[0].latest?.split_adjusted_close).toBeNull();
  expect(decimal(market[0].latest?.native_close ?? "")).toBe(
    decimal(before.expected.price),
  );
  const overview = await (
    await request.get(`${api}/v1/portfolios/${before.portfolio_id}/overview`)
  ).json();
  expect(isOverview(overview)).toBe(true);
  if (!isOverview(overview)) throw new Error("Portfolio contract failed");
  expect(decimal(overview.base_market_value ?? "")).toBe(
    decimal(before.expected.portfolio_eur),
  );
  expect(
    decimal(overview.companies[0].positions[0].base_market_value ?? ""),
  ).toBe(decimal(before.expected.position_eur));
  expect(overview.valuation_status).toBe("VALUED");
  expect(overview.cash_valuations).toHaveLength(3);
  expect(
    overview.cash_valuations.every(
      (c) => c.valuation_status === "VALUED" && c.portfolio_weight !== null,
    ),
  ).toBe(true);
  expect(overview.companies[0].positions[0].portfolio_weight).not.toBeNull();
  await page.goto("/portfolio#portfolio-holdings");
  await expect(
    page
      .getByText(formatCurrency(before.expected.portfolio_eur, "EUR", 2), {
        exact: true,
      })
      .first(),
  ).toBeVisible();
  await expect(
    page
      .getByText(/Indicative test-drive data/)
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  await expect(
    page
      .getByText("Unadjusted native close", { exact: false })
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: artifact("portfolio-dark.png"),
    fullPage: true,
    animations: "disabled",
    scale: "css",
  });
  await page.getByLabel("Appearance").selectOption("light");
  await page.screenshot({
    path: artifact("portfolio-light.png"),
    fullPage: true,
    animations: "disabled",
    scale: "css",
  });
  const repeated = await control(true, "incremental", true);
  expect(repeated.counts).toEqual(scheduled.counts);
  expect(repeated.offline_transport_calls).toBe(
    scheduled.offline_transport_calls,
  );
  expect(repeated.protected_state_sha256).toBe(before.protected_state_sha256);
  expect(repeated.worker_errors).toEqual([]);
  expect(errors).toEqual([]);
  expect(writes).toEqual(["/api/research/operations/job-requests"]);
  await writeFile(
    artifact("readback.json"),
    JSON.stringify(
      {
        before,
        initial,
        scheduled,
        repeated,
        overview,
        market,
        production: false,
        fictional_quantities: true,
      },
      null,
      2,
    ),
  );
});
