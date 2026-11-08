import { expect, test } from "@playwright/test";
import { portfolioFixture, portfolioId, iso } from "./fixtures/portfolio";
import path from "node:path";

test("Portfolio presents 22 exact positions, cash and missing states on desktop and mobile", async ({
  page,
}, testInfo) => {
  const overview = portfolioFixture();
  const writeRequests: string[] = [];
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) {
      writeRequests.push(
        `${request.method()} ${new URL(request.url()).pathname}`,
      );
    }
  });

  await page.route("**/api/research/portfolios", (route) =>
    route.fulfill({ json: [overview.portfolio] }),
  );
  await page.route(
    `**/api/research/portfolios/${portfolioId}/overview`,
    (route) => route.fulfill({ json: overview }),
  );
  for (const path of [
    "universe/ranking-summary",
    "universe/execution-pace-summary",
    "universe/score-summary",
    "universe/estimate-momentum-summary",
    "universe/model-output-summary",
  ]) {
    await page.route(`**/api/research/${path}`, (route) =>
      route.fulfill({ json: [] }),
    );
  }
  await page.route("**/api/research/attention**", (route) =>
    route.fulfill({
      json: {
        as_of: iso,
        lookback_days: 30,
        total: 0,
        events: [],
      },
    }),
  );

  await page.goto("/portfolio");
  await expect(
    page.getByRole("heading", { name: "Portfolio at a glance" }),
  ).toBeVisible();
  if (process.env.DESIGN_REVIEW_SCREENSHOTS) {
    await page.screenshot({
      path: path.join(
        process.env.DESIGN_REVIEW_SCREENSHOTS,
        `portfolio-${testInfo.project.name}.png`,
      ),
    });
  }
  await expect(
    page.getByText("Holdings confirmation is 6 days old."),
  ).toBeVisible();
  await expect(
    page.getByText("EUR cash", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("USD cash", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Strategic targets need investor review"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Sector · unavailable/ }),
  ).toBeDisabled();
  await expect(
    page.getByRole("heading", {
      name: "Historical portfolio performance is unavailable",
    }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Holdings", exact: true }).click();
  await expect(page.getByText("22 listing positions")).toBeVisible();
  await expect(
    page.getByText("SPYY · XETRA · EUR").filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(
    page
      .getByText("Listing 20000000-0000-4000-8000-000000000022")
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  await page.getByLabel("Sort holdings by").selectOption("company");
  await expect(page.getByText("Fixture issuer 01").first()).toBeVisible();
  const search = page.getByRole("searchbox", { name: "Find a position" });
  await search.fill("SPYY");
  await expect(
    page.getByRole("status").filter({ hasText: "1 of 22 rows shown" }),
  ).toBeVisible();
  await expect(
    page.getByText("SPYY · XETRA · EUR").filter({ visible: true }).first(),
  ).toBeVisible();
  await search.fill("no-such-listing");
  await expect(
    page.getByRole("status").filter({ hasText: "0 of 22 rows shown" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "22 of 22 rows shown" }),
  ).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Portfolio at a glance" }),
  ).toBeVisible();
  await expect(
    page.locator(
      '[aria-label="Portfolio holdings and current valuation, mobile view"] dl',
    ),
  ).toHaveCount(22);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 320, height: 720 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: "Confirm holdings" }).click();
  await expect(page.getByLabel("Cash balance in USD")).toHaveValue("100");
  await expect(
    page.getByRole("button", { name: "Append confirmed snapshot" }),
  ).toBeDisabled();
  expect(writeRequests).toEqual([]);
});
