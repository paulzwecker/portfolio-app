import { expect, test } from "@playwright/test";
import { isPortfolioLedgerAnchor } from "../src/lib/domain-contracts";
import { ledgerPacket } from "./fixtures/ledger";

test.skip(
  process.env.E2E_LEDGER_REVIEW_API !== "1",
  "Requires the isolated ledger-receipt browser fixture",
);

test("saved candidate review, corrections, rejection and historical readback", async ({
  page,
  request,
}, info) => {
  const port = process.env.BROWSER_API_PORT;
  if (
    port !== "8015" ||
    process.env.API_BASE_URL !== `http://127.0.0.1:${port}`
  )
    throw new Error("Use the exact isolated loopback fixture");
  const api = `http://127.0.0.1:${port}`;
  const baseline = await (await request.get(`${api}/__test/fixture`)).json();
  expect(baseline.ledger_receipts_only).toBe(true);
  const path = `/api/research/portfolios/${baseline.portfolio_id}/ledger`;
  const anchor: unknown = await (await request.get(`${path}/anchor`)).json();
  if (!isPortfolioLedgerAnchor(anchor))
    throw new Error("Unverified synthetic anchor");
  const initial = await (await request.get(`${path}/candidates`)).json();
  const packet = ledgerPacket(anchor, new Date().toISOString());
  expect(
    packet.accounts[0].cash.find((row) => row.currency === "USD")?.balance,
  ).toBe("5.0000000000");
  const deposit = crypto.randomUUID(),
    fee = crypto.randomUUID();
  packet.activity = [
    {
      id: deposit,
      account_id: packet.accounts[0].account_id,
      kind: "DEPOSIT",
      sequence: 1,
      effective_at: packet.as_of,
      currency: "USD",
      amount: "0.125",
      evidence: {
        source_sha256: "d".repeat(64),
        source_record_id: "synthetic-deposit",
      },
    },
    {
      id: fee,
      account_id: packet.accounts[0].account_id,
      kind: "FEE",
      sequence: 2,
      effective_at: packet.as_of,
      currency: "USD",
      amount: "1",
      evidence: {
        source_sha256: "d".repeat(64),
        source_record_id: "synthetic-fee",
      },
    },
  ];
  packet.ending_statement.accounts[0].cash.find(
    (row) => row.currency === "USD",
  )!.balance = "4.125";
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("request", (req) => {
    if (req.method() === "POST") writes.push(new URL(req.url()).pathname);
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/portfolio/ledger");
  const upload = async (name: string) => {
    await page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
      name,
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(packet)),
    });
    await page
      .getByRole("button", { name: "Validate and reconcile", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Candidate reason", exact: true }),
    ).toBeVisible();
  };
  const save = async (reason: string) => {
    await page
      .getByRole("textbox", { name: "Candidate reason", exact: true })
      .fill(reason);
    await page
      .getByRole("button", { name: "Save candidate for review", exact: true })
      .click();
    await expect(
      page
        .getByRole("article", { name: "Saved ledger candidate" })
        .getByRole("heading", { name: /PENDING candidate/ }),
    ).toBeVisible();
  };
  const article = page.getByRole("article", { name: "Saved ledger candidate" });
  const evidence = async () => {
    for (const checkbox of await article.getByRole("checkbox").all())
      await checkbox.check();
  };
  await upload("synthetic-initial.json");
  await save(`Synthetic ${info.project.name} initial statement`);
  await expect(
    article.getByRole("button", { name: "Review acceptance", exact: true }),
  ).toBeDisabled();
  await article
    .getByLabel("Decision rationale")
    .fill("Reviewed source, accounts and settled statements");
  await evidence();
  await article
    .getByRole("button", { name: "Review acceptance", exact: true })
    .click();
  const beforeConfirm = writes.length;
  await article
    .getByRole("button", { name: "Cancel decision", exact: true })
    .click();
  expect(writes.length).toBe(beforeConfirm);
  await article
    .getByRole("button", { name: "Review acceptance", exact: true })
    .click();
  await article
    .getByRole("group", { name: "Confirm ledger decision" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ledger-confirm.png"),
    scale: "css",
  });
  await article
    .getByRole("button", { name: "Confirm acceptance", exact: true })
    .click();
  await expect(
    article.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText(`Reviewed revision ${initial.current_revision_number + 1}`);
  const accepted = await (await request.get(`${path}/candidates`)).json();
  const firstId = accepted.current_accepted_candidate_id;
  // A full replacement both corrects one source row and removes one evidenced fee.
  packet.activity = packet.activity.slice(0, 1);
  (
    packet.activity[0].evidence as { source_record_id: string }
  ).source_record_id = "synthetic-corrected-deposit";
  packet.ending_statement.accounts[0].cash.find(
    (row) => row.currency === "USD",
  )!.balance = "5.125";
  await upload("synthetic-correction.json");
  await save(`Synthetic ${info.project.name} correction for rejection`);
  await expect(article.getByLabel("Replacement scope")).toContainText(
    "1 changed · 1 removed",
  );
  await article
    .getByLabel("Decision rationale")
    .fill("Reject pending source clarification");
  await article
    .getByRole("button", { name: "Review rejection", exact: true })
    .click();
  await article
    .getByRole("button", { name: "Confirm rejection", exact: true })
    .click();
  await expect(
    article.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText("Rejected candidate");
  await save(`Synthetic ${info.project.name} correction approved after review`);
  await article
    .getByLabel("Decision rationale")
    .fill("Verified corrected row and explicit fee exclusion");
  const checks = article.getByRole("checkbox");
  for (const checkbox of (await checks.all()).slice(0, 4))
    await checkbox.check();
  await expect(
    article.getByRole("button", { name: "Review acceptance", exact: true }),
  ).toBeDisabled();
  await evidence();
  await article
    .getByRole("button", { name: "Review acceptance", exact: true })
    .click();
  await article
    .getByRole("button", { name: "Confirm acceptance", exact: true })
    .click();
  await expect(
    article.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText(`Reviewed revision ${initial.current_revision_number + 2}`);
  await article
    .getByText("Candidate hashes and revision base", { exact: true })
    .click();
  await article.getByRole("button", { name: firstId, exact: true }).click();
  await expect(
    article.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText(`Reviewed revision ${initial.current_revision_number + 1}`);
  await expect(
    article.getByRole("button", { name: "Review acceptance", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", {
      name: "Open current reviewed candidate",
      exact: true,
    })
    .click();
  await expect(
    article.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText(`Reviewed revision ${initial.current_revision_number + 2}`);
  await article.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ledger-reviewed.png"),
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(baseline.protected_state_sha256);
  expect(writes.filter((path) => path.endsWith("/review"))).toHaveLength(3);
});

test("authorization failures, conflicts and ambiguous commit require readback", async ({
  page,
  request,
}, info) => {
  const api = "http://127.0.0.1:8015";
  if (process.env.API_BASE_URL !== api)
    throw new Error("Use the isolated loopback API");
  const identity = await (await request.get(`${api}/__test/fixture`)).json();
  expect(identity.ledger_receipts_only).toBe(true);
  const path = `/api/research/portfolios/${identity.portfolio_id}/ledger`;
  const anchor: unknown = await (await request.get(`${path}/anchor`)).json();
  if (!isPortfolioLedgerAnchor(anchor)) throw new Error("Unverified anchor");
  const before = await (await request.get(`${path}/candidates`)).json();
  await page.goto("/portfolio/ledger");
  await page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
    name: "synthetic-authorization.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify(ledgerPacket(anchor, new Date().toISOString())),
    ),
  });
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Candidate reason", exact: true })
    .fill(`Synthetic ${info.project.name} ambiguous response`);
  await page.route(`**${path}/candidates`, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 403,
          json: { detail: "Server authorization required" },
        })
      : route.continue(),
  );
  await page
    .getByRole("button", { name: "Save candidate for review", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Server authorization" }),
  ).toBeVisible();
  expect(
    (await (await request.get(`${path}/candidates`)).json()).candidates.length,
  ).toBe(before.candidates.length);
  await page.unroute(`**${path}/candidates`);
  await page
    .getByRole("button", { name: "Save candidate for review", exact: true })
    .click();
  const article = page.getByRole("article", { name: "Saved ledger candidate" });
  await expect(
    article.getByRole("heading", { name: /PENDING candidate/ }),
  ).toBeVisible();
  const approve = async () => {
    await article
      .getByRole("textbox", { name: "Decision rationale", exact: true })
      .fill("Explicit review after independently checking the source");
    for (const box of await article.getByRole("checkbox").all())
      await box.check();
    await article
      .getByRole("button", { name: "Review acceptance", exact: true })
      .click();
    await article
      .getByRole("button", { name: "Confirm acceptance", exact: true })
      .click();
  };
  let mutations = 0;
  await page.route(`**${path}/candidates/*/review`, async (route) => {
    mutations++;
    if (mutations === 1) {
      await route.fulfill({
        status: 409,
        json: { detail: "Synthetic conflict" },
      });
      return;
    }
    const result = await route.fetch();
    expect(result.status()).toBe(200);
    await route.fulfill({
      status: 503,
      json: { detail: "Synthetic lost response after commit" },
    });
  });
  await approve();
  await expect(article.getByRole("alert")).toContainText(
    "accepted base changed",
  );
  await expect(
    article.getByRole("button", { name: "Review acceptance", exact: true }),
  ).toBeDisabled();
  expect(mutations).toBe(1);
  await approve();
  await expect(
    article.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText(`Reviewed revision ${before.current_revision_number + 1}`);
  expect(mutations).toBe(2);
  expect(
    (await (await request.get(`${api}/__test/fixture`)).json())
      .protected_state_sha256,
  ).toBe(identity.protected_state_sha256);
  await article.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ledger-readback.png"),
    scale: "css",
  });
});
