import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  isCompanyFinancialStatements,
  isCompanyConsensusEstimates,
} from "../src/lib/domain-contracts";
import { quantity } from "../src/lib/display";

test.skip(
  process.env.E2E_REAL_CONSENSUS_API !== "1" ||
    process.env.E2E_MANAGED_PRODUCTION_SERVER === "1",
  "Requires an isolated API with reviewed private analyst-source recordings.",
);
// Authentic source values, traces and screenshots must not become public artifacts.
test.use({ trace: "off", screenshot: "off", video: "off" });

type Sample = {
  metric: "REVENUE" | "EPS";
  period_type: "ANNUAL" | "QUARTERLY";
  period_end: string;
  value: string;
  low_value: string | null;
  high_value: string | null;
  analyst_count: number | null;
  currency: string;
  unit: string;
  data_quality: "PASS" | "DATA_CHECK";
};
type Metadata = {
  scenario: string;
  schema: string;
  company_id: string;
  captured_at: string;
  expected: { observations: number; samples: Sample[] };
  protected_state_sha256: string;
};
function decimal(value: string | null) {
  return value?.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "") ?? null;
}
function escaped(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test("private captured analyst estimates reach Financials with source ranges and explicit EPS limits", async ({
  page,
  request,
}, info) => {
  test.setTimeout(120_000);
  const apiPort = process.env.BROWSER_API_PORT ?? "";
  if (
    !/^\d{4,5}$/.test(apiPort) ||
    Number(apiPort) < 1024 ||
    Number(apiPort) > 65535
  )
    throw new Error("Expected a bounded loopback fixture port");
  const api = `http://127.0.0.1:${apiPort}`;
  expect(process.env.API_BASE_URL).toBe(api);
  expect(new URL(String(info.project.use.baseURL)).hostname).toBe("127.0.0.1");
  const directory = process.env.CONSENSUS_ARTIFACT_DIR;
  if (
    !directory ||
    !path.isAbsolute(directory) ||
    !path.relative(path.resolve("../.."), directory).startsWith("..")
  )
    throw new Error(
      "An absolute private artifact directory outside the repository is required",
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
  expect(before.scenario).toBe("real-consensus");
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  expect(before.expected.observations).toBeGreaterThan(0);
  const errors: string[] = [],
    writes: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (r) => {
    if (r.url().includes("/api/research/") && r.method() !== "GET")
      writes.push(new URL(r.url()).pathname);
  });
  await page.goto(`/company/${before.company_id}?view=financials`);
  await page.getByLabel("Appearance").selectOption("light");
  await expect(
    page.getByText("EODHD demo · private evaluation.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/EPS accounting basis is unresolved/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Financial development", exact: true }),
  ).toBeVisible();
  const consensusResponse = await request.get(
    `${api}/v1/companies/${before.company_id}/consensus-estimates`,
  );
  const consensus: unknown = await consensusResponse.json();
  expect(isCompanyConsensusEstimates(consensus)).toBe(true);
  if (!isCompanyConsensusEstimates(consensus))
    throw new Error("Consensus contract failed");
  expect(consensus.selected_provider_id).toBe("eodhd_demo_estimates");
  const provider = consensus.providers.find((item) => item.selected);
  expect(provider?.observation_count).toBe(before.expected.observations);
  expect(provider?.currency).toBe("USD");
  const readbacks: unknown[] = [];
  for (const periodType of ["ANNUAL", "QUARTERLY"] as const) {
    await page
      .getByRole("group", { name: "Financial period type" })
      .getByRole("button", {
        name: periodType === "ANNUAL" ? "Annual" : "Quarterly",
        exact: true,
      })
      .click();
    const response = await request.get(
      `${api}/v1/companies/${before.company_id}/financial-statements?period_type=${periodType}&period_limit=10`,
    );
    const financials: unknown = await response.json();
    expect(isCompanyFinancialStatements(financials)).toBe(true);
    if (!isCompanyFinancialStatements(financials))
      throw new Error("Financial statement contract failed");
    readbacks.push(financials);
    await page.getByRole("button", { name: "Estimates", exact: true }).click();
    for (const sample of before.expected.samples.filter(
      (item) => item.period_type === periodType,
    )) {
      const sourcePeriod = provider?.periods.find(
        (item) =>
          item.metric === sample.metric &&
          item.period_type === sample.period_type &&
          item.period_end === sample.period_end,
      );
      const source = sourcePeriod?.current_observation;
      expect(decimal(source?.value ?? null)).toBe(decimal(sample.value));
      expect(decimal(source?.low_value ?? null)).toBe(
        decimal(sample.low_value),
      );
      expect(decimal(source?.high_value ?? null)).toBe(
        decimal(sample.high_value),
      );
      expect(source?.analyst_count).toBe(sample.analyst_count);
      expect(source?.currency).toBe(sample.currency);
      expect(sample.unit).toBe(
        sample.metric === "REVENUE" ? "currency" : "currency/share",
      );
      expect(source?.unit).toBe(
        sample.metric === "REVENUE" ? "CURRENCY" : "CURRENCY_PER_SHARE",
      );
      expect(source?.data_quality).toBe(sample.data_quality);
      expect(sourcePeriod?.history).toHaveLength(1);
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
        throw new Error("Expected forecast alignment absent");
      expect(decimal(cell.value)).toBe(decimal(sample.value));
      expect(cell.status).toBe(
        sample.metric === "EPS" ? "DATA_CHECK" : "AVAILABLE",
      );
      const cellButton = page.getByRole("button", {
        name: new RegExp(`^${escaped(row.label)}, ${escaped(column.label)},`),
      });
      await expect(cellButton).toHaveAccessibleName(
        new RegExp(escaped(quantity(sample.value))),
      );
      if (sample.metric === "EPS")
        await expect(
          page.getByRole("checkbox", { name: /^Chart EPS/ }),
        ).toBeDisabled();
      if (sample.metric === "REVENUE") {
        await cellButton.click();
        const drawer = page.getByRole("dialog");
        await expect(drawer).toBeVisible();
        await expect(
          drawer.getByText(
            new RegExp(
              `Analyst range: ${escaped(quantity(sample.low_value))} – ${escaped(quantity(sample.high_value))} USD`,
            ),
          ),
        ).toBeVisible();
        await expect(
          drawer.getByText(
            new RegExp(`${sample.analyst_count} analysts · snapshot`),
          ),
        ).toBeVisible();
        await expect(
          drawer.getByRole("link", { name: /Consensus source/ }),
        ).toBeVisible();
        await page.screenshot({
          path: artifact(`${periodType.toLowerCase()}-source.png`),
          fullPage: true,
          animations: "disabled",
          scale: "css",
        });
        await drawer.getByRole("button", { name: "Close details" }).click();
      }
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    for (const theme of ["light", "dark"] as const) {
      await page.getByLabel("Appearance").selectOption(theme);
      await page.screenshot({
        path: artifact(`${periodType.toLowerCase()}-${theme}.png`),
        fullPage: true,
        animations: "disabled",
        scale: "css",
      });
    }
  }
  const prior = new Date(Date.parse(before.captured_at) - 86400000)
    .toISOString()
    .slice(0, 10);
  await page.getByLabel("App knowledge cutoff").fill(prior);
  await expect(
    page.getByRole("heading", {
      name: "No aligned financial periods",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Financial development", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Sources & alignment", exact: true })
    .click();
  await expect(
    page
      .getByRole("dialog")
      .getByText("No consensus provider mapping.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Close details" })
    .click();
  await page.getByRole("button", { name: "Latest known", exact: true }).click();
  await page.reload();
  await expect(
    page.getByText("EODHD demo · private evaluation.", { exact: true }),
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
        consensus,
        financials: readbacks,
        production: false,
        source: "recorded provider response; not fixture estimate values",
      },
      null,
      2,
    ),
  );
});
