import { expect, test } from "@playwright/test";
import {
  isCompanyFinancialStatements,
  isCompanySecCoverage,
  isCompanySourceDocuments,
} from "../src/lib/domain-contracts";
import { quantity } from "../src/lib/display";

test.skip(
  process.env.E2E_REAL_SEC_REFRESH_API !== "1" ||
    process.env.E2E_MANAGED_PRODUCTION_SERVER === "1",
  "Requires a fresh isolated SEC refresh API with verified private source recordings.",
);

type RealRecordingMetadata = {
  scenario: "sec-real-refresh";
  schema: string;
  company_id: string;
  provider_fixture: "recorded-real-sec-v1";
  recorded_capture_at: string;
  issuer: { name: string; cik: string };
  expected: {
    fundamental_observations: number;
    source_documents: number;
    annual_periods: number;
    sample_fact: {
      metric: string;
      value: string;
      period_end: string;
      accession_number: string;
      source_concept: string;
      source_url: string;
    };
  };
  counts: Record<string, number>;
  provider_request_count: number;
  provider_urls: string[];
  worker_errors: string[];
  protected_state_sha256: string;
  last_cycle: {
    jobs: { job_name: string; operation_status: string }[];
  } | null;
};

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Independently checked against the recorded MSCI CompanyFacts, not API-derived.
const annualRevenue = [
  { year: 2025, value: "3134459000" },
  { year: 2024, value: "2856128000" },
  { year: 2023, value: "2528920000" },
];
function decimalText(value: string | null | undefined) {
  return value?.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

test("recorded real SEC data reaches Financials and source evidence through manual and scheduled refresh", async ({
  page,
  request,
}, info) => {
  test.setTimeout(120_000);
  const port = process.env.BROWSER_API_PORT ?? "8011";
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535)
    throw new Error("Expected a loopback fixture port");
  const api = `http://127.0.0.1:${port}`;
  if (process.env.API_BASE_URL !== api)
    throw new Error("Expected the isolated API target");
  const frontend = new URL(String(info.project.use.baseURL));
  if (
    frontend.protocol !== "http:" ||
    !["127.0.0.1", "localhost", "[::1]"].includes(frontend.hostname)
  )
    throw new Error("The real-recording journey requires a loopback frontend");

  const read = async (): Promise<RealRecordingMetadata> => {
    const response = await request.get(`${api}/__test/fixture`);
    expect(response.status()).toBe(200);
    return response.json();
  };
  const control = async (paused: boolean, scheduledDaysLater?: number) => {
    const response = await request.post(`${api}/__test/refresh-control`, {
      data: {
        paused,
        response: "initial",
        ...(scheduledDaysLater === undefined
          ? {}
          : { scheduled_days_later: scheduledDaysLater }),
      },
    });
    expect(response.status()).toBe(200);
    return (await response.json()) as RealRecordingMetadata;
  };
  const before = await read();
  expect(before.scenario).toBe("sec-real-refresh");
  expect(before.provider_fixture).toBe("recorded-real-sec-v1");
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  expect(before.issuer.cik).toBe("0001408198");
  expect(before.issuer.name).toBe("MSCI Inc.");
  expect(Number.isFinite(Date.parse(before.recorded_capture_at))).toBe(true);
  expect(before.expected.fundamental_observations).toBeGreaterThan(0);
  expect(before.expected.source_documents).toBeGreaterThan(0);
  expect(before.counts.reported_fundamental_observations).toBe(0);
  expect(before.counts.source_documents).toBe(0);
  expect(before.provider_request_count).toBe(0);
  info.annotations.push({
    type: "source",
    description: `${before.issuer.name}, CIK ${before.issuer.cik}: official SEC responses recorded ${before.recorded_capture_at}; replayed offline in a synthetic portfolio, not production or a fresh source fetch.`,
  });
  const writes: string[] = [];
  const pageErrors: string[] = [];
  page.on("request", (response) => {
    if (
      response.url().includes("/api/research/") &&
      response.method() !== "GET"
    )
      writes.push(new URL(response.url()).pathname);
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const company = `/company/${before.company_id}?view=financials`;
  await page.goto(company);
  await page.getByLabel("Appearance").selectOption("light");
  await expect(
    page.getByRole("heading", { name: "No aligned financial periods" }),
  ).toBeVisible();
  await page.getByText("Data & refresh", { exact: true }).click();
  const queued = page.waitForResponse(
    (response) =>
      response.url().endsWith("/operations/job-requests") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Refresh SEC fundamentals", exact: true })
    .click();
  const queuedResponse = await queued;
  expect(queuedResponse.status()).toBe(202);
  const job = await queuedResponse.json();
  expect(job.scope_kind).toBe("COMPANY");
  expect(job.company_id).toBe(before.company_id);
  expect(job.status).toBe("QUEUED");
  expect((await read()).provider_request_count).toBe(0);
  await page.goto("/portfolio");
  await page.goto(company);
  await page.reload();
  await page.getByText("Data & refresh", { exact: true }).click();
  const refreshGroup = page.getByRole("group", {
    name: "Company refresh requests",
  });
  await expect(refreshGroup.getByText("QUEUED", { exact: true })).toBeVisible();
  await refreshGroup
    .getByText("Refresh receipt and source details", { exact: true })
    .click();
  await expect(refreshGroup.getByText(job.id, { exact: true })).toBeVisible();
  await control(false);
  await expect(
    refreshGroup.getByText("PARTIAL", { exact: true }).first(),
  ).toBeVisible({ timeout: 45_000 });
  await expect(refreshGroup.locator("pre")).toBeVisible();
  await expect(refreshGroup.locator("pre")).toContainText(
    "UNMAPPED_STANDARD_CONCEPTS",
  );
  await expect(refreshGroup.locator("pre")).toContainText(
    "standard taxonomy concepts are not mapped to the current canonical fact set",
  );
  await expect(
    refreshGroup.getByText(
      /A completed request does not imply complete financial history/,
    ),
  ).toBeVisible();
  await refreshGroup.screenshot({
    path: info.outputPath("recorded-real-sec-partial-receipt-light.png"),
    scale: "css",
  });
  // Receipt completion refreshes the existing Financials hook without a reload.
  await expect(
    page.getByRole("heading", { name: "No aligned financial periods" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Financial development", exact: true }),
  ).toBeVisible();

  const manual = await read();
  expect(manual.counts.reported_fundamental_observations).toBe(
    before.expected.fundamental_observations,
  );
  expect(manual.provider_request_count).toBe(1);
  expect(manual.protected_state_sha256).toBe(before.protected_state_sha256);
  const financialResponse = await request.get(
    `${api}/v1/companies/${before.company_id}/financial-statements?period_type=ANNUAL&period_limit=10`,
  );
  expect(financialResponse.status()).toBe(200);
  const financials: unknown = await financialResponse.json();
  expect(isCompanyFinancialStatements(financials)).toBe(true);
  if (!isCompanyFinancialStatements(financials))
    throw new Error("Financial statements contract failed");
  expect(financials.periods).toHaveLength(before.expected.annual_periods);
  const sample = before.expected.sample_fact;
  expect(sample.metric).toBe("REVENUE");
  expect(sample.period_end).toBe("2025-12-31");
  expect(decimalText(sample.value)).toBe("3134459000");
  expect(sample.accession_number).toBe("0001408198-26-000011");
  const row = financials.rows.find(
    (item) =>
      item.metric === sample.metric && item.source_kind === "REPORTED_ACTUAL",
  );
  const period = financials.periods.find(
    (item) => item.period_end === sample.period_end,
  );
  const cell = row?.cells.find((item) => item.period_end === sample.period_end);
  expect(cell?.status).toBe("AVAILABLE");
  expect(decimalText(cell?.value)).toBe(decimalText(sample.value));
  for (const expected of annualRevenue) {
    const periodEnd = `${expected.year}-12-31`;
    const fiscalPeriod = financials.periods.find(
      (item) => item.period_end === periodEnd,
    );
    expect(fiscalPeriod?.fiscal_year).toBe(expected.year);
    expect(fiscalPeriod?.label).toBe(`FY${expected.year}`);
    const revenue = financials.rows.find(
      (item) =>
        item.metric === "REVENUE" && item.source_kind === "REPORTED_ACTUAL",
    );
    const annualCell = revenue?.cells.find(
      (item) => item.period_end === periodEnd,
    );
    expect(revenue?.currency).toBe("USD");
    expect(annualCell?.status).toBe("AVAILABLE");
    expect(decimalText(annualCell?.value)).toBe(expected.value);
  }
  const observation = financials.reported_periods
    .flatMap((item) => item.observations)
    .find((item) => item.id === cell?.selected_source_id);
  expect(observation?.accession_number).toBe(sample.accession_number);
  expect(observation?.source_concept).toBe(sample.source_concept);
  expect(observation?.source_url).toBe(sample.source_url);
  if (!row || !period)
    throw new Error("Recorded sample period is not displayed");
  await page.getByText("Data & refresh", { exact: true }).click();
  await page.locator("#reported-fundamentals").scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("recorded-real-sec-financials-light.png"),
    fullPage: true,
    scale: "css",
  });
  await page.getByLabel("Appearance").selectOption("dark");
  await page
    .getByRole("button", {
      name: new RegExp(
        `^${escapeRegex(row.label)}, ${escapeRegex(period.label)},`,
      ),
    })
    .click();
  const source = page.getByRole("dialog", {
    name: `${row.label} · ${sample.period_end}`,
  });
  const selectedSource = source
    .locator("article")
    .filter({ hasText: "Selected source" });
  await expect(selectedSource).toHaveCount(1);
  await expect(
    selectedSource.getByText(sample.accession_number, { exact: true }),
  ).toBeVisible();
  await expect(
    selectedSource.getByText(new RegExp(escapeRegex(sample.source_concept))),
  ).toBeVisible();
  await expect(
    selectedSource.getByText(new RegExp(escapeRegex(quantity(sample.value)))),
  ).toBeVisible();
  await expect(
    selectedSource
      .locator("a")
      .filter({ hasText: "Filing / original evidence" })
      .first(),
  ).toHaveAttribute("href", sample.source_url);
  await selectedSource.scrollIntoViewIfNeeded();
  await source.screenshot({
    path: info.outputPath("recorded-real-sec-source-dark.png"),
    scale: "css",
  });
  await source.getByRole("button", { name: "Close details" }).click();

  const quarterlyResponse = page.waitForResponse(
    (response) =>
      response
        .url()
        .includes(`/companies/${before.company_id}/financial-statements?`) &&
      response.url().includes("period_type=QUARTERLY"),
  );
  await page.getByRole("button", { name: "Quarterly", exact: true }).click();
  const quarterlyResult = await quarterlyResponse;
  expect(quarterlyResult.status()).toBe(200);
  const quarterly: unknown = await quarterlyResult.json();
  if (!isCompanyFinancialStatements(quarterly))
    throw new Error("Quarterly financial statements contract failed");
  const quarter = quarterly.periods.find(
    (period) => period.period_end === "2026-09-30",
  );
  expect(quarter?.label).toBe("FY2026 · Q3");
  const quarterlyRevenue = quarterly.rows.find(
    (item) =>
      item.metric === "REVENUE" && item.source_kind === "REPORTED_ACTUAL",
  );
  const quarterlyCell = quarterlyRevenue?.cells.find(
    (cell) => cell.period_end === "2026-09-30",
  );
  expect(quarterlyRevenue?.currency).toBe("USD");
  expect(quarterlyCell?.status).toBe("AVAILABLE");
  expect(decimalText(quarterlyCell?.value)).toBe("892000000");
  await expect(
    page.getByRole("button", { name: /^Revenue, FY2026 · Q3,/ }),
  ).toBeVisible();
  await page.locator("#reported-fundamentals").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("recorded-real-sec-quarterly-dark.png"),
    fullPage: true,
    scale: "css",
  });
  await page.getByRole("button", { name: /^Revenue, FY2026 · Q3,/ }).click();
  const quarterlySource = page.getByRole("dialog", {
    name: "Revenue · 2026-09-30",
  });
  const selectedQuarterlySource = quarterlySource
    .locator("article")
    .filter({ hasText: "Selected source" });
  await expect(
    selectedQuarterlySource.getByText("0001408198-26-000056", { exact: true }),
  ).toBeVisible();
  await expect(
    selectedQuarterlySource.getByText(
      /RevenueFromContractWithCustomerExcludingAssessedTax/,
    ),
  ).toBeVisible();
  await expect(
    selectedQuarterlySource
      .locator("a")
      .filter({ hasText: "Filing / original evidence" }),
  ).toHaveAttribute(
    "href",
    "https://www.sec.gov/Archives/edgar/data/1408198/000140819826000056/0001408198-26-000056-index.html",
  );
  await quarterlySource.getByRole("button", { name: "Close details" }).click();

  await control(true);
  await page.goto("/operations");
  await page
    .getByRole("button", { name: "Refresh eligible SEC data", exact: true })
    .click();
  await expect(
    page.getByText(/SEC filings and fundamentals requests are recorded below/),
  ).toBeVisible();
  await page.reload();
  await control(false);
  await expect
    .poll(
      async () => {
        const jobs = await (
          await request.get(`${api}/v1/operations/job-requests`)
        ).json();
        return jobs
          .filter(
            (item: { scope_kind: string }) =>
              item.scope_kind === "ACTIVE_UNIVERSE",
          )
          .map(
            (item: { job_name: string; status: string }) =>
              `${item.job_name}:${item.status}`,
          )
          .sort();
      },
      { timeout: 45_000 },
    )
    .toEqual(["SEC_FILINGS:PARTIAL", "SEC_FUNDAMENTALS:PARTIAL"]);
  const completed = await read();
  expect(completed.counts.source_documents).toBe(
    before.expected.source_documents,
  );
  expect(completed.counts.reported_fundamental_observations).toBe(
    before.expected.fundamental_observations,
  );
  expect(completed.protected_state_sha256).toBe(before.protected_state_sha256);

  const documentResponse = await request.get(
    `${api}/v1/companies/${before.company_id}/source-documents`,
  );
  expect(documentResponse.status()).toBe(200);
  const documents: unknown = await documentResponse.json();
  if (!isCompanySourceDocuments(documents))
    throw new Error("Source documents contract failed");
  // The existing source-document endpoint returns a bounded view, not the total
  // canonical archive. Complete ingestion counts are checked via fixture readback.
  const visibleDocumentCount = Math.min(100, before.expected.source_documents);
  expect(documents.source_count).toBe(visibleDocumentCount);
  expect(documents.documents).toHaveLength(visibleDocumentCount);
  expect(documents.sec_identity_status).toBe("MAPPED");
  expect(documents.documents.length).toBeGreaterThan(0);
  await page.goto(
    `/company/${before.company_id}?view=research#source-documents`,
  );
  await page.getByLabel("Evidence recency").selectOption("ALL");
  const filings = page.getByRole("region", {
    name: "Filings & source documents",
    exact: true,
  });
  await expect(
    filings.getByRole("heading", { name: "Filings & source documents" }),
  ).toBeVisible();
  const quarterlyDocument = documents.documents.find(
    (document) => document.external_identifier === "0001408198-26-000056",
  );
  if (!quarterlyDocument)
    throw new Error("The recorded quarterly filing is missing");
  expect(quarterlyDocument.canonical_url).toBe(
    "https://www.sec.gov/Archives/edgar/data/1408198/000140819826000056/0001408198-26-000056-index.html",
  );
  const quarterlyFiling = filings.locator("li").filter({
    has: page.locator(`a[href="${quarterlyDocument.canonical_url}"]`),
  });
  await expect(quarterlyFiling).toBeVisible();
  await expect(
    quarterlyFiling.getByRole("heading", {
      name: quarterlyDocument.title,
      exact: true,
    }),
  ).toBeVisible();
  const filingLink = quarterlyFiling
    .locator("a")
    .filter({ hasText: "Open source" })
    .first();
  await expect(filingLink).toHaveAttribute(
    "href",
    quarterlyDocument.canonical_url,
  );
  await filings.scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("recorded-real-sec-filings-dark.png"),
    scale: "css",
  });

  // Replaying an unchanged real recording proves the same scheduled path without inventing new facts.
  const scheduled = await control(true, 3);
  expect(
    scheduled.last_cycle?.jobs
      .map((job) => `${job.job_name}:${job.operation_status}`)
      .sort(),
  ).toEqual(["SEC_FILINGS:PARTIAL", "SEC_FUNDAMENTALS:PARTIAL"]);
  expect(scheduled.provider_request_count).toBeGreaterThan(
    completed.provider_request_count,
  );
  expect(scheduled.counts.reported_fundamental_observations).toBe(
    completed.counts.reported_fundamental_observations,
  );
  expect(scheduled.counts.source_documents).toBe(
    completed.counts.source_documents,
  );
  const repeated = await control(true, 3);
  expect(repeated.provider_request_count).toBe(
    scheduled.provider_request_count,
  );
  expect(repeated.counts).toEqual(scheduled.counts);
  expect(repeated.worker_errors).toEqual([]);
  expect(repeated.protected_state_sha256).toBe(before.protected_state_sha256);
  expect(
    repeated.provider_urls.every(
      (url) => new URL(url).hostname === "data.sec.gov",
    ),
  ).toBe(true);
  const coverage: unknown = await (
    await request.get(`${api}/v1/companies/${before.company_id}/sec-coverage`)
  ).json();
  if (!isCompanySecCoverage(coverage))
    throw new Error("SEC coverage contract failed");
  expect(coverage.cik).toBe(before.issuer.cik);
  expect(coverage.provider_company_name).toBe(before.issuer.name);
  expect(coverage.mapping_status).toBe("MAPPED");
  expect(writes).toEqual(
    Array(3).fill("/api/research/operations/job-requests"),
  );
  expect(pageErrors).toEqual([]);
});
