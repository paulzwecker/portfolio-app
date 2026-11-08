import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import {
  ledgerAnchor,
  ledgerPortfolioId,
  ledgerReport,
} from "./fixtures/ledger";
import { isPortfolioLedgerPreview } from "../src/lib/domain-contracts";

const previewPath = `/api/research/portfolios/${ledgerPortfolioId}/ledger/preview`;
const acknowledgement =
  "I confirm the entered source balances are as of the observed anchor date.";

async function setup(page: Page, status = 200) {
  const calls: { path: string; text: string }[] = [];
  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: {
        status: "ok",
        database: "connected",
        schema: "current",
        checked_at: ledgerAnchor.snapshot.effective_at,
      },
    }),
  );
  await page.route("**/api/research/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET") {
      const text = request.postData() ?? "";
      calls.push({ path, text });
      if (path !== previewPath)
        return route.fulfill({
          status: 403,
          json: { detail: "Synthetic read-only test" },
        });
      if (status !== 200)
        return route.fulfill({
          status,
          json: { detail: "Synthetic changed anchor" },
        });
      const packet = JSON.parse(text);
      const report = ledgerReport();
      report.contract_version = "portfolio-ledger-preview-v2";
      report.projection_version = "settled-booking-v2";
      report.as_of = ledgerAnchor.snapshot.effective_at;
      report.status = "OPENING_RECONCILED";
      report.ending_status = "NOT_PROVIDED";
      report.ending_statement_at = null;
      report.ending_reconciliation = [];
      report.accounts[0].account_id = packet.accounts[0].account_id;
      expect(isPortfolioLedgerPreview(report)).toBe(true);
      return route.fulfill({ json: report });
    }
    if (path === "/api/research/portfolios")
      return route.fulfill({
        json: [
          {
            id: ledgerPortfolioId,
            name: "Synthetic portfolio",
            base_currency: "EUR",
            created_at: ledgerAnchor.snapshot.effective_at,
            is_demo: false,
          },
        ],
      });
    if (path.endsWith("/ledger/anchor"))
      return route.fulfill({ json: ledgerAnchor });
    if (path.endsWith("/ledger/candidates"))
      return route.fulfill({
        json: {
          portfolio_id: ledgerPortfolioId,
          current_accepted_candidate_id: null,
          current_revision_number: 0,
          candidates: [],
        },
      });
    return route.fulfill({
      status: 404,
      json: { detail: "Unknown synthetic read" },
    });
  });
  await page.goto("/portfolio/ledger");
  await expect(
    page.getByText("Build an opening review", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add opening account", exact: true })
    .click();
  await page
    .getByLabel("Account name", { exact: true })
    .fill("Synthetic account");
  await page
    .getByLabel("Broker name", { exact: true })
    .fill("Synthetic broker");
  await page
    .getByLabel("Statement reference", { exact: true })
    .fill("synthetic-opening-1");
  await page
    .getByLabel("Source document SHA-256", { exact: true })
    .fill("b".repeat(64));
  await page.getByRole("button", { name: "Add position", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Position 1 listing", exact: true })
    .selectOption(ledgerAnchor.listings[0].listing_id);
  await page
    .getByLabel("Position 1 quantity", { exact: true })
    .fill("2.5000000000");
  for (const [index, currency, balance] of [
    [1, "USD", "100.0000000000"],
    [2, "EUR", "0"],
  ] as const) {
    await page
      .getByRole("button", { name: "Add cash balance", exact: true })
      .click();
    await page
      .getByLabel(`Cash ${index} currency`, { exact: true })
      .fill(currency);
    await page
      .getByLabel(`Cash ${index} balance`, { exact: true })
      .fill(balance);
  }
  return calls;
}

test("guided opening balances reconcile, download and replay exact private input", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const calls = await setup(page);
  await expect(
    page.getByRole("option", { name: "XETRA · SYNF · USD · ETF", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("button", {
      name: "Reconcile opening balances",
      exact: true,
    }),
  ).toBeDisabled();
  const statement = Buffer.from("Synthetic statement bytes only");
  await page
    .getByLabel("Hash a private statement file", { exact: true })
    .setInputFiles({
      name: "synthetic-statement.txt",
      mimeType: "text/plain",
      buffer: statement,
    });
  const digest = createHash("sha256").update(statement).digest("hex");
  await expect(
    page.getByLabel("Source document SHA-256", { exact: true }),
  ).toHaveValue(digest);
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls).toHaveLength(1);
  const packet = JSON.parse(calls[0].text);
  expect(packet.anchor_sha256).toBe(ledgerAnchor.anchor_sha256);
  expect(packet.as_of).toBe(ledgerAnchor.snapshot.effective_at);
  expect(packet.activity).toEqual([]);
  expect(packet.ending_statement).toBeNull();
  expect(packet.accounts[0].evidence).toEqual({
    source_sha256: digest,
    source_record_id: "synthetic-opening-1",
  });
  expect(packet.accounts[0].positions).toEqual([
    {
      listing_id: ledgerAnchor.listings[0].listing_id,
      quantity: "2.5000000000",
    },
  ]);
  expect(packet.accounts[0].cash).toEqual([
    { currency: "USD", balance: "100.0000000000" },
    { currency: "EUR", balance: "0" },
  ]);
  expect(calls[0].text).not.toContain(statement.toString());
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download private review JSON", exact: true })
    .click();
  const download = await downloadEvent;
  const downloadedPath = await download.path();
  if (!downloadedPath) throw new Error("Synthetic review download missing");
  expect(await readFile(downloadedPath, "utf8")).toBe(calls[0].text);
  await page
    .getByLabel("Ledger review JSON", { exact: true })
    .setInputFiles(downloadedPath);
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls[1].text).toBe(calls[0].text);
  await page.getByLabel("Differences only", { exact: true }).uncheck();
  for (const appearance of ["light", "dark"]) {
    await page
      .getByRole("combobox", { name: "Appearance", exact: true })
      .selectOption(appearance);
    await page
      .getByRole("heading", { name: "2. Review opening balances", exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: info.outputPath(`opening-${appearance}.png`),
      fullPage: true,
      scale: "css",
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.getByLabel("Position 1 quantity", { exact: true }).fill("2.5");
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("textbox", { name: "Candidate reason", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByLabel(acknowledgement, { exact: true }),
  ).not.toBeChecked();
  await expect(
    page.getByRole("button", {
      name: "Reconcile opening balances",
      exact: true,
    }),
  ).toBeDisabled();
  expect(calls.map((call) => call.path)).toEqual([previewPath, previewPath]);
  await page
    .getByRole("button", { name: "Clear opening draft", exact: true })
    .click();
  await expect(
    page.getByRole("group", { name: "Opening account 1", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByLabel("Replace draft from downloaded opening review JSON", {
      exact: true,
    })
    .setInputFiles(downloadedPath);
  await expect(
    page.getByLabel("Position 1 quantity", { exact: true }),
  ).toHaveValue("2.5000000000");
  await expect(page.getByLabel("Cash 2 balance", { exact: true })).toHaveValue(
    "0",
  );
  await expect(
    page.getByLabel(acknowledgement, { exact: true }),
  ).not.toBeChecked();
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls[2].text).toBe(calls[0].text);
  expect(errors).toEqual([]);
});

test("opening source errors and changed anchors cannot become a reviewed result", async ({
  page,
}) => {
  const calls = await setup(page, 409);
  await page.getByLabel("Position 1 quantity", { exact: true }).fill("");
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "exact nonnegative decimal text",
  );
  expect(calls).toHaveLength(0);
  await page
    .getByLabel("Position 1 quantity", { exact: true })
    .fill("2.5000000000");
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "current anchor changed",
  );
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("textbox", { name: "Candidate reason", exact: true }),
  ).toHaveCount(0);
  expect(calls.map((call) => call.path)).toEqual([previewPath]);
});

test("late statement hashing cannot replace a manually reviewed source hash", async ({
  page,
}) => {
  await setup(page);
  await page.evaluate(() => {
    const original = crypto.subtle.digest.bind(crypto.subtle);
    const state = window as Window & {
      finishOpeningHash?: () => void;
      openingHashFinished?: boolean;
    };
    const gate = new Promise<void>((resolve) => {
      state.finishOpeningHash = resolve;
    });
    crypto.subtle.digest = async (...args) => {
      await gate;
      const digest = await original(...args);
      state.openingHashFinished = true;
      return digest;
    };
  });
  await page
    .getByLabel("Hash a private statement file", { exact: true })
    .setInputFiles({
      name: "synthetic.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Synthetic only"),
    });
  await expect(
    page.getByText("Hashing private statement…", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Source document SHA-256", { exact: true })
    .fill("e".repeat(64));
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page.evaluate(() =>
    (
      window as Window & { finishOpeningHash?: () => void }
    ).finishOpeningHash?.(),
  );
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as Window & { openingHashFinished?: boolean })
            .openingHashFinished,
      ),
    )
    .toBe(true);
  await expect(
    page.getByLabel("Source document SHA-256", { exact: true }),
  ).toHaveValue("e".repeat(64));
  await expect(page.getByLabel(acknowledgement, { exact: true })).toBeChecked();
  await expect(
    page.getByText("Hashing private statement…", { exact: true }),
  ).toHaveCount(0);
});

test("a rejected replacement keeps the draft but clears its previous review", async ({
  page,
}) => {
  const calls = await setup(page);
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Replace draft from downloaded opening review JSON", {
      exact: true,
    })
    .setInputFiles({
      name: "invalid.json",
      mimeType: "application/json",
      buffer: Buffer.from('{"activity":[1]}'),
    });
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "unchanged opening review JSON",
  );
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByLabel("Position 1 quantity", { exact: true }),
  ).toHaveValue("2.5000000000");
  expect(calls).toHaveLength(1);
});

test("restoring the same account cannot reuse an earlier pending hash", async ({
  page,
}) => {
  const calls = await setup(page);
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  const saved = calls[0].text;
  await page.evaluate(() => {
    const original = crypto.subtle.digest.bind(crypto.subtle);
    const state = window as Window & {
      releaseHash?: (() => void)[];
      finishedHashes?: number;
    };
    state.releaseHash = [];
    state.finishedHashes = 0;
    crypto.subtle.digest = async (...args) => {
      await new Promise<void>((resolve) => state.releaseHash!.push(resolve));
      const digest = await original(...args);
      state.finishedHashes! += 1;
      return digest;
    };
  });
  const statement = page.getByLabel("Hash a private statement file", {
    exact: true,
  });
  await statement.setInputFiles({
    name: "old.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("old"),
  });
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as Window & { releaseHash?: (() => void)[] }).releaseHash
            ?.length,
      ),
    )
    .toBe(1);
  await page
    .getByLabel("Replace draft from downloaded opening review JSON", {
      exact: true,
    })
    .setInputFiles({
      name: "opening.json",
      mimeType: "application/json",
      buffer: Buffer.from(saved),
    });
  await expect(
    page.getByLabel("Source document SHA-256", { exact: true }),
  ).toHaveValue("b".repeat(64));
  const newBytes = Buffer.from("new statement");
  await statement.setInputFiles({
    name: "new.txt",
    mimeType: "text/plain",
    buffer: newBytes,
  });
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as Window & { releaseHash?: (() => void)[] }).releaseHash
            ?.length,
      ),
    )
    .toBe(2);
  await page.evaluate(() =>
    (window as Window & { releaseHash?: (() => void)[] }).releaseHash![0](),
  );
  await expect
    .poll(() =>
      page.evaluate(
        () => (window as Window & { finishedHashes?: number }).finishedHashes,
      ),
    )
    .toBe(1);
  await expect(
    page.getByLabel("Source document SHA-256", { exact: true }),
  ).toHaveValue("");
  await expect(
    page.getByText("Hashing private statement…", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() =>
    (window as Window & { releaseHash?: (() => void)[] }).releaseHash![1](),
  );
  await expect(
    page.getByLabel("Source document SHA-256", { exact: true }),
  ).toHaveValue(createHash("sha256").update(newBytes).digest("hex"));
});
