import { expect, test } from "@playwright/test";

test("company finder resolves canonical companies and preserves company context", async ({
  page,
}, testInfo) => {
  const companyId = "11111111-1111-4111-8111-111111111111";
  await page.route("**/api/research/universe/market-summary**", (route) =>
    route.fulfill({
      json: [
        {
          company: {
            id: companyId,
            name: "Microsoft Corporation",
            reporting_currency: "USD",
            created_at: "2026-10-16T08:00:00Z",
            is_demo: false,
            lifecycle: "WATCHLIST",
            lifecycle_event_id: null,
          },
          market_data: [
            {
              listing: {
                id: "22222222-2222-4222-8222-222222222222",
                security_id: "33333333-3333-4333-8333-333333333333",
                ticker: "MSFT",
                venue: "NASDAQ",
                currency: "USD",
                is_demo: false,
              },
              latest: null,
              freshness: "NO_DATA",
              availability: "UNAVAILABLE",
              age_days: null,
              price_regime: null,
              analytics: {
                status: "UNAVAILABLE",
                methodology_version: "price-regime-v1",
                observation_count: 0,
                as_of: null,
                daily_return: null,
                dma_20: null,
                dma_50: null,
                dma_200: null,
                high_52w: null,
                drawdown_52w: null,
                price_return_1m: null,
                price_return_3m: null,
                price_return_6m: null,
                realized_vol_20d: null,
                trend_state: null,
                correction_state: null,
              },
              last_market_update: null,
              history: [],
            },
          ],
        },
      ],
    }),
  );
  await page.route(`**/api/research/companies/${companyId}`, (route) =>
    route.fulfill({ status: 404, json: { detail: "Not found" } }),
  );

  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Search companies and listings",
  });
  await search.fill("MSF");
  await expect(
    page.getByRole("option", { name: /Microsoft Corporation/ }),
  ).toBeVisible();
  await expect(page.getByText("MSFT · NASDAQ · USD")).toBeVisible();
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/company/${companyId}$`));
  await expect(
    page.getByRole("heading", { name: "Company", exact: true, level: 1 }),
  ).toBeVisible();

  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Menu" }).click();
    await page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: "Modeling" })
      .click();
  } else {
    await page
      .getByRole("banner")
      .getByRole("link", { name: "Modeling" })
      .click();
  }
  await expect(page).toHaveURL(new RegExp(`#canonical-models$`));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("Decisions navigation opens its dedicated read-only workspace", async ({
  page,
}, testInfo) => {
  await page.route("**/api/research/portfolios", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/decisions");
  await expect(page).toHaveURL(/\/decisions$/);
  await expect(
    page.getByRole("heading", { name: "Decisions", exact: true, level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "No portfolio decision context" }),
  ).toBeVisible();
  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Menu" }).click();
    await expect(page.getByRole("link", { name: "Decisions" })).toBeVisible();
  }
});

test("mobile navigation is a single expandable menu, not a compressed link grid", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "mobile");
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Menu" })).toBeVisible();
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Portfolio", exact: true })
    .click();
  await expect(page).toHaveURL(/\/portfolio$/);
  await expect(page.getByRole("button", { name: "Menu" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
});
