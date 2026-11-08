import { expect, test } from "@playwright/test";
import { isOverview } from "../src/lib/domain-contracts";
import {
  isLedgerPublicationPlan,
  isLedgerOwnership,
} from "../src/lib/ledger-publication-contracts";

test.skip(
  process.env.E2E_LEDGER_PUBLICATION_API !== "1",
  "Requires an isolated synthetic publication fixture, fresh per project",
);

test("reviewed ledger publication is explicit, hash-bound and recoverable by readback", async ({
  page,
  request,
}, info) => {
  test.setTimeout(90000);
  const api = "http://127.0.0.1:8017";
  if (process.env.API_BASE_URL !== api)
    throw new Error("Use the verified loopback publication fixture");
  await expect
    .poll(
      async () => {
        try {
          return (await request.get(`${api}/__test/fixture`)).status();
        } catch {
          return 0;
        }
      },
      { timeout: 30000 },
    )
    .toBe(200);
  const before = await (await request.get(`${api}/__test/fixture`)).json();
  expect(before.ledger_publication_only).toBe(true);
  expect(before.schema).toMatch(/^test_browser_[a-f0-9]{32}$/);
  const base = `/api/research/portfolios/${before.portfolio_id}/ledger`;
  const candidatePath = `${base}/candidates/${before.candidate_id}`;
  const rawPlan: unknown = await (
    await request.get(`${candidatePath}/publication-preview`)
  ).json();
  if (!isLedgerPublicationPlan(rawPlan))
    throw new Error("Unverified publication plan");
  expect(rawPlan.status).toBe("READY");
  const errors: string[] = [],
    posts: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (req) => {
    if (req.method() === "POST") posts.push(req.url());
  });
  await page.goto("/portfolio/ledger");
  await page
    .getByRole("button", {
      name: "Open current reviewed candidate",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", {
      name: "Load read-only publication plan",
      exact: true,
    })
    .click();
  const publication = page.getByRole("region", {
    name: "Holdings publication",
    exact: true,
  });
  await expect(
    publication.getByLabel("Current canonical holdings", { exact: true }),
  ).toContainText("USD 5.0000000000");
  await expect(
    publication.getByLabel("Proposed complete replacement", { exact: true }),
  ).toContainText("USD 5.125");
  await expect(publication).toContainText("ETF");
  expect(posts).toEqual([]);
  await publication
    .getByRole("heading", { name: "Publish reviewed holdings", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ledger-publication-plan.png"),
    scale: "css",
  });
  await publication
    .getByLabel("Proposed complete replacement", { exact: true })
    .screenshot({ path: info.outputPath("ledger-publication-balances.png") });
  const review = publication.getByRole("button", {
    name: "Review holdings publication",
    exact: true,
  });
  await expect(review).toBeDisabled();
  const authorize = async () => {
    await publication
      .getByLabel("Publication rationale", { exact: true })
      .fill("Reviewed fictional account and current-state recovery");
    for (const checkbox of await publication.getByRole("checkbox").all())
      await checkbox.check();
    await publication
      .getByLabel("Typed publication confirmation", { exact: true })
      .fill(rawPlan.confirmation_phrase + " incorrect");
    await expect(review).toBeDisabled();
    await publication
      .getByLabel("Typed publication confirmation", { exact: true })
      .fill(rawPlan.confirmation_phrase);
    await expect(review).toBeEnabled();
  };
  await authorize();
  await review.click();
  await expect(
    publication.getByRole("heading", {
      name: "Confirm whole-portfolio publication",
      exact: true,
    }),
  ).toBeFocused();
  await publication
    .getByRole("button", { name: "Cancel publication", exact: true })
    .click();
  expect(posts).toEqual([]);
  const confirm = publication.getByRole("button", {
    name: "Confirm holdings publication",
    exact: true,
  });
  for (const status of [403, 409]) {
    await page.route(
      `**${candidatePath}/publish`,
      async (route) => {
        await route.fulfill({
          status,
          contentType: "application/json",
          body: JSON.stringify({ error: "Synthetic owner or source conflict" }),
        });
      },
      { times: 1 },
    );
    await review.click();
    await confirm.click();
    await expect(publication).toContainText(
      status === 403
        ? "Server-side owner authorization is required"
        : "The plan, source or holdings authority changed",
    );
    await expect(
      publication.getByLabel("Publication rationale", { exact: true }),
    ).toHaveValue("");
    await expect(review).toBeDisabled();
    expect(await publication.getByRole("checkbox").first().isChecked()).toBe(
      false,
    );
    await authorize();
  }
  expect(posts).toHaveLength(2);
  await review.click();
  await publication
    .getByRole("heading", {
      name: "Confirm whole-portfolio publication",
      exact: true,
    })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ledger-publication-confirm.png"),
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  let actualWrites = 0;
  await page.route(
    `**${candidatePath}/publish`,
    async (route) => {
      const body = route.request().postDataJSON();
      expect(body.expected_plan_sha256).toBe(rawPlan.plan_sha256);
      expect(body.expected_previous_publication_id).toBe(null);
      expect(body.confirmation).toBe(rawPlan.confirmation_phrase);
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      actualWrites += 1;
      if (info.project.name === "mobile") await route.abort("connectionreset");
      else await route.fulfill({ response });
    },
    { times: 1 },
  );
  await confirm.click();
  await expect(
    publication.getByRole("status", {
      name: "Holdings publication receipt",
      exact: true,
    }),
  ).toBeVisible();
  await expect(publication).toContainText("Already published");
  if (info.project.name === "mobile")
    await expect(publication).toContainText(
      "Read-only receipt confirms publication after an uncertain response",
    );
  else await expect(publication).toContainText("Publication verified");
  expect(actualWrites).toBe(1);
  expect(posts).toHaveLength(3);
  await expect(review).toHaveCount(0);
  const owner: unknown = await (await request.get(`${base}/ownership`)).json();
  if (!isLedgerOwnership(owner) || !owner.latest_publication)
    throw new Error("Unverified ownership readback");
  expect(owner.latest_publication.plan.plan_sha256).toBe(rawPlan.plan_sha256);
  const overview: unknown = await (
    await request.get(
      `/api/research/portfolios/${before.portfolio_id}/overview`,
    )
  ).json();
  if (!isOverview(overview)) throw new Error("Unverified canonical readback");
  expect(overview.holdings_authority?.publication_id).toBe(
    owner.latest_publication.id,
  );
  expect(
    overview.snapshot?.cash_positions.find((row) => row.currency === "USD")
      ?.balance,
  ).toBe("5.1250000000");
  const after = await (await request.get(`${api}/__test/fixture`)).json();
  expect(after.protected_state_sha256).toBe(before.protected_state_sha256);
  await publication
    .getByRole("status", { name: "Holdings publication receipt", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ledger-publication-receipt.png"),
    scale: "css",
  });
  expect(errors).toEqual([]);
});
