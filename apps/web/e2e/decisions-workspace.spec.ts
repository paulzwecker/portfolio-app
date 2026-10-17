import { expect, test, type Page } from "@playwright/test";
import type { Overview } from "../src/lib/domain-contracts";

const portfolioId = "10000000-0000-4000-8000-000000000001";
const now = "2026-10-16T12:00:00Z";
const uuid = (value: number) =>
  `20000000-0000-4000-8000-${String(value).padStart(12, "0")}`;

function company(value: number, name: string) {
  return {
    id: uuid(value),
    name,
    reporting_currency: "USD",
    is_demo: false,
    created_at: "2026-01-01T00:00:00Z",
    lifecycle: "PORTFOLIO",
    lifecycle_event_id: null,
  };
}

function overviewFixture(): Overview {
  const held = company(1, "Fixture held zero target");
  const targetOnly = company(2, "Fixture target only");
  const noTarget = company(3, "Fixture missing target");
  const listingId = uuid(101);
  const position = {
    listing_id: listingId,
    security_id: uuid(201),
    ticker: "HOLD",
    venue: "NASDAQ",
    currency: "USD",
    security_name: "Fixture held listing",
    quantity: "1",
    latest_price: "100",
    price_date: "2026-10-15T00:00:00Z",
    price_observed_at: "2026-10-15T20:00:00Z",
    price_currency: "USD",
    portfolio_weight: "0.1",
    fx_rate: "0.92",
    fx_effective_at: "2026-10-15T16:00:00Z",
    valuation_sync_status: "NON_SYNCHRONOUS",
    price_freshness: "FRESH",
    native_market_value: "100",
    base_market_value: "92",
    valuation_status: "VALUED",
  };
  const context = (
    issuer: typeof held,
    positions: (typeof position)[],
    target_weight: string | null,
    current_weight: string | null,
    allocation_gap: string | null,
    allocation_status: string,
  ) => ({
    company: issuer,
    positions,
    target_weight,
    current_market_value:
      current_weight === null ? null : current_weight === "0" ? "0" : "92",
    current_market_currency: "EUR",
    current_weight,
    allocation_gap,
    allocation_status,
  });

  return {
    portfolio: {
      id: portfolioId,
      name: "Primary Portfolio",
      base_currency: "EUR",
      created_at: "2026-01-01T00:00:00Z",
      is_demo: false,
    },
    snapshot: {
      id: uuid(990),
      portfolio_id: portfolioId,
      completeness: "COMPLETE",
      positions: [{ listing_id: listingId, quantity: "1" }],
      cash_positions: [{ currency: "EUR", balance: "0" }],
      actor: "LOCAL_USER",
      reason: "Confirmed for UI fixture.",
      source: "decisions-e2e",
      effective_at: "2026-10-10T12:00:00Z",
      recorded_at: "2026-10-10T12:00:00Z",
    },
    target_revision: {
      id: uuid(991),
      portfolio_id: portfolioId,
      status: "ACCEPTED",
      allocations: [
        { company_id: held.id, weight: "0" },
        { company_id: targetOnly.id, weight: "0.05" },
      ],
      actor: "LOCAL_USER",
      reason:
        "Fixture preserves a zero target and an explicit target-only row.",
      source: "decisions-e2e",
      effective_at: "2026-10-01T12:00:00Z",
      recorded_at: "2026-10-01T12:00:00Z",
      accepted_at: "2026-10-01T12:00:00Z",
      invested_weight: "0.05",
      strategic_cash_weight: "0.95",
    },
    companies: [
      context(held, [position], "0", "0.1", "-0.1", "VALUED"),
      context(targetOnly, [], "0.05", "0", "0.05", "VALUED"),
      context(noTarget, [], null, null, null, "PORTFOLIO_TOTAL_UNAVAILABLE"),
    ],
    standalone_positions: [],
    cash_valuations: [],
    valuation_gaps: [],
    valuation_status: "VALUED",
    valuation_mode: "CURRENT_MARK_TO_MARKET",
    valuation_as_of: now,
    market_data_through: "2026-10-15T20:00:00Z",
    fx_data_through: "2026-10-15T16:00:00Z",
    holdings_age_days: 6,
    holdings_freshness: "STALE",
    base_market_value: "92",
    valuation_currency: "EUR",
  } as unknown as Overview;
}

function returnMethodology(id: number, title: string, group: string) {
  return {
    id: uuid(id),
    code: `METHOD_${id}`,
    title,
    version: 1,
    perspective: "EQUITY",
    cash_flow_basis: title,
    entry_value_basis: "Current exact-listing price basis.",
    share_price_basis: "Canonical listing quote.",
    comparability_group: group,
    cross_method_policy: "SAME_METHOD_ONLY",
    limitation: "Fixture methodology policy for comparison tests.",
    effective_from: "2026-01-01T00:00:00Z",
    recorded_at: "2026-01-01T00:00:00Z",
  };
}

function portfolioInput({
  cohort,
  method,
  expectedIrr,
}: {
  cohort: string | null;
  method: ReturnType<typeof returnMethodology>;
  expectedIrr: string | null;
}) {
  const score = {
    score: "4",
    status: "ASSESSED",
    assessment_id: uuid(600),
    effective_at: now,
    recorded_at: now,
    source: "UI test assessment",
  };
  return {
    context_version: "portfolio-rank-inputs-v3",
    score_formula: "LEGACY_IRR_FIRST_ALLOCATION_V1",
    portfolio_score: null,
    current_weight: "0.1",
    target_weight: "0",
    target_minus_current_gap: "-0.1",
    lifecycle: "PORTFOLIO",
    allocation_status: "VALUED",
    holding_snapshot_id: uuid(990),
    holding_effective_at: "2026-10-10T12:00:00Z",
    holdings_freshness: "STALE",
    holdings_age_days: 6,
    target_revision_id: uuid(991),
    target_effective_at: "2026-10-01T12:00:00Z",
    expected_irr: expectedIrr,
    return_comparability_cohort: cohort,
    expected_excess: expectedIrr === null ? null : "0.03",
    hurdle: "0.1",
    bear_fair_value: "80",
    weighted_fair_value: "110",
    bull_fair_value: "140",
    valuation_uncertainty: "0.2",
    durability_10y: score,
    compounder_quality: score,
    execution: score,
    risk: { ...score, score: "2" },
    model_source: {
      source_kind: "NATIVE_MODEL_REVISION",
      record_id: uuid(601),
      model_id: uuid(602),
      revision_id: uuid(603),
      revision_number: 1,
      model_key: method.title,
      model_type: method.code,
      methodology_version: "1",
      return_methodology: method,
      return_methodology_status: "CLASSIFIED",
      share_price_basis_status: "CAPTURED",
      source: "Accepted model revision",
      effective_at: now,
      recorded_at: now,
      effective_time_status: "KNOWN",
      model_currency: "USD",
      currency_status: "DOCUMENTED",
      output_quality: "COMPLETE",
      contract_status: "PASS",
      price_status: "FRESH",
      price_effective_at: "2026-10-15T20:00:00Z",
      price_observation_id: uuid(604),
      listing_id: uuid(101),
      listing_ticker: "HOLD",
      listing_venue: "NASDAQ",
    },
    score_contributions: {
      target_underweight: null,
      expected_irr: null,
      durability_10y: null,
      compounder_quality: null,
      execution: null,
      risk: null,
      valuation_uncertainty_penalty: null,
      negative_expected_excess_penalty: null,
    },
    context_note: "Exact methodology cohort comes from canonical rank inputs.",
  };
}

function rankDefinition(
  type: "PORTFOLIO" | "WATCHLIST" | "RESEARCH",
  index: number,
) {
  return {
    id: uuid(300 + index),
    ranking_type: type,
    version: 1,
    title: `${type} Rank`,
    methodology: "Versioned canonical ranking methodology.",
    population_rule: "Lifecycle-scoped companies.",
    required_inputs: "Domain inputs.",
    source_reference: "Canonical ranking definition.",
    implementation_status: "READY",
    effective_from: "2026-01-01T00:00:00Z",
    status: "ACTIVE",
    recorded_at: "2026-01-01T00:00:00Z",
  };
}

function rankingSummary(overview: Overview, cohorts: [string, string]) {
  return overview.companies.map((context, index) => {
    const definitions = [
      rankDefinition("PORTFOLIO", 1),
      rankDefinition("WATCHLIST", 2),
      rankDefinition("RESEARCH", 3),
    ];
    const rankings = definitions.map((definition) => {
      if (definition.ranking_type !== "PORTFOLIO")
        return { definition, run: null, entry: null };
      const runId = uuid(400 + index);
      const run = {
        id: runId,
        definition,
        as_of: now,
        recorded_at: now,
        status: "PARTIAL",
        actor: "SYSTEM",
        reason: "Portfolio incremental-capital review.",
        source: "fixture",
        company_count: 3,
        ranked_count: index === 0 ? 1 : 0,
      };
      return {
        definition,
        run,
        entry: {
          id: uuid(500 + index),
          run_id: runId,
          company_id: context.company.id,
          position: index === 0 ? 1 : null,
          status: index === 0 ? "RANKED" : "DATA_CHECK",
          reason:
            index === 0
              ? "Eligible within its canonical method cohort."
              : "Expected IRR is unavailable for this method-specific case.",
          input_snapshot:
            index < 2
              ? portfolioInput({
                  cohort: cohorts[index],
                  method: returnMethodology(
                    700 + index,
                    index === 0 ? "UFCF DCF" : "Owner Cash Flow",
                    cohorts[index],
                  ),
                  expectedIrr: index === 0 ? "0.14" : null,
                })
              : null,
        },
      };
    });
    return { company: context.company, rankings };
  });
}

function executionSummary(overview: Overview) {
  const issuer = overview.companies[0].company;
  const runId = uuid(800);
  const decision = {
    id: uuid(801),
    run_id: runId,
    company_id: issuer.id,
    decision_status: "REVIEW",
    pace: null,
    reason:
      "A stale market input requires human review before timing guidance.",
    target_revision_id: uuid(991),
    holding_snapshot_id: uuid(990),
    model_revision_id: null,
    model_output_snapshot_id: null,
    price_observation_id: null,
    input_snapshot: {
      context_version: "execution-pace-inputs-v2",
      lifecycle: "PORTFOLIO",
      target_revision_id: uuid(991),
      holding_snapshot_id: uuid(990),
      model_source_id: null,
      model_revision_id: null,
      model_output_snapshot_id: null,
      valuation_listing_id: uuid(101),
      price_observation_id: null,
      model_price_observation_id: null,
      accepted_reference_price_observation_id: null,
      target_effective_at: "2026-10-01T12:00:00Z",
      holding_effective_at: "2026-10-10T12:00:00Z",
      model_effective_at: null,
      model_recorded_at: null,
      price_market_date: null,
      price_recorded_at: null,
      model_price_effective_at: null,
      accepted_reference_price_effective_at: null,
      price_regime_as_of: null,
      current_weight: "0.1",
      target_weight: "0",
      allocation_gap: "-0.1",
      expected_irr: null,
      hurdle: null,
      price: null,
      model_reference_price: null,
      accepted_reference_price: null,
      weighted_fair_value: null,
      weighted_upside: null,
      valuation_range_ratio: null,
      allocation_status: "VALUED",
      model_key: null,
      model_currency: null,
      model_output_quality: null,
      model_contract_status: null,
      model_review_flag: null,
      valuation_ticker: "HOLD",
      valuation_venue: "NASDAQ",
      valuation_currency: "USD",
      price_currency: null,
      price_provider: null,
      price_quality: null,
      model_price_status: null,
      model_price_currency: null,
      estimate_provider_id: null,
      estimate_momentum_reason: null,
      price_regime_source_ref: null,
      price_regime_raw: null,
      price_regime: null,
      model_source_kind: null,
      return_semantics: null,
      price_freshness: "STALE",
      valuation_zone: null,
      estimate_momentum_availability: null,
      estimate_momentum_direction: null,
      estimate_momentum_freshness: null,
      estimate_momentum_quality: null,
      price_regime_quality: "DATA_CHECK",
      price_regime_freshness: "DATA_CHECK",
      estimate_latest_snapshot_date: null,
      holdings_freshness: "STALE",
      holdings_age_days: 6,
      context_notes: ["Exact-listing quote is stale."],
    },
  };
  return [
    {
      company: issuer,
      decision: {
        run: {
          id: runId,
          portfolio_id: portfolioId,
          as_of: now,
          recorded_at: now,
          methodology_version: "execution-pace-v1",
          status: "PARTIAL",
          actor: "SYSTEM",
          reason: "Periodic review.",
          source: "fixture",
          company_count: 1,
          available_count: 0,
          review_count: 1,
          unavailable_count: 0,
          not_applicable_count: 0,
        },
        decision,
      },
    },
  ];
}

async function mockDecisionData(page: Page) {
  const overview = overviewFixture();
  await page.route("**/api/research/portfolios", (route) =>
    route.fulfill({ json: [overview.portfolio] }),
  );
  await page.route(
    `**/api/research/portfolios/${portfolioId}/overview`,
    (route) => route.fulfill({ json: overview }),
  );
  await page.route("**/api/research/universe/ranking-summary", (route) =>
    route.fulfill({
      json: rankingSummary(overview, ["UFCF_EQUITY", "OWNER_EQUITY"]),
    }),
  );
  await page.route("**/api/research/universe/execution-pace-summary", (route) =>
    route.fulfill({ json: executionSummary(overview) }),
  );
  await page.route("**/api/research/universe/model-output-summary", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/research/universe/score-summary", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/research/return-methodologies", (route) =>
    route.fulfill({
      json: {
        definitions: [],
        rules: [],
        currency_policy: "Same currency unless a canonical bridge applies.",
      },
    }),
  );
}

test("Decisions keeps target authority, return cohorts, and REVIEW states visible on desktop", async ({
  page,
}, testInfo) => {
  const writes: string[] = [];
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method()))
      writes.push(request.method());
  });
  await mockDecisionData(page);
  await page.goto("/decisions");

  await expect(
    page.getByRole("heading", { name: "Decisions", level: 1 }),
  ).toBeVisible();
  const allocation =
    testInfo.project.name === "mobile"
      ? page.locator(
          '[aria-label="Current versus strategic allocation, mobile view"]',
        )
      : page.getByRole("table", {
          name: "Current versus strategic allocation",
        });
  await expect(
    page.getByText("Holdings confirmation is stale (6 days old)"),
  ).toBeVisible();
  await expect(
    allocation.getByText("Held position", { exact: true }),
  ).toBeVisible();
  await expect(
    allocation.getByText("Target only", { exact: true }),
  ).toBeVisible();
  await expect(
    allocation.getByText("No target", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Comparable cohort · UFCF EQUITY" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Comparable cohort · OWNER EQUITY" }),
  ).toBeVisible();
  await expect(
    page.getByText("IRR Unavailable").filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Review required; no timing pace is available.").first(),
  ).toBeVisible();

  await page
    .getByRole("button", {
      name: "Inspect Fixture held zero target decision context",
    })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("UFCF DCF · v1")).toBeVisible();
  await expect(page.getByText("This is not a trade order.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect(writes).toEqual([]);
});

test("Decisions remains usable on mobile without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDecisionData(page);
  await page.goto("/decisions");

  await expect(page.getByRole("heading", { name: "Allocation" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Opportunity" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Execution Pace" }),
  ).toBeVisible();
  await expect(
    page.getByText("Review required; no timing pace is available.").first(),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
