import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  isCompanyConsensusEstimates,
  isCompanyFinancialStatements,
  isCompanySourceDocuments,
  isListingMarketDataList,
  isOverview,
} from "../src/lib/domain-contracts";
import { formatCurrency, quantity } from "../src/lib/display";

test.skip(
  process.env.E2E_INTEGRATED_REAL_SOURCES_API !== "1" ||
    process.env.E2E_MANAGED_PRODUCTION_SERVER === "1",
  "Requires the isolated combined API and reviewed private source recordings.",
);
test.use({ trace: "off", screenshot: "off", video: "off" });

type Sample = {
  metric: string;
  period_type: "ANNUAL" | "QUARTERLY";
  period_end: string;
  value: string;
  source_url?: string;
  accession_number?: string;
};
type Metadata = {
  scenario: string;
  schema: string;
  company_id: string;
  listing_id: string;
  portfolio_id: string;
  protected_state_sha256: string;
  market: {
    expected: { final_prices: number; final_fx: number; portfolio_eur: string };
    readback: { counts: Record<string, number> };
  };
  estimates: {
    company_id: string;
    expected: { observations: number; samples: Sample[] };
  };
  sec: {
    company_id: string;
    issuer: { name: string; ticker: string; cik: string };
    expected: {
      fundamental_observations: number;
      source_documents: number;
      statement_samples: Sample[];
    };
    readback: { counts: Record<string, number> };
  };
};
const decimal = (value: string | null | undefined) =>
  value?.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
const escaped = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

test("portfolio research joins exact prices, expectations and separate SEC evidence without investment writes", async ({
  page,
  request,
}, info) => {
  test.setTimeout(120_000);
  const port = process.env.BROWSER_API_PORT ?? "";
  if (!/^\d{4,5}$/.test(port) || Number(port) < 1024 || Number(port) > 65535)
    throw new Error("Expected a bounded loopback fixture port");
  const api = `http://127.0.0.1:${port}`;
  expect(process.env.API_BASE_URL).toBe(api);
  expect(new URL(String(info.project.use.baseURL)).hostname).toBe("127.0.0.1");
  const directory = process.env.INTEGRATED_SOURCE_ARTIFACT_DIR;
  if (
    !directory ||
    !path.isAbsolute(directory) ||
    !path.relative(path.resolve("../.."), directory).startsWith("..")
  )
    throw new Error(
      "A private artifact directory outside the repository is required",
    );
  await mkdir(directory, { recursive: true });
  const artifact = (name: string) =>
    path.join(directory, `${info.project.name}-${name}`);
  const read = async (): Promise<Metadata> => {
    const response = await request.get(`${api}/__test/fixture`);
    expect(response.status()).toBe(200);
    return response.json();
  };
  const before = await read();
  expect(before.scenario).toBe("integrated-real-sources");
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  expect(before.estimates.company_id).toBe(before.company_id);
  expect(before.sec.company_id).not.toBe(before.company_id);
  expect(before.market.readback.counts.price_observations).toBe(
    before.market.expected.final_prices,
  );
  expect(before.market.readback.counts.fx_observations).toBe(
    before.market.expected.final_fx,
  );
  expect(before.sec.readback.counts.reported_fundamental_observations).toBe(
    before.sec.expected.fundamental_observations,
  );
  expect(before.sec.readback.counts.source_documents).toBe(
    before.sec.expected.source_documents,
  );
  const writes: string[] = [],
    errors: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/research/") && r.method() !== "GET")
      writes.push(new URL(r.url()).pathname);
  });
  page.on("pageerror", (error) => errors.push(error.message));
  const capture = async (name: string) => {
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    for (const theme of ["light", "dark"] as const) {
      await page.getByLabel("Appearance").selectOption(theme);
      await page.screenshot({
        path: artifact(`${name}-${theme}.png`),
        fullPage: true,
        animations: "disabled",
        scale: "css",
      });
    }
  };
  const overview: unknown = await (
    await request.get(`${api}/v1/portfolios/${before.portfolio_id}/overview`)
  ).json();
  if (!isOverview(overview)) throw new Error("Portfolio contract failed");
  expect(overview.valuation_status).toBe("VALUED");
  expect(decimal(overview.base_market_value)).toBe(
    decimal(before.market.expected.portfolio_eur),
  );
  await page.goto("/portfolio");
  await expect(
    page
      .getByText(formatCurrency(overview.base_market_value, "EUR"), {
        exact: true,
      })
      .first(),
  ).toBeVisible();
  await capture("portfolio");
  await page
    .getByRole("region", { name: "Holdings", exact: true })
    .locator(`a[href^="/company/${before.company_id}"]`)
    .filter({ visible: true })
    .first()
    .click();
  await expect(page).toHaveURL(new RegExp(`/company/${before.company_id}\\?`));
  expect(new URL(page.url()).searchParams.get("listing")).toBe(
    before.listing_id,
  );
  expect(new URL(page.url()).searchParams.get("from")).toBe("portfolio");
  await page
    .getByRole("tab", { name: "Prices & history", exact: true })
    .click();
  await expect(
    page.getByRole("img", { name: "Exact-listing price history for AMZN" }),
  ).toBeVisible();
  await expect(
    page.getByText(/EODHD test-drive data is indicative/),
  ).toBeVisible();
  await expect(
    page.getByText(/This chart is not a comparable return series/),
  ).toBeVisible();
  const market: unknown = await (
    await request.get(
      `${api}/v1/companies/${before.company_id}/market-data?history_limit=252`,
    )
  ).json();
  if (!isListingMarketDataList(market))
    throw new Error("Market contract failed");
  expect(market[0].listing.id).toBe(before.listing_id);
  expect(market[0].latest?.split_adjusted_close).toBeNull();
  expect(market[0].native_history?.length).toBeGreaterThan(1);
  await capture("amazon-prices");
  await page.getByRole("tab", { name: "Financials", exact: true }).click();
  await expect(
    page.getByText("EODHD demo · private evaluation.", { exact: true }),
  ).toBeVisible();
  const consensus: unknown = await (
    await request.get(
      `${api}/v1/companies/${before.company_id}/consensus-estimates`,
    )
  ).json();
  if (!isCompanyConsensusEstimates(consensus))
    throw new Error("Consensus contract failed");
  expect(
    consensus.providers.find((item) => item.selected)?.observation_count,
  ).toBe(before.estimates.expected.observations);
  const financialReadbacks: unknown[] = [];
  for (const periodType of ["ANNUAL", "QUARTERLY"] as const) {
    await page
      .getByRole("group", { name: "Financial period type" })
      .getByRole("button", {
        name: periodType === "ANNUAL" ? "Annual" : "Quarterly",
        exact: true,
      })
      .click();
    await page.getByRole("button", { name: "Estimates", exact: true }).click();
    const financials: unknown = await (
      await request.get(
        `${api}/v1/companies/${before.company_id}/financial-statements?period_type=${periodType}&period_limit=10`,
      )
    ).json();
    if (!isCompanyFinancialStatements(financials))
      throw new Error("Estimate financials contract failed");
    financialReadbacks.push(financials);
    for (const sample of before.estimates.expected.samples.filter(
      (item) => item.period_type === periodType,
    )) {
      const row = financials.rows.find(
        (item) =>
          item.metric === sample.metric && item.source_kind === "CONSENSUS",
      );
      const column = financials.periods.find(
        (item) => item.period_end === sample.period_end,
      );
      const cell = row?.cells.find(
        (item) => item.period_end === sample.period_end,
      );
      if (!row || !column || !cell)
        throw new Error("Recorded estimate alignment missing");
      expect(decimal(cell.value)).toBe(decimal(sample.value));
      expect(cell.status).toBe(
        sample.metric === "EPS" ? "DATA_CHECK" : "AVAILABLE",
      );
      await expect(
        page.getByRole("button", {
          name: new RegExp(`^${escaped(row.label)}, ${escaped(column.label)},`),
        }),
      ).toHaveAccessibleName(new RegExp(escaped(quantity(sample.value))));
    }
    await expect(
      page.getByRole("checkbox", { name: /^Chart EPS/ }),
    ).toBeDisabled();
    await capture(`amazon-estimates-${periodType.toLowerCase()}`);
  }
  await page.getByRole("tab", { name: "Valuation", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "No valuation is available",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Return hurdle explorer" }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "← Back to holdings" }).click();
  await expect(page).toHaveURL(/\/portfolio#portfolio-holdings$/);
  await page
    .getByRole("combobox", { name: "Search companies and listings" })
    .fill(before.sec.issuer.ticker);
  await page
    .getByRole("option", { name: new RegExp(escaped(before.sec.issuer.name)) })
    .click();
  await expect(page).toHaveURL(new RegExp(`/company/${before.sec.company_id}`));
  await page.getByRole("tab", { name: "Financials", exact: true }).click();
  for (const periodType of ["ANNUAL", "QUARTERLY"] as const) {
    await page
      .getByRole("group", { name: "Financial period type" })
      .getByRole("button", {
        name: periodType === "ANNUAL" ? "Annual" : "Quarterly",
        exact: true,
      })
      .click();
    const financials: unknown = await (
      await request.get(
        `${api}/v1/companies/${before.sec.company_id}/financial-statements?period_type=${periodType}&period_limit=16`,
      )
    ).json();
    if (!isCompanyFinancialStatements(financials))
      throw new Error("SEC financials contract failed");
    financialReadbacks.push(financials);
    const sample = before.sec.expected.statement_samples.find(
      (item) => item.metric === "REVENUE" && item.period_type === periodType,
    );
    const row = financials.rows.find(
      (item) =>
        item.metric === "REVENUE" && item.source_kind === "REPORTED_ACTUAL",
    );
    const column = financials.periods.find(
      (item) => item.period_end === sample?.period_end,
    );
    const cell = row?.cells.find(
      (item) => item.period_end === sample?.period_end,
    );
    if (!sample || !row || !column || !cell)
      throw new Error("Verified SEC sample missing");
    expect(decimal(cell.value)).toBe(decimal(sample.value));
    await page
      .getByRole("button", { name: "Income Statement", exact: true })
      .click();
    const button = page.getByRole("button", {
      name: new RegExp(`^${escaped(row.label)}, ${escaped(column.label)},`),
    });
    await expect(button).toHaveAccessibleName(
      new RegExp(escaped(quantity(sample.value))),
    );
    await capture(`sec-financials-${periodType.toLowerCase()}`);
    await button.click();
    const drawer = page.getByRole("dialog");
    const selected = drawer
      .locator("article")
      .filter({ hasText: "Selected source" });
    await expect(
      selected.getByText(sample.accession_number!, { exact: true }),
    ).toBeVisible();
    await expect(
      selected.getByRole("link", { name: /Filing \/ original evidence/ }),
    ).toHaveAttribute("href", sample.source_url!);
    await drawer.screenshot({
      path: artifact(`sec-source-${periodType.toLowerCase()}.png`),
      scale: "css",
    });
    await drawer.getByRole("button", { name: "Close details" }).click();
  }
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  const documents: unknown = await (
    await request.get(
      `${api}/v1/companies/${before.sec.company_id}/source-documents`,
    )
  ).json();
  if (!isCompanySourceDocuments(documents))
    throw new Error("Filing evidence contract failed");
  expect(documents.documents.length).toBeGreaterThan(0);
  await expect(
    page.getByRole("heading", {
      name: "Filings & source documents",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Filings & source documents", exact: true })
      .locator("a")
      .filter({ hasText: "Open source" })
      .first(),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Financials", exact: true }).click();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Financial development", exact: true }),
  ).toBeVisible();
  expect((await read()).protected_state_sha256).toBe(
    before.protected_state_sha256,
  );
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  await writeFile(
    artifact("readback.json"),
    JSON.stringify(
      {
        metadata: before,
        overview,
        market,
        consensus,
        financials: financialReadbacks,
        documents,
        production: false,
        fixture_quantities: true,
        source:
          "Privately recorded real provider responses; no new provider requests",
      },
      null,
      2,
    ),
  );
});
