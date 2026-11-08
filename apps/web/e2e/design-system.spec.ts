import { expect, test } from "@playwright/test";
import path from "node:path";

test("design reference components preserve status, responsive layout and drawer keyboard behavior", async ({
  page,
}, testInfo) => {
  await page.goto("/design-system");
  await expect(
    page.getByRole("heading", { name: "Design system", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("No chart data available")).toBeVisible();
  await expect(page.getByText("STALE").first()).toBeVisible();

  if (process.env.DESIGN_REVIEW_SCREENSHOTS) {
    await page.screenshot({
      path: path.join(
        process.env.DESIGN_REVIEW_SCREENSHOTS,
        `design-${testInfo.project.name}.png`,
      ),
    });
  }

  const opener = page.getByRole("button", { name: "Open details" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "Observation details" });
  await expect(drawer).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  await expect(opener).toBeFocused();

  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
    { width: 320, height: 720 },
  ]) {
    await page.setViewportSize(viewport);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }

  if (testInfo.project.name === "desktop") {
    await page.emulateMedia({ colorScheme: "dark" });
    await expect
      .poll(() =>
        page.evaluate(() =>
          getComputedStyle(document.documentElement)
            .getPropertyValue("--background")
            .trim(),
        ),
      )
      .toBe("#1d252e");
  }
});

test("appearance and sample filters are keyboard accessible and persistent", async ({
  page,
}, testInfo) => {
  await page.goto("/design-system");
  const search = page.getByRole("searchbox", {
    name: "Search illustrative states",
  });
  await search.fill("stale");
  await expect(
    page.getByRole("status").filter({ hasText: "1 of 5 rows shown" }),
  ).toBeVisible();
  await expect(
    page.getByText("Historical observation").filter({ visible: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(search).toHaveValue("");
  await expect(
    page.getByRole("status").filter({ hasText: "5 of 5 rows shown" }),
  ).toBeVisible();

  const appearance = page.getByLabel("Appearance");
  await appearance.selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect
    .poll(() =>
      page
        .getByRole("button", { name: "Quiet action" })
        .evaluate((element) => getComputedStyle(element).color),
    )
    .toBe("rgb(236, 240, 245)");
  await expect
    .poll(() =>
      page
        .getByRole("button", { name: "Primary action" })
        .evaluate((element) => getComputedStyle(element).color),
    )
    .toBe("rgb(32, 40, 49)");
  if (process.env.DESIGN_REVIEW_SCREENSHOTS) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(
        process.env.DESIGN_REVIEW_SCREENSHOTS,
        `design-dark-${testInfo.project.name}.png`,
      ),
    });
  }
  await page.reload();
  await expect(appearance).toHaveValue("dark");
  await appearance.selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await appearance.selectOption("system");
  expect(
    await page.evaluate(() => localStorage.getItem("personal-universe-theme")),
  ).toBeNull();
  await page.getByText("View chart data").click();
  await expect(page.getByText(/March: unavailable/)).toBeVisible();
});
