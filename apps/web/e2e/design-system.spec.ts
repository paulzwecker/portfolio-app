import { expect, test } from "@playwright/test";

test("design reference components preserve status, responsive layout and drawer keyboard behavior", async ({
  page,
}, testInfo) => {
  await page.goto("/design-system");
  await expect(
    page.getByRole("heading", { name: "Design system", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("No chart data available")).toBeVisible();
  await expect(page.getByText("STALE").first()).toBeVisible();

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
    const darkBackground = await page.evaluate(() =>
      getComputedStyle(document.documentElement)
        .getPropertyValue("--background")
        .trim(),
    );
    expect(darkBackground).toBe("#101512");
  }
});
