import { expect, test } from "@playwright/test";
import {
  isOverview,
  isPortfolioLedgerAnchor,
} from "../src/lib/domain-contracts";

test.skip(
  process.env.E2E_LEDGER_OWNERSHIP_API !== "1",
  "Requires an isolated pre-published ledger fixture",
);
test("published ledger ownership is visible with exact readback and source-safe controls", async ({
  page,
  request,
}, info) => {
  const api = "http://127.0.0.1:8016";
  if (process.env.API_BASE_URL !== api)
    throw new Error("Use the verified loopback ownership fixture");
  await expect
    .poll(
      async () => {
        try {
          return (await request.get(`${api}/__test/fixture`)).status();
        } catch {
          return 0;
        }
      },
      { timeout: 20000 },
    )
    .toBe(200);
  const before = await (await request.get(`${api}/__test/fixture`)).json();
  expect(before.ledger_owned).toBe(true);
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  const overview: unknown = await (
    await request.get(
      `/api/research/portfolios/${before.portfolio_id}/overview`,
    )
  ).json();
  if (!isOverview(overview)) throw new Error("Unverified overview");
  expect(overview.holdings_authority?.source).toBe("ACCEPTED_LEDGER");
  expect(overview.holdings_authority?.publication_id).toBe(
    before.publication_id,
  );
  expect(
    overview.snapshot?.cash_positions.find((row) => row.currency === "USD")
      ?.balance,
  ).toBe("5.1250000000");
  expect(
    overview.snapshot?.cash_positions.find((row) => row.currency === "EUR")
      ?.balance,
  ).toBe("10.0000000000");
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("request", (req) => {
    if (["POST", "PATCH", "DELETE", "PUT"].includes(req.method()))
      writes.push(req.url());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/portfolio");
  await expect(
    page.getByRole("link", { name: "Review ledger", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Confirm holdings", { exact: true })).toHaveCount(
    0,
  );
  const heading = page.getByRole("heading", {
    name: "Ledger-owned holdings",
    exact: true,
  });
  await expect(heading).toBeVisible();
  await heading.scrollIntoViewIfNeeded();
  await expect(
    page.getByText(`Publication ${before.publication_id}`, { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("ledger-ownership.png"),
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("link", { name: "Review ledger history", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Transaction ledger review",
      exact: true,
    }),
  ).toBeVisible();
  const anchor: unknown = await (
    await request.get(
      `/api/research/portfolios/${before.portfolio_id}/ledger/anchor`,
    )
  ).json();
  if (!isPortfolioLedgerAnchor(anchor))
    throw new Error("Unverified opening anchor");
  expect(anchor.snapshot.id).toBe(before.opening_snapshot_id);
  await page
    .getByRole("button", {
      name: "Open current reviewed candidate",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("status", { name: "Ledger decision receipt" }),
  ).toContainText("Reviewed revision 1");
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  expect(
    (await (await request.get(`${api}/__test/fixture`)).json())
      .protected_state_sha256,
  ).toBe(before.protected_state_sha256);
  expect(
    (
      await request.post(
        `${api}/v1/portfolios/${before.portfolio_id}/ledger/candidates/33333333-3333-4333-8333-333333333333/publish`,
        { data: {} },
      )
    ).status(),
  ).toBe(405);
});
