import { expect, test } from "@playwright/test";
import {
  isLedgerCandidate,
  isPortfolioLedgerAnchor,
} from "../src/lib/domain-contracts";

test.skip(
  process.env.E2E_LEDGER_REVIEW_API !== "1",
  "Requires the isolated ledger-receipt browser fixture",
);
test.setTimeout(90_000);

test("guided non-anchor purchase and ending statements reach explicit candidate review", async ({
  page,
  request,
}, info) => {
  if (info.config.workers !== 1)
    throw new Error("Use one worker for the shared isolated receipt fixture");
  const api = "http://127.0.0.1:8015";
  if (
    process.env.BROWSER_API_PORT !== "8015" ||
    process.env.API_BASE_URL !== api
  )
    throw new Error("Use the exact isolated loopback fixture");
  const before = await (await request.get(`${api}/__test/fixture`)).json();
  expect(before.test_only).toBe("portfolio-data-v1");
  expect(before.ledger_receipts_only).toBe(true);
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  const path = `/api/research/portfolios/${before.portfolio_id}/ledger`;
  const anchor: unknown = await (await request.get(`${path}/anchor`)).json();
  if (!isPortfolioLedgerAnchor(anchor))
    throw new Error("Synthetic anchor could not be verified");
  expect(
    anchor.listings.some(
      (listing) => listing.listing_id === before.unheld_listing_id,
    ),
  ).toBe(false);
  const errors: string[] = [];
  const posts: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (req) => {
    if (req.method() === "POST") posts.push(new URL(req.url()).pathname);
  });
  await page.goto("/portfolio/ledger");
  await page
    .getByRole("button", { name: "Add opening account", exact: true })
    .click();
  await page
    .getByLabel("Account name", { exact: true })
    .fill(`Synthetic ${info.project.name} account`);
  await page
    .getByLabel("Broker name", { exact: true })
    .fill("Synthetic broker");
  await page
    .getByLabel("Statement reference", { exact: true })
    .fill(`opening-${info.project.name}`);
  await page
    .getByLabel("Source document SHA-256", { exact: true })
    .fill("b".repeat(64));
  for (const [index, position] of anchor.snapshot.positions.entries()) {
    await page
      .getByRole("button", { name: "Add position", exact: true })
      .click();
    await page
      .getByRole("combobox", {
        name: `Position ${index + 1} listing`,
        exact: true,
      })
      .selectOption(position.listing_id);
    await page
      .getByLabel(`Position ${index + 1} quantity`, { exact: true })
      .fill(position.quantity!);
  }
  for (const [index, balance] of anchor.snapshot.cash_positions.entries()) {
    await page
      .getByRole("button", { name: "Add cash balance", exact: true })
      .click();
    await page
      .getByLabel(`Cash ${index + 1} currency`, { exact: true })
      .fill(balance.currency);
    await page
      .getByLabel(`Cash ${index + 1} balance`, { exact: true })
      .fill(balance.balance!);
  }
  await page
    .getByLabel(
      "I confirm the entered source balances are as of the observed anchor date.",
      { exact: true },
    )
    .check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get(`${api}/__test/fixture`)).json())
      .protected_state_sha256,
  ).toBe(before.protected_state_sha256);
  // An unexpected ending-only holding must be observable without inventing a trade.
  await page
    .getByRole("button", { name: "Add ending statement", exact: true })
    .click();
  await page.getByLabel("Exact listing ticker", { exact: true }).fill("SYNNEW");
  await page.getByLabel("Exact listing ticker", { exact: true }).press("Enter");
  await page
    .getByRole("button", { name: "Use this listing", exact: true })
    .click();
  await expect(
    page.getByLabel("Additional selected ending listings"),
  ).toContainText("Demo data at lookup");
  await page
    .getByLabel("Statement SHA-256", { exact: true })
    .fill("d".repeat(64));
  await page
    .getByLabel("Statement record reference", { exact: true })
    .fill(`unexpected-${info.project.name}`);
  for (const [index, position] of [
    ...anchor.snapshot.positions,
    { listing_id: before.unheld_listing_id, quantity: "0.5000000000" },
  ].entries()) {
    await page
      .getByRole("button", { name: "Add ending position", exact: true })
      .click();
    await page
      .getByRole("combobox", {
        name: `Ending position ${index + 1} listing`,
        exact: true,
      })
      .selectOption(position.listing_id);
    await page
      .getByLabel(`Ending position ${index + 1} quantity`, { exact: true })
      .fill(position.quantity!);
  }
  for (const [index, cash] of anchor.snapshot.cash_positions.entries()) {
    await page
      .getByRole("button", { name: "Add ending cash", exact: true })
      .click();
    await page
      .getByLabel(`Ending cash ${index + 1} currency`, { exact: true })
      .fill(cash.currency);
    await page
      .getByLabel(`Ending cash ${index + 1} balance`, { exact: true })
      .fill(cash.balance!);
  }
  await page
    .getByLabel(
      "I confirm these ending observations are effective at the review cutoff.",
      { exact: true },
    )
    .check();
  await page
    .getByRole("heading", { name: "Ending statement", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ending-unexpected-listing.png"),
    fullPage: true,
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // Verify the ending builder forwards the selected identity to the drift guard.
  await page.route(
    "**/ledger/preview",
    async (route) => {
      const response = await route.fetch();
      const result = await response.json();
      const item = result.consumed_listings.find(
        (row: { listing_id: string }) =>
          row.listing_id === before.unheld_listing_id,
      );
      if (!item) throw new Error("Synthetic ending identity was not returned");
      item.identity_source_ref = "synthetic-drift";
      await route.fulfill({ response, json: result });
    },
    { times: 1 },
  );
  await page
    .getByRole("button", { name: "Reconcile ending statement", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "listing identity is missing or changed",
  );
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  const unexpectedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/ledger/preview") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Reconcile ending statement", exact: true })
    .click();
  const unexpected = await (await unexpectedResponse).json();
  expect(unexpected.status).toBe("BLOCKED");
  expect(unexpected.ending_status).toBe("MISMATCH");
  expect(
    unexpected.ending_reconciliation.some(
      (row: { key: string; status: string }) =>
        row.key === before.unheld_listing_id && row.status !== "MATCH",
    ),
  ).toBe(true);
  expect(
    unexpected.consumed_listings.some(
      (row: { listing_id: string }) =>
        row.listing_id === before.unheld_listing_id,
    ),
  ).toBe(true);
  await expect(page.getByText("Review blocked", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Discard ending statement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add settled activity", exact: true })
    .click();
  await page.getByLabel("Exact listing ticker", { exact: true }).fill("SYNNEW");
  await page.getByLabel("Exact listing ticker", { exact: true }).press("Enter");
  await expect(
    page.getByText(/SYNNEW · XNYS · USD · ETF · Demo data/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Use this listing", exact: true })
    .click();
  const cutoff = new Date().toISOString();
  await page
    .getByLabel("Review cutoff timestamp", { exact: true })
    .fill(cutoff);
  await page
    .getByRole("button", { name: "Add activity record", exact: true })
    .click();
  const accountOption = await page
    .getByRole("combobox", { name: "Account", exact: true })
    .locator("option")
    .nth(1)
    .getAttribute("value");
  if (!accountOption) throw new Error("Synthetic brokerage is unavailable");
  await page
    .getByRole("combobox", { name: "Account", exact: true })
    .selectOption(accountOption);
  await page
    .getByRole("combobox", { name: "Type", exact: true })
    .selectOption("BUY");
  await page.getByLabel("Booking timestamp", { exact: true }).fill(cutoff);
  await page.getByLabel("Sequence", { exact: true }).fill("1");
  await page.getByLabel("Currency", { exact: true }).fill("USD");
  await page
    .getByRole("combobox", { name: "Listing", exact: true })
    .selectOption(before.unheld_listing_id);
  await page.getByLabel("Quantity", { exact: true }).fill("0.5000000000");
  await page.getByLabel("Gross settlement cash", { exact: true }).fill("1.00");
  await page.getByLabel("Fees", { exact: true }).fill("0.10");
  await page.getByLabel("Taxes", { exact: true }).fill("0.05");
  await page
    .getByLabel("Trade date", { exact: true })
    .fill(cutoff.slice(0, 10));
  await page
    .getByLabel("Settlement date", { exact: true })
    .fill(cutoff.slice(0, 10));
  await page
    .getByLabel("Source document SHA-256", { exact: true })
    .last()
    .fill("c".repeat(64));
  await page
    .getByLabel("Source record reference", { exact: true })
    .fill(`purchase-${info.project.name}`);
  await page
    .getByRole("button", { name: "Review activity", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add ending statement", exact: true })
    .click();
  await page
    .getByLabel("Statement SHA-256", { exact: true })
    .fill("d".repeat(64));
  await page
    .getByLabel("Statement record reference", { exact: true })
    .fill(`ending-${info.project.name}`);
  const positions = [
    ...anchor.snapshot.positions,
    { listing_id: before.unheld_listing_id, quantity: "0.5000000000" },
  ];
  for (const [index, position] of positions.entries()) {
    await page
      .getByRole("button", { name: "Add ending position", exact: true })
      .click();
    await page
      .getByRole("combobox", {
        name: `Ending position ${index + 1} listing`,
        exact: true,
      })
      .selectOption(position.listing_id);
    await page
      .getByLabel(`Ending position ${index + 1} quantity`, { exact: true })
      .fill(position.quantity!);
  }
  for (const [index, cash] of anchor.snapshot.cash_positions.entries()) {
    await page
      .getByRole("button", { name: "Add ending cash", exact: true })
      .click();
    await page
      .getByLabel(`Ending cash ${index + 1} currency`, { exact: true })
      .fill(cash.currency);
    await page
      .getByLabel(`Ending cash ${index + 1} balance`, { exact: true })
      .fill(cash.currency === "USD" ? "3.8500000000" : cash.balance!);
  }
  await page
    .getByLabel(
      "I confirm these ending observations are effective at the review cutoff.",
      { exact: true },
    )
    .check();
  const endingPreview = page.waitForResponse(
    (response) =>
      response.url().endsWith("/ledger/preview") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Reconcile ending statement", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  const reviewedPreview = await (await endingPreview).json();
  await page
    .getByRole("button", { name: "Inspect source evidence", exact: true })
    .click();
  const drawer = page.getByRole("dialog");
  await drawer
    .getByText("Preview listing identities (3)", { exact: true })
    .click();
  await expect(
    drawer.getByText(`Listing ${before.unheld_listing_id}`, { exact: true }),
  ).toBeVisible();
  await expect(
    drawer.getByText("Identity source synthetic-browser-identity", {
      exact: true,
    }),
  ).toBeVisible();
  await drawer
    .getByRole("button", { name: "Close details", exact: true })
    .click();
  await page
    .getByLabel("Candidate reason", { exact: true })
    .fill(`Synthetic ${info.project.name} guided review`);
  await page
    .getByRole("button", { name: "Save candidate for review", exact: true })
    .click();
  const article = page.getByRole("article", { name: "Saved ledger candidate" });
  await expect(
    article.getByRole("heading", { name: /PENDING candidate/ }),
  ).toBeVisible();
  await expect(
    article.getByRole("button", { name: "Review acceptance", exact: true }),
  ).toBeDisabled();
  await article
    .getByLabel("Decision rationale")
    .fill("Synthetic source and account review");
  for (const checkbox of await article.getByRole("checkbox").all())
    await checkbox.check();
  await article
    .getByRole("button", { name: "Review acceptance", exact: true })
    .click();
  await article
    .getByRole("group", { name: "Confirm ledger decision" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("guided-native-review.png"),
    fullPage: true,
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // The projects share one synthetic portfolio: desktop cancels before the
  // terminal decision, then mobile performs the only acceptance.
  if (info.project.name === "desktop") {
    await article
      .getByRole("button", { name: "Cancel decision", exact: true })
      .click();
  } else {
    await article
      .getByRole("button", { name: "Confirm acceptance", exact: true })
      .click();
    await expect(
      article.getByRole("status", { name: "Ledger decision receipt" }),
    ).toContainText("Reviewed revision");
  }
  const history = await (await request.get(`${path}/candidates`)).json();
  const row = history.candidates.find(
    (item: { reason: string }) =>
      item.reason === `Synthetic ${info.project.name} guided review`,
  );
  if (!row) throw new Error("Synthetic candidate is missing from history");
  const detailResponse = await request.get(`${path}/candidates/${row.id}`);
  if (!detailResponse.ok()) {
    const direct = await request.get(
      `${api}/v1/portfolios/${before.portfolio_id}/ledger/candidates/${row.id}`,
    );
    throw new Error(
      `Synthetic candidate readback failed: proxy ${detailResponse.status()}, direct ${direct.status()}`,
    );
  }
  const saved: unknown = await detailResponse.json();
  if (!isLedgerCandidate(saved))
    throw new Error("Invalid synthetic saved candidate");
  expect(saved.status).toBe(
    info.project.name === "desktop" ? "PENDING" : "ACCEPTED",
  );
  const purchase = saved.packet.activity[0];
  if (purchase.kind !== "BUY")
    throw new Error("Saved synthetic purchase is missing");
  expect(purchase.listing_id).toBe(before.unheld_listing_id);
  expect(purchase.quantity).toMatch(/^0\.5(?:0+)?$/);
  expect(purchase.gross_cash).toMatch(/^1(?:\.0+)?$/);
  expect(purchase.fees).toMatch(/^0\.1(?:0+)?$/);
  expect(purchase.taxes).toMatch(/^0\.05(?:0+)?$/);
  expect(purchase.evidence).toEqual({
    source_sha256: "c".repeat(64),
    source_record_id: `purchase-${info.project.name}`,
  });
  expect(saved.input_sha256).toBe(reviewedPreview.input_sha256);
  expect(saved.preview.anchor_sha256).toBe(anchor.anchor_sha256);
  expect(
    saved.preview.consumed_listings.some(
      (listing) => listing.listing_id === before.unheld_listing_id,
    ),
  ).toBe(true);
  expect(
    saved.preview.cash.find((row) => row.currency === "USD")?.balance,
  ).toMatch(/^3\.85(?:0+)?$/);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(before.protected_state_sha256);
  expect(posts.filter((path) => path.endsWith("/review"))).toHaveLength(
    info.project.name === "desktop" ? 0 : 1,
  );
  expect(
    posts.every(
      (path) =>
        path.endsWith("/preview") ||
        path.endsWith("/candidates") ||
        path.endsWith("/review"),
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
