import { expect, test } from "@playwright/test";

test.skip(
  process.env.E2E_RETURN_HURDLE_API !== "1" ||
    process.env.E2E_MANAGED_PRODUCTION_SERVER === "1",
  "Requires the isolated read-only return-hurdle PostgreSQL/API fixture.",
);

test("investor explores accepted-model return requirements and returns to holdings without writes", async ({
  page,
  request,
}, info) => {
  const port = process.env.BROWSER_API_PORT ?? "8013";
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535)
    throw new Error("Invalid fixture port");
  const api = `http://127.0.0.1:${port}`;
  if (process.env.API_BASE_URL !== api)
    throw new Error("Expected the isolated loopback API");
  const metadata = await (await request.get(`${api}/__test/fixture`)).json();
  expect(metadata.model_fixture).toBe("fictional-accepted-models-v1");
  expect(metadata.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  const unpriced = metadata.scenario === "return-hurdle-unpriced";
  const accepted = async () => {
    const dcf = await (
      await request.get(
        `${api}/v1/companies/${metadata.company_id}/financial-models`,
      )
    ).json();
    const other = await (
      await request.get(
        `${api}/v1/companies/${metadata.company_id}/canonical-financial-models`,
      )
    ).json();
    return [...dcf, ...other].map((model) => ({
      id: model.id,
      revision: model.current_revision,
    }));
  };
  const before = await accepted();
  let writes = 0;
  page.on("request", (r) => {
    if (r.url().includes("/api/research/") && r.method() !== "GET") writes += 1;
  });
  await page.goto("/portfolio");
  await page
    .locator(`a[href^="/company/${metadata.company_id}"]`)
    .filter({ visible: true })
    .first()
    .click();
  await page.getByRole("tab", { name: "Valuation", exact: true }).click();
  expect(new URL(page.url()).searchParams.get("listing")).toBe(
    metadata.stock_listing_id,
  );
  expect(new URL(page.url()).searchParams.get("from")).toBe("portfolio");
  await expect(page.getByLabel("Accepted model / listing")).toBeVisible();

  for (const [key, modelId, basis] of [
    ["dcf", metadata.dcf_model_id, "Enterprise return basis"],
    ["owner", metadata.owner_model_id, "Equity return basis"],
    ["residual", metadata.residual_model_id, "Equity return basis"],
  ]) {
    await page
      .getByLabel("Accepted model / listing")
      .selectOption(`native:${modelId}`);
    const panel = page.getByRole("region", { name: "Return hurdle explorer" });
    await panel
      .getByRole("button", { name: "Explore required return" })
      .click();
    await expect(panel.getByLabel("Required annual return (%)")).toHaveValue(
      "",
    );
    await panel.getByLabel("Required annual return (%)").fill("10");
    await panel
      .getByLabel("Hypothetical entry price (USD, optional)")
      .fill("5");
    const response = page.waitForResponse((r) =>
      r.url().includes(`/financial-models/${modelId}/return-hurdle?`),
    );
    await panel.getByRole("button", { name: "Calculate entry value" }).click();
    const resultResponse = await response;
    expect(resultResponse.status()).toBe(200);
    const result = await resultResponse.json();
    expect(result.model_id).toBe(modelId);
    expect(result.required_return).toBe("0.1");
    expect(Number(result.reconciled_irr)).toBeCloseTo(0.1, 12);
    expect(result.hypothetical_status).toBe("AVAILABLE");
    expect(result.cash_flows).toHaveLength(10);
    await expect(panel.getByText(basis, { exact: true })).toBeVisible();
    await expect(
      panel.getByText("Model entry price at selected return", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByText("Modeled return at your entry price", { exact: true }),
    ).toBeVisible();
    if (unpriced) {
      expect(result.current_price).toBeNull();
      await expect(
        panel.getByText(/Observed market comparison unavailable/),
      ).toBeVisible();
    } else {
      expect(result.current_price).not.toBeNull();
      await expect(
        panel.getByRole("heading", { name: "Observed market context" }),
      ).toBeVisible();
    }
    await page
      .getByLabel("Appearance")
      .selectOption(key === "dcf" ? "light" : "dark");
    await panel.scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await panel.screenshot({
      path: info.outputPath(`${metadata.scenario}-${key}.png`),
      scale: "css",
    });
    await panel
      .getByText("Method, cash flows and source evidence", { exact: true })
      .click();
    await expect(
      panel.getByText(result.revision_id, { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByText(/Forecast years below are model ordinals/),
    ).toBeVisible();
    if (key === "dcf") {
      await panel.getByLabel("Required annual return (%)").fill("12");
      await expect(
        panel.getByText("Model entry price at selected return", {
          exact: true,
        }),
      ).toHaveCount(0);
      await expect(panel.getByText(/Inputs changed/)).toBeVisible();
      const updated = page.waitForResponse((r) =>
        r.url().includes(`/financial-models/${modelId}/return-hurdle?`),
      );
      await panel
        .getByRole("button", { name: "Calculate entry value" })
        .click();
      const updatedResult = await (await updated).json();
      expect(Number(updatedResult.weighted_entry_price)).toBeLessThan(
        Number(result.weighted_entry_price),
      );
    }
  }
  await page.getByRole("link", { name: "← Back to holdings" }).click();
  await expect(page).toHaveURL(/\/portfolio#portfolio-holdings$/);
  expect(writes).toBe(0);
  expect(await accepted()).toEqual(before);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(metadata.protected_state_sha256);
});
