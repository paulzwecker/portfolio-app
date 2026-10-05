import { expect, test } from "@playwright/test";

const healthy = {
  status: "ok",
  database: "connected",
  schema: "current",
  checked_at: "2026-10-04T10:00:00Z",
};

test("empty workspace is usable without horizontal overflow", async ({
  page,
}, testInfo) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: healthy }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Your research workspace" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("All services connected");
  await expect(page.getByText("Research foundation")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("workspace.png"),
    fullPage: true,
  });
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
});

test("loading, unavailable and retry states are explicit", async ({ page }) => {
  let release: () => void = () => undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  // Development mode may mount effects twice. All initial requests must keep
  // the same state until the test explicitly starts recovery.
  let recovered = false;
  await page.route("**/api/health", async (route) => {
    await pending;
    if (!recovered) {
      await route.fulfill({ status: 503, json: { detail: "API unavailable" } });
    } else {
      await route.fulfill({ json: healthy });
    }
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Checking connection");
  await expect(page.getByRole("button", { name: "Checking" })).toBeDisabled();
  release();
  await expect(page.getByRole("status")).toHaveText(
    "Connection needs attention",
  );
  recovered = true;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("status")).toHaveText("All services connected");
});

test("reachable database with outdated schema is not reported ready", async ({
  page,
}) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({
      status: 503,
      json: { ...healthy, status: "error", schema: "outdated" },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText(
    "Connection needs attention",
  );
  await expect(page.getByText("Migration required")).toBeVisible();
});

test("real frontend to API to PostgreSQL connectivity", async ({ page }) => {
  test.skip(
    process.env.E2E_LIVE_API !== "1",
    "Requires the explicitly enabled running API and migrated PostgreSQL database.",
  );
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("All services connected");
  await expect(page.getByText("Current", { exact: true })).toBeVisible();
});

test("imported workbook data appears in the live portfolio and universe flows", async ({
  page,
}) => {
  test.skip(
    process.env.E2E_LIVE_API !== "1",
    "Requires the explicitly enabled running API and imported local PostgreSQL data.",
  );
  await page.goto("/portfolio");
  await expect(page.getByText("Imported Legacy Portfolio")).toBeVisible();
  await expect(page.getByText("Current market value")).toBeVisible();
  await expect(page.getByText("VALUED", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Standalone securities" }),
  ).toBeVisible();
  await expect(
    page.getByText("· SPYY · ETR · EUR", { exact: true }),
  ).toBeVisible();
  await page.goto("/universe");
  await expect(page.getByRole("status")).toContainText("219 businesses shown");
  await expect(page.getByRole("link", { name: "AAON, Inc." })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("listing-specific market facts keep ordinary shares and ADR quotes distinct responsively", async ({
  page,
}) => {
  test.skip(
    process.env.E2E_LIVE_API !== "1",
    "Requires the read-only imported market-data snapshot in local PostgreSQL.",
  );
  const response = await page.request.get(
    "/api/research/universe/market-summary",
  );
  expect(response.ok()).toBe(true);
  const rows: unknown = await response.json();
  expect(Array.isArray(rows)).toBe(true);
  const tsm = (
    rows as Array<{
      company: { id: string; name: string };
      market_data: Array<{
        listing: { ticker: string; venue: string; currency?: string | null };
        latest: { split_adjusted_close: string | null } | null;
        freshness: string;
      }>;
    }>
  ).find((row) => row.company.name.includes("Taiwan Semiconductor"));
  expect(tsm).toBeDefined();
  const ordinary = tsm!.market_data.find(
    (item) => item.listing.venue === "TPE" && item.listing.ticker === "2330",
  );
  const adr = tsm!.market_data.find(
    (item) => item.listing.venue === "NYSE" && item.listing.ticker === "TSM",
  );
  expect(ordinary?.latest?.split_adjusted_close).not.toBeNull();
  expect(ordinary?.freshness).toBe("FRESH");
  expect(adr?.latest?.split_adjusted_close).not.toBeNull();
  expect(adr?.freshness).toBe("FRESH");

  await page.goto(`/company/${tsm!.company.id}`);
  await expect(
    page.getByRole("heading", { name: "Market facts" }),
  ).toBeVisible();
  await expect(
    page.locator("#market-facts").getByText(/2330.*TPE.*TWD/),
  ).toBeVisible();
  await expect(
    page.locator("#market-facts").getByText(/TSM.*NYSE.*USD/),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
