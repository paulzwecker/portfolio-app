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
      report.as_of = packet.as_of;
      report.activity_count = packet.activity.length;
      if (packet.activity.length > 0) {
        const hasBuy = packet.activity.some(
          (row: { kind: string }) => row.kind === "BUY",
        );
        const usd = hasBuy ? "89.7500000000" : "101.2500000000";
        report.cash.find((row) => row.currency === "USD")!.balance = usd;
        report.accounts[0].cash.find((row) => row.currency === "USD")!.balance =
          usd;
        if (hasBuy) {
          report.positions[0].quantity = "3.0000000000";
          report.accounts[0].positions[0].quantity = "3.0000000000";
        }
      }
      if (packet.ending_statement) {
        report.status = "ENDING_RECONCILED";
        report.ending_status = "MATCH";
        report.ending_statement_at = packet.as_of;
        report.ending_reconciliation = report.ending_reconciliation.map(
          (row) => ({
            ...row,
            account_id: row.account_id ? packet.accounts[0].account_id : null,
            ...(packet.activity.length > 0 && row.key === "USD"
              ? { projected: "101.2500000000", observed: "101.2500000000" }
              : {}),
          }),
        );
        if (
          !packet.ending_statement.accounts[0].cash.some(
            (row: { currency: string }) => row.currency === "EUR",
          )
        ) {
          report.status = "BLOCKED";
          report.ending_status = "MISMATCH";
          report.issues = [
            {
              code: "ENDING_MISMATCH",
              activity_id: null,
              account_id: null,
              asset_key: "EUR",
            },
          ];
          report.ending_reconciliation = report.ending_reconciliation.map(
            (row) =>
              row.key === "EUR"
                ? {
                    ...row,
                    observed: null,
                    difference: null,
                    status: "MISSING_OBSERVATION",
                  }
                : row,
          );
        }
      } else {
        report.status = "OPENING_RECONCILED";
        report.ending_status = "NOT_PROVIDED";
        report.ending_statement_at = null;
        report.ending_reconciliation = [];
      }
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

test("guided cash activity reviews exact source evidence against a reconciled opening", async ({
  page,
}, info) => {
  const calls = await setup(page);
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add settled activity", exact: true })
    .click();
  await expect(
    page.getByLabel("Ledger review JSON", { exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Reload observed anchor", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Review cutoff timestamp", { exact: true })
    .fill("2026-01-31T23:59:59+01:00");
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Add activity record", exact: true })
    .click();
  const selected = JSON.parse(calls[0].text).accounts[0].account_id;
  await page
    .getByRole("combobox", { name: "Account", exact: true })
    .selectOption(selected);
  await page
    .getByRole("combobox", { name: "Type", exact: true })
    .selectOption("DEPOSIT");
  await page
    .getByLabel("Booking timestamp", { exact: true })
    .fill("2026-01-15T10:30:00+01:00");
  await page.getByLabel("Sequence", { exact: true }).fill("1");
  await page.getByLabel("Currency", { exact: true }).fill("USD");
  await page.getByLabel("Amount", { exact: true }).fill("1.2500000000");
  await page
    .getByLabel("Source document SHA-256", { exact: true })
    .last()
    .fill("c".repeat(64));
  await page
    .getByLabel("Source record reference", { exact: true })
    .fill("synthetic-deposit");
  await page
    .getByRole("button", { name: "Review activity", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls).toHaveLength(2);
  const packet = JSON.parse(calls[1].text);
  expect(packet.accounts).toEqual(JSON.parse(calls[0].text).accounts);
  expect(packet.activity).toEqual([
    {
      id: expect.any(String),
      account_id: selected,
      kind: "DEPOSIT",
      sequence: 1,
      effective_at: "2026-01-15T10:30:00+01:00",
      evidence: {
        source_sha256: "c".repeat(64),
        source_record_id: "synthetic-deposit",
      },
      currency: "USD",
      amount: "1.2500000000",
    },
  ]);
  expect(packet.as_of).toBe("2026-01-31T23:59:59+01:00");
  expect(packet.ending_statement).toBeNull();
  expect(calls.map((call) => call.path)).toEqual([previewPath, previewPath]);
  const projection = page.getByRole("region", {
    name: "Candidate balances at cutoff",
  });
  await expect(
    projection.getByText("101.25", { exact: true }).filter({ visible: true }),
  ).toBeVisible();
  await projection
    .getByRole("combobox", { name: "Projection account" })
    .selectOption(selected);
  await expect(
    projection.getByText("101.25", { exact: true }).filter({ visible: true }),
  ).toBeVisible();
  await page
    .getByRole("heading", { name: "Settled activity", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("cash-activity.png"),
    fullPage: true,
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download private review JSON", exact: true })
    .click();
  const download = await downloadEvent;
  const savedPath = await download.path();
  if (!savedPath) throw new Error("Synthetic cash review download missing");
  expect(await readFile(savedPath, "utf8")).toBe(calls[1].text);
  await page
    .getByRole("button", { name: "Discard activity", exact: true })
    .click();
  await page.reload();
  await page
    .getByLabel("Ledger review JSON", { exact: true })
    .setInputFiles(savedPath);
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls[2].text).toBe(calls[1].text);
  await page
    .getByRole("button", { name: "Edit supported activity", exact: true })
    .click();
  await expect(
    page.getByLabel("Review cutoff timestamp", { exact: true }),
  ).toHaveValue("2026-01-31T23:59:59+01:00");
  await expect(page.getByLabel("Amount", { exact: true })).toHaveValue(
    "1.2500000000",
  );
  await expect(
    page.getByLabel("Source record reference", { exact: true }),
  ).toHaveValue("synthetic-deposit");
  await page
    .getByRole("heading", { name: "Settled activity", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("cash-resumed.png"),
    fullPage: true,
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Review activity", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls[3].text).toBe(calls[1].text);
  await page.getByLabel("Amount", { exact: true }).fill("2");
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("textbox", { name: "Candidate reason", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Discard activity", exact: true })
    .click();
  await expect(
    page.getByLabel("Ledger review JSON", { exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Add opening account", exact: true }),
  ).toBeEnabled();
});

test("independent ending observations reconcile and edits invalidate the result", async ({
  page,
}, info) => {
  const calls = await setup(page);
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add ending statement", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Reload observed anchor", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Ledger review JSON", { exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Statement SHA-256", { exact: true })
    .fill("d".repeat(64));
  await page
    .getByLabel("Statement record reference", { exact: true })
    .fill("ending-observation");
  await page
    .getByRole("button", { name: "Add ending position", exact: true })
    .click();
  await expect(
    page.getByLabel("Ending position 1 quantity", { exact: true }),
  ).toHaveValue("");
  await page
    .getByRole("combobox", { name: "Ending position 1 listing", exact: true })
    .selectOption(ledgerAnchor.listings[0].listing_id);
  await page
    .getByLabel("Ending position 1 quantity", { exact: true })
    .fill("2.5000000000");
  for (const [index, currency, balance] of [
    [1, "USD", "100.0000000000"],
    [2, "EUR", "0"],
  ] as const) {
    await page
      .getByRole("button", { name: "Add ending cash", exact: true })
      .click();
    await page
      .getByLabel(`Ending cash ${index} currency`, { exact: true })
      .fill(currency);
    await page
      .getByLabel(`Ending cash ${index} balance`, { exact: true })
      .fill(balance);
  }
  const confirmed = page.getByLabel(
    "I confirm these ending observations are effective at the review cutoff.",
    { exact: true },
  );
  await confirmed.check();
  await page
    .getByRole("button", { name: "Reconcile ending statement", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls).toHaveLength(2);
  const packet = JSON.parse(calls[1].text);
  expect(packet.accounts).toEqual(JSON.parse(calls[0].text).accounts);
  expect(packet.activity).toEqual([]);
  expect(packet.ending_statement).toEqual({
    effective_at: packet.as_of,
    accounts: [
      {
        account_id: packet.accounts[0].account_id,
        evidence: {
          source_sha256: "d".repeat(64),
          source_record_id: "ending-observation",
        },
        positions: [
          {
            listing_id: ledgerAnchor.listings[0].listing_id,
            quantity: "2.5000000000",
          },
        ],
        cash: [
          { currency: "USD", balance: "100.0000000000" },
          { currency: "EUR", balance: "0" },
        ],
      },
    ],
  });
  await page
    .getByRole("heading", { name: "Ending statement", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ending-statement.png"),
    fullPage: true,
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Remove ending cash 2", exact: true })
    .click();
  await expect(confirmed).not.toBeChecked();
  await confirmed.check();
  await page
    .getByRole("button", { name: "Reconcile ending statement", exact: true })
    .click();
  await expect(page.getByText("Review blocked", { exact: true })).toBeVisible();
  await expect(
    page
      .getByText("MISSING OBSERVATION", { exact: true })
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download private review JSON", exact: true })
    .click();
  const savedPath = await (await downloadEvent).path();
  if (!savedPath) throw new Error("Synthetic ending review download missing");
  expect(await readFile(savedPath, "utf8")).toBe(calls[2].text);
  await page
    .getByRole("button", { name: "Discard ending statement", exact: true })
    .click();
  await page.reload();
  await page
    .getByLabel("Ledger review JSON", { exact: true })
    .setInputFiles(savedPath);
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(page.getByText("Review blocked", { exact: true })).toBeVisible();
  expect(calls[3].text).toBe(calls[2].text);
  await page
    .getByRole("button", {
      name: "Edit supported ending statement",
      exact: true,
    })
    .click();
  await expect(confirmed).not.toBeChecked();
  await expect(
    page.getByLabel("Ending position 1 quantity", { exact: true }),
  ).toHaveValue("2.5000000000");
  await expect(
    page.getByLabel("Ending cash 1 balance", { exact: true }),
  ).toHaveValue("100.0000000000");
  await expect(
    page.getByLabel("Ending cash 2 balance", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByLabel("Statement record reference", { exact: true }),
  ).toHaveValue("ending-observation");
  await page
    .getByRole("heading", { name: "Ending statement", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ending-restored.png"),
    fullPage: true,
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Discard ending statement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(page.getByText("Review blocked", { exact: true })).toBeVisible();
  expect(calls[4].text).toBe(calls[2].text);
  await page
    .getByRole("button", {
      name: "Edit supported ending statement",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Add ending cash", exact: true })
    .click();
  await page.getByLabel("Ending cash 2 currency", { exact: true }).fill("EUR");
  await page.getByLabel("Ending cash 2 balance", { exact: true }).fill("0");
  await confirmed.check();
  await page
    .getByRole("button", { name: "Reconcile ending statement", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Ending cash 2 balance", { exact: true }).fill("1");
  await expect(confirmed).not.toBeChecked();
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Discard ending statement", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Validate and reconcile", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(page.getByText("Review blocked", { exact: true })).toBeVisible();
  expect(calls[6].text).toBe(calls[2].text);
  expect(calls.map((call) => call.path)).toEqual(Array(7).fill(previewPath));
});

test("a reconciled ending packet can be reloaded and edited without changing its evidence", async ({
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
  const packet = JSON.parse(calls[0].text);
  packet.ending_statement = {
    effective_at: packet.as_of,
    accounts: [
      {
        account_id: packet.accounts[0].account_id,
        evidence: { source_sha256: "d".repeat(64), source_record_id: "ending" },
        positions: [
          {
            listing_id: ledgerAnchor.listings[0].listing_id,
            quantity: "2.5000000000",
          },
        ],
        cash: [
          { currency: "USD", balance: "100.0000000000" },
          { currency: "EUR", balance: "0" },
        ],
      },
    ],
  };
  const text = JSON.stringify(packet);
  await page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
    name: "ending.json",
    mimeType: "application/json",
    buffer: Buffer.from(text),
  });
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Edit supported ending statement",
      exact: true,
    })
    .click();
  await expect(
    page.getByLabel("Ending cash 2 balance", { exact: true }),
  ).toHaveValue("0");
  const confirmed = page.getByLabel(
    "I confirm these ending observations are effective at the review cutoff.",
    { exact: true },
  );
  await expect(confirmed).not.toBeChecked();
  await confirmed.check();
  await page
    .getByRole("button", { name: "Reconcile ending statement", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls[2].text).toBe(text);
});

test("a reviewed cash draft can transition to ending observations without losing activity", async ({
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
    .getByRole("button", { name: "Add settled activity", exact: true })
    .click();
  await page
    .getByLabel("Review cutoff timestamp", { exact: true })
    .fill("2026-01-31T23:59:59+01:00");
  await page
    .getByRole("button", { name: "Add activity record", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Account", exact: true })
    .selectOption(JSON.parse(calls[0].text).accounts[0].account_id);
  await page
    .getByRole("combobox", { name: "Type", exact: true })
    .selectOption("DEPOSIT");
  await page
    .getByLabel("Booking timestamp", { exact: true })
    .fill("2026-01-15T10:30:00+01:00");
  await page.getByLabel("Sequence", { exact: true }).fill("1");
  await page.getByLabel("Currency", { exact: true }).fill("USD");
  await page.getByLabel("Amount", { exact: true }).fill("1.2500000000");
  await page
    .getByLabel("Source document SHA-256", { exact: true })
    .last()
    .fill("c".repeat(64));
  await page
    .getByLabel("Source record reference", { exact: true })
    .fill("deposit");
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
    .fill("ending");
  await page
    .getByRole("button", { name: "Add ending position", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Ending position 1 listing", exact: true })
    .selectOption(ledgerAnchor.listings[0].listing_id);
  await page
    .getByLabel("Ending position 1 quantity", { exact: true })
    .fill("2.5000000000");
  for (const [index, currency, balance] of [
    [1, "USD", "101.2500000000"],
    [2, "EUR", "0"],
  ] as const) {
    await page
      .getByRole("button", { name: "Add ending cash", exact: true })
      .click();
    await page
      .getByLabel(`Ending cash ${index} currency`, { exact: true })
      .fill(currency);
    await page
      .getByLabel(`Ending cash ${index} balance`, { exact: true })
      .fill(balance);
  }
  await page
    .getByLabel(
      "I confirm these ending observations are effective at the review cutoff.",
      { exact: true },
    )
    .check();
  await page
    .getByRole("button", { name: "Reconcile ending statement", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  expect(JSON.parse(calls[2].text).activity).toEqual(
    JSON.parse(calls[1].text).activity,
  );
  await page
    .getByRole("button", { name: "Discard ending statement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls[3].text).toBe(calls[1].text);
  await page
    .getByRole("button", { name: "Edit supported activity", exact: true })
    .click();
  await expect(page.getByLabel("Amount", { exact: true })).toHaveValue(
    "1.2500000000",
  );
});

for (const mismatch of ["cutoff", "ending"] as const) {
  test(`preview rejects mismatched ${mismatch} timestamps below one millisecond`, async ({
    page,
  }) => {
    await setup(page);
    await page.route(`**${previewPath}`, async (route) => {
      const packet = JSON.parse(route.request().postData() ?? "{}");
      const report = ledgerReport();
      report.contract_version = "portfolio-ledger-preview-v2";
      report.projection_version = "settled-booking-v2";
      report.as_of =
        mismatch === "cutoff" ? "2026-01-01T00:00:00.000001Z" : packet.as_of;
      report.accounts[0].account_id = packet.accounts[0].account_id;
      if (mismatch === "ending") {
        report.ending_statement_at = "2026-01-01T00:00:00.000001Z";
        report.ending_reconciliation = report.ending_reconciliation.map(
          (row) => ({
            ...row,
            account_id: row.account_id ? packet.accounts[0].account_id : null,
          }),
        );
      } else {
        report.status = "OPENING_RECONCILED";
        report.ending_status = "NOT_PROVIDED";
        report.ending_statement_at = null;
        report.ending_reconciliation = [];
      }
      expect(isPortfolioLedgerPreview(report)).toBe(true);
      await route.fulfill({ json: report });
    });
    await page.getByLabel(acknowledgement, { exact: true }).check();
    await page
      .getByRole("button", { name: "Reconcile opening balances", exact: true })
      .click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(
      "could not be verified",
    );
    await expect(
      page.getByLabel("Ledger review result", { exact: true }),
    ).toHaveCount(0);
  });
}

for (const mismatch of ["account", "activity", "duplicate account"] as const) {
  test(`ending form rejects a preview with mismatched ${mismatch} metadata`, async ({
    page,
  }) => {
    await setup(page);
    await page.route(`**${previewPath}`, async (route) => {
      const packet = JSON.parse(route.request().postData() ?? "{}");
      const report = ledgerReport();
      report.contract_version = "portfolio-ledger-preview-v2";
      report.projection_version = "settled-booking-v2";
      report.as_of = packet.as_of;
      report.status = "OPENING_RECONCILED";
      report.ending_status = "NOT_PROVIDED";
      report.ending_statement_at = null;
      report.ending_reconciliation = [];
      report.accounts[0].account_id =
        mismatch === "account"
          ? "77777777-7777-4777-8777-777777777777"
          : packet.accounts[0].account_id;
      report.activity_count = mismatch === "activity" ? 1 : 0;
      if (mismatch === "duplicate account")
        report.accounts.push({ ...report.accounts[0] });
      expect(isPortfolioLedgerPreview(report)).toBe(true);
      await route.fulfill({ json: report });
    });
    await page.getByLabel(acknowledgement, { exact: true }).check();
    await page
      .getByRole("button", { name: "Reconcile opening balances", exact: true })
      .click();
    await expect(
      page.getByText("Opening balances reconciled", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Add ending statement", exact: true })
      .click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(
      "review does not match the source activity and accounts",
    );
    await expect(
      page.getByRole("heading", { name: "Ending statement", exact: true }),
    ).toHaveCount(0);
  });
}

test("activity failures cannot be treated as ending-only differences", async ({
  page,
}) => {
  await setup(page);
  await page.route(`**${previewPath}`, async (route) => {
    const packet = JSON.parse(route.request().postData() ?? "{}");
    const report = ledgerReport();
    report.contract_version = "portfolio-ledger-preview-v2";
    report.projection_version = "settled-booking-v2";
    report.as_of = packet.as_of;
    report.status = "BLOCKED";
    report.ending_status = "MISMATCH";
    report.ending_statement_at = packet.as_of;
    report.accounts[0].account_id = packet.accounts[0].account_id;
    report.ending_reconciliation = report.ending_reconciliation.map((row) => ({
      ...row,
      account_id: row.account_id ? packet.accounts[0].account_id : null,
    }));
    report.issues = [
      {
        code: "NEGATIVE_CASH",
        activity_id: null,
        account_id: null,
        asset_key: "USD",
      },
      {
        code: "ENDING_MISMATCH",
        activity_id: null,
        account_id: null,
        asset_key: "EUR",
      },
    ];
    expect(isPortfolioLedgerPreview(report)).toBe(true);
    await route.fulfill({ json: report });
  });
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(page.getByText("Review blocked", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Edit supported ending statement",
      exact: true,
    }),
  ).toHaveCount(0);
});

test("unsupported reviewed activity stays available in its original file", async ({
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
  const packet = JSON.parse(calls[0].text);
  packet.as_of = "2026-01-31T23:59:59+01:00";
  packet.activity = [
    {
      id: "66666666-6666-4666-8666-666666666666",
      account_id: packet.accounts[0].account_id,
      kind: "DIVIDEND",
      sequence: 1,
      effective_at: "2026-01-15T10:30:00+01:00",
      evidence: {
        source_sha256: "c".repeat(64),
        source_record_id: "synthetic-dividend",
      },
      listing_id: ledgerAnchor.listings[0].listing_id,
      currency: "USD",
      gross_cash: "1",
      fees: "0",
      taxes: "0",
    },
  ];
  const text = JSON.stringify(packet);
  await page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
    name: "dividend.json",
    mimeType: "application/json",
    buffer: Buffer.from(text),
  });
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edit supported activity", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "cannot be edited in the settled activity form",
  );
  await expect(
    page.getByRole("heading", { name: "Settled activity", exact: true }),
  ).toHaveCount(0);
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download private review JSON", exact: true })
    .click();
  const savedPath = await (await downloadEvent).path();
  if (!savedPath) throw new Error("Synthetic dividend review missing");
  expect(await readFile(savedPath, "utf8")).toBe(text);
  expect(calls.map((call) => call.path)).toEqual([previewPath, previewPath]);
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

test("a guided purchase keeps source evidence and exact amounts through download and restoration", async ({
  page,
}, info) => {
  const calls = await setup(page);
  await page.getByLabel(acknowledgement, { exact: true }).check();
  await page
    .getByRole("button", { name: "Reconcile opening balances", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add settled activity", exact: true })
    .click();
  await page
    .getByLabel("Review cutoff timestamp", { exact: true })
    .fill("2026-01-31T23:59:59+01:00");
  await page
    .getByRole("button", { name: "Add activity record", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Account", exact: true })
    .selectOption(JSON.parse(calls[0].text).accounts[0].account_id);
  await page
    .getByRole("combobox", { name: "Type", exact: true })
    .selectOption("BUY");
  await expect(
    page.getByRole("combobox", { name: "Type", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Booking timestamp", { exact: true })
    .fill("2026-01-15T10:30:00+01:00");
  await page.getByLabel("Sequence", { exact: true }).fill("1");
  await page.getByLabel("Currency", { exact: true }).fill("USD");
  await page
    .getByRole("combobox", { name: "Listing", exact: true })
    .selectOption(ledgerAnchor.listings[0].listing_id);
  await page.getByLabel("Quantity", { exact: true }).fill("0.5000000000");
  await page
    .getByLabel("Gross settlement cash", { exact: true })
    .fill("10.0000000000");
  await page.getByLabel("Fees", { exact: true }).fill("0.20");
  await page.getByLabel("Taxes", { exact: true }).fill("0.05");
  await page.getByLabel("Trade date", { exact: true }).fill("2026-01-13");
  await page.getByLabel("Settlement date", { exact: true }).fill("2026-01-15");
  await page
    .getByLabel("Source document SHA-256", { exact: true })
    .last()
    .fill("c".repeat(64));
  await page
    .getByLabel("Source record reference", { exact: true })
    .fill("synthetic-purchase");
  await page
    .getByRole("heading", { name: "Settled activity", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("trade-entry.png"),
    fullPage: true,
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Review activity", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(JSON.parse(calls[1].text).activity[0]).toMatchObject({
    kind: "BUY",
    quantity: "0.5000000000",
    gross_cash: "10.0000000000",
    fees: "0.20",
    taxes: "0.05",
    trade_date: "2026-01-13",
    settlement_date: "2026-01-15",
  });
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download private review JSON", exact: true })
    .click();
  const savedPath = await (await downloadEvent).path();
  if (!savedPath) throw new Error("Synthetic trade review download missing");
  expect(await readFile(savedPath, "utf8")).toBe(calls[1].text);
  await page
    .getByRole("button", { name: "Discard activity", exact: true })
    .click();
  await page.reload();
  await page
    .getByLabel("Ledger review JSON", { exact: true })
    .setInputFiles(savedPath);
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edit supported activity", exact: true })
    .click();
  await expect(page.getByLabel("Quantity", { exact: true })).toHaveValue(
    "0.5000000000",
  );
  await expect(page.getByLabel("Fees", { exact: true })).toHaveValue("0.20");
  await page
    .getByRole("button", { name: "Review activity", exact: true })
    .click();
  await expect(
    page.getByText("Opening balances reconciled", { exact: true }),
  ).toBeVisible();
  expect(calls[3].text).toBe(calls[1].text);
  await page.getByLabel("Fees", { exact: true }).fill("0");
  await expect(
    page.getByLabel("Ledger review result", { exact: true }),
  ).toHaveCount(0);
});
