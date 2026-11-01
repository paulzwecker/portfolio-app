import { expect, test } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const proposalId = "22222222-2222-4222-8222-222222222222";
const modelId = "33333333-3333-4333-8333-333333333333";
const listingId = "44444444-4444-4444-8444-444444444444";
const baseRevisionId = "55555555-5555-4555-8555-555555555555";
const evidenceId = "66666666-6666-4666-8666-666666666666";
const acceptedRevisionId = "77777777-7777-4777-8777-777777777777";
const recordedAt = "2026-10-16T10:00:00Z";

const company = {
  id: companyId,
  name: "Synthetic Model Company",
  reporting_currency: "USD",
  is_demo: true,
  created_at: "2026-10-01T00:00:00Z",
  lifecycle: "WATCHLIST",
  lifecycle_event_id: "88888888-8888-4888-8888-888888888888",
};

const listing = {
  id: listingId,
  security_id: "99999999-9999-4999-8999-999999999999",
  venue: "NASDAQ",
  ticker: "SYNM",
  currency: "USD",
  is_demo: true,
};

const years = Array.from({ length: 5 }, (_, index) => ({
  forecast_year: index + 1,
  revenue_growth: "0.08",
  ebit_margin: "0.22",
  tax_rate: "0.21",
  da_to_revenue: "0.03",
  capex_to_revenue: "0.02",
  nwc_to_revenue: "0.04",
  discount_rate: "0.09",
}));

const proposal = {
  contract_type: "FinancialModelRevisionProposalV1",
  contract_version: "1.0.0",
  model_id: modelId,
  company_id: companyId,
  valuation_listing_id: listingId,
  model_currency: "USD",
  methodology_version: "ufcf-dcf-fade-v1",
  base_revision_id: baseRevisionId,
  base_revision_number: 2,
  external_revision_id: "research-agent-r3",
  authored_at: recordedAt,
  effective_at: recordedAt,
  source_reference: "https://example.com/research/source-note",
  rationale: "The supported evidence changes the long-term revenue outlook.",
  supporting_evidence: [
    {
      evidence_type: "RESEARCH_REVISION",
      reference_id: evidenceId,
      relationship: "SUPPORTS",
      note: "Synthetic source-linked evidence for browser verification.",
    },
  ],
  method: {
    methodology: "UFCF_DCF_10Y_FADE",
    inputs: {
      base: {
        base_revenue: "100",
        base_ebit_margin: "0.2",
        base_tax_rate: "0.21",
        base_da_to_revenue: "0.03",
        base_capex_to_revenue: "0.02",
        base_nwc_to_revenue: "0.04",
        net_cash_debt: "-5",
        diluted_shares: "10",
      },
      scenarios: ["BEAR", "BASE", "BULL"].map((scenario) => ({
        scenario,
        probability: scenario === "BASE" ? "0.6" : "0.2",
        terminal_growth: "0.02",
        year10_ufcf_growth: "0.04",
        rationale: `${scenario} synthetic scenario`,
        years,
      })),
    },
  },
};

function proposalRead(status: "PENDING" | "ACCEPTED") {
  return {
    id: proposalId,
    producer_id: "synthetic-research-agent",
    proposal,
    content_fingerprint: "a".repeat(64),
    status,
    issue: null,
    conflicting_proposal_ids: [],
    accepted_revision_id: status === "ACCEPTED" ? acceptedRevisionId : null,
    reviewer_id: status === "ACCEPTED" ? "synthetic-reviewer" : null,
    decision_note:
      status === "ACCEPTED" ? "Reviewed synthetic proposal." : null,
    submitted_at: recordedAt,
    reviewed_at: status === "ACCEPTED" ? "2026-10-16T10:05:00Z" : null,
  };
}

test("model proposal review previews and requires an explicit confirmed decision", async ({
  page,
}) => {
  let accepted = false;
  let acceptRequests = 0;
  const preview = {
    proposal_id: proposalId,
    status: "READY",
    reason: null,
    current_revision_id: baseRevisionId,
    current_revision_number: 2,
    input_changes: [
      { field: "base.base_revenue", before: "100", after: "105" },
    ],
    output_changes: [{ field: "weighted_fv", before: "120", after: "126" }],
    current_inputs: { base: { base_revenue: "100" } },
    proposed_inputs: { base: { base_revenue: "105" } },
    current_outputs: { weighted_fv: "120" },
    proposed_outputs: { weighted_fv: "126" },
    proposed_projections: [],
    preview_fingerprint: "b".repeat(64),
    previewed_at: "2026-10-16T10:03:00Z",
  };

  await page.route(/\/api\/research\//, async (route) => {
    const pathname = new URL(route.request().url()).pathname.replace(
      "/api/research/",
      "",
    );
    if (pathname === `companies/${companyId}`)
      return route.fulfill({
        json: {
          company,
          securities: [
            {
              id: listing.security_id,
              company_id: companyId,
              name: "Synthetic common stock",
              security_type: "COMMON_STOCK",
              share_class: null,
              underlying_security_id: null,
              is_demo: true,
            },
          ],
          listings: [listing],
          lifecycle_history: [],
          portfolio: null,
          portfolio_context: null,
          holding_snapshot: null,
          positions: [],
          target_weight: null,
          target_revision_id: null,
        },
      });
    if (pathname === `companies/${companyId}/market-data`)
      return route.fulfill({ json: [] });
    if (
      pathname === `companies/${companyId}/financial-models` ||
      pathname === `companies/${companyId}/canonical-financial-models`
    )
      return route.fulfill({ json: [] });
    if (pathname === `companies/${companyId}/model-outputs/current`)
      return route.fulfill({
        json: {
          company_id: companyId,
          status: "NO_MODEL",
          history_count: 0,
          models: [],
        },
      });
    if (pathname === `companies/${companyId}/expected-return-history`)
      return route.fulfill({
        json: {
          company_id: companyId,
          as_of: "2026-10-16",
          known_at: recordedAt,
          status: "NO_HISTORY",
          history: [],
          current_calculations: [],
        },
      });
    if (pathname === "model-revision-proposals")
      return route.fulfill({
        json: [proposalRead(accepted ? "ACCEPTED" : "PENDING")],
      });
    if (pathname === `model-revision-proposals/${proposalId}/preview`)
      return route.fulfill({ json: preview });
    if (pathname === `model-revision-proposals/${proposalId}/accept`) {
      acceptRequests += 1;
      accepted = true;
      return route.fulfill({
        json: {
          status: "ACCEPTED",
          proposal: proposalRead("ACCEPTED"),
          accepted_revision_id: acceptedRevisionId,
        },
      });
    }
    return route.fulfill({
      status: 404,
      json: { detail: "No synthetic route" },
    });
  });

  await page.goto(`/company/${companyId}?view=valuation`);
  await expect(
    page.getByRole("heading", { name: "Agent model proposals" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "research-agent-r3 PENDING" }),
  ).toBeVisible();
  const accept = page.getByRole("button", { name: "Accept revision" });
  await expect(accept).toBeDisabled();
  expect(acceptRequests).toBe(0);

  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(page.getByText("Recalculated output changes")).toBeVisible();
  await expect(page.getByText("weighted_fv", { exact: true })).toBeVisible();
  await expect(accept).toBeDisabled();

  await page
    .getByLabel("Review decision note")
    .fill("Reviewed synthetic evidence and deterministic model impact.");
  await expect(accept).toBeEnabled();
  await accept.click();
  await expect(
    page.getByRole("button", { name: "Confirm acceptance" }),
  ).toBeVisible();
  expect(acceptRequests).toBe(0);

  await page.getByRole("button", { name: "Confirm acceptance" }).click();
  await expect(
    page.getByText("Accepted as a new immutable canonical model revision."),
  ).toBeVisible();
  expect(acceptRequests).toBe(1);
  await expect(page.getByText(acceptedRevisionId)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Accept revision" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Reject proposal" }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth + 1,
    ),
  ).toBe(true);
});
