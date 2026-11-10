import { expect, test } from "@playwright/test";
import {
  isMarketBootstrapScopePreview,
  isOverview,
  isRecurringOperationsStatus,
} from "../src/lib/domain-contracts";

test.skip(
  process.env.E2E_REAL_API !== "1",
  "Requires the isolated portfolio-data API fixture.",
);

test("real API and browser review exact selected identities without writes", async ({
  page,
  request,
}) => {
  const port = process.env.BROWSER_API_PORT ?? "8011";
  if (
    !/^\d+$/.test(port) ||
    process.env.API_BASE_URL?.replace(/\/$/, "") !== `http://127.0.0.1:${port}`
  )
    throw new Error("Use the explicit loopback fixture API.");
  const api = `http://127.0.0.1:${port}`;
  const beforeResponse = await request.get(`${api}/__test/fixture`);
  const before = await beforeResponse.json();
  expect(before.test_only).toBe("portfolio-data-v1");
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  expect(before.scenario).toBe("unpriced");
  expect(before.provider_request_count).toBe(0);
  const query = "start_date=2024-02-01&end_date=2024-11-30";
  const direct = await request.get(
    `${api}/v1/market-data/bootstrap-scope?${query}`,
  );
  expect(direct.status()).toBe(200);
  const expected: unknown = await direct.json();
  if (!isMarketBootstrapScopePreview(expected))
    throw new Error("Invalid direct scope preview");
  expect(expected.omitted_listing_count).toBe(0);
  expect(expected.listing_review.length).toBeGreaterThan(0);
  const proxied = await request.get(
    `/api/research/market-data/bootstrap-scope?${query}`,
  );
  expect(proxied.status()).toBe(200);
  const observed: unknown = await proxied.json();
  if (!isMarketBootstrapScopePreview(observed))
    throw new Error("Invalid proxied scope preview");
  expect(observed.listing_review).toEqual(expected.listing_review);
  const writes: string[] = [];
  page.on("request", (req) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(req.method()))
      writes.push(req.method());
  });
  await page.goto("/operations");
  await page.getByLabel("Start date").fill("2024-02-01");
  await page.getByLabel("End date").fill("2024-11-30");
  await page.getByRole("button", { name: "Review scope" }).click();
  await page
    .getByText(`Review ${expected.listing_review.length} selected listings`)
    .click();
  const first = expected.listing_review[0];
  await expect(
    page
      .getByText(
        `${first.ticker} · ${first.venue} · ${first.currency ?? "Currency unavailable"}`,
      )
      .filter({ visible: true }),
  ).toBeVisible();
  await expect(
    page
      .getByText(
        first.mapping_verified
          ? `Verified: ${first.provider_symbol}`
          : "Needs review",
        { exact: true },
      )
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(before.protected_state_sha256);
  expect(after.provider_request_count).toBe(0);
  expect(writes).toEqual([]);
});

test("real importer, proxy and browser preserve the portfolio baseline", async ({
  page,
  request,
}, testInfo) => {
  const port = process.env.BROWSER_API_PORT ?? "8011";
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535) {
    throw new Error("The fixture API requires an explicit local test port.");
  }
  const api = `http://127.0.0.1:${port}`;
  if (process.env.API_BASE_URL?.replace(/\/$/, "") !== api) {
    throw new Error(
      "API_BASE_URL must match the loopback fixture API for this check.",
    );
  }
  const identityResponse = await request.get(`${api}/__test/fixture`);
  expect(identityResponse.status()).toBe(200);
  const identity = await identityResponse.json();
  expect(identity.test_only).toBe("portfolio-data-v1");
  expect(identity.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  expect(["unpriced", "fx-outage", "valued"]).toContain(identity.scenario);
  expect(identity.crosswalk_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(identity.provider_request_count).toBe(
    identity.scenario === "unpriced" ? 0 : 3,
  );

  const writes: string[] = [];
  const apiErrors: string[] = [];
  page.on("request", (message) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(message.method())) {
      writes.push(`${message.method()} ${new URL(message.url()).pathname}`);
    }
  });
  page.on("response", (response) => {
    if (
      new URL(response.url()).pathname.startsWith("/api/") &&
      response.status() >= 400
    ) {
      apiErrors.push(
        `${response.status()} ${new URL(response.url()).pathname}`,
      );
    }
  });
  const path = `/api/research/portfolios/${identity.portfolio_id}/overview`;
  const proxied = await request.get(path);
  expect(proxied.status()).toBe(200);
  const overview: unknown = await proxied.json();
  expect(isOverview(overview)).toBe(true);
  if (!isOverview(overview))
    throw new Error("The proxied portfolio contract failed validation.");
  const direct = await request.get(
    `${api}/v1/portfolios/${identity.portfolio_id}/overview`,
  );
  const directOverview = await direct.json();
  expect(overview.snapshot).toEqual(directOverview.snapshot);
  expect(overview.snapshot?.id).toBe(identity.snapshot_id);
  expect(overview.target_revision?.id).toBe(identity.target_revision_id);
  expect(
    overview.snapshot?.positions.map((position) => position.quantity).sort(),
  ).toEqual(["1.0000000000", "2.5000000000"]);
  expect(
    overview.snapshot?.cash_positions.map((cash) => cash.currency).sort(),
  ).toEqual(["EUR", "USD"]);
  expect(
    overview.snapshot?.cash_positions
      .map((cash) => [cash.currency, cash.balance])
      .sort(),
  ).toEqual([
    ["EUR", "10.0000000000"],
    ["USD", "5.0000000000"],
  ]);
  expect(overview.target_revision?.allocations).toHaveLength(1);
  expect(overview.target_revision?.allocations[0].weight).toMatch(/^0\.50*$/);
  expect(overview.standalone_positions[0].listing_id).toBe(
    identity.fund_listing_id,
  );
  expect(overview.base_market_value).toBe(directOverview.base_market_value);
  if (identity.scenario === "valued") {
    expect(overview.base_market_value).toMatch(/^391\.750*$/);
  } else {
    expect(overview.base_market_value).toBeNull();
  }
  const health = await request.get("/api/health");
  expect(health.status()).toBe(200);
  expect((await health.json()).schema).toBe("current");

  await page.goto("/portfolio");
  await expect(
    page.getByRole("heading", { name: "Portfolio at a glance" }),
  ).toBeVisible();
  if (identity.scenario === "valued") {
    await expect(
      page.getByText("€391.75", { exact: true }).first(),
    ).toBeVisible();
  } else {
    await expect(
      page.getByText(/Portfolio total incomplete (price|fx) coverage/),
    ).toBeVisible();
  }
  await page.getByRole("link", { name: "Holdings", exact: true }).click();
  await expect(page.getByText("2 listing positions")).toBeVisible();
  await expect(
    page.getByText("SYNTH · NASDAQ · USD").filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("SYNF · XETRA · EUR").filter({ visible: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath(`live-${identity.scenario}-holdings.png`),
    scale: "css",
  });
  if (identity.scenario === "valued") {
    await page
      .getByRole("link", { name: "Allocation & exposure", exact: true })
      .click();
    const gaps = page.getByRole("region", { name: "Largest strategic gaps" });
    await expect(
      gaps.getByRole("link", { name: "Synthetic Example Corporation" }),
    ).toBeVisible();
    await expect(
      gaps.getByText("Gap -20.75 pp", { exact: false }),
    ).toBeVisible();
    await gaps.screenshot({
      path: testInfo.outputPath("live-valued-strategic-gaps.png"),
      scale: "css",
    });
    await page.screenshot({
      path: testInfo.outputPath("live-valued-allocation.png"),
      scale: "css",
    });
  }
  await page.getByRole("link", { name: "Review prices and FX" }).click();
  const panel = page.getByRole("region", {
    name: "Market data refresh",
    exact: true,
  });
  await expect(panel).toBeFocused();
  const state =
    identity.scenario === "valued"
      ? "AVAILABLE"
      : identity.scenario === "fx-outage"
        ? "PARTIAL"
        : "UNAVAILABLE";
  await expect(panel.getByText(state, { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Market prices and FX", exact: true }),
  ).toBeDisabled();
  if (identity.scenario !== "unpriced") {
    await panel.getByRole("button", { name: "Inspect FX refresh" }).click();
    const drawer = page.getByRole("dialog", { name: "FX refresh details" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("Attempt 1", { exact: true })).toBeVisible();
    await expect(drawer.locator("pre").first()).toContainText(
      identity.crosswalk_sha256,
    );
    if (identity.scenario === "fx-outage")
      await expect(
        drawer
          .getByRole("region", { name: "Recorded attempts" })
          .getByText(
            "No provider response could be normalized for this domain.",
          ),
      ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`live-${identity.scenario}-fx.png`),
      scale: "css",
    });
    await page.keyboard.press("Escape");
  }
  const statusResponse = await request.get(
    "/api/research/recurring-operations/status",
  );
  expect(statusResponse.status()).toBe(200);
  expect(isRecurringOperationsStatus(await statusResponse.json())).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const after = await request.get(`${api}/__test/fixture`);
  expect((await after.json()).protected_state_sha256).toBe(
    identity.protected_state_sha256,
  );
  expect(writes).toEqual([]);
  expect(apiErrors).toEqual([]);
});
