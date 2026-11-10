import { expect, test } from "@playwright/test";

test.skip(
  process.env.E2E_SEC_API !== "1",
  "Requires the isolated SEC API fixture.",
);

test("placeholder-only statements keep source coverage without empty chart controls", async ({
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
  expect(fixture.scenario).toBe("sec-unmapped");
  const response = await request.get(
    `${api}/v1/companies/${fixture.company_id}/financial-statements?period_type=ANNUAL&period_limit=10`,
  );
  expect(response.status()).toBe(200);
  const statements = await response.json();
  expect(statements.periods).toHaveLength(0);
  expect(statements.rows.length).toBeGreaterThan(0);
  expect(
    statements.rows.every(
      (row: { cells: unknown[] }) => row.cells.length === 0,
    ),
  ).toBe(true);
  await page.goto(`/company/${fixture.company_id}?view=financials`);
  const section = page.locator("#reported-fundamentals");
  await expect(
    section.getByRole("heading", { name: "No aligned financial periods" }),
  ).toBeVisible();
  await expect(
    section.getByRole("region", { name: "SEC source coverage" }),
  ).toBeVisible();
  await expect(
    section.getByRole("group", { name: "Financial statement category" }),
  ).toHaveCount(0);
  await expect(
    section.getByRole("group", { name: "Financial chart comparison mode" }),
  ).toHaveCount(0);
  await expect(
    section.getByText("Select a metric row to explore its history."),
  ).toHaveCount(0);
  await section.screenshot({
    path: info.outputPath("real-empty-financials.png"),
    scale: "css",
  });
  await section.getByRole("button", { name: "Sources & alignment" }).click();
  await expect(
    page.getByRole("dialog", { name: "Financial sources & limitations" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(fixture.protected_state_sha256);
});
