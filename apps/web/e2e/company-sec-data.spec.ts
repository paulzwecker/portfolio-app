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
      if (route.request().url().endsWith(String(current?.id))) {
        polling += 1;
        maximumPolling = Math.max(maximumPolling, polling);
        // A response slower than the poll interval must not overlap a later poll
        // or replace the subsequent request's status with an old request receipt.
        if (submissions.length === 1)
          await new Promise((resolve) => setTimeout(resolve, 4000));
        polling -= 1;
        return route.fulfill({
          json: {
            ...current,
            status: submissions.length === 1 ? "PARTIAL" : "FAILED",
            finished_at: new Date().toISOString(),
            error_code: "SYNTHETIC_SEC_RESULT",
            error_message: "Synthetic source coverage needs review.",
          },
        });
      }
      return route.continue();
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
