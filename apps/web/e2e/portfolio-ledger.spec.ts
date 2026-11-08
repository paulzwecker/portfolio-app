import { expect, test } from "@playwright/test";
import { isPortfolioLedgerAnchor } from "../src/lib/domain-contracts";
import { ledgerPacket } from "./fixtures/ledger";

test.skip(
  process.env.E2E_REAL_API !== "1",
  "Requires the isolated read-only portfolio API fixture.",
);

test("private ledger source reconciles through the real API with exact ending differences", async ({
  page,
  request,
}, info) => {
  const port = process.env.BROWSER_API_PORT ?? "8011";
  if (!/^\d+$/.test(port) || Number(port) < 1024 || Number(port) > 65535)
    throw new Error("Use an explicit local fixture port.");
  const api = `http://127.0.0.1:${port}`;
  if (process.env.API_BASE_URL?.replace(/\/$/, "") !== api)
    throw new Error("API_BASE_URL must match the loopback fixture.");
  const identity = await (await request.get(`${api}/__test/fixture`)).json();
  expect(identity.test_only).toBe("portfolio-data-v1");
  expect(identity.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  const anchorResponse = await request.get(
    `/api/research/portfolios/${identity.portfolio_id}/ledger/anchor`,
  );
  expect(anchorResponse.status()).toBe(200);
  const anchor: unknown = await anchorResponse.json();
  if (!isPortfolioLedgerAnchor(anchor))
    throw new Error("The real anchor failed validation.");
  const previewPath = `/api/research/portfolios/${identity.portfolio_id}/ledger/preview`;
  const calls: string[] = [];
  const errors: string[] = [];
  page.on("request", (req) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(req.method()))
      calls.push(`${req.method()} ${new URL(req.url()).pathname}`);
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/portfolio");
  await page.getByRole("link", { name: "Ledger review", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Transaction ledger review",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.locator("a[href='/portfolio'][aria-current='page']").first(),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    page.getByRole("button", { name: "Validate and reconcile", exact: true }),
  ).toBeDisabled();
  const packet = ledgerPacket(anchor, new Date().toISOString());
  packet.anchor_snapshot_id = packet.anchor_snapshot_id.toUpperCase();
  packet.accounts[0].account_id = "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF";
  packet.ending_statement.accounts[0].account_id =
    packet.accounts[0].account_id;
  const usd = packet.accounts[0].cash.find(
    (row) => row.currency === "USD",
  )?.balance;
  if (usd === null || usd === undefined)
    throw new Error("The fictional fixture needs explicit USD cash.");
  packet.activity.push({
    id: "88888888-8888-4888-8888-888888888888",
    account_id: packet.accounts[0].account_id,
    kind: "WITHDRAWAL",
    sequence: 1,
    effective_at: packet.as_of,
    currency: "USD",
    amount: usd,
    evidence: {
      source_sha256: "e".repeat(64),
      source_record_id: "synthetic-withdrawal",
    },
  });
  const ending = packet.ending_statement.accounts[0];
  ending.cash.find((row) => row.currency === "USD")!.balance = "0";
  const upload = async (name: string) =>
    page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
      name,
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(packet)),
    });
  await upload("synthetic-ledger.json");
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Differences only", { exact: true }).uncheck();
  const table =
    info.project.name === "mobile"
      ? page.getByLabel("Ledger balance comparison, mobile view", {
          exact: true,
        })
      : page.getByRole("table", {
          name: "Ledger balance comparison",
          exact: true,
        });
  await expect(table.getByText("USD cash", { exact: true })).toBeVisible();
  await expect(table.getByText("0", { exact: true }).first()).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect source evidence", exact: true })
    .click();
  const drawer = page.getByRole("dialog", {
    name: "Ledger source and replay evidence",
    exact: true,
  });
  await expect(
    drawer.getByText(anchor.anchor_sha256, { exact: true }),
  ).toBeVisible();
  await drawer.getByText(/Source records/).click();
  await expect(
    drawer.getByText("synthetic-withdrawal", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("ledger-evidence.png"),
    scale: "css",
  });
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Inspect source evidence", exact: true }),
  ).toBeFocused();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: info.outputPath("ledger-matched.png"),
    fullPage: true,
    scale: "css",
  });

  ending.cash = ending.cash.filter((row) => row.currency !== "USD");
  await upload("synthetic-missing-zero.json");
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(page.getByText("Review blocked", { exact: true })).toBeVisible();
  await expect(
    table.getByText("Missing", { exact: true }).first(),
  ).toBeVisible();
  await expect(table.getByText("0", { exact: true }).first()).toBeVisible();
  await page
    .getByRole("combobox", { name: "Account scope", exact: true })
    .selectOption(packet.accounts[0].account_id.toLowerCase());
  await expect(
    table.getByText("MISSING OBSERVATION", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: info.outputPath("ledger-missing-zero.png"),
    fullPage: true,
    scale: "css",
  });
  await page
    .getByRole("button", { name: "Clear private file", exact: true })
    .click();
  await expect(page.getByText("Review blocked", { exact: true })).toHaveCount(
    0,
  );
  await page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
    name: "invalid.json",
    mimeType: "application/json",
    buffer: Buffer.from("{private-invalid"),
  });
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Choose a valid ledger review JSON file",
  );
  packet.anchor_sha256 = "f".repeat(64);
  await upload("stale-anchor.json");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "different or stale anchor",
  );
  await expect(
    page.getByRole("button", { name: "Validate and reconcile", exact: true }),
  ).toBeDisabled();
  expect(calls).toEqual([`POST ${previewPath}`, `POST ${previewPath}`]);
  expect(errors).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(identity.protected_state_sha256);
});

test("clearing a pending private review cannot restore a late result", async ({
  page,
  request,
}) => {
  const port = process.env.BROWSER_API_PORT ?? "8011";
  if (
    !/^\d+$/.test(port) ||
    process.env.API_BASE_URL !== `http://127.0.0.1:${port}`
  )
    throw new Error("Use the local fixture API.");
  const api = `http://127.0.0.1:${port}`;
  const identity = await (await request.get(`${api}/__test/fixture`)).json();
  expect(identity.test_only).toBe("portfolio-data-v1");
  const data: unknown = await (
    await request.get(
      `/api/research/portfolios/${identity.portfolio_id}/ledger/anchor`,
    )
  ).json();
  if (!isPortfolioLedgerAnchor(data))
    throw new Error("The real anchor failed validation.");
  let release: (() => void) | undefined;
  let capturedStatus = 0;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(
    `**/api/research/portfolios/${identity.portfolio_id}/ledger/preview`,
    async (route) => {
      const response = await route.fetch();
      capturedStatus = response.status();
      await pending;
      await route.fulfill({ response }).catch(() => {});
    },
  );
  await page.goto("/portfolio/ledger");
  const packet = ledgerPacket(data, new Date().toISOString());
  await page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
    name: "pending.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(packet)),
  });
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Validating ledger…", exact: true }),
  ).toBeVisible();
  await expect.poll(() => capturedStatus).toBe(200);
  const canceled = page.waitForEvent("requestfailed", (event) =>
    event.url().endsWith("/ledger/preview"),
  );
  await page
    .getByRole("button", { name: "Clear private file", exact: true })
    .click();
  await canceled;
  release?.();
  await expect(
    page.getByRole("button", { name: "Validate and reconcile", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(identity.protected_state_sha256);
});
