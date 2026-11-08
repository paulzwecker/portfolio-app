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

test("observed dividend and tax reconcile, retain evidence and require explicit review", async ({
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
    throw new Error("Unverified test anchor");
  const fund = anchor.listings.find((row) => row.security_type === "ETF");
  if (!fund || fund.company_id !== null)
    throw new Error("The synthetic fund needs a companyless exact listing");
  const packet = ledgerPacket(anchor, new Date().toISOString());
  packet.contract_version = "portfolio-ledger-preview-v2";
  expect(
    packet.accounts[0].cash.find((row) => row.currency === "USD")?.balance,
  ).toBe("5.0000000000");
  const record = {
    account_id: packet.accounts[0].account_id,
    effective_at: packet.as_of,
    currency: "USD",
  };
  packet.activity = [
    {
      ...record,
      id: crypto.randomUUID(),
      kind: "DIVIDEND",
      sequence: 1,
      listing_id: fund.listing_id,
      gross_cash: "4.0000000001",
      fees: "0",
      taxes: "1",
      evidence: {
        source_sha256: "d".repeat(64),
        source_record_id: "synthetic-observed-dividend",
      },
    },
    {
      ...record,
      id: crypto.randomUUID(),
      kind: "TAX",
      sequence: 2,
      amount: "0.0000000001",
      evidence: {
        source_sha256: "d".repeat(64),
        source_record_id: "synthetic-separate-tax",
      },
    },
  ];
  packet.ending_statement.accounts[0].cash.find(
    (row) => row.currency === "USD",
  )!.balance = "8";
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/portfolio/ledger");
  await page.getByLabel("Ledger review JSON", { exact: true }).setInputFiles({
    name: "synthetic-income.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(packet)),
  });
  await page
    .getByRole("button", { name: "Validate and reconcile", exact: true })
    .click();
  await expect(
    page.getByText("Ending statement reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Candidate reason", { exact: true })
    .fill(`Synthetic ${info.project.name} income`);
  await page
    .getByRole("button", { name: "Save candidate for review", exact: true })
    .click();
  const article = page.getByRole("article", { name: "Saved ledger candidate" });
  await expect(
    article.getByRole("heading", { name: /PENDING candidate/ }),
  ).toBeVisible();
  await article
    .getByText("Saved activity records (2)", { exact: true })
    .click();
  await expect(
    article.getByText(/Gross receipt 4.0000000001 USD/),
  ).toBeVisible();
  await expect(article.getByText(/Withholding 1\b/)).toBeVisible();
  await expect(
    article.getByText("Source record synthetic-observed-dividend", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(article.getByText(/Amount 0.0000000001 USD/)).toBeVisible();
  await expect(
    article.getByRole("button", { name: "Review acceptance", exact: true }),
  ).toBeDisabled();
  await article
    .getByLabel("Decision rationale")
    .fill("Verified gross settlement, withholding and separate tax evidence");
  for (const checkbox of await article.getByRole("checkbox").all())
    await checkbox.check();
  await article
    .getByRole("button", { name: "Review acceptance", exact: true })
    .click();
  const candidatesBefore = await (
    await request.get(`${path}/candidates`)
  ).json();
  await article
    .getByRole("button", { name: "Confirm acceptance", exact: true })
    .click();
  await expect(
    article.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText(
    `Reviewed revision ${candidatesBefore.current_revision_number + 1}`,
  );
  const history = await (await request.get(`${path}/candidates`)).json();
  const candidate: unknown = await (
    await request.get(
      `${path}/candidates/${history.current_accepted_candidate_id}`,
    )
  ).json();
  if (!isLedgerCandidate(candidate))
    throw new Error("Invalid income candidate readback");
  expect(candidate.status).toBe("ACCEPTED");
  expect(candidate.packet.activity[0].kind).toBe("DIVIDEND");
  expect(
    candidate.preview.cash.find((row) => row.currency === "USD")?.balance,
  ).toMatch(/^8(?:\.0+)?$/);
  expect(candidate.preview.positions).toEqual(
    anchor.snapshot.positions.map((row) => ({
      listing_id: row.listing_id,
      quantity: row.quantity,
    })),
  );
  expect(
    (await (await request.get(`${api}/__test/fixture`)).json())
      .protected_state_sha256,
  ).toBe(before.protected_state_sha256);
  if (!(await article.getByText(/Gross receipt/).isVisible()))
    await article
      .getByText("Saved activity records (2)", { exact: true })
      .click();
  await article.getByText(/Gross receipt/).scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("ledger-income-review.png"),
    scale: "css",
  });
  expect(errors).toEqual([]);
});
