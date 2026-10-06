import { expect, test } from "@playwright/test";

const id = "11111111-1111-4111-8111-111111111111";
const company = {
  id,
  name: "Example business",
  reporting_currency: null,
  is_demo: false,
  created_at: "2026-10-04T00:00:00Z",
  lifecycle: null,
  lifecycle_event_id: null,
};
const momentumSummary = (
  companyId: string,
  availability: "NO_MAPPING" | "INSUFFICIENT_HISTORY" = "NO_MAPPING",
) => ({
  company_id: companyId,
  methodology_version: "legacy-estimate-momentum-v2-partial-1",
  availability,
  direction: null,
  raw_score: null,
  confidence_adjusted_score: null,
  confidence: "0",
  confidence_band: "NO_DATA",
  coverage_fraction: "0",
  coverage_count: 0,
  coverage_total: 20,
  freshness: "NO_DATA",
  data_quality: availability === "NO_MAPPING" ? "NO_DATA" : "DATA_CHECK",
  provider_id:
    availability === "NO_MAPPING" ? null : "legacy_workbook_estimates",
  latest_snapshot_date: null,
  as_of: "2026-10-05",
  known_at: null,
  reason:
    availability === "NO_MAPPING"
      ? "No consensus source is selected for this as-of date."
      : "The selected source has no future annual Revenue/EPS estimates with resolved fiscal-period ends.",
});
const scoreDimensions = [
  ["DURABILITY_10Y", "0.00", "HIGHER_IS_BETTER"],
  ["COMPOUNDER_QUALITY", "0.00", "HIGHER_IS_BETTER"],
  ["EXECUTION", "1.00", "HIGHER_IS_BETTER"],
  ["RISK", "1.00", "HIGHER_IS_RISK"],
] as const;
const scoreSummary = (issuer: Pick<typeof company, "created_at">) => [
  {
    company: issuer,
    scores: scoreDimensions.map(
      ([dimension, minimum_score, directionality], index) => ({
        definition: {
          id: `55555555-5555-4555-8555-55555555555${index}`,
          dimension,
          version: 1,
          minimum_score,
          maximum_score: "5.00",
          directionality,
          units: "points",
          methodology: "Canonical fictional test definition.",
          effective_from: issuer.created_at,
          status: "ACTIVE",
          recorded_at: issuer.created_at,
        },
        assessment: null,
      }),
    ),
  },
];
const companyRankingCurrent = {
  current: (["PORTFOLIO", "WATCHLIST", "RESEARCH"] as const).map(
    (ranking_type, index) => ({
      definition: {
        id: `66666666-6666-4666-8666-66666666666${index}`,
        ranking_type,
        version: 1,
        title: `${ranking_type} Rank`,
        methodology: "Documented ordering; ranking input is not migrated.",
        population_rule: "Explicit domain population.",
        required_inputs: "Canonical source values.",
        source_reference: "test-fixture",
        implementation_status: "NOT_MIGRATED",
        effective_from: company.created_at,
        status: "ACTIVE",
        recorded_at: company.created_at,
      },
      run: null,
      entry: null,
    }),
  ),
  history: [],
};

const emptyModelMigrationStatus = (companyId: string) => ({
  company_id: companyId,
  inventory_available: true,
  models: [],
});

const contractModelId = "99999999-9999-4999-8999-999999999999";
const contractRevisionId = "22222222-2222-4222-8222-222222222222";
const contractListing = {
  id: "77777777-7777-4777-8777-777777777777",
  security_id: "88888888-8888-4888-8888-888888888888",
  venue: "NASDAQ",
  ticker: "EXM",
  currency: "USD",
  is_demo: true,
};
const contractBase = {
  base_revenue: "100",
  base_ebit_margin: "0.2",
  base_tax_rate: "0.25",
  base_da_to_revenue: "0.03",
  base_capex_to_revenue: "0.02",
  base_nwc_to_revenue: "0.04",
  net_cash_debt: "-5",
  diluted_shares: "10",
};
const scenarioNames = ["BEAR", "BASE", "BULL"] as const;
const contractScenarioIds = [
  "33333333-3333-4333-8333-333333333331",
  "33333333-3333-4333-8333-333333333332",
  "33333333-3333-4333-8333-333333333333",
];
const contractScenarios = scenarioNames.map((scenario, scenarioIndex) => ({
  scenario,
  probability: scenario === "BASE" ? "0.6" : "0.2",
  terminal_growth: "0.025",
  year10_ufcf_growth: "0.04",
  rationale: `${scenario} case assumptions`,
  years: Array.from({ length: 5 }, (_, index) => ({
    forecast_year: index + 1,
    revenue_growth: scenario === "BASE" ? "0.1" : "0.08",
    ebit_margin: "0.2",
    tax_rate: "0.25",
    da_to_revenue: "0.03",
    capex_to_revenue: "0.02",
    nwc_to_revenue: "0.04",
    discount_rate: "0.09",
  })),
  id: contractScenarioIds[scenarioIndex],
}));
const contractOutputs = {
  id: "44444444-4444-4444-8444-444444444444",
  revision_id: contractRevisionId,
  status: "PARTIAL",
  model_currency: "USD",
  price_observation_id: null,
  current_price: null,
  price_effective_at: null,
  price_status: "NO_DATA",
  price_unavailable_reason: "No comparable quote is available.",
  irr_unavailable_reason: "No comparable quote is available.",
  bear_fv: "15",
  base_fv: "20",
  bull_fv: "30",
  bear_probability: "0.2",
  base_probability: "0.6",
  bull_probability: "0.2",
  weighted_fv: "21",
  weighted_upside: null,
  expected_cash_flow_irr: null,
  hurdle: "0.09",
  expected_excess: null,
  forward_fundamental_cagr: null,
};
const contractProjections = contractScenarioIds.flatMap((scenario_id) =>
  Array.from({ length: 10 }, (_, index) => {
    const forecast_year = index + 1;
    const detailed = forecast_year <= 5;
    return {
      id: `55555555-5555-4555-8555-55555555555${index % 10}`,
      scenario_id,
      forecast_year,
      revenue: detailed ? "100" : null,
      ebit: detailed ? "20" : null,
      nopat: detailed ? "15" : null,
      depreciation_amortization: detailed ? "3" : null,
      capex: detailed ? "2" : null,
      net_working_capital: detailed ? "4" : null,
      change_in_nwc: detailed ? "1" : null,
      unlevered_free_cash_flow: "15",
      revenue_growth: "0.1",
      discount_rate: "0.09",
      discount_factor: "0.65",
      present_value_ufcf: "10",
      terminal_value: forecast_year === 10 ? "100" : null,
    };
  }),
);
const contractRevision = {
  id: contractRevisionId,
  model_id: contractModelId,
  revision_number: 1,
  base_revision_id: null,
  methodology_version: "ufcf-dcf-fade-v1",
  source_revision_id: null,
  actor: "SYSTEM",
  source: "browser fixture",
  rationale: "Initial reviewed scenario assumptions.",
  effective_at: "2026-10-05T00:00:00Z",
  recorded_at: "2026-10-05T00:00:00Z",
  outputs: contractOutputs,
  base: contractBase,
  scenarios: contractScenarios.map((scenario) => ({
    id: scenario.id,
    revision_id: contractRevisionId,
    scenario: scenario.scenario,
    probability: scenario.probability,
    terminal_growth: scenario.terminal_growth,
    year10_ufcf_growth: scenario.year10_ufcf_growth,
    rationale: scenario.rationale,
    years: scenario.years.map((year, index) => ({
      ...year,
      id: `66666666-6666-4666-8666-66666666666${index}`,
      scenario_id: scenario.id,
    })),
  })),
  projections: contractProjections,
};
const contractModel = {
  id: contractModelId,
  company_id: id,
  model_type: "UFCF_DCF_10Y_FADE",
  model_name: "Example operating DCF",
  valuation_listing: contractListing,
  model_currency: "USD",
  source_model_key: null,
  created_at: "2026-10-05T00:00:00Z",
  current_revision_id: contractRevisionId,
  current_revision: contractRevision,
  history: [contractRevision],
};
const portableContract = {
  contract_version: "1.0.0",
  exported_at: "2026-10-05T00:00:00Z",
  model: {
    model_id: contractModelId,
    company_id: id,
    model_type: "UFCF_DCF_10Y_FADE",
    model_name: "Example operating DCF",
    valuation_listing_id: contractListing.id,
    valuation_listing: contractListing,
    model_currency: "USD",
    source_model_key: null,
  },
  base_revision: {
    revision_id: contractRevisionId,
    revision_number: 1,
    methodology_version: "ufcf-dcf-fade-v1",
  },
  candidate_revision: {
    source_revision_id: "google-sheets:browser-roundtrip-1",
    actor: "IMPORT",
    source: "Google Sheets portable contract",
    rationale: contractRevision.rationale,
    effective_at: "2026-10-05T00:00:00Z",
    base: contractBase,
    scenarios: contractScenarios.map((scenario) => ({
      scenario: scenario.scenario,
      probability: scenario.probability,
      terminal_growth: scenario.terminal_growth,
      year10_ufcf_growth: scenario.year10_ufcf_growth,
      rationale: scenario.rationale,
      years: scenario.years,
    })),
  },
  base_calculation: {
    revision_id: contractRevisionId,
    outputs: contractOutputs,
    projections: contractProjections,
  },
};

test("research empty and unavailable states recover", async ({ page }) => {
  let available = false;
  await page.route(/\/api\/research\/universe(?:\/|$)/, (route) =>
    route.fulfill({
      status: available ? 200 : 503,
      json: available ? [] : { detail: "Unavailable" },
    }),
  );
  await page.goto("/universe");
  await expect(
    page.getByRole("alert").filter({ hasText: "Research data" }),
  ).toContainText("unavailable");
  available = true;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(
    page.getByRole("heading", { name: "No companies match" }),
  ).toBeVisible();
  await page.route("**/api/research/portfolios", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/portfolio");
  await expect(
    page.getByRole("heading", { name: "No portfolio yet" }),
  ).toBeVisible();
});

test("universe pending, identity and missing lifecycle states are explicit", async ({
  page,
}) => {
  let release: () => void = () => undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(/\/api\/research\/universe(?:\/|$)/, async (route) => {
    await pending;
    const url = new URL(route.request().url());
    return route.fulfill({
      json: url.searchParams.has("search")
        ? []
        : url.pathname.endsWith("/score-summary")
          ? scoreSummary(company)
          : [],
    });
  });
  await page.goto("/universe");
  await expect(page.getByRole("status")).toHaveText("Loading research data");
  release();
  await expect(page.getByText("Unassigned", { exact: true })).toBeVisible();
  await expect(page.getByText("Reporting currency: Unknown")).toBeVisible();
  await page.getByRole("textbox", { name: "Company name" }).fill("no match");
  await expect(
    page.getByRole("heading", { name: "No companies match" }),
  ).toBeVisible();
});

test("universe keeps unavailable and data-check ranking states explicit", async ({
  page,
}) => {
  const types = ["PORTFOLIO", "WATCHLIST", "RESEARCH"] as const;
  const watchlistInputSnapshot = {
    context_version: "watchlist-rank-inputs-v1",
    expected_irr: "0.12",
    return_semantics: "LEGACY_NORMALIZED_FIELD",
    return_source: {
      source_kind: "IMPORTED_CURRENT_CONTRACT",
      record_id: id,
      model_id: null,
      revision_id: null,
      revision_number: null,
      model_key: "P-EXAMPLE",
      model_type: null,
      methodology_version: null,
      contract_version: "1.0.0",
      source_revision_id: "legacy-1",
      source: "Workbook fixture",
      effective_at: null,
      recorded_at: company.created_at,
      effective_time_status: "UNKNOWN",
      model_currency: "USD",
      currency_status: "DOCUMENTED",
      output_quality: "COMPLETE",
      contract_status: "PASS",
      price_status: null,
      price_effective_at: null,
      price_observation_id: null,
      listing_id: id,
      listing_ticker: "EX",
      listing_venue: "NASDAQ",
      migration_status: null,
    },
    durability_10y: {
      score: "4.0",
      status: "ASSESSED",
      assessment_id: id,
      effective_at: company.created_at,
      recorded_at: company.created_at,
      rationale: "Long business life supported by evidence.",
      source: "fixture",
    },
    compounder_quality: {
      score: null,
      status: "NOT_ASSESSED",
      assessment_id: null,
      effective_at: null,
      recorded_at: null,
      rationale: null,
      source: null,
    },
    forward_fundamental_cagr: "0.11",
    weighted_fair_value: "25",
    hurdle: "0.09",
    expected_excess: "0.03",
    decision_context: "QUALITY_GATE_THRESHOLDS_NOT_DOCUMENTED",
    context_note: "Missing quality context remains explicit.",
  };
  const rankings = types.map((ranking_type, index) => {
    const definition = {
      id: `22222222-2222-4222-8222-22222222222${index}`,
      ranking_type,
      version: ranking_type === "WATCHLIST" ? 3 : 2,
      title: `${ranking_type} Rank`,
      methodology: "Documented workbook order; input not migrated.",
      population_rule: "Explicit domain population.",
      required_inputs: "Canonical source values.",
      source_reference: "reference/workbook/Portfolio_Watchlist.xlsx",
      implementation_status: "READY",
      effective_from: company.created_at,
      status: "ACTIVE",
      recorded_at: company.created_at,
    };
    const run = {
      id: `33333333-3333-4333-8333-33333333333${index}`,
      definition,
      as_of: company.created_at,
      recorded_at: company.created_at,
      status: "PARTIAL",
      actor: "SYSTEM",
      reason: "Availability-only fixture.",
      source: "browser-fixture",
      company_count: 1,
      ranked_count: 0,
    };
    return {
      definition,
      run,
      entry: {
        id: `44444444-4444-4444-8444-44444444444${index}`,
        run_id: run.id,
        company_id: id,
        position: null,
        status:
          ranking_type === "WATCHLIST" ? "DATA_CHECK" : "INPUTS_UNAVAILABLE",
        reason:
          ranking_type === "RESEARCH"
            ? "Point-in-time lifecycle is unavailable."
            : "Required source inputs are unavailable.",
        ...(ranking_type === "WATCHLIST"
          ? { input_snapshot: watchlistInputSnapshot }
          : ranking_type === "RESEARCH"
            ? {
                input_snapshot: {
                  context_version: "research-rank-inputs-v1",
                  lifecycle: null,
                  candidate_tier: null,
                  priority_seed: null,
                  legacy_default_priority_seed: null,
                  used_legacy_default: false,
                  sort_key: null,
                  input_quality: "MISSING",
                  source_digest: null,
                  bucket_source_ref: null,
                  priority_seed_source_ref: null,
                  context_note: "Lifecycle is unavailable at this run.",
                },
              }
            : {}),
      },
    };
  });
  let submittedReason = "";
  let submittedType = "";
  await page.route(/\/api\/research\/ranking-runs$/, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as {
      ranking_type: string;
      reason: string;
    };
    submittedReason = body.reason;
    submittedType = body.ranking_type;
    const selectedDefinition = rankings.find(
      (item) => item.definition.ranking_type === body.ranking_type,
    )!.definition;
    await route.fulfill({
      json: {
        id: "77777777-7777-4777-8777-777777777777",
        definition: selectedDefinition,
        as_of: company.created_at,
        recorded_at: company.created_at,
        status: "PARTIAL",
        actor: "LOCAL_USER",
        reason: body.reason,
        source: "web-universe",
        company_count: 1,
        ranked_count: 0,
      },
    });
  });
  await page.route(/\/api\/research\/universe(?:\/|$)/, (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/ranking-summary")) {
      return route.fulfill({ json: [{ company, rankings }] });
    }
    if (url.pathname.endsWith("/score-summary")) {
      return route.fulfill({ json: scoreSummary(company) });
    }
    return route.fulfill({ json: [company] });
  });

  await page.goto("/universe");
  await expect(page.getByRole("link", { name: company.name })).toBeVisible();
  await expect(
    page.getByText("INPUTS_UNAVAILABLE", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("DATA_CHECK", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Legacy output · separate return semantics"),
  ).toBeVisible();
  await expect(page.getByText("12%", { exact: true })).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ranking run reason" })
    .fill("Record explicit Watchlist Rank from the UI.");
  await page.getByRole("button", { name: "Record Watchlist Rank" }).click();
  await expect
    .poll(() => submittedReason)
    .toBe("Record explicit Watchlist Rank from the UI.");
  await expect.poll(() => submittedType).toBe("WATCHLIST");
  await page.getByLabel("Ranking type").selectOption("RESEARCH");
  await expect(
    page.getByText(
      /Research Rank orders Candidate High\/Low deep-dive priority/,
    ),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ranking run reason" })
    .fill("Record Research Rank from the UI.");
  await page.getByRole("button", { name: "Record Research Rank" }).click();
  await expect.poll(() => submittedType).toBe("RESEARCH");
  await expect
    .poll(() => submittedReason)
    .toBe("Record Research Rank from the UI.");
  await page.getByLabel("Ranking filter").selectOption("UNRANKED");
  await expect(page.getByRole("status")).toHaveText("1 businesses shown");
  await page.getByLabel("Sort companies").selectOption("rank-asc");
  await expect(page.getByRole("link", { name: company.name })).toBeVisible();
  await expect(page.getByText("#0", { exact: true })).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("Research Rank explains research priority, records a run, and fits mobile", async ({
  page,
}) => {
  const candidate = { ...company, lifecycle: "CANDIDATE" };
  const recordedAt = "2026-10-06T00:00:00Z";
  const types = ["PORTFOLIO", "WATCHLIST", "RESEARCH"] as const;
  const currents = types.map((ranking_type, index) => {
    const definition = {
      id: `23232323-2323-4232-8232-23232323232${index}`,
      ranking_type,
      version: ranking_type === "WATCHLIST" ? 3 : 2,
      title: `${ranking_type} Rank`,
      methodology: "Documented ranking methodology.",
      population_rule: "Explicit domain population.",
      required_inputs: "Canonical source values.",
      source_reference: "reference/workbook/Portfolio_Watchlist.xlsx",
      implementation_status: "READY",
      effective_from: recordedAt,
      status: "ACTIVE",
      recorded_at: recordedAt,
    };
    if (ranking_type !== "RESEARCH") {
      return { definition, run: null, entry: null };
    }
    const run = {
      id: "34343434-3434-4343-8343-343434343434",
      definition,
      as_of: recordedAt,
      recorded_at: recordedAt,
      status: "COMPLETE",
      actor: "SYSTEM",
      reason: "Canonical candidate research-priority snapshot.",
      source: "research-rank-test",
      company_count: 1,
      ranked_count: 1,
    };
    return {
      definition,
      run,
      entry: {
        id: "45454545-4545-4454-8454-454545454545",
        run_id: run.id,
        company_id: candidate.id,
        position: 1,
        status: "RANKED",
        reason: "Research Sort Key descending, then ticker ascending.",
        input_snapshot: {
          context_version: "research-rank-inputs-v1",
          lifecycle: "CANDIDATE",
          candidate_tier: "HIGH",
          priority_seed: "3.0000",
          legacy_default_priority_seed: null,
          used_legacy_default: false,
          sort_key: "199997.0000",
          input_quality: "AVAILABLE",
          source_digest: "a".repeat(64),
          bucket_source_ref: "Portfolio_Watchlist.xlsx:Universe Registry!C5",
          priority_seed_source_ref:
            "Portfolio_Watchlist.xlsx:Candidate Ranking!A2",
          context_note: "Research Rank prioritizes research attention only.",
        },
      },
    };
  });
  let submittedType = "";
  let submittedReason = "";
  await page.route(/\/api\/research\/ranking-runs$/, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as {
      ranking_type: string;
      reason: string;
    };
    submittedType = body.ranking_type;
    submittedReason = body.reason;
    const definition = currents.find(
      (item) => item.definition.ranking_type === body.ranking_type,
    )!.definition;
    await route.fulfill({
      json: {
        id: "56565656-5656-4565-8565-565656565656",
        definition,
        as_of: recordedAt,
        recorded_at: recordedAt,
        status: "COMPLETE",
        actor: "LOCAL_USER",
        reason: body.reason,
        source: "web-universe",
        company_count: 1,
        ranked_count: 1,
      },
    });
  });
  await page.route(/\/api\/research\/universe(?:\/|$)/, (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/ranking-summary")) {
      return route.fulfill({
        json: [{ company: candidate, rankings: currents }],
      });
    }
    if (url.pathname.endsWith("/score-summary")) {
      return route.fulfill({
        json: [{ ...scoreSummary(company)[0]!, company: candidate }],
      });
    }
    return route.fulfill({ json: [] });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/universe");
  await expect(page.getByRole("link", { name: candidate.name })).toBeVisible();
  await expect(page.getByText("No Execution Pace run recorded.")).toBeVisible();
  await page.getByLabel("Ranking type").selectOption("RESEARCH");
  await expect(
    page.getByText(
      /research-attention queue, not an investment-attractiveness signal/,
    ),
  ).toBeVisible();
  await expect(page.getByText("Candidate tier / sort key")).toBeVisible();
  await expect(page.getByText("HIGH / 199997")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ranking run reason" })
    .fill("Review next research priority.");
  await page.getByRole("button", { name: "Record Research Rank" }).click();
  await expect.poll(() => submittedType).toBe("RESEARCH");
  await expect
    .poll(() => submittedReason)
    .toBe("Review next research priority.");
  await page.getByLabel("Execution Pace state").selectOption("NO_RUN");
  await expect(page.getByRole("status")).toContainText("1 businesses shown");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(
    page.getByText("Research attention queue · not an investment rank"),
  ).toBeVisible();
});

test("model outputs keep missing values visible across responsive universe and company views", async ({
  page,
}) => {
  const missingId = "22222222-2222-4222-8222-222222222222";
  const missingCompany = {
    ...company,
    id: missingId,
    name: "No model business",
  };
  const outputSnapshot = {
    id: "33333333-3333-4333-8333-333333333333",
    company_id: id,
    model_key: "P-EXAMPLE",
    snapshot_key: "CONTRACT:contract-hash",
    snapshot_kind: "CURRENT_CONTRACT",
    contract_version: "v1",
    contract_status: "PASS",
    output_quality: "PARTIAL",
    model_currency: null,
    currency_status: "UNKNOWN",
    currency_source_ref: null,
    model_status: "Legacy outputs imported",
    effective_at: null,
    recorded_at: "2026-10-05T00:00:00Z",
    actor: "IMPORT",
    source: "Portfolio_Watchlist.xlsx:P-EXAMPLE!AZ3:BA20",
    source_revision_id: null,
    revision_source: null,
    revision_type: null,
    source_actor: null,
    rationale: null,
    evidence: null,
    notes: null,
    field_issues: [],
    bear_fv: "0",
    base_fv: null,
    bull_fv: null,
    bear_probability: null,
    base_probability: null,
    bull_probability: null,
    weighted_fv: null,
    weighted_upside: null,
    expected_cash_flow_irr: null,
    hurdle: null,
    expected_excess: null,
    forward_fundamental_cagr: null,
  };
  const historySnapshot = {
    ...outputSnapshot,
    id: "44444444-4444-4444-8444-444444444444",
    snapshot_key: "LEGACY:review-1",
    snapshot_kind: "LEGACY_REVISION",
    contract_version: null,
    contract_status: "HISTORICAL_ONLY",
    effective_at: "2026-09-01T00:00:00Z",
    source_revision_id: "review-1",
    revision_type: "Prior model review",
    source_actor: "Research team",
    rationale: "Prior output retained as a historical model revision.",
    evidence: "Legacy review record",
    base_fv: "120",
  };
  const currentOutputs = {
    company_id: id,
    status: "PARTIAL",
    history_count: 2,
    models: [
      { model_key: "P-EXAMPLE", status: "PARTIAL", snapshot: outputSnapshot },
    ],
  };
  const missingOutputs = {
    company_id: missingId,
    status: "NO_MODEL",
    history_count: 0,
    models: [],
  };
  const momentumRead = {
    ...momentumSummary(id, "INSUFFICIENT_HISTORY"),
    periods: [],
  };

  await page.route(/\/api\/research\//, async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname.replace("/api/research/", "");
    if (pathname === "universe/score-summary")
      return route.fulfill({
        json: [...scoreSummary(company), ...scoreSummary(missingCompany)],
      });
    if (pathname === "universe/ranking-summary")
      return route.fulfill({ json: [] });
    if (pathname === "universe/market-summary")
      return route.fulfill({
        json: [company, missingCompany].map((issuer) => ({
          company: issuer,
          market_data: [],
        })),
      });
    if (pathname === "universe/model-output-summary")
      return route.fulfill({
        json: [
          { company, outputs: currentOutputs },
          { company: missingCompany, outputs: missingOutputs },
        ],
      });
    if (pathname === "universe/estimate-momentum-summary")
      return route.fulfill({
        json: [
          {
            company,
            estimate_momentum: momentumSummary(id, "INSUFFICIENT_HISTORY"),
          },
          {
            company: missingCompany,
            estimate_momentum: momentumSummary(missingId),
          },
        ],
      });
    if (pathname === "universe")
      return route.fulfill({ json: [company, missingCompany] });
    if (pathname === `companies/${id}`)
      return route.fulfill({
        json: {
          company,
          securities: [],
          listings: [],
          lifecycle_history: [],
          portfolio: null,
          portfolio_context: null,
          holding_snapshot: null,
          positions: [],
          target_weight: null,
          target_revision_id: null,
        },
      });
    if (pathname === `companies/${id}/market-data`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/estimate-momentum`)
      return route.fulfill({ json: momentumRead });
    if (pathname === `companies/${id}/model-outputs/current`)
      return route.fulfill({ json: currentOutputs });
    if (pathname === `companies/${id}/model-outputs/history`)
      return route.fulfill({ json: [outputSnapshot, historySnapshot] });
    if (pathname === `companies/${id}/expected-return-history`)
      return route.fulfill({
        json: {
          company_id: id,
          as_of: "2026-10-05",
          known_at: "2026-10-05T12:00:00Z",
          status: "NO_HISTORY",
          history: [],
        },
      });
    if (pathname === `companies/${id}/financial-models`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/canonical-financial-models`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/scores/current`)
      return route.fulfill({ json: scoreSummary(company)[0].scores });
    if (pathname === `companies/${id}/scores/history`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/rankings`)
      return route.fulfill({ json: companyRankingCurrent });
    if (pathname.endsWith("/model-migration-status"))
      return route.fulfill({
        json: emptyModelMigrationStatus(pathname.split("/")[1]),
      });
    return route.fulfill({
      status: 404,
      json: { detail: "Fixture route missing" },
    });
  });

  await page.goto("/universe");
  await expect(page.getByRole("link", { name: company.name })).toBeVisible();
  await expect(
    page.getByText("Not supplied", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("No current model contract is published.").first(),
  ).toBeVisible();
  await expect(
    page.getByText("No direction", { exact: true }).first(),
  ).toBeVisible();
  await page.getByLabel("Estimate Momentum state").selectOption("UNAVAILABLE");
  await expect(page.getByRole("status")).toHaveText("2 businesses shown");
  await page.getByLabel("Estimate Momentum state").selectOption("");
  await page.getByLabel("Model output coverage").selectOption("AVAILABLE");
  await expect(page.getByRole("status")).toHaveText("1 businesses shown");
  await page.getByLabel("Sort companies").selectOption("irr-desc");
  await page.getByRole("link", { name: company.name }).click();
  await expect(
    page.getByRole("navigation", { name: "Company research sections" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Company context" }),
  ).toBeVisible();
  await expect(
    page.getByText("No legacy model tab is mapped to this company."),
  ).toBeVisible();
  await expect(page.getByText("Lifecycle unassigned")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Estimate Momentum" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "No usable forward annual Revenue/EPS estimate periods are available.",
    ),
  ).toBeVisible();
  await expect(
    page.getByText("No target", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("No holding observed; data may be incomplete."),
  ).toBeVisible();
  await page.getByRole("link", { name: "Quality & risk" }).click();
  await expect(
    page.getByRole("heading", { name: "Investment quality" }),
  ).toBeVisible();
  await page.getByText("Record a new score assessment").click();
  await expect(page.getByLabel("Score dimension")).toBeVisible();
  await page.getByRole("link", { name: "Model & valuation" }).click();
  await expect(
    page.getByRole("heading", { name: "Canonical financial models" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Imported outputs" }).click();
  await expect(
    page.getByRole("heading", { name: "Imported model-output history" }),
  ).toBeVisible();
  await expect(page.getByText("Model currency: Not documented")).toBeVisible();
  await expect(
    page.getByText("Not supplied", { exact: true }).first(),
  ).toBeVisible();
  await page.getByText("Model output history (2)").click();
  await expect(
    page.getByText("Prior output retained as a historical model revision."),
  ).toBeVisible();
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await expect(
      page.getByRole("navigation", { name: "Company research sections" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Company context" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("Company Explorer composes canonical company context at desktop and mobile widths", async ({
  page,
}) => {
  const securityId = "77777777-7777-4777-8777-777777777777";
  const listingId = "88888888-8888-4888-8888-888888888888";
  const portfolioId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const snapshotId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const eventId = "99999999-9999-4999-8999-999999999999";
  const observedAt = "2026-10-04T00:00:00Z";
  const explorerCompany = {
    ...company,
    name: "Explorer business",
    reporting_currency: "USD",
    lifecycle: "PORTFOLIO",
    lifecycle_event_id: eventId,
  };
  const security = {
    id: securityId,
    company_id: id,
    name: "Explorer common stock",
    security_type: "COMMON_STOCK",
    share_class: null,
    underlying_security_id: null,
    is_demo: false,
  };
  const listing = {
    id: listingId,
    security_id: securityId,
    ticker: "EXPL",
    venue: "NASDAQ",
    currency: "USD",
    is_demo: false,
  };
  const quote = {
    id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    listing_id: listingId,
    market_date: observedAt,
    recorded_at: observedAt,
    provider_close: "42.50",
    split_adjusted_close: "42.50",
    total_return_close: null,
    volume: "100000",
    currency: "USD",
    provider: "Fixture market source",
    provider_symbol: "NASDAQ:EXPL",
    adjustment_basis: "SPLIT_ADJUSTED",
    data_quality: "PASS",
    source_ref: "browser-fixture",
  };
  const priorQuote = {
    ...quote,
    id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    market_date: "2026-10-03T00:00:00Z",
    provider_close: "41.75",
    split_adjusted_close: "41.75",
  };
  const scoreAssessments = scoreSummary(company)[0].scores.map(
    ({ definition }, index) => ({
      definition,
      assessment: {
        id: [
          "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1",
          "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2",
          "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee3",
          "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee4",
        ][index],
        company_id: id,
        score_definition_id: definition.id,
        score: ["4.50", "4.00", "3.50", "2.00"][index],
        status: "ASSESSED",
        effective_at: observedAt,
        recorded_at: observedAt,
        rationale: `Current ${definition.dimension.toLowerCase()} assessment.`,
        actor: "IMPORT",
        source: "browser-fixture",
        superseded_assessment_id: null,
      },
    }),
  );
  const portfolioRankDefinition = companyRankingCurrent.current[0].definition;
  const rankingRun = {
    id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
    definition: portfolioRankDefinition,
    as_of: observedAt,
    recorded_at: observedAt,
    status: "COMPLETE",
    actor: "IMPORT",
    reason: "Retained source position fixture.",
    source: "browser-fixture",
    company_count: 1,
    ranked_count: 1,
  };
  const rankingEntry = {
    id: "12121212-1212-4121-8121-121212121212",
    run_id: rankingRun.id,
    company_id: id,
    position: 1,
    status: "RANKED",
    reason: "Source position retained as observed.",
  };
  const rankings = {
    current: companyRankingCurrent.current.map((item, index) =>
      index === 0 ? { ...item, run: rankingRun, entry: rankingEntry } : item,
    ),
    history: [{ run: rankingRun, entry: rankingEntry }],
  };
  const paceRun = {
    id: "14141414-1414-4141-8141-141414141414",
    portfolio_id: portfolioId,
    as_of: observedAt,
    recorded_at: observedAt,
    methodology_version: "legacy-execution-pace-v1",
    status: "UNAVAILABLE",
    actor: "LOCAL_USER",
    reason: "Record current execution context.",
    source: "web-company-explorer",
    company_count: 1,
    available_count: 0,
    review_count: 1,
    unavailable_count: 0,
    not_applicable_count: 0,
  };
  let submittedPaceReason = "";
  const companyDetail = {
    company: explorerCompany,
    securities: [security],
    listings: [listing],
    lifecycle_history: [
      {
        id: eventId,
        company_id: id,
        previous_state: null,
        new_state: "PORTFOLIO",
        sequence: 1,
        actor: "IMPORT",
        reason: "Retained explicit lifecycle state.",
        source: "browser-fixture",
        effective_at: observedAt,
        recorded_at: observedAt,
      },
    ],
    portfolio: {
      id: portfolioId,
      name: "Research portfolio",
      base_currency: "USD",
      created_at: observedAt,
      is_demo: false,
    },
    portfolio_context: {
      company: explorerCompany,
      positions: [
        {
          listing_id: listingId,
          security_id: securityId,
          ticker: "EXPL",
          venue: "NASDAQ",
          currency: "USD",
          security_name: security.name,
          quantity: "2",
          latest_price: "42.50",
          price_date: observedAt,
          price_currency: "USD",
          price_freshness: "FRESH",
          native_market_value: "85.00",
          base_market_value: "85.00",
          valuation_status: "VALUED",
        },
      ],
      target_weight: "0.1",
      current_market_value: "85.00",
      current_market_currency: "USD",
      current_weight: "0.2",
      allocation_gap: "-0.1",
      allocation_status: "VALUED",
    },
    holding_snapshot: {
      id: snapshotId,
      portfolio_id: portfolioId,
      completeness: "COMPLETE",
      positions: [{ listing_id: listingId, quantity: "2" }],
      cash_positions: [],
      actor: "IMPORT",
      reason: "Complete fixture snapshot.",
      source: "browser-fixture",
      effective_at: observedAt,
      recorded_at: observedAt,
    },
    positions: [
      {
        listing_id: listingId,
        security_id: securityId,
        ticker: "EXPL",
        venue: "NASDAQ",
        currency: "USD",
        security_name: security.name,
        quantity: "2",
        latest_price: "42.50",
        price_date: observedAt,
        price_currency: "USD",
        price_freshness: "FRESH",
        native_market_value: "85.00",
        base_market_value: "85.00",
        valuation_status: "VALUED",
      },
    ],
    target_weight: "0.1",
    target_revision_id: portfolioId,
  };
  const priceRegime = {
    listing_id: listingId,
    as_of: observedAt,
    provider_close: "42.50",
    split_adjusted_close: "42.50",
    dma_20: "41.50",
    dma_50: "40.00",
    dma_200: null,
    high_52w: "45.00",
    drawdown_52w: "-0.0555",
    vs_dma_20: "0.0241",
    vs_dma_50: "0.0625",
    vs_dma_200: null,
    return_1m: "0.03",
    return_3m: "0.08",
    return_6m: null,
    realized_vol_20d: "0.20",
    trend_state: "UPTREND",
    correction_state: "NO_CORRECTION",
    regime: "UPTREND",
    data_quality: "PASS",
    quality_reason: null,
    methodology_version: "fixture-v1",
    source_ref: "browser-fixture",
  };
  const marketData = [
    {
      listing,
      latest: quote,
      history: [quote, priorQuote],
      freshness: "FRESH",
      age_days: 1,
      price_regime: priceRegime,
    },
  ];
  const revenueObservation = {
    id: "23232323-2323-4323-8323-232323232323",
    company_id: id,
    security_id: null,
    provider_id: "sec_edgar",
    provider_entity_id: "0000000001",
    source_priority: 10,
    metric: "REVENUE",
    statement: "INCOME_STATEMENT",
    period_type: "ANNUAL",
    period_start: "2025-01-01T00:00:00Z",
    period_end: "2025-12-31T00:00:00Z",
    fiscal_year: 2025,
    fiscal_period: "FY",
    filed_at: "2026-02-10T00:00:00Z",
    observed_at: observedAt,
    recorded_at: observedAt,
    value: "1000000",
    currency: "USD",
    unit: "currency",
    source_taxonomy: "us-gaap",
    source_concept: "RevenueFromContractWithCustomerExcludingAssessedTax",
    source_unit: "USD",
    accession_number: "0000000001-26-000001",
    form: "10-K",
    frame: "CY2025",
    source_record_id: "CIK0000000001:us-gaap:Revenue:USD:0000000001-26-000001",
    source_url: "https://www.sec.gov/Archives/edgar/data/1/filing-index.html",
    source_ref: "0000000001-26-000001:us-gaap:Revenue:USD",
    revision_context: "ORIGINAL",
    data_quality: "PASS",
    quality_reason: null,
    supersedes_observation_id: null,
  };
  const fundamentalMetrics = [
    ["REVENUE", "INCOME_STATEMENT"],
    ["GROSS_PROFIT", "INCOME_STATEMENT"],
    ["OPERATING_INCOME", "INCOME_STATEMENT"],
    ["NET_INCOME", "INCOME_STATEMENT"],
    ["CASH_AND_CASH_EQUIVALENTS", "BALANCE_SHEET"],
    ["CURRENT_DEBT", "BALANCE_SHEET"],
    ["NONCURRENT_DEBT", "BALANCE_SHEET"],
    ["OPERATING_CASH_FLOW", "CASH_FLOW_STATEMENT"],
    ["CAPITAL_EXPENDITURES", "CASH_FLOW_STATEMENT"],
    ["DILUTED_WEIGHTED_AVERAGE_SHARES", "INCOME_STATEMENT"],
  ] as const;
  const reportedFundamentals = {
    company_id: id,
    provider_identity_status: "MAPPED",
    provider_ids: ["0000000001"],
    coverage: fundamentalMetrics.map(([metric, statement]) => ({
      metric,
      statement,
      observation_count: metric === "REVENUE" ? 1 : 0,
      latest_period_end:
        metric === "REVENUE" ? revenueObservation.period_end : null,
      status: metric === "REVENUE" ? "AVAILABLE" : "NOT_IMPORTED",
    })),
    periods: [
      {
        metric: "REVENUE",
        statement: "INCOME_STATEMENT",
        period_type: "ANNUAL",
        period_start: revenueObservation.period_start,
        period_end: revenueObservation.period_end,
        fiscal_year: 2025,
        fiscal_period: "FY",
        currency: "USD",
        unit: "currency",
        value: "1000000",
        selection_status: "AVAILABLE",
        selected_observation: revenueObservation,
        observations: [revenueObservation],
      },
    ],
    as_of: null,
    known_at: null,
    latest_observed_at: observedAt,
  };
  const originalFilingId = "13131313-1313-4131-8131-131313131313";
  const amendmentId = "14141414-1414-4141-8141-141414141414";
  const sourceDocuments = {
    company_id: id,
    sec_identity_status: "MAPPED",
    source_count: 2,
    as_of: null,
    known_at: null,
    documents: [
      {
        id: amendmentId,
        company_id: id,
        security_id: null,
        batch_id: "15151515-1515-4151-8151-151515151515",
        provider_id: "sec_edgar",
        source_name: "U.S. Securities and Exchange Commission · EDGAR",
        source_jurisdiction: "US-SEC",
        external_identifier: "0000000001-26-000002",
        document_type: "10-K",
        source_form: "10-K/A",
        title: "2025 annual report amendment",
        reporting_period: "Period ending 2025-12-31",
        fiscal_year: null,
        fiscal_period: null,
        period_end: "2025-12-31",
        filed_at: "2026-03-01",
        published_at: "2026-03-01",
        canonical_url:
          "https://www.sec.gov/Archives/edgar/data/1/000000000126000002/0000000001-26-000002-index.html",
        retrieved_at: observedAt,
        recorded_at: observedAt,
        is_amendment: true,
        amends_document_id: originalFilingId,
        supersedes_document_id: null,
        data_quality: "PASS",
        quality_reason: null,
        actor: "IMPORT",
      },
      {
        id: originalFilingId,
        company_id: id,
        security_id: null,
        batch_id: "15151515-1515-4151-8151-151515151515",
        provider_id: "sec_edgar",
        source_name: "U.S. Securities and Exchange Commission · EDGAR",
        source_jurisdiction: "US-SEC",
        external_identifier: "0000000001-26-000001",
        document_type: "10-K",
        source_form: "10-K",
        title: "2025 annual report",
        reporting_period: "Period ending 2025-12-31",
        fiscal_year: null,
        fiscal_period: null,
        period_end: "2025-12-31",
        filed_at: "2026-02-10",
        published_at: "2026-02-10",
        canonical_url:
          "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/0000000001-26-000001-index.html",
        retrieved_at: observedAt,
        recorded_at: observedAt,
        is_amendment: false,
        amends_document_id: null,
        supersedes_document_id: null,
        data_quality: "PASS",
        quality_reason: null,
        actor: "IMPORT",
      },
    ],
  };
  const estimateObservation = {
    id: "14141414-1414-4141-8141-141414141414",
    company_id: id,
    listing_id: null,
    provider_mapping_id: "15151515-1515-4151-8151-151515151515",
    provider_id: "legacy_workbook_estimates",
    metric: "REVENUE",
    period_type: "ANNUAL",
    forecast_period: "FY+1",
    period_end: null,
    value: "120.5",
    low_value: null,
    high_value: null,
    analyst_count: null,
    currency: null,
    unit: "CURRENCY",
    snapshot_date: "2026-09-12",
    observed_at: null,
    recorded_at: observedAt,
    source_record_id: "EXPL:4:REVENUE:FY+1",
    source_ref: "workbook#Estimate History!D4",
    revision_context: "LEGACY_BASELINE",
    data_quality: "DATA_CHECK",
    quality_reason: "Source currency and absolute fiscal period are unknown.",
    supersedes_observation_id: null,
  };
  let consensusEstimateRead: {
    company_id: string;
    continuity_status: string;
    selected_provider_id: string | null;
    as_of: string | null;
    known_at: string | null;
    providers: Array<Record<string, unknown>>;
  } = {
    company_id: id,
    continuity_status: "FALLBACK_SELECTED",
    selected_provider_id: "legacy_workbook_estimates",
    as_of: null,
    known_at: null,
    providers: [
      {
        provider_id: "legacy_workbook_estimates",
        provider_symbol: "EXPL",
        role: "FALLBACK",
        priority: 1000,
        selected: true,
        mapping_status: "SELECTED",
        currency: null,
        currency_evidence_source: null,
        identity_evidence_source: "sha256:source#Estimate History",
        effective_from: "2026-09-12T00:00:00Z",
        freshness: "DATA_CHECK",
        latest_snapshot_date: "2026-09-12",
        latest_observed_at: null,
        observation_count: 1,
        missing_metrics: ["EPS"],
        periods: [
          {
            metric: "REVENUE",
            period_type: "ANNUAL",
            forecast_period: "FY+1",
            period_end: null,
            currency: null,
            unit: "CURRENCY",
            current_observation: estimateObservation,
            history: [estimateObservation],
          },
        ],
      },
    ],
  };
  const estimateMomentumRead = {
    ...momentumSummary(id, "INSUFFICIENT_HISTORY"),
    availability: "DIRECTION_ONLY",
    direction: "POSITIVE",
    raw_score: "0.5",
    confidence_adjusted_score: "0.05",
    confidence: "0.1",
    confidence_band: "COLLECTING",
    coverage_fraction: "0.05",
    coverage_count: 1,
    freshness: "FRESH",
    data_quality: "PASS",
    provider_id: "fmp_estimates",
    latest_snapshot_date: "2026-10-05",
    reason: "Direction is visible with low history coverage.",
    periods: [
      {
        metric: "REVENUE",
        horizon: "FY+1",
        forecast_period: "FY2027",
        period_end: "2027-12-31",
        currency: "USD",
        unit: "CURRENCY",
        analyst_count: 11,
        current_value: "1200000",
        current_snapshot_date: "2026-10-05",
        data_quality: "PASS",
        quality_reason: null,
        windows: [
          {
            window: "12M",
            status: "AVAILABLE",
            reference_value: "1000000",
            reference_snapshot_date: "2025-10-05",
            reference_days_before_target: 0,
            revision_fraction: "0.2",
            component_score: "2",
            reason: null,
          },
          {
            window: "6M",
            status: "MISSING_REFERENCE",
            reference_value: null,
            reference_snapshot_date: null,
            reference_days_before_target: null,
            revision_fraction: null,
            component_score: null,
            reason: "No same-provider reference exists.",
          },
          {
            window: "3M",
            status: "MISSING_REFERENCE",
            reference_value: null,
            reference_snapshot_date: null,
            reference_days_before_target: null,
            revision_fraction: null,
            component_score: null,
            reason: "No same-provider reference exists.",
          },
        ],
      },
    ],
  };
  const noModel = {
    company_id: id,
    status: "NO_MODEL",
    history_count: 0,
    models: [],
  };
  const expectedPoint = ({
    pointId,
    sourceKind,
    effectiveAt,
    recordedAt,
    seriesId,
    revisionNumber,
    isCurrent,
    weightedFairValue,
    quote,
  }: {
    pointId: string;
    sourceKind: string;
    effectiveAt: string;
    recordedAt: string;
    seriesId: string;
    revisionNumber: number | null;
    isCurrent: boolean;
    weightedFairValue: string;
    quote: string;
  }) => ({
    point_id: pointId,
    source_kind: sourceKind,
    event_status: "DATED",
    effective_at: effectiveAt,
    recorded_at: recordedAt,
    series_id: seriesId,
    model_key: "P-EXPL",
    model_id:
      sourceKind === "NATIVE_MODEL_REVISION"
        ? "13131313-1313-4131-8131-131313131313"
        : null,
    revision_id: sourceKind === "NATIVE_MODEL_REVISION" ? pointId : null,
    revision_number: revisionNumber,
    model_type:
      sourceKind === "NATIVE_MODEL_REVISION" ? "UFCF_DCF_10Y_FADE" : null,
    methodology_version:
      sourceKind === "NATIVE_MODEL_REVISION" ? "dcf-v1" : null,
    model_label: "Explorer DCF",
    model_currency: "USD",
    currency_status: "DOCUMENTED",
    valuation_listing_id: listingId,
    valuation_ticker: "EXPL",
    valuation_venue: "NASDAQ",
    valuation_listing_currency: "USD",
    is_current_at_cutoff: isCurrent,
    output_status: "COMPLETE",
    output_quality: "COMPLETE",
    contract_status: sourceKind === "NATIVE_MODEL_REVISION" ? null : "PASS",
    return_semantics:
      sourceKind === "NATIVE_MODEL_REVISION"
        ? "NATIVE_METHOD_OUTPUT"
        : "LEGACY_NORMALIZED_FIELD",
    actor: sourceKind === "NATIVE_MODEL_REVISION" ? "LOCAL_USER" : "IMPORT",
    source_actor:
      sourceKind === "NATIVE_MODEL_REVISION" ? null : "Workbook researcher",
    revision_source: sourceKind === "NATIVE_MODEL_REVISION" ? null : "Workbook",
    revision_type:
      sourceKind === "NATIVE_MODEL_REVISION" ? null : "Periodic review",
    bear_fv: "35",
    base_fv: weightedFairValue,
    bull_fv: "75",
    bear_probability: "0.2",
    base_probability: "0.6",
    bull_probability: "0.2",
    weighted_fv: weightedFairValue,
    weighted_upside: "0.25",
    expected_cash_flow_irr: "0.14",
    hurdle: "0.10",
    expected_excess: "0.04",
    forward_fundamental_cagr: "0.09",
    market_price: {
      status: "AVAILABLE",
      listing_id: listingId,
      ticker: "EXPL",
      venue: "NASDAQ",
      listing_currency: "USD",
      quote,
      quote_currency: "USD",
      model_reference_price: quote,
      model_currency: "USD",
      effective_at: effectiveAt,
      observed_at: effectiveAt,
      recorded_at: effectiveAt,
      provider: "Fixture market source",
      adjustment_basis: "SPLIT_ADJUSTED",
      observation_id: "23232323-2323-4232-8232-232323232323",
      source_ref: "browser-fixture",
      reason: null,
    },
    estimate_context: {
      status: "AVAILABLE",
      provider_id: "fmp_estimates",
      periods: [
        {
          observation_id: "24242424-2424-4242-8242-242424242424",
          metric: "REVENUE",
          period_type: "ANNUAL",
          forecast_period: "FY2027",
          period_end: "2027-12-31",
          value: "1200000",
          currency: "USD",
          unit: "CURRENCY",
          analyst_count: 11,
          snapshot_date: effectiveAt.slice(0, 10),
          observed_at: effectiveAt,
          recorded_at: effectiveAt,
          provider_id: "fmp_estimates",
          source_ref: "browser-fixture",
          data_quality: "PASS",
          quality_reason: null,
        },
      ],
    },
    source:
      sourceKind === "NATIVE_MODEL_REVISION" ? "Web editor" : "Legacy workbook",
    source_revision_id: revisionNumber === null ? "legacy-revision-1" : null,
    rationale: "Retained point-in-time output for the browser fixture.",
    evidence: null,
  });
  const expectedReturnHistory = {
    company_id: id,
    as_of: "2026-10-05",
    known_at: "2026-10-05T23:59:59Z",
    status: "AVAILABLE",
    history: [
      expectedPoint({
        pointId: "19191919-1919-4191-8191-191919191919",
        sourceKind: "NATIVE_MODEL_REVISION",
        effectiveAt: "2026-10-01T16:00:00Z",
        recordedAt: "2026-10-01T16:00:00Z",
        seriesId: "native:13131313-1313-4131-8131-131313131313",
        revisionNumber: 1,
        isCurrent: false,
        weightedFairValue: "50",
        quote: "40",
      }),
      expectedPoint({
        pointId: "legacy:fixture-snapshot",
        sourceKind: "IMPORTED_LEGACY_REVISION",
        effectiveAt: "2026-10-02T16:00:00Z",
        recordedAt: "2026-10-03T10:00:00Z",
        seriesId: "legacy:P-EXPL",
        revisionNumber: null,
        isCurrent: false,
        weightedFairValue: "48",
        quote: "41",
      }),
      expectedPoint({
        pointId: "20202020-2020-4202-8202-202020202020",
        sourceKind: "NATIVE_MODEL_REVISION",
        effectiveAt: "2026-10-05T16:00:00Z",
        recordedAt: "2026-10-05T16:00:00Z",
        seriesId: "native:13131313-1313-4131-8131-131313131313",
        revisionNumber: 2,
        isCurrent: true,
        weightedFairValue: "55",
        quote: "42.5",
      }),
    ],
  };
  const attributionState = (
    point: (typeof expectedReturnHistory.history)[number],
  ) => ({
    point_id: point.point_id,
    source_kind: point.source_kind,
    effective_at: point.effective_at,
    recorded_at: point.recorded_at,
    series_id: point.series_id,
    model_id: point.model_id,
    revision_id: point.revision_id,
    revision_number: point.revision_number,
    model_type: point.model_type,
    methodology_version: point.methodology_version,
    return_semantics: point.return_semantics,
    model_currency: point.model_currency,
    expected_cash_flow_irr: point.expected_cash_flow_irr,
    hurdle: point.hurdle,
    expected_excess: point.expected_excess,
    bear_fv: point.bear_fv,
    base_fv: point.base_fv,
    bull_fv: point.bull_fv,
    bear_probability: point.bear_probability,
    base_probability: point.base_probability,
    bull_probability: point.bull_probability,
    weighted_fv: point.weighted_fv,
    market_price: point.market_price,
    estimate_context: point.estimate_context,
    source: point.source,
    source_revision_id: point.source_revision_id,
    rationale: point.rationale,
  });
  const temporalValue = (
    value: string,
    effectiveAt: string,
    source: string,
    recordedAt = observedAt,
  ) => ({
    status: "AVAILABLE",
    value,
    currency: "USD",
    unit: "currency",
    source_name: source,
    source_reference: "browser-fixture",
    source_observation_id: "16161616-1616-4161-8161-161616161616",
    period_end: "2027-12-31",
    effective_at: effectiveAt,
    observed_at: observedAt,
    recorded_at: recordedAt,
    data_quality: "PASS",
    quality_reason: null,
    low_value: null,
    high_value: null,
    analyst_count: null,
  });
  let temporalAlignment: Record<string, unknown> = {
    company_id: id,
    metric: "REVENUE",
    fiscal_year: 2027,
    as_of: "2026-10-04",
    forecast_known_at: "2026-10-04T23:59:59.999999Z",
    outcome_known_at: "2028-03-01T12:00:00Z",
    horizon_days: 365,
    fiscal_year_mapping_basis: "NO_EXPLICIT_MODEL_FISCAL_YEAR_ANCHOR",
    comparison_status: "FISCAL_YEAR_MAPPING_UNAVAILABLE",
    consensus: {
      ...temporalValue("1100000", "2026-10-04T00:00:00Z", "fmp_estimates"),
      low_value: "1000000",
      high_value: "1200000",
      analyst_count: 14,
    },
    actual: temporalValue("1050000", "2028-02-15T00:00:00Z", "sec_edgar"),
    model_forecasts: [
      {
        model_id: "17171717-1717-4171-8171-171717171717",
        model_name: "Native DCF",
        model_type: "UFCF_DCF_10Y_FADE",
        model_currency: "USD",
        valuation_listing: listing,
        status: "FISCAL_YEAR_MAPPING_UNAVAILABLE",
        forecast_year: null,
        fiscal_year_mapping_basis: "NO_EXPLICIT_MODEL_FISCAL_YEAR_ANCHOR",
        value: null,
        unit: "currency",
        revision_id: "18181818-1818-4181-8181-181818181818",
        revision_number: 3,
        methodology_version: "dcf-v1",
        revision_source: "local research",
        rationale: "Ordinal projections have no explicit fiscal-year anchor.",
        effective_at: "2026-10-01T00:00:00Z",
        recorded_at: observedAt,
        price_at_forecast: {
          status: "AVAILABLE",
          listing,
          market_date: observedAt,
          close: "42.50",
          total_return_close: "42.50",
          currency: "USD",
          provider: "YAHOO_FINANCE",
          observed_at: observedAt,
          recorded_at: observedAt,
          data_quality: "PASS",
          age_days: 0,
          reason: null,
        },
        subsequent_market_return: {
          status: "AVAILABLE",
          horizon_days: 365,
          target_date: "2027-10-04",
          start_market_date: observedAt,
          end_market_date: "2027-10-04T00:00:00Z",
          start_total_return_close: "42.50",
          end_total_return_close: "55.25",
          return_fraction: "0.3",
          actual_days: 365,
          basis: "TOTAL_RETURN_CLOSE",
          reason: null,
        },
      },
    ],
  };
  const migrationStatus = {
    company_id: id,
    inventory_available: true,
    models: [
      {
        model_key: "P-EXPL",
        company_name: "Explorer business",
        canonical_ticker: "EXPL",
        lifecycle: "PORTFOLIO",
        methodology_family: "UFCF_DCF_10Y_FADE",
        model_currency: "USD",
        inventory_status: "READY_FOR_NATIVE_IMPORT",
        representation_status: "NATIVE_EDITABLE",
        output_snapshot_available: true,
        output_contract_status: "PASS",
        native_model_id: "13131313-1313-4131-8131-131313131313",
        native_revision_number: 1,
        parity_status: "PARITY_PASS",
        projections_compared: 30,
        projections_passed: 30,
        outputs_compared: 22,
        outputs_passed: 22,
        blockers: [],
        legacy_return_semantics:
          "Legacy enterprise cash-flow return semantics.",
      },
    ],
  };

  await page.route(/\/api\/research\//, (route) => {
    const pathname = new URL(route.request().url()).pathname.replace(
      "/api/research/",
      "",
    );
    if (pathname === `companies/${id}`)
      return route.fulfill({ json: companyDetail });
    if (pathname === `companies/${id}/scores/current`)
      return route.fulfill({ json: scoreAssessments });
    if (pathname === `companies/${id}/scores/history`)
      return route.fulfill({ json: scoreAssessments });
    if (pathname === `companies/${id}/rankings`)
      return route.fulfill({ json: rankings });
    if (pathname === `companies/${id}/execution-pace`)
      return route.fulfill({
        json: { company_id: id, current: null, history: [] },
      });
    if (pathname === "execution-pace-runs") {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON() as { reason: string };
        submittedPaceReason = body.reason;
        return route.fulfill({
          status: 201,
          json: { ...paceRun, reason: body.reason },
        });
      }
      return route.fulfill({ json: [] });
    }
    if (pathname === `companies/${id}/model-migration-status`)
      return route.fulfill({ json: migrationStatus });
    if (pathname === `companies/${id}/market-data`)
      return route.fulfill({ json: marketData });
    if (pathname === `companies/${id}/reported-fundamentals`)
      return route.fulfill({ json: reportedFundamentals });
    if (pathname === `companies/${id}/source-documents`)
      return route.fulfill({ json: sourceDocuments });
    if (pathname === `companies/${id}/consensus-estimates`)
      return route.fulfill({ json: consensusEstimateRead });
    if (pathname === `companies/${id}/estimate-momentum`)
      return route.fulfill({ json: estimateMomentumRead });
    if (pathname === `companies/${id}/temporal-alignment`)
      return route.fulfill({ json: temporalAlignment });
    if (pathname === `companies/${id}/expected-return-history`)
      return route.fulfill({ json: expectedReturnHistory });
    if (pathname === `companies/${id}/expected-return-attribution`) {
      const url = new URL(route.request().url());
      const prior = expectedReturnHistory.history.find(
        (point) => point.point_id === url.searchParams.get("prior_point_id"),
      );
      const current = expectedReturnHistory.history.find(
        (point) => point.point_id === url.searchParams.get("current_point_id"),
      );
      if (!prior || !current)
        return route.fulfill({
          status: 404,
          json: { detail: "Point missing" },
        });
      return route.fulfill({
        json: {
          company_id: id,
          status: "ATTRIBUTED",
          method: "SYMMETRIC_COUNTERFACTUAL_SHAPLEY",
          prior: attributionState(prior),
          current: attributionState(current),
          expected_irr_change: "0.02",
          drivers: [
            {
              code: "MARKET_PRICE",
              label: "Market-price movement",
              effect: "-0.01",
              explanation: "Exact accepted prices were recalculated.",
            },
            {
              code: "SCENARIO_PROBABILITIES",
              label: "Scenario-probability changes",
              effect: "0.005",
              explanation: "Scenario cash flows were reweighted.",
            },
            {
              code: "REQUIRED_RETURN_ASSUMPTIONS",
              label: "Required-return assumptions",
              effect: "0.01",
              explanation:
                "A lower hurdle is a changed return constraint, not improved company economics.",
            },
            {
              code: "MODEL_ASSUMPTIONS",
              label: "Operating and model assumptions",
              effect: "0.015",
              explanation: "Operating and terminal assumptions changed.",
            },
          ],
          residual: "0",
          residual_reason: null,
          context_changes: {
            weighted_fv: "5",
            bear_fv: "0",
            base_fv: "5",
            bull_fv: "0",
            bear_probability: "0",
            base_probability: "0",
            bull_probability: "0",
            hurdle: "0",
            expected_excess: "0.02",
          },
          estimate_context_note:
            "Estimates are contextual and not consumed by this model.",
        },
      });
    }
    if (pathname === `companies/${id}/model-outputs/current`)
      return route.fulfill({ json: noModel });
    if (pathname === `companies/${id}/model-outputs/history`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/financial-models`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/canonical-financial-models`)
      return route.fulfill({ json: [] });
    return route.fulfill({
      status: 404,
      json: { detail: "Fixture route missing" },
    });
  });

  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto(`/company/${id}`);
    await expect(
      page.getByRole("heading", { name: "Company context" }),
    ).toBeVisible();
    await expect(page.getByText("EXPL · NASDAQ · USD").first()).toBeVisible();
    await expect(
      page.locator("#overview").getByText("10%", { exact: true }),
    ).toBeVisible();
    await expect(
      page.locator("#overview").getByText("20%", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("-10%", { exact: true })).toBeVisible();
    await expect(
      page.getByText("VALUED", { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByText("4.50 / 5", { exact: true })).toBeVisible();
    await expect(page.getByText("Higher means greater risk")).toBeVisible();
    await expect(page.getByText("$42.50").first()).toBeVisible();
    await expect(page.getByText("Fresh · 1d")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Reported fundamentals" }),
    ).toBeVisible();
    await expect(
      page.locator("#reported-fundamentals").getByText("SEC identity · mapped"),
    ).toBeVisible();
    await expect(page.getByText("$1,000,000.00")).toBeVisible();
    await expect(page.getByText("Cash & equivalents")).toBeVisible();
    await expect(page.getByText("Not imported").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Filings & source documents" }),
    ).toBeVisible();
    const documents = page.getByRole("region", {
      name: "Filings & source documents",
    });
    await expect(documents.getByText("SEC identity · mapped")).toBeVisible();
    await expect(
      documents.getByText("2025 annual report amendment"),
    ).toBeVisible();
    await expect(
      documents.getByText("Amendment", { exact: true }),
    ).toBeVisible();
    await expect(
      documents.getByText("Amends · 2025 annual report", { exact: true }),
    ).toBeVisible();
    await expect(
      documents.getByRole("link", { name: "Open source" }).first(),
    ).toHaveAttribute("href", /https:\/\/www\.sec\.gov\/Archives/);
    await expect(
      page.getByRole("heading", { name: "Consensus estimates" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Estimate Momentum" }),
    ).toBeVisible();
    await expect(page.getByText("Analyst coverage: 11")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Forecast vs. outcome" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Expected-return history" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Execution Pace" }),
    ).toBeVisible();
    await expect(
      page.getByText("No decision has been recorded."),
    ).toBeVisible();
    const returnHistory = page.getByRole("region", {
      name: "Expected-return history",
    });
    await expect(
      returnHistory.getByText("Current accepted model state"),
    ).toBeVisible();
    await expect(
      returnHistory.getByText("Why Expected IRR changed"),
    ).toBeVisible();
    await expect(
      returnHistory.getByText("Counterfactual contributions"),
    ).toBeVisible();
    await expect(
      returnHistory.getByText("Residual / unexplained"),
    ).toBeVisible();
    await expect(
      returnHistory.getByLabel("Prior Expected IRR state"),
    ).toBeVisible();
    await returnHistory
      .getByLabel("Expected-return model series")
      .selectOption("legacy:P-EXPL::USD");
    await expect(
      returnHistory.getByText("Imported legacy snapshot"),
    ).toBeVisible();
    await returnHistory
      .locator("details")
      .filter({ hasText: "Imported legacy snapshot" })
      .locator("summary")
      .click();
    await expect(
      returnHistory.getByText(/source author Workbook researcher/),
    ).toBeVisible();
    await expect(
      returnHistory.getByRole("img", {
        name: /Fair value and comparable price/,
      }),
    ).toBeVisible();
    await expect(returnHistory.getByRole("status")).toContainText(
      "3 total immutable imported/native model point(s)",
    );
    const temporal = page.getByRole("region", { name: "Forecast vs. outcome" });
    await expect(temporal.getByText(/FY2027 cannot be assigned/)).toBeVisible();
    await expect(temporal.getByText("fmp_estimates")).toBeVisible();
    await expect(temporal.getByText("sec_edgar")).toBeVisible();
    await expect(temporal.getByText("30%", { exact: true })).toBeVisible();
    await expect(temporal.getByLabel("Forecast date")).toBeVisible();
    await expect(temporal.getByLabel("Return horizon")).toBeVisible();
    await expect(page.getByText("FALLBACK SELECTED")).toBeVisible();
    await expect(page.getByText("FY+1 · legacy horizon only")).toBeVisible();
    await expect(
      page
        .getByRole("region", { name: "Consensus estimates" })
        .locator("span.text-2xl")
        .filter({ hasText: "Currency unknown 120.5" }),
    ).toBeVisible();
    await expect(page.getByText("Coverage · Unknown")).toBeVisible();
    await expect(
      page.getByText("No captured EPS estimate for this source."),
    ).toBeVisible();
    await page.getByText("Revision history · 1 snapshot").click();
    await expect(
      page.getByText("Workbook reference · Estimate History!D4"),
    ).toBeVisible();
    await page.getByText("Filing history (1)").click();
    await expect(page.getByText("ORIGINAL · filed")).toBeVisible();
    await expect(page.getByText("#1", { exact: true }).first()).toBeVisible();
    await expect(
      page.getByText(/Ranking inputs are not migrated/).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Canonical financial models" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Model migration status" }),
    ).toBeVisible();
    await expect(page.getByText("Native · editable")).toBeVisible();
    await expect(page.getByText("Projections: 30/30 matched")).toBeVisible();
    await expect(
      page.getByText(/No application-owned financial model has been accepted/),
    ).toBeVisible();
    await page.getByRole("button", { name: "Create first DCF model" }).click();
    await expect(
      page.getByRole("heading", { name: "Create the first DCF model" }),
    ).toBeVisible();
    await expect(page.getByLabel("Valuation listing")).toBeVisible();
    await expect(page.getByLabel("Model currency")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByRole("heading", { name: "Additional canonical models" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "New residual-income model" })
      .click();
    await expect(
      page.getByText("Create residual-income model", { exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("Current book value per share")).toBeVisible();
    await expect(page.getByLabel("BASE scenario rationale")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Cancel" }).click();
    await page
      .getByText("Price history and regime measures (90 sessions)")
      .click();
    await expect(
      page.getByRole("img", {
        name: "Recent split-adjusted daily closing prices",
      }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page
    .getByLabel("Review rationale")
    .fill("Reassessed source coverage before pacing.");
  await page.getByRole("button", { name: "Record Execution Pace" }).click();
  await expect
    .poll(() => submittedPaceReason)
    .toBe("Reassessed source coverage before pacing.");
  consensusEstimateRead = {
    company_id: id,
    continuity_status: "NO_MAPPING",
    selected_provider_id: null,
    as_of: null,
    known_at: null,
    providers: [],
  };
  const emptyTemporalValue = {
    status: "NO_MAPPING",
    value: null,
    currency: null,
    unit: null,
    source_name: null,
    source_reference: null,
    source_observation_id: null,
    period_end: null,
    effective_at: null,
    observed_at: null,
    recorded_at: null,
    data_quality: null,
    quality_reason: null,
    low_value: null,
    high_value: null,
    analyst_count: null,
  };
  temporalAlignment = {
    ...temporalAlignment,
    comparison_status: "FISCAL_YEAR_MAPPING_UNAVAILABLE",
    consensus: emptyTemporalValue,
    actual: { ...emptyTemporalValue, status: "NOT_REPORTED" },
  };
  await page.goto(`/company/${id}`);
  await expect(
    page.getByText("No consensus provider identity is mapped."),
  ).toBeVisible();
  const temporalRegion = page.getByRole("region", {
    name: "Forecast vs. outcome",
  });
  await expect(
    temporalRegion.getByText("Unavailable", { exact: true }),
  ).toHaveCount(3);
  await expect(temporalRegion.getByText("NOT REPORTED")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("Company Explorer exports, previews and accepts a Sheets contract responsively", async ({
  page,
}) => {
  const security = {
    id: contractListing.security_id,
    company_id: id,
    name: "Example common stock",
    security_type: "COMMON_STOCK",
    share_class: null,
    underlying_security_id: null,
    is_demo: true,
  };
  const detail = {
    company,
    securities: [security],
    listings: [contractListing],
    lifecycle_history: [],
    portfolio: null,
    portfolio_context: null,
    holding_snapshot: null,
    positions: [],
    target_weight: null,
    target_revision_id: null,
  };
  const noModelOutputs = {
    company_id: id,
    status: "NO_MODEL",
    history_count: 0,
    models: [],
  };
  const outputSummary = {
    status: "PARTIAL",
    model_currency: "USD",
    price_status: "NO_DATA",
    current_price: null,
    price_effective_at: null,
    price_unavailable_reason: "No comparable quote is available.",
    bear_fv: "15",
    base_fv: "20",
    bull_fv: "30",
    weighted_fv: "21",
    weighted_upside: null,
    expected_cash_flow_irr: null,
    hurdle: "0.09",
    expected_excess: null,
    irr_unavailable_reason: "No comparable quote is available.",
  };
  let activeModel: object = contractModel;
  let draftCalculation: Record<string, unknown> | null = null;
  const uploadedContract: {
    value:
      | {
          candidate_revision: {
            source_revision_id: string;
            effective_at: string;
            scenarios: Array<{ years: Array<{ revenue_growth: string }> }>;
          };
        }
      | undefined;
  } = { value: undefined };
  await page.route(/\/api\/research\//, async (route) => {
    const pathname = new URL(route.request().url()).pathname.replace(
      "/api/research/",
      "",
    );
    if (pathname === `companies/${id}`) return route.fulfill({ json: detail });
    if (pathname === `companies/${id}/financial-models`)
      return route.fulfill({ json: [activeModel] });
    if (pathname === `companies/${id}/market-data`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/scores/current`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/scores/history`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/rankings`)
      return route.fulfill({ json: companyRankingCurrent });
    if (pathname.endsWith("/model-migration-status"))
      return route.fulfill({
        json: emptyModelMigrationStatus(pathname.split("/")[1]),
      });
    if (pathname === `companies/${id}/model-outputs/current`)
      return route.fulfill({ json: noModelOutputs });
    if (pathname === `companies/${id}/model-outputs/history`)
      return route.fulfill({ json: [] });
    if (pathname === `companies/${id}/expected-return-history`)
      return route.fulfill({
        json: {
          company_id: id,
          as_of: "2026-10-05",
          known_at: "2026-10-05T12:00:00Z",
          status: "NO_HISTORY",
          history: [],
        },
      });
    if (pathname === `financial-models/${contractModelId}/contract`)
      return route.fulfill({ json: portableContract });
    if (
      pathname === `financial-models/${contractModelId}/contract/preview` &&
      route.request().method() === "POST"
    ) {
      const posted = route.request().postDataJSON();
      uploadedContract.value = posted;
      return route.fulfill({
        json: {
          status: "READY",
          model_id: contractModelId,
          base_revision_id: contractRevisionId,
          current_revision_id: contractRevisionId,
          current_revision_number: 1,
          source_revision_id: posted.candidate_revision.source_revision_id,
          actor: "IMPORT",
          source: "Google Sheets portable contract",
          effective_at: posted.candidate_revision.effective_at,
          proposed_revision_number: 2,
          already_imported_revision_id: null,
          reason: null,
          changes: [
            {
              path: "scenarios.BASE.years.1.revenue_growth",
              previous: "0.1",
              proposed: "0.11",
            },
            {
              path: "revision.rationale",
              previous: "Initial reviewed scenario assumptions.",
              proposed: "Sheets review updated the Base case.",
            },
          ],
          output_changes: [
            {
              path: "outputs.base_fv",
              previous: "20",
              proposed: "21",
            },
          ],
          current_outputs: outputSummary,
          calculated_outputs: outputSummary,
        },
      });
    }
    if (
      pathname === `financial-models/${contractModelId}/contract/import` &&
      route.request().method() === "POST"
    ) {
      const candidate = route.request().postDataJSON().candidate_revision;
      const revisionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
      const outputs = {
        ...contractOutputs,
        id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        revision_id: revisionId,
        base_fv: "21",
        weighted_fv: "22",
      };
      const scenarios = candidate.scenarios.map(
        (scenario: Record<string, unknown>, scenarioIndex: number) => {
          const scenarioId = contractScenarioIds[scenarioIndex];
          const years = scenario.years as Array<Record<string, unknown>>;
          return {
            ...scenario,
            id: scenarioId,
            revision_id: revisionId,
            years: years.map((year, yearIndex) => ({
              ...year,
              id: `cccccccc-cccc-4ccc-8ccc-${String(scenarioIndex * 5 + yearIndex).padStart(12, "0")}`,
              scenario_id: scenarioId,
            })),
          };
        },
      );
      const revision = {
        ...contractRevision,
        id: revisionId,
        revision_number: 2,
        base_revision_id: contractRevisionId,
        source_revision_id: candidate.source_revision_id,
        actor: "IMPORT",
        source: candidate.source,
        rationale: candidate.rationale,
        effective_at: candidate.effective_at,
        recorded_at: "2026-10-05T00:05:00Z",
        outputs,
        scenarios,
      };
      activeModel = {
        ...contractModel,
        current_revision_id: revisionId,
        current_revision: revision,
        history: [revision, contractRevision],
      };
      return route.fulfill({
        json: { status: "IMPORTED", model: activeModel, revision },
      });
    }
    if (
      pathname === `financial-models/${contractModelId}/revisions/preview` &&
      route.request().method() === "POST"
    ) {
      const currentModel = activeModel as {
        current_revision_id: string;
        current_revision: {
          id: string;
          revision_number: number;
          outputs: Record<string, unknown>;
          scenarios: Array<{ id: string; scenario: string }>;
          projections: Array<Record<string, unknown>>;
        };
      };
      const current = currentModel.current_revision;
      const outputs = { ...current.outputs };
      delete outputs.id;
      delete outputs.revision_id;
      const scenarios = new Map(
        current.scenarios.map((scenario) => [scenario.id, scenario.scenario]),
      );
      const projections = current.projections.map((projection) => {
        const values = { ...projection };
        delete values.id;
        const scenario_id = values.scenario_id;
        delete values.scenario_id;
        const changed =
          scenarios.get(String(scenario_id)) === "BASE" &&
          Number(values.forecast_year) === 1;
        return {
          ...values,
          scenario: scenarios.get(String(scenario_id)),
          revenue: changed ? "112" : values.revenue,
        };
      });
      draftCalculation = {
        model_id: contractModelId,
        base_revision_id: currentModel.current_revision_id,
        current_revision_id: currentModel.current_revision_id,
        current_revision_number: current.revision_number,
        model_currency: "USD",
        outputs: {
          ...outputs,
          base_fv: "21.5",
          weighted_fv: "22.5",
        },
        projections,
      };
      return route.fulfill({ json: draftCalculation });
    }
    if (
      pathname === `financial-models/${contractModelId}/revisions` &&
      route.request().method() === "POST"
    ) {
      const posted = route.request().postDataJSON();
      const previousModel = activeModel as {
        history: Array<Record<string, unknown>>;
        current_revision: Record<string, unknown>;
        current_revision_id: string;
      };
      const previous = previousModel.current_revision;
      const revisionId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
      const scenarioNames = posted.scenarios as Array<Record<string, unknown>>;
      const scenarios = scenarioNames.map((scenario, index) => {
        const scenarioId = contractScenarioIds[index];
        const prior = previous as {
          scenarios: Array<{
            scenario: string;
            years: Array<{ id: string }>;
          }>;
        };
        const priorScenario = prior.scenarios.find(
          (item) => item.scenario === scenario.scenario,
        );
        return {
          ...scenario,
          scenario: String(scenario.scenario),
          id: scenarioId,
          revision_id: revisionId,
          years: (scenario.years as Array<Record<string, unknown>>).map(
            (year, yearIndex) => ({
              ...year,
              id:
                priorScenario?.years[yearIndex]?.id ??
                `77777777-7777-4777-8777-${String(index * 5 + yearIndex).padStart(12, "0")}`,
              scenario_id: scenarioId,
            }),
          ),
        };
      });
      const calculation = draftCalculation as {
        outputs: Record<string, unknown>;
        projections: Array<Record<string, unknown>>;
      };
      const outputs = {
        ...(previous.outputs as Record<string, unknown>),
        ...calculation.outputs,
        id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        revision_id: revisionId,
      };
      const scenarioIds = new Map<string, string>(
        scenarios.map(
          (scenario) =>
            [String(scenario.scenario), String(scenario.id)] as [
              string,
              string,
            ],
        ),
      );
      const projections = calculation.projections.map((projection, index) => ({
        ...projection,
        id: `88888888-8888-4888-8888-${String(index + 1).padStart(12, "0")}`,
        scenario_id: scenarioIds.get(String(projection.scenario)),
      }));
      const revision = {
        ...previous,
        id: revisionId,
        revision_number: Number(previous.revision_number) + 1,
        base_revision_id: previousModel.current_revision_id,
        source_revision_id: null,
        actor: "LOCAL_USER",
        source: posted.source,
        rationale: posted.rationale,
        effective_at: posted.effective_at,
        recorded_at: "2026-10-05T00:06:00Z",
        base: posted.base,
        scenarios,
        projections,
        outputs,
      };
      activeModel = {
        ...contractModel,
        current_revision_id: revisionId,
        current_revision: revision,
        history: [revision, ...previousModel.history],
      };
      return route.fulfill({ json: revision });
    }
    if (
      pathname.startsWith(`financial-models/${contractModelId}/revisions/`) &&
      route.request().method() === "GET"
    ) {
      const revisionId = pathname.split("/").at(-1);
      const history = (activeModel as { history: Array<{ id: string }> })
        .history;
      const revision = history.find((item) => item.id === revisionId);
      return route.fulfill({
        status: revision ? 200 : 404,
        json: revision ?? { detail: "Revision fixture missing" },
      });
    }
    return route.fulfill({
      status: 404,
      json: { detail: "Fixture route missing" },
    });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/company/${id}`);
  await page.getByRole("link", { name: "Model & valuation" }).click();
  await expect(page.getByText("Google Sheets round trip")).toBeVisible();
  const downloadStarted = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export contract" }).click();
  expect((await downloadStarted).suggestedFilename()).toContain(
    "model-contract-v1.json",
  );

  const edited = structuredClone(portableContract);
  edited.candidate_revision.scenarios[1].years[0].revenue_growth = "0.11";
  edited.candidate_revision.rationale = "Sheets review updated the Base case.";
  await page.getByLabel("Preview edited contract").setInputFiles({
    name: "sheets-edited-contract.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(edited)),
  });
  await expect(page.getByText("Preview: READY")).toBeVisible();
  await expect(
    page.getByText("scenarios.BASE.years.1.revenue_growth"),
  ).toBeVisible();
  expect(
    uploadedContract.value?.candidate_revision.scenarios[1].years[0]
      .revenue_growth,
  ).toBe("0.11");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Accept as revision 2" }).click();
  await expect(
    page.getByText("External model revision accepted and added to history."),
  ).toBeVisible();
  await expect(page.getByText(/revision 2/).first()).toBeVisible();
  await expect(page.getByText(/Accepted .*IMPORT/).first()).toBeVisible();
  await page.getByRole("button", { name: "Revise assumptions" }).click();
  await page.getByLabel("Base revenue (billions)").fill("110");
  await page
    .getByLabel("Revision rationale")
    .fill("Updated the base-year revenue after reviewing the latest filing.");
  await page
    .getByLabel("Source URL or reference (optional)")
    .fill("https://example.test/filing");
  await expect(
    page.getByText("Recalculating projections and normalized outputs…"),
  ).toBeVisible();
  await expect(page.getByText("Accepted revision 2 → draft")).toBeVisible();
  await expect(page.getByText("$21.50")).toBeVisible();
  await expect(page.getByText("100 → 112")).toBeVisible();
  await page.getByRole("button", { name: "BEAR", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ten-year projections" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Accept model revision" }).click();
  await expect(page.getByText(/Revision 3 accepted/)).toBeVisible();
  await expect(page.getByText(/2 normalized outputs changed/)).toBeVisible();
  await page.getByText("Revision history (3)").click();
  await page
    .getByRole("button", { name: "Inspect and compare with current revision" })
    .first()
    .click();
  const revisionComparison = page.getByText(
    "Compare with current revision · 1 changed assumption",
  );
  await expect(revisionComparison).toBeVisible();
  await revisionComparison.click();
  await expect(
    page.getByText("Base revenue (billions): 100 → 110"),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("portfolio dashboard composes canonical posture, ranks and missing states responsively", async ({
  page,
}) => {
  const portfolioId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const listingId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const securityId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
  const watchlistId = "22222222-2222-4222-8222-222222222222";
  const portfolioCompany = { ...company, lifecycle: "PORTFOLIO" as const };
  const watchlistCompany = {
    ...company,
    id: watchlistId,
    name: "Watchlist opportunity",
    lifecycle: "WATCHLIST" as const,
  };
  const currentTime = "2026-10-05T12:00:00Z";
  const overview = {
    portfolio: {
      id: portfolioId,
      name: "Long-term portfolio",
      base_currency: "USD",
      created_at: "2026-01-01T00:00:00Z",
      is_demo: false,
    },
    snapshot: {
      id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      portfolio_id: portfolioId,
      completeness: "COMPLETE",
      positions: [{ listing_id: listingId, quantity: "10" }],
      cash_positions: [{ currency: "USD", balance: "100" }],
      actor: "IMPORT",
      reason: "Complete test holding observation.",
      source: "browser-fixture",
      effective_at: currentTime,
      recorded_at: currentTime,
    },
    target_revision: {
      id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      portfolio_id: portfolioId,
      status: "ACCEPTED",
      allocations: [{ company_id: id, weight: "0.4" }],
      actor: "IMPORT",
      reason: "Accepted strategic target.",
      source: "browser-fixture",
      effective_at: currentTime,
      recorded_at: currentTime,
      accepted_at: currentTime,
      invested_weight: "0.4",
      strategic_cash_weight: "0.6",
    },
    companies: [
      {
        company: portfolioCompany,
        positions: [
          {
            listing_id: listingId,
            security_id: securityId,
            ticker: "EXM",
            venue: "NASDAQ",
            currency: "USD",
            security_name: "Example common stock",
            quantity: "10",
            latest_price: "90",
            price_date: currentTime,
            price_currency: "USD",
            price_freshness: "FRESH",
            native_market_value: "900",
            base_market_value: "900",
            valuation_status: "VALUED",
          },
        ],
        target_weight: "0.4",
        current_market_value: "900",
        current_market_currency: "USD",
        current_weight: "0.9",
        allocation_gap: "-0.5",
        allocation_status: "VALUED",
      },
    ],
    standalone_positions: [],
    valuation_status: "VALUED",
    base_market_value: "1000",
    valuation_currency: "USD",
    cash_valuations: [
      {
        currency: "USD",
        balance: "100",
        base_market_value: "100",
        valuation_status: "VALUED",
      },
    ],
    valuation_gaps: [],
  };
  const emptyRanks = () =>
    companyRankingCurrent.current.map((rank) => ({
      ...rank,
      run: null,
      entry: null,
    }));
  const modelSummary = [portfolioCompany, watchlistCompany].map((issuer) => ({
    company: issuer,
    outputs: {
      company_id: issuer.id,
      status: "NO_MODEL",
      history_count: 0,
      models: [],
    },
  }));
  const scores = [portfolioCompany, watchlistCompany].map((issuer) => ({
    company: issuer,
    scores: scoreSummary(issuer)[0].scores,
  }));

  await page.route("**/api/research/portfolios", (route) =>
    route.fulfill({ json: [overview.portfolio] }),
  );
  await page.route(
    `**/api/research/portfolios/${portfolioId}/overview`,
    (route) => route.fulfill({ json: overview }),
  );
  await page.route("**/api/research/universe/ranking-summary", (route) =>
    route.fulfill({
      json: [portfolioCompany, watchlistCompany].map((issuer) => ({
        company: issuer,
        rankings: emptyRanks(),
      })),
    }),
  );
  await page.route("**/api/research/universe/execution-pace-summary", (route) =>
    route.fulfill({
      json: [portfolioCompany, watchlistCompany].map((issuer) => ({
        company: issuer,
        decision: null,
      })),
    }),
  );
  await page.route("**/api/research/universe/score-summary", (route) =>
    route.fulfill({ json: scores }),
  );
  await page.route(
    "**/api/research/universe/estimate-momentum-summary",
    (route) =>
      route.fulfill({
        json: [portfolioCompany, watchlistCompany].map((issuer) => ({
          company: issuer,
          estimate_momentum: momentumSummary(issuer.id),
        })),
      }),
  );
  await page.route("**/api/research/universe/model-output-summary", (route) =>
    route.fulfill({ json: modelSummary }),
  );
  await page.route("**/api/research/universe", (route) =>
    route.fulfill({ json: [portfolioCompany, watchlistCompany] }),
  );
  await page.route("**/api/research/attention?*", (route) =>
    route.fulfill({
      json: {
        as_of: currentTime,
        lookback_days: 30,
        total: 1,
        events: [
          {
            id: "financial_model_revision:fixture-revision",
            company_id: portfolioCompany.id,
            company_name: portfolioCompany.name,
            lifecycle: "PORTFOLIO",
            event_type: "MODEL_REVISION",
            severity: "MEDIUM",
            status: "INFORMATIONAL",
            title: "Model revision 2",
            explanation: "An accepted native model revision was recorded.",
            effective_at: currentTime,
            time_precision: "TIMESTAMP",
            recorded_at: currentTime,
            source_domain: "financial_model_revision",
            source_id: "fixture-revision",
            source_reference: "web-test",
            href: `/company/${portfolioCompany.id}`,
            prior_value: null,
            current_value: null,
            unit: null,
          },
        ],
      },
    }),
  );

  await page.goto("/portfolio");
  await expect(
    page.getByRole("heading", { name: "Portfolio posture" }),
  ).toBeVisible();
  await expect(page.getByText("$1,000.00", { exact: true })).toBeVisible();
  await expect(page.getByText("Largest strategic gaps")).toBeVisible();
  await expect(page.getByText("Above target", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Portfolio No run", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("NO MAPPING", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("NO MODEL", { exact: false }).first(),
  ).toBeVisible();
  await expect(page.getByText("Needs attention")).toBeVisible();
  await expect(page.getByText("Model revision 2")).toBeVisible();
  await page.getByText("Quality, model and decision evidence").click();
  await expect(page.getByText("Not assessed").first()).toBeVisible();

  await page.getByText("Record a new analytical review").click();
  await expect(
    page.getByRole("button", { name: "Record Portfolio Rank" }),
  ).toBeVisible();
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("Attention Center keeps missing times explicit and filters by company and event type", async ({
  page,
}) => {
  const companyId = "33333333-3333-4333-8333-333333333333";
  await page.route("**/api/research/universe", (route) =>
    route.fulfill({
      json: [{ ...company, id: companyId, lifecycle: "PORTFOLIO" }],
    }),
  );
  const queries: string[] = [];
  await page.route(/\/api\/research\/attention(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.search);
    await route.fulfill({
      json: {
        as_of: "2026-10-05T12:00:00Z",
        lookback_days: 30,
        total: 1,
        events: [
          {
            id: "model_output_coverage:missing-model",
            company_id: companyId,
            company_name: "Example business",
            lifecycle: "PORTFOLIO",
            event_type: "DATA_QUALITY",
            severity: "LOW",
            status: "REVIEW",
            title: "No complete normalized model output",
            explanation:
              "Missing model values remain unavailable; no neutral value was substituted.",
            effective_at: null,
            time_precision: "UNKNOWN",
            recorded_at: null,
            source_domain: "model_output_coverage",
            source_id: "missing-model",
            source_reference: null,
            href: `/company/${companyId}`,
            prior_value: null,
            current_value: null,
            unit: null,
          },
        ],
      },
    });
  });

  await page.goto("/attention");
  await expect(
    page.getByRole("heading", { name: "Attention Center" }),
  ).toBeVisible();
  await expect(
    page.getByText("No complete normalized model output"),
  ).toBeVisible();
  await expect(page.getByText(/Current status · checked/)).toBeVisible();
  await page.getByLabel("Filter by company").selectOption(companyId);
  await page.getByLabel("Filter by event type").selectOption("DATA_QUALITY");
  await expect
    .poll(() => queries.some((query) => query.includes("company_id=")))
    .toBe(true);
  await expect
    .poll(() =>
      queries.some((query) => query.includes("event_type=DATA_QUALITY")),
    )
    .toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("live portfolio, universe filters, company identity and history", async ({
  page,
}, testInfo) => {
  test.skip(
    process.env.E2E_DEMO_SEED !== "1",
    "Requires a disposable API database with the fictional development seed",
  );
  await page.goto("/portfolio");
  await expect(
    page.getByText("Demonstration portfolio", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("40%", { exact: true })).toBeVisible();
  await expect(page.getByText("12.5 shares", { exact: false })).toBeVisible();
  await expect(
    page.getByText("Portfolio weights and allocation gaps", {
      exact: false,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("portfolio.png"),
    fullPage: true,
  });
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Universe" })
    .click();
  await page
    .getByRole("combobox", { name: "Lifecycle", exact: true })
    .selectOption("CANDIDATE");
  await expect(page.getByRole("status")).toHaveText("1 businesses shown");
  await expect(
    page.getByRole("link", { name: "Harbor Robotics (Demo)" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Lifecycle", exact: true })
    .selectOption("");
  await page.getByRole("textbox", { name: "Company name" }).fill("Atlas");
  await expect(page.getByRole("status")).toHaveText("1 businesses shown");
  await expect(page.getByText("Latest ranking snapshots")).toBeVisible();
  await expect(
    page.getByText("NOT_MIGRATED", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "Atlas Software (Demo)" }).click();
  await expect(
    page.getByRole("heading", { name: "Atlas Software (Demo)", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("ATLC · DEMO-EU")).toBeVisible();
  await expect(page.getByText("Unassigned → PORTFOLIO")).toBeVisible();
  await expect(page.getByText("35%", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Ranking snapshots" }),
  ).toBeVisible();
  await page.getByText("Ranking history (1)").first().click();
  await expect(page.getByText("Definition v1").first()).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("company.png"),
    fullPage: true,
  });
});

test("live explicit lifecycle operation preserves company target", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_ALLOW_WRITES !== "1",
    "Creates a test issuer and lifecycle history in the configured API database",
  );
  // Test-owned identity: do not rewrite the demo companies' histories.
  const apiBaseURL = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8000";
  const result = await request.post(`${apiBaseURL}/v1/companies`, {
    data: { name: "Browser verification issuer", reporting_currency: null },
  });
  expect(result.status()).toBe(201);
  const issuer = await result.json();
  await page.goto(`/company/${issuer.id}`);
  await page.getByLabel("New lifecycle").selectOption("WATCHLIST");
  await page
    .getByLabel("Decision reason")
    .fill("Explicit browser verification operation");
  await page.getByRole("button", { name: "Record lifecycle decision" }).click();
  await expect(page.getByText("Unassigned → WATCHLIST")).toBeVisible();
  await expect(page.getByText("No target", { exact: true })).toBeVisible();
});
