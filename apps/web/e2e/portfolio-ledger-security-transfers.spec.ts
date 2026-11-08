import { expect, test } from "@playwright/test";
import {
  isLedgerCandidate,
  isPortfolioLedgerAnchor,
} from "../src/lib/domain-contracts";
import { ledgerPacket } from "./fixtures/ledger";

test.skip(
  process.env.E2E_LEDGER_REVIEW_API !== "1",
  "Requires the isolated ledger-receipt browser fixture",
);

test("security transfer reviews exact account quantities with acquisition basis unavailable", async ({
  page,
  request,
}, info) => {
  if (
    process.env.BROWSER_API_PORT !== "8015" ||
    process.env.API_BASE_URL !== "http://127.0.0.1:8015"
  )
    throw new Error("Use the exact isolated loopback fixture");
  const api = "http://127.0.0.1:8015";
  const before = await (await request.get(`${api}/__test/fixture`)).json();
  expect(before.ledger_receipts_only).toBe(true);
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  const path = `/api/research/portfolios/${before.portfolio_id}/ledger`;
  const anchor: unknown = await (await request.get(`${path}/anchor`)).json();
  if (!isPortfolioLedgerAnchor(anchor))
    throw new Error("Unverified fictional opening anchor");
  const fund = anchor.listings.find((row) => row.security_type === "ETF");
  if (!fund || fund.company_id !== null)
    throw new Error("Use the companyless synthetic fund");
  const packet = ledgerPacket(anchor, new Date().toISOString());
  const recipient = "77777777-7777-4777-8777-777777777777";
  packet.contract_version = "portfolio-ledger-preview-v2";
  expect(
    packet.accounts[0].positions.find(
      (row) => row.listing_id === fund.listing_id,
    )?.quantity,
  ).toBe("1.0000000000");
  packet.accounts.push({
    account_id: recipient,
    name: "Synthetic receiving account",
    kind: "BROKERAGE",
    broker_name: "Synthetic Receiving Broker",
    evidence: {
      source_sha256: "b".repeat(64),
      source_record_id: "recipient-opening",
    },
    positions: [],
    cash: [],
  });
  packet.activity = [
    {
      id: crypto.randomUUID(),
      account_id: packet.accounts[0].account_id,
      kind: "SECURITY_TRANSFER",
      sequence: 1,
      effective_at: packet.as_of,
      listing_id: fund.listing_id,
      quantity: "0.1234567891",
      basis_status: "UNAVAILABLE",
      evidence: {
        source_sha256: "d".repeat(64),
        source_record_id: "security-sent",
      },
      destination: {
        account_id: recipient,
        listing_id: fund.listing_id,
        quantity: "0.1234567891",
        effective_at: packet.as_of,
        evidence: {
          source_sha256: "e".repeat(64),
          source_record_id: "security-received",
        },
      },
    },
  ];
  packet.ending_statement.accounts[0].positions.find(
    (row) => row.listing_id === fund.listing_id,
  )!.quantity = "0.8765432109";
  packet.ending_statement.accounts.push({
    account_id: recipient,
    evidence: {
      source_sha256: "c".repeat(64),
      source_record_id: "recipient-closing",
    },
    positions: [{ listing_id: fund.listing_id, quantity: "0.1234567891" }],
    cash: [],
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/portfolio/ledger");
  await page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
    name: "synthetic-security-transfer.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(packet)),
  });
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Differences only", { exact: true }).uncheck();
  await page
    .getByRole("combobox", { name: "Account scope", exact: true })
    .selectOption(recipient);
  const table =
    info.project.name === "mobile"
      ? page.getByLabel("Ledger balance comparison, mobile view", {
          exact: true,
        })
      : page.getByRole("table", {
          name: "Ledger balance comparison",
          exact: true,
        });
  await expect(table.getByTitle("0.1234567891").first()).toBeVisible();
  await page
    .getByLabel("Candidate reason", { exact: true })
    .fill(`Synthetic ${info.project.name} security transfer`);
  await page
    .getByRole("button", { name: "Save candidate for review", exact: true })
    .click();
  const article = page.getByRole("article", { name: "Saved ledger candidate" });
  await expect(
    article.getByRole("heading", { name: /PENDING candidate/ }),
  ).toBeVisible();
  await article
    .getByText("Saved activity records (1)", { exact: true })
    .click();
  await expect(
    article.getByText(/Security transfer.*Synthetic receiving account/),
  ).toBeVisible();
  await expect(
    article.getByText("Sent quantity 0.1234567891", { exact: true }),
  ).toBeVisible();
  await expect(
    article.getByText(/Received quantity 0.1234567891/),
  ).toBeVisible();
  await expect(
    article.getByText("Acquisition basis unavailable · Gains unavailable", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    article.getByText("Receipt source record security-received", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    article.getByText("Source record security-sent", { exact: true }),
  ).toBeVisible();
  await expect(
    article.getByRole("button", { name: "Review acceptance", exact: true }),
  ).toBeDisabled();
  await article
    .getByLabel("Decision rationale")
    .fill(
      "Matched exact listing and both settled quantities; acquisition basis remains unavailable",
    );
  for (const checkbox of await article.getByRole("checkbox").all())
    await checkbox.check();
  await article
    .getByRole("button", { name: "Review acceptance", exact: true })
    .click();
  const historyBefore = await (await request.get(`${path}/candidates`)).json();
  await article
    .getByRole("button", { name: "Confirm acceptance", exact: true })
    .click();
  await expect(
    article.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText(
    `Reviewed revision ${historyBefore.current_revision_number + 1}`,
  );
  const history = await (await request.get(`${path}/candidates`)).json();
  const detail: unknown = await (
    await request.get(
      `${path}/candidates/${history.current_accepted_candidate_id}`,
    )
  ).json();
  if (!isLedgerCandidate(detail))
    throw new Error("Unverified security-transfer readback");
  const activity = detail.packet.activity[0];
  if (activity.kind !== "SECURITY_TRANSFER")
    throw new Error("Expected the saved security transfer");
  expect(activity.basis_status).toBe("UNAVAILABLE");
  expect(activity.destination.listing_id).toBe(fund.listing_id);
  expect(activity.destination.evidence.source_record_id).toBe(
    "security-received",
  );
  expect(detail.preview.cash).toEqual(anchor.snapshot.cash_positions);
  expect(detail.preview.positions).toEqual(anchor.snapshot.positions);
  expect(
    (await (await request.get(`${api}/__test/fixture`)).json())
      .protected_state_sha256,
  ).toBe(before.protected_state_sha256);
  if (!(await article.getByText(/Sent quantity 0.1234567891/).isVisible()))
    await article
      .getByText("Saved activity records (1)", { exact: true })
      .click();
  await article
    .getByText(/Sent quantity 0.1234567891/)
    .scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("ledger-security-transfer.png"),
    scale: "css",
  });
  expect(errors).toEqual([]);
});
