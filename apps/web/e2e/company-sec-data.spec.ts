import { expect, test } from "@playwright/test";
import { isCompanySecCoverage } from "../src/lib/domain-contracts";

test.skip(
  process.env.E2E_SEC_API !== "1",
  "Requires the isolated SEC API fixture.",
);

test("company SEC evidence leads to scoped diagnostics without writes", async ({
  page,
  request,
}, info) => {
  const port = process.env.BROWSER_API_PORT ?? "8011";
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535)
    throw new Error("The SEC fixture requires a local test port.");
  const api = `http://127.0.0.1:${port}`;
  if (process.env.API_BASE_URL?.replace(/\/$/, "") !== api)
    throw new Error("API_BASE_URL must match the loopback SEC fixture.");
  const initial = await request.get(`${api}/__test/fixture`);
  expect(initial.status()).toBe(200);
  const fixture = await initial.json();
  expect(fixture.test_only).toBe("portfolio-data-v1");
  expect(fixture.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  expect([
    "sec-covered",
    "sec-outage",
    "sec-unmapped",
    "sec-refresh-partial",
    "sec-refresh-outage",
  ]).toContain(fixture.scenario);
  const result = await request.get(
    `/api/research/companies/${fixture.company_id}/sec-coverage`,
  );
  expect(result.status()).toBe(200);
  const data: unknown = await result.json();
  expect(isCompanySecCoverage(data)).toBe(true);
  if (!isCompanySecCoverage(data))
    throw new Error("The SEC coverage contract failed.");
  expect(data.mapping_status).toBe(
    fixture.scenario === "sec-unmapped" ? "UNMAPPED" : "MAPPED",
  );
  expect(data.filings.record_count).toBe(
    fixture.scenario === "sec-unmapped" ? 0 : 4,
  );
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("request", (event) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(event.method()))
      writes.push(event.method());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (
      new URL(response.url()).pathname.startsWith("/api/") &&
      response.status() >= 400
    )
      errors.push(`${response.status()} ${new URL(response.url()).pathname}`);
  });
  await page.goto(`/company/${fixture.company_id}?view=financials`);
  const panel = page.getByRole("region", {
    name: "SEC source coverage",
    exact: true,
  });
  await expect(
    panel
      .getByText(data.mapping_status, { exact: true })
      .filter({ visible: true }),
  ).toBeVisible();
  await panel.screenshot({
    path: info.outputPath(`${fixture.scenario}-summary.png`),
    scale: "css",
  });
  await panel.getByRole("button", { name: "Inspect SEC coverage" }).click();
  const drawer = page.getByRole("dialog", {
    name: "SEC coverage and provenance",
  });
  await expect(drawer).toBeVisible();
  await expect(
    drawer.getByRole("region", { name: "Reported metric coverage" }),
  ).toBeVisible();
  if (fixture.scenario === "sec-outage") {
    const filings = drawer.getByRole("region", {
      name: "Filing metadata",
      exact: true,
    });
    await expect(filings.getByText("FAILED", { exact: true })).toBeVisible();
    await expect(filings.getByText(/Retryable checkpoint/)).toBeVisible();
  }
  if (fixture.scenario.startsWith("sec-refresh-")) {
    const filings = drawer.getByRole("region", {
      name: "Filing metadata",
      exact: true,
    });
    const refresh = filings.getByRole("region", {
      name: "Latest incremental refresh",
      exact: true,
    });
    await expect(refresh).toBeVisible();
    await expect(
      filings.getByText("Latest bootstrap checkpoint", { exact: true }),
    ).toBeVisible();
    if (fixture.scenario === "sec-refresh-outage") {
      await expect(
        refresh.getByText("No issuer-specific result recorded", {
          exact: false,
        }),
      ).toBeVisible();
      await expect(refresh.getByText("FAILED", { exact: true })).toBeVisible();
      await expect(
        refresh.getByText(/Last recorded attempt is retryable/),
      ).toBeVisible();
    } else {
      await expect(refresh.getByText("PARTIAL", { exact: true })).toBeVisible();
      expect(data.filings.refresh?.scope_company_count).toBe(2);
      expect(data.filings.refresh?.issuer_outcome).toBe("REPORTED");
      expect(data.filings.refresh?.source_record_count).toBe(2);
      await expect(
        refresh.getByText("Source response reported", { exact: false }),
      ).toBeVisible();
      await expect(
        refresh.getByText("Supported filing rows in result", { exact: false }),
      ).toBeVisible();
    }
    await refresh.scrollIntoViewIfNeeded();
  }
  if (fixture.scenario === "sec-unmapped")
    await expect(
      drawer.getByText(/reviewed SEC CIK mapping is required/),
    ).toBeVisible();
  else {
    await expect(
      drawer.getByRole("link", { name: "SEC identity evidence" }),
    ).toHaveAttribute("href", /^https:\/\/www\.sec\.gov\//);
    await expect(
      drawer.getByText("Latest economic period end").first(),
    ).toBeVisible();
  }
  await page.screenshot({
    path: info.outputPath(`${fixture.scenario}-drawer.png`),
    scale: "css",
  });
  await page.keyboard.press("Escape");
  await expect(
    panel.getByRole("button", { name: "Inspect SEC coverage" }),
  ).toBeFocused();
  await page.getByLabel("App knowledge cutoff").fill("2024-12-31");
  await expect(panel).toHaveCount(0);
  await page.getByRole("button", { name: "Latest known", exact: true }).click();
  await expect(panel).toBeVisible();
  await page
    .getByRole("tab", { name: "Research & Evidence", exact: true })
    .click();
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "Inspect SEC coverage" }).click();
  await drawer
    .getByRole("link", { name: "Open Financials", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "Financials", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(panel).toBeVisible();
  await panel
    .getByRole("link", { name: "Open company data diagnostics" })
    .click();
  await expect(panel).toBeFocused();
  await expect(
    page.getByRole("button", { name: "Refresh SEC fundamentals", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Refresh SEC filings", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("Manual and recurring operations are disabled.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    panel
      .getByText(data.company_name, { exact: true })
      .filter({ visible: true }),
  ).toBeVisible();
  await panel.screenshot({
    path: info.outputPath(`${fixture.scenario}-operations.png`),
    scale: "css",
  });
  await expect(page.locator("html")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  const after = await request.get(`${api}/__test/fixture`);
  expect((await after.json()).protected_state_sha256).toBe(
    fixture.protected_state_sha256,
  );
});

test("a changed issuer identity is visible beside the historical refresh", async ({
  page,
  request,
}, info) => {
  const api = "http://127.0.0.1:8011";
  if (
    process.env.BROWSER_API_PORT !== "8011" ||
    process.env.API_BASE_URL !== api
  )
    throw new Error("Use the isolated loopback SEC fixture");
  const before = await (await request.get(`${api}/__test/fixture`)).json();
  expect(before.test_only).toBe("portfolio-data-v1");
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  test.skip(
    before.scenario !== "sec-refresh-partial",
    "Requires a synthetic recorded refresh",
  );
  const path = `/api/research/companies/${before.company_id}/sec-coverage`;
  const response = await request.get(path);
  const data: unknown = await response.json();
  if (
    !response.ok() ||
    !isCompanySecCoverage(data) ||
    !data.fundamentals.refresh
  )
    throw new Error("Synthetic SEC refresh is unavailable");
  const historical = {
    ...data,
    fundamental_identity_counts: {
      matching_cik: 0,
      other_cik: Math.max(1, data.fundamentals.record_count),
      unverified: 0,
    },
    fundamentals: {
      ...data.fundamentals,
      record_count: Math.max(1, data.fundamentals.record_count),
      refresh: {
        ...data.fundamentals.refresh,
        identity: { status: "CHANGED", frozen_cik: "0000000999" },
      },
    },
  };
  expect(isCompanySecCoverage(historical)).toBe(true);
  await page.route(`**${path}`, (route) => route.fulfill({ json: historical }));
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (req) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(req.method()))
      writes.push(req.method());
  });
  await page.goto(`/company/${before.company_id}?view=financials`);
  const panel = page.getByRole("region", {
    name: "SEC source coverage",
    exact: true,
  });
  await expect(
    panel
      .getByText(
        /Issuer mapping or recorded issuer details changed since this refresh/,
      )
      .filter({ visible: true }),
  ).toBeVisible();
  await expect(panel.getByRole("alert")).toContainText(
    "Review attribution before relying on financial statements",
  );
  await panel.screenshot({
    path: info.outputPath("sec-identity-drift-summary.png"),
    scale: "css",
  });
  await panel.getByRole("button", { name: "Inspect SEC coverage" }).click();
  const drawer = page.getByRole("dialog", {
    name: "SEC coverage and provenance",
  });
  await expect(drawer.getByText(/Frozen refresh CIK 0000000999/)).toBeVisible();
  await expect(
    drawer.getByText("Recorded issuer CIK on retained facts"),
  ).toBeVisible();
  await expect(
    drawer.getByText(/historical, not evidence for the current identity/),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("sec-identity-drift-detail.png"),
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(before.protected_state_sha256);
});

test("a changed issuer identity in a bootstrap remains visible when complete", async ({
  page,
  request,
}, info) => {
  const api = "http://127.0.0.1:8011";
  if (
    process.env.BROWSER_API_PORT !== "8011" ||
    process.env.API_BASE_URL !== api
  )
    throw new Error("Use the isolated loopback SEC fixture");
  const before = await (await request.get(`${api}/__test/fixture`)).json();
  expect(before.test_only).toBe("portfolio-data-v1");
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  test.skip(
    before.scenario !== "sec-refresh-partial",
    "Requires a synthetic bootstrap",
  );
  const path = `/api/research/companies/${before.company_id}/sec-coverage`;
  const response = await request.get(path);
  const data: unknown = await response.json();
  if (!response.ok() || !isCompanySecCoverage(data) || !data.filings.bootstrap)
    throw new Error("Synthetic SEC bootstrap is unavailable");
  const historical = {
    ...data,
    filings: {
      ...data.filings,
      refresh: null,
      bootstrap: {
        ...data.filings.bootstrap,
        status: "COMPLETE",
        identity: { status: "CHANGED", frozen_cik: "0000000999" },
      },
    },
  };
  expect(isCompanySecCoverage(historical)).toBe(true);
  await page.route(`**${path}`, (route) => route.fulfill({ json: historical }));
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (req) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(req.method()))
      writes.push(req.method());
  });
  await page.goto(`/company/${before.company_id}?view=financials`);
  const panel = page.getByRole("region", {
    name: "SEC source coverage",
    exact: true,
  });
  await expect(
    panel
      .getByText(/issuer details changed since this bootstrap/)
      .filter({ visible: true }),
  ).toBeVisible();
  await panel.screenshot({
    path: info.outputPath("sec-bootstrap-identity-summary.png"),
    scale: "css",
  });
  await panel.getByRole("button", { name: "Inspect SEC coverage" }).click();
  const drawer = page.getByRole("dialog", {
    name: "SEC coverage and provenance",
  });
  await expect(
    drawer.getByText(/Frozen bootstrap CIK 0000000999/),
  ).toBeVisible();
  await expect(
    drawer.getByText(/historical, not evidence for the current identity/),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("sec-bootstrap-identity-detail.png"),
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(before.protected_state_sha256);
});

test("scoped company controls queue only the selected SEC job and retain terminal diagnostics", async ({
  page,
  request,
}, info) => {
  const port = process.env.BROWSER_API_PORT ?? "8011";
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535)
    throw new Error("The SEC fixture requires a local test port.");
  const api = `http://127.0.0.1:${port}`;
  if (process.env.API_BASE_URL?.replace(/\/$/, "") !== api)
    throw new Error("API_BASE_URL must match the loopback SEC fixture.");
  const fixture = await (await request.get(`${api}/__test/fixture`)).json();
  expect(fixture.test_only).toBe("portfolio-data-v1");
  expect(fixture.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  const path = `/api/research/companies/${fixture.company_id}/refresh-options`;
  const response = await request.get(path);
  expect(response.status()).toBe(200);
  const options = await response.json();
  expect(options.execution_mode).toBe("DISABLED");
  expect(options.sec_eligibility_basis).toBe("VERIFIED_HOLDING");
  expect(options.lifecycle).toBeNull();
  expect(options.eligible_job_names).toEqual([
    "SEC_FUNDAMENTALS",
    "SEC_FILINGS",
  ]);

  // Exercise enabled controls with synthetic HTTP receipts. The real fixture
  // remains SQL read-only and rejects writes throughout this browser journey.
  await page.route(`**${path}`, (route) =>
    route.fulfill({ json: { ...options, execution_mode: "OPERATOR" } }),
  );
  const submissions: unknown[] = [];
  let polling = 0;
  let maximumPolling = 0;
  let historyReads = 0;
  let current: Record<string, unknown> | null = null;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    Object.assign(window, { refreshEvents: 0 });
    window.addEventListener("portfolio:data-refreshed", () => {
      const state = window as unknown as { refreshEvents: number };
      state.refreshEvents += 1;
    });
  });
  await page.route(
    "**/api/research/operations/job-requests**",
    async (route) => {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        submissions.push(body);
        historyReads = 0;
        const at = new Date().toISOString();
        current = {
          id: `11111111-1111-4111-8111-11111111111${submissions.length}`,
          ...body,
          company_name: options.company_name,
          lifecycle: null,
          requested_by: "LOCAL_USER",
          status: "QUEUED",
          requested_at: at,
          started_at: null,
          finished_at: null,
          next_attempt_at: null,
          attempt_count: 0,
          retry_of_id: null,
          affected_domains: [
            body.job_name === "SEC_FILINGS"
              ? "SOURCE_DOCUMENTS"
              : "REPORTED_FUNDAMENTALS",
          ],
          scope_detail: {
            selection_basis: "VERIFIED_HOLDING",
            holding_snapshot_id: options.holding_snapshot_id,
          },
          result: {},
          error_code: null,
          error_message: null,
          retry_available: false,
          deduplicated: false,
          cooldown_until: new Date(Date.now() + 900_000).toISOString(),
          attempts: [],
        };
        return route.fulfill({ status: 202, json: current });
      }
      return route.continue();
    },
  );
  await page.route(
    `**/api/research/companies/${fixture.company_id}/job-requests**`,
    async (route) => {
      if (current) {
        if (historyReads++ === 0) return route.fulfill({ json: [current] });
        polling += 1;
        maximumPolling = Math.max(maximumPolling, polling);
        // A response slower than the poll interval must not overlap a later poll
        // or replace the subsequent request's status with an old request receipt.
        if (submissions.length === 1)
          await new Promise((resolve) => setTimeout(resolve, 4000));
        polling -= 1;
        current = {
          ...current,
          status: submissions.length === 1 ? "PARTIAL" : "FAILED",
          finished_at: new Date().toISOString(),
          error_code: "SYNTHETIC_SEC_RESULT",
          error_message: "Synthetic source coverage needs review.",
        };
        return route.fulfill({ json: [current] });
      }
      return route.fulfill({ json: [] });
    },
  );
  await page.goto(`/company/${fixture.company_id}?view=financials`);
  await expect(
    page.getByText(/SEC eligibility comes from verified holdings/),
  ).toBeVisible();
  await expect(
    page.getByText("Lifecycle unassigned", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Refresh this company", exact: true }),
  ).toHaveCount(0);
  const controls = page.getByRole("group", {
    name: "Company refresh requests",
    exact: true,
  });
  for (const [index, name] of [
    "Refresh SEC fundamentals",
    "Refresh SEC filings",
  ].entries()) {
    const button = page.getByRole("button", { name, exact: true });
    await expect(button).toBeEnabled();
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(controls.getByText("QUEUED", { exact: true })).toBeVisible();
    if (index === 0) {
      await page.reload();
      await expect(controls.getByText("QUEUED", { exact: true })).toBeVisible();
    }
    await expect(button).toBeDisabled();
    await expect(
      controls.getByText(index === 0 ? "PARTIAL" : "FAILED", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Synthetic source coverage needs review.", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(button).toBeDisabled();
    await expect(page.getByText(/Available after/).first()).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(
          () => (window as unknown as { refreshEvents: number }).refreshEvents,
        ),
      )
      .toBe(index + 1);
  }
  expect(submissions).toEqual([
    {
      job_name: "SEC_FUNDAMENTALS",
      scope_kind: "COMPANY",
      company_id: fixture.company_id,
    },
    {
      job_name: "SEC_FILINGS",
      scope_kind: "COMPANY",
      company_id: fixture.company_id,
    },
  ]);
  expect(maximumPolling).toBe(1);
  await controls.screenshot({
    path: info.outputPath("scoped-sec-controls.png"),
    scale: "css",
  });
  await page.screenshot({
    path: info.outputPath("scoped-sec-terminal.png"),
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(fixture.protected_state_sha256);
});

test("company refresh history restores multiple active jobs and rejects a mismatched response", async ({
  page,
  request,
}, info) => {
  const api = `http://127.0.0.1:${process.env.BROWSER_API_PORT ?? "8011"}`;
  const fixture = await (await request.get(`${api}/__test/fixture`)).json();
  const optionsPath = `/api/research/companies/${fixture.company_id}/refresh-options`;
  const options = await (await request.get(optionsPath)).json();
  await page.route(`**${optionsPath}`, (route) =>
    route.fulfill({ json: { ...options, execution_mode: "OPERATOR" } }),
  );
  const at = new Date().toISOString();
  const job = (id: string, job_name: string, status: string) => ({
    id,
    job_name,
    scope_kind: "COMPANY",
    company_id: fixture.company_id,
    company_name: options.company_name,
    lifecycle: null,
    requested_by: "LOCAL_USER",
    status,
    requested_at: at,
    started_at: null,
    finished_at: null,
    next_attempt_at: null,
    attempt_count: 0,
    retry_of_id: null,
    affected_domains: [],
    scope_detail: {},
    result: {},
    error_code: null,
    error_message: null,
    retry_available: false,
    deduplicated: false,
    cooldown_until: at,
    attempts: [],
  });
  const jobs = [
    job("11111111-1111-4111-8111-111111111111", "SEC_FILINGS", "QUEUED"),
    job("22222222-2222-4222-8222-222222222222", "SEC_FUNDAMENTALS", "RUNNING"),
  ];
  let mismatch = false;
  await page.route(
    `**/api/research/companies/${fixture.company_id}/job-requests**`,
    (route) =>
      route.fulfill({
        json: mismatch
          ? [{ ...jobs[0], company_id: "33333333-3333-4333-8333-333333333333" }]
          : jobs,
      }),
  );
  await page.goto(`/company/${fixture.company_id}?view=financials`);
  const controls = page.getByRole("group", {
    name: "Company refresh requests",
    exact: true,
  });
  await expect(controls.getByText("QUEUED", { exact: true })).toBeVisible();
  await expect(controls.getByText("RUNNING", { exact: true })).toBeVisible();
  await controls.screenshot({
    path: info.outputPath("company-active-refreshes.png"),
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(
    controls.getByRole("button", { name: "Refresh SEC filings" }),
  ).toBeDisabled();
  await page.reload();
  await expect(controls.getByText("QUEUED", { exact: true })).toBeVisible();
  await expect(controls.getByText("RUNNING", { exact: true })).toBeVisible();
  mismatch = true;
  await expect(
    controls.getByText(/Company refresh history could not be verified/),
  ).toBeVisible();
  await expect(
    controls.getByRole("button", { name: "Refresh SEC filings" }),
  ).toBeDisabled();
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(fixture.protected_state_sha256);
});

test("company refresh history fails closed on timeout and older API then allows retry", async ({
  page,
  request,
}) => {
  const api = `http://127.0.0.1:${process.env.BROWSER_API_PORT ?? "8011"}`;
  const fixture = await (await request.get(`${api}/__test/fixture`)).json();
  const optionsPath = `/api/research/companies/${fixture.company_id}/refresh-options`;
  const options = await (await request.get(optionsPath)).json();
  await page.route(`**${optionsPath}`, (route) =>
    route.fulfill({ json: { ...options, execution_mode: "OPERATOR" } }),
  );
  let calls = 0;
  await page.route(
    `**/api/research/companies/${fixture.company_id}/job-requests**`,
    async (route) => {
      calls += 1;
      if (calls === 1) {
        await new Promise((resolve) => setTimeout(resolve, 11_000));
        return route.fulfill({ json: [] }).catch(() => undefined);
      }
      return calls === 2
        ? route.fulfill({ status: 404, json: { detail: "Not found" } })
        : route.fulfill({ json: [] });
    },
  );
  await page.goto(`/company/${fixture.company_id}?view=financials`);
  const controls = page.getByRole("group", {
    name: "Company refresh requests",
    exact: true,
  });
  const filings = controls.getByRole("button", { name: "Refresh SEC filings" });
  await expect(filings).toBeDisabled();
  await expect(
    controls.getByText(/Company refresh history timed out/),
  ).toBeVisible();
  await controls.getByRole("button", { name: "Retry refresh history" }).click();
  await expect(
    controls.getByText(/Company refresh history could not be verified/),
  ).toBeVisible();
  await expect(filings).toBeDisabled();
  await controls.getByRole("button", { name: "Retry refresh history" }).click();
  await expect(filings).toBeEnabled();
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(fixture.protected_state_sha256);
});

test("a completed older job is recovered after it leaves the bounded history", async ({
  page,
  request,
}) => {
  const api = `http://127.0.0.1:${process.env.BROWSER_API_PORT ?? "8011"}`;
  const fixture = await (await request.get(`${api}/__test/fixture`)).json();
  const optionsPath = `/api/research/companies/${fixture.company_id}/refresh-options`;
  const options = await (await request.get(optionsPath)).json();
  await page.route(`**${optionsPath}`, (route) =>
    route.fulfill({ json: { ...options, execution_mode: "OPERATOR" } }),
  );
  const at = new Date().toISOString();
  const base = {
    job_name: "SEC_FILINGS",
    scope_kind: "COMPANY",
    company_id: fixture.company_id,
    company_name: options.company_name,
    lifecycle: null,
    requested_by: "LOCAL_USER",
    requested_at: at,
    started_at: null,
    finished_at: at,
    next_attempt_at: null,
    attempt_count: 0,
    retry_of_id: null,
    affected_domains: [],
    scope_detail: {},
    result: {},
    error_code: null,
    error_message: null,
    retry_available: false,
    deduplicated: false,
    cooldown_until: at,
    attempts: [],
  };
  const old = {
    ...base,
    id: "99999999-9999-4999-8999-999999999999",
    status: "RUNNING",
    finished_at: null,
  };
  const newer = Array.from({ length: 30 }, (_, index) => ({
    ...base,
    id: `11111111-1111-4111-8111-${String(index).padStart(12, "0")}`,
    status: "SUCCEEDED",
  }));
  const stillActive = {
    ...base,
    id: "88888888-8888-4888-8888-888888888888",
    job_name: "SEC_FUNDAMENTALS",
    status: "QUEUED",
    finished_at: null,
  };
  let finished = false;
  let pollsAfterFinish = 0;
  await page.route(
    `**/api/research/companies/${fixture.company_id}/job-requests**`,
    (route) => {
      if (finished) pollsAfterFinish += 1;
      return route.fulfill({
        json: finished
          ? [stillActive, ...newer.slice(0, 29)]
          : [old, stillActive, ...newer.slice(0, 28)],
      });
    },
  );
  await page.route(
    `**/api/research/operations/job-requests/${old.id}`,
    (route) =>
      route.fulfill({
        json: {
          ...old,
          status: "FAILED",
          finished_at: at,
          error_message: "Older job failed.",
        },
      }),
  );
  await page.goto(`/company/${fixture.company_id}?view=financials`);
  const controls = page.getByRole("group", {
    name: "Company refresh requests",
    exact: true,
  });
  await expect(controls.getByText("RUNNING", { exact: true })).toBeVisible();
  finished = true;
  await expect(controls.getByText("Older job failed.")).toBeVisible();
  await expect(controls.getByText("FAILED", { exact: true })).toBeVisible();
  await expect.poll(() => pollsAfterFinish).toBeGreaterThanOrEqual(2);
  await expect(controls.getByText("Older job failed.")).toBeVisible();
  await expect(controls.getByText("QUEUED", { exact: true })).toBeVisible();
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(fixture.protected_state_sha256);
});
