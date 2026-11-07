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
