import { expect, test } from "@playwright/test";

test.skip(
  process.env.E2E_SEC_REFRESH_API !== "1" ||
    process.env.E2E_MANAGED_PRODUCTION_SERVER === "1",
  "Requires a fresh isolated sec-refresh-workflow API scenario for each project.",
);

test("SEC refresh runs from company and Operations through real database to updated UI", async ({
  page,
  request,
}, info) => {
  const port = process.env.BROWSER_API_PORT ?? "8011";
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535)
    throw new Error("Expected a loopback fixture port");
  const api = `http://127.0.0.1:${port}`;
  if (process.env.API_BASE_URL !== api)
    throw new Error("Expected the isolated API target");
  const read = async () => (await request.get(`${api}/__test/fixture`)).json();
  const control = async (data: {
    paused: boolean;
    response?: string;
    scheduled_days_later?: number;
  }) => {
    const result = await request.post(`${api}/__test/refresh-control`, {
      data,
    });
    expect(result.status()).toBe(200);
    return result.json();
  };
  const before = await read();
  expect(before.scenario).toBe("sec-refresh-workflow");
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  expect(before.provider_fixture).toBe("recorded-fictional-sec-v1");
  expect(before.counts.reported_fundamental_observations).toBe(0);
  const company = `/company/${before.company_id}?view=financials`;
  await page.goto(company);
  await expect(
    page.getByRole("heading", { name: "No aligned financial periods" }),
  ).toBeVisible();
  await page.getByText("Data & refresh", { exact: true }).click();
  const queued = page.waitForResponse(
    (r) =>
      r.url().endsWith("/operations/job-requests") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Refresh SEC fundamentals", exact: true })
    .click();
  const jobResponse = await queued;
  expect(jobResponse.status()).toBe(202);
  const job = await jobResponse.json();
  expect(job.scope_kind).toBe("COMPANY");
  expect(job.company_id).toBe(before.company_id);
  expect(job.status).toBe("QUEUED");
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
  await control({ paused: false });
  await expect(
    refreshGroup.getByText("SUCCEEDED", { exact: true }).first(),
  ).toBeVisible({ timeout: 30000 });
  // No reload: the terminal receipt invalidates the existing Financials API hook.
  await expect(
    page.getByRole("heading", { name: "No aligned financial periods" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /^Revenue, FY/ }).first(),
  ).toBeVisible();
  const manual = await read();
  expect(manual.counts.reported_fundamental_observations).toBe(2);
  expect(manual.provider_request_count).toBe(1);
  expect(manual.protected_state_sha256).toBe(before.protected_state_sha256);
  // An expanded receipt must keep the second SEC action and its evidence reachable.
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("company-refreshed.png"),
    fullPage: true,
    scale: "css",
  });

  await control({ paused: true });
  await page.goto("/operations");
  await page
    .getByRole("button", { name: "Refresh eligible SEC data", exact: true })
    .click();
  await expect(
    page.getByText(/SEC filings and fundamentals requests are recorded below/),
  ).toBeVisible();
  const batch = await (
    await request.get(`${api}/v1/operations/job-requests`)
  ).json();
  const globalJobs = batch.filter(
    (j: { scope_kind: string }) => j.scope_kind === "ACTIVE_UNIVERSE",
  );
  expect(
    globalJobs.map((j: { job_name: string }) => j.job_name).sort(),
  ).toEqual(["SEC_FILINGS", "SEC_FUNDAMENTALS"].sort());
  await page.reload();
  await control({ paused: false });
  await expect
    .poll(
      async () => {
        const jobs = await (
          await request.get(`${api}/v1/operations/job-requests`)
        ).json();
        return jobs.every(
          (j: { status: string }) => !["QUEUED", "RUNNING"].includes(j.status),
        );
      },
      { timeout: 30000 },
    )
    .toBe(true);
  await expect(
    page.getByText("SUCCEEDED", { exact: true }).first(),
  ).toBeVisible();
  const refreshed = await read();
  expect(refreshed.counts.source_documents).toBe(2);
  expect(
    refreshed.scopes.every(
      (scope: { max_mapped_issuers: number }) =>
        scope.max_mapped_issuers === 30,
    ),
  ).toBe(true);
  await page.getByLabel("Appearance").selectOption("dark");
  await page
    .getByRole("heading", { name: "Manual refresh", exact: true })
    .scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("operations-sec-refresh-dark.png"),
    scale: "css",
  });

  // Simulate an existing free host waking three days late: one due pass, not a catch-up loop.
  const scheduled = await control({
    paused: true,
    response: "updated",
    scheduled_days_later: 3,
  });
  expect(scheduled.counts.reported_fundamental_observations).toBeGreaterThan(
    refreshed.counts.reported_fundamental_observations,
  );
  const repeated = await control({
    paused: true,
    response: "updated",
    scheduled_days_later: 3,
  });
  expect(repeated.provider_request_count).toBe(
    scheduled.provider_request_count,
  );
  await page.goto(company);
  await expect(page.getByRole("button", { name: /^Revenue, FY/ })).toHaveCount(
    2,
  );
  await page.screenshot({
    path: info.outputPath("scheduled-new-period-dark.png"),
    fullPage: true,
    scale: "css",
  });

  const outage = await control({
    paused: true,
    response: "outage",
    scheduled_days_later: 4,
  });
  expect(outage.counts.reported_fundamental_observations).toBe(
    scheduled.counts.reported_fundamental_observations,
  );
  await page.goto("/operations");
  await expect(
    page.getByText("FAILED", { exact: true }).filter({ visible: true }).first(),
  ).toBeVisible();
  const partial = await control({
    paused: true,
    response: "partial",
    scheduled_days_later: 5,
  });
  await page.goto(company);
  await page.getByText("Data & refresh", { exact: true }).click();
  await page.getByRole("button", { name: "Inspect SEC coverage" }).click();
  const drawer = page.getByRole("dialog", {
    name: "SEC coverage and provenance",
  });
  await expect(drawer.getByText(/PARTIAL|DATA CHECK/).first()).toBeVisible();
  await page.screenshot({
    path: info.outputPath("partial-source-coverage.png"),
    scale: "css",
  });
  expect(partial.protected_state_sha256).toBe(before.protected_state_sha256);
  expect(partial.worker_errors).toEqual([]);
  expect(
    partial.provider_urls.every((url: string) =>
      url.startsWith("https://data.sec.gov/"),
    ),
  ).toBe(true);
});
