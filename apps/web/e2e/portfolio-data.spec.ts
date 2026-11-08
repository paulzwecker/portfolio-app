import { expect, test, type Page } from "@playwright/test";
import type {
  MarketRefreshRun,
  RecurringOperationsStatus,
} from "../src/lib/domain-contracts";
import { portfolioFixture, portfolioId, iso } from "./fixtures/portfolio";

function operationsFixture(): RecurringOperationsStatus {
  const run = (
    domain: MarketRefreshRun["domain"],
    number: number,
  ): MarketRefreshRun => ({
    run_id: `30000000-0000-4000-8000-${String(number).padStart(12, "0")}`,
    domain,
    status: domain === "FX" ? "FAILED" : "COMPLETE",
    last_attempt_at: iso,
    finished_at: iso,
    last_successful_at: domain === "FX" ? null : iso,
    attempt_count: 1,
    max_attempts: 3,
    retry_state: domain === "FX" ? "COOLDOWN" : "NONE",
    retry_eligible_at: domain === "FX" ? "2026-10-16T12:15:00Z" : null,
    failure_code: domain === "FX" ? "NO_FX_RESPONSES" : null,
    failure_message:
      domain === "FX"
        ? "No provider response could be normalized for this domain."
        : null,
    request_scope: {
      scope: "listings",
      crosswalk_sha256: "a".repeat(64),
      required_fx_pairs: [["USD", "EUR"]],
    },
    report: {
      domain_report: {
        required_fx_pairs: ["USD/EUR"],
        provider_fetch_failures: [{ code: "NETWORK_ERROR", retryable: true }],
      },
    },
    attempts: [
      {
        attempt_number: 1,
        status: domain === "FX" ? "FAILED" : "SUCCEEDED",
        started_at: iso,
        finished_at: iso,
        retryable: domain === "FX",
        failure_code: domain === "FX" ? "NETWORK_ERROR" : null,
        failure_message:
          domain === "FX" ? "Provider network request failed." : null,
      },
    ],
  });
  return {
    enabled: false,
    manual_operations_enabled: false,
    workbook_sync_enabled: false,
    portfolio_workbook_source_configured: false,
    portfolio_workbook_credentials_available: false,
    worker_state: "DISABLED",
    worker_started_at: null,
    worker_last_seen_at: null,
    sec_user_agent_configured: false,
    google_sheets_configured: false,
    google_sheets_credentials_available: false,
    google_sheets_poll_seconds: 0,
    fmp_consensus_ingestion_enabled: false,
    jobs: [],
    market_data: {
      state: "PARTIAL",
      last_attempt_at: iso,
      last_successful_update: iso,
      market_run_id: "30000000-0000-4000-8000-000000000001",
      fx_run_id: "30000000-0000-4000-8000-000000000002",
      message: "No provider response could be normalized for this domain.",
      runs: [run("MARKET_DATA", 1), run("FX", 2), run("CORPORATE_ACTIONS", 3)],
    },
  };
}

async function installRoutes(
  page: Page,
  operations: RecurringOperationsStatus,
) {
  const writes: string[] = [];
  const overview = portfolioFixture();
  overview.base_market_value = null;
  overview.valuation_status = "INCOMPLETE_FX_COVERAGE";
  overview.valuation_gaps = [{ identity: "USD/EUR", reason: "FX_MISSING" }];
  overview.fx_data_through = null;
  for (const company of overview.companies) {
    company.current_weight = null;
    company.allocation_gap = null;
    for (const position of company.positions) {
      position.portfolio_weight = null;
      if (position.currency === "USD") {
        position.base_market_value = null;
        position.fx_rate = null;
        position.fx_effective_at = null;
        position.valuation_status = "FX_UNAVAILABLE";
        company.current_market_value = null;
        company.allocation_status = "FX_UNAVAILABLE";
      }
    }
  }
  for (const position of overview.standalone_positions)
    position.portfolio_weight = null;
  for (const cash of overview.cash_valuations) {
    cash.portfolio_weight = null;
    if (cash.currency === "USD") {
      cash.base_market_value = null;
      cash.fx_rate = null;
      cash.fx_effective_at = null;
      cash.valuation_status = "FX_UNAVAILABLE";
    }
  }
  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: {
        status: "ok",
        database: "connected",
        schema: "current",
        checked_at: iso,
      },
    }),
  );
  await page.route("**/api/research/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/research/", "");
    if (request.method() !== "GET") {
      writes.push(`${request.method()} ${path}`);
      return route.fulfill({
        status: 409,
        json: { detail: "Read-only browser fixture" },
      });
    }
    if (path === "portfolios")
      return route.fulfill({ json: [overview.portfolio] });
    if (path === `portfolios/${portfolioId}/overview`)
      return route.fulfill({ json: overview });
    if (path === "recurring-operations/status")
      return route.fulfill({ json: operations });
    if (path.startsWith("google-sheets"))
      return route.fulfill({
        status: 503,
        json: { detail: "Integration unavailable in this fixture" },
      });
    if (path === "attention")
      return route.fulfill({
        json: { as_of: iso, lookback_days: 30, total: 0, events: [] },
      });
    return route.fulfill({ json: [] });
  });
  return { overview, writes };
}

test("Portfolio data investigation reaches Operations without writes", async ({
  page,
}, testInfo) => {
  const operations = operationsFixture();
  const { overview, writes } = await installRoutes(page, operations);
  await page.goto("/portfolio");
  await expect(
    page.getByRole("heading", { name: "Portfolio at a glance" }),
  ).toBeVisible();
  await expect(
    page.getByText("Portfolio total incomplete fx coverage"),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("portfolio-data-after.png"),
    scale: "css",
  });
  await page.getByRole("link", { name: "Review prices and FX" }).click();
  await expect(
    page.getByRole("heading", { name: "Data and integration status" }),
  ).toBeVisible();
  const panel = page.getByRole("region", {
    name: "Market data refresh",
    exact: true,
  });
  await expect(panel).toBeFocused();
  await expect(panel).toBeInViewport({ ratio: 0.25 });
  await expect(
    panel.getByText("Waiting for the retry cooldown.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Market prices and FX", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: testInfo.outputPath("operations-data-after.png"),
    scale: "css",
  });
  const inspect = panel.getByRole("button", { name: "Inspect FX refresh" });
  await inspect.click();
  const drawer = page.getByRole("dialog", { name: "FX refresh details" });
  await expect(drawer).toBeVisible();
  const bounds = (await drawer.boundingBox())!;
  expect(Math.round(bounds.x + bounds.width)).toBe(page.viewportSize()!.width);
  expect(bounds.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  await expect(drawer.getByText("Attempt 1", { exact: true })).toBeVisible();
  await expect(
    drawer.getByText("Frozen request scope", { exact: true }),
  ).toBeVisible();
  await expect(drawer.locator("pre").first()).toContainText("a".repeat(64));
  await drawer
    .getByRole("heading", { name: "Recorded diagnostic report" })
    .scrollIntoViewIfNeeded();
  await expect(drawer.locator("pre").last()).toContainText("NETWORK_ERROR");
  await page.screenshot({
    path: testInfo.outputPath("fx-evidence-after.png"),
    scale: "css",
  });
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  await expect(inspect).toBeFocused();
  const fx = operations.market_data.runs![1];
  operations.market_data.state = "AVAILABLE";
  operations.market_data.message = null;
  fx.status = "COMPLETE";
  fx.retry_state = "NONE";
  fx.retry_eligible_at = null;
  fx.attempt_count = 2;
  fx.failure_code = null;
  fx.failure_message = null;
  fx.attempts.push({
    ...fx.attempts[0],
    attempt_number: 2,
    status: "SUCCEEDED",
    retryable: false,
    failure_code: null,
    failure_message: null,
  });
  Object.assign(overview, portfolioFixture());
  await page
    .getByRole("button", { name: "Refresh status", exact: true })
    .click();
  await expect(panel.getByText("AVAILABLE", { exact: true })).toBeVisible();
  await expect(
    panel.getByText("Attempts 2 of 3", { exact: false }),
  ).toBeVisible();
  await inspect.click();
  await expect(drawer.getByText("Attempt 2", { exact: true })).toBeVisible();
  await expect(drawer.getByText("Attempt 1", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.goto("/portfolio");
  await expect(
    page.getByText("€2,262.00", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "Holdings", exact: true }).click();
  await expect(page.getByText("22 listing positions")).toBeVisible();
  await expect(
    page.getByText("SPYY · XETRA · EUR").filter({ visible: true }).first(),
  ).toBeVisible();
  expect(writes).toEqual([]);
});

test("Historical bootstrap schedule evidence is reviewable without writes", async ({
  page,
}) => {
  const { writes } = await installRoutes(page, operationsFixture());
  await page.route(
    "**/api/research/market-data/historical-bootstrap*",
    (route) =>
      route.fulfill({
        json: {
          run_id: "11111111-1111-4111-8111-111111111111",
          run_status: "COMPLETE",
          prepared_at: "2026-11-08T20:00:00Z",
          requested_start: "2025-01-01",
          requested_end: "2026-12-31",
          checked_at: "2026-11-09T00:00:00Z",
          listing_count: 31,
          fx_checkpoint_count: 1,
          offset:
            new URL(route.request().url()).searchParams.get("offset") === "30"
              ? 30
              : 0,
          omitted_listing_count:
            new URL(route.request().url()).searchParams.get("offset") === "30"
              ? 0
              : 1,
          listings:
            new URL(route.request().url()).searchParams.get("offset") === "30"
              ? [
                  {
                    subject_key: "NYSE:LAST",
                    checkpoint_status: "UNAVAILABLE",
                    reason: "CHECKPOINT_UNAVAILABLE",
                    scheduled_session_review: null,
                    checkpoint_diagnostics: {
                      failure_kind: "NO_PROVIDER_DATA",
                      raw_response_count: 1,
                      normalized_daily_rows: 0,
                      provider_failure_count: 0,
                      normalization_rejection_count: 1,
                      normalization_warning_count: null,
                      retryable: false,
                    },
                  },
                ]
              : [
                  {
                    subject_key: "NYSE:SYNTH",
                    checkpoint_status: "COMPLETE",
                    reason: "AVAILABLE",
                    scheduled_session_review: {
                      venue: "NYSE",
                      schedule_id: "synthetic",
                      source_url:
                        "https://www.nyse.com/publicdocs/nyse/ICE_NYSE_2026_Yearly_Trading_Calendar.pdf",
                      source_sha256: "a".repeat(64),
                      schedule_fingerprint: "b".repeat(64),
                      source_as_of: null,
                      source_observed_at: "2026-11-08T18:37:45Z",
                      start_date: "2026-07-02",
                      end_date: "2026-07-07",
                      full_selected_span_covered: true,
                      scheduled_count: 3,
                      absent_scheduled_dates: ["2026-07-06"],
                      selected_unscheduled_dates: [],
                    },
                    requested_window_review: {
                      venue: "NYSE",
                      schedule_id: "synthetic",
                      source_url:
                        "https://www.nyse.com/publicdocs/nyse/ICE_NYSE_2026_Yearly_Trading_Calendar.pdf",
                      source_sha256: "a".repeat(64),
                      schedule_fingerprint: "b".repeat(64),
                      source_as_of: null,
                      source_observed_at: "2026-11-08T18:37:45Z",
                      start_date: "2026-07-01",
                      end_date: "2026-07-10",
                      full_selected_span_covered: true,
                      scheduled_count: 7,
                      absent_scheduled_dates: [
                        "2026-07-01",
                        "2026-07-06",
                        "2026-07-08",
                      ],
                      selected_unscheduled_dates: [],
                    },
                  },
                  ...Array.from({ length: 29 }, (_, i) => ({
                    subject_key: `NYSE:TEST${i}`,
                    checkpoint_status: "PENDING",
                    reason: "CHECKPOINT_NOT_COMPLETE",
                    scheduled_session_review: null,
                  })),
                ],
        },
      }),
  );
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto("/operations");
    const panel = page
      .locator("div")
      .filter({
        has: page.getByText("Historical bootstrap review", { exact: true }),
      })
      .filter({ hasText: "Run:" })
      .last();
    await expect(panel).toContainText("FX sessions remain unassessed");
    await panel.getByText("NYSE:SYNTH", { exact: false }).click();
    await expect(panel).toContainText("not confirmed missing trades");
    await panel.getByText("Requested-window schedule review").click();
    await expect(
      panel.getByText("3 scheduled dates without eligible closes", {
        exact: false,
      }),
    ).toBeVisible();
    await expect(
      panel.getByText("Dates outside this window remain unassessed.", {
        exact: false,
      }),
    ).toBeVisible();
    await expect(panel).toContainText("1 additional listings follow this page");
    await panel.getByRole("button", { name: "Next listings" }).click();
    await expect(panel).toContainText("NYSE:LAST");
    await expect(panel).toContainText("Showing 31–31 of 31");
    await panel.getByText("NYSE:LAST", { exact: false }).click();
    await expect(
      panel.getByText("Provider reported no observations."),
    ).toBeVisible();
    await expect(
      panel.getByText("Normalization warnings: Not recorded", { exact: false }),
    ).toBeVisible();
    await panel.getByRole("button", { name: "Previous listings" }).click();
    await expect(panel).toContainText("NYSE:SYNTH");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  expect(writes).toEqual([]);
});

test("Provider quality warnings are reviewable without writes", async ({
  page,
}) => {
  const operations = operationsFixture();
  const fx = operations.market_data.runs?.find((run) => run.domain === "FX");
  if (!fx) throw new Error("FX fixture missing");
  fx.status = "PARTIAL";
  fx.failure_code = "PARTIAL_COVERAGE";
  fx.failure_message = "1 provider, identity, or quality checks remain for FX.";
  fx.retry_state = "REVIEW_REQUIRED";
  fx.retry_eligible_at = null;
  fx.attempts[0].status = "PARTIAL";
  fx.attempts[0].retryable = false;
  fx.attempts[0].failure_code = "PARTIAL_COVERAGE";
  fx.attempts[0].failure_message = fx.failure_message;
  operations.market_data.message = fx.failure_message;
  fx.report = {
    domain_report: {
      normalization_warnings: [{ code: "FX_ROWS_WITHOUT_CLOSE" }],
    },
  };
  const { writes } = await installRoutes(page, operations);
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto("/operations#market-data-refresh");
    await page.getByRole("button", { name: "Inspect FX refresh" }).click();
    const drawer = page.getByRole("dialog", { name: "FX refresh details" });
    const warning = drawer.getByRole("region", {
      name: "Provider quality warnings",
    });
    await expect(warning).toContainText(
      "Some returned FX rows lacked a usable timestamp or positive close",
    );
    await expect(warning).toContainText(
      "do not establish expected-session coverage",
    );
    await expect(
      drawer.getByText("A fresh scope check or operator review is required."),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.keyboard.press("Escape");
  }
  expect(writes).toEqual([]);
});

test("Preflight blockers expose their scope and preserve last data success", async ({
  page,
}, testInfo) => {
  const operations = operationsFixture();
  const blocked = operations.market_data.runs![0];
  blocked.status = "BLOCKED";
  blocked.retry_state = "REVIEW_REQUIRED";
  blocked.failure_code = "MARKET_SCOPE_BUDGET_EXCEEDED";
  blocked.last_successful_at = null;
  blocked.attempts[0].status = "BLOCKED";
  blocked.attempts[0].failure_code = "MARKET_SCOPE_BUDGET_EXCEEDED";
  blocked.request_scope = { scope: "cloud_market_preflight" };
  blocked.report = {
    phase: "PREFLIGHT",
    subject_count: 31,
    maximum_subjects: 30,
  };
  operations.market_data.runs = [blocked];
  operations.market_data.message =
    "Cloud market preflight blocked (MARKET_SCOPE_BUDGET_EXCEEDED). Inspect the recorded scope diagnostics.";
  const { writes } = await installRoutes(page, operations);
  await page.goto("/operations#market-data-refresh");
  const panel = page.getByRole("region", {
    name: "Market data refresh",
    exact: true,
  });
  await expect(panel).toBeInViewport({ ratio: 0.25 });
  await expect(panel.getByText("Scope check", { exact: false })).toBeVisible();
  await expect(
    panel.getByText("MARKET_SCOPE_BUDGET_EXCEEDED", { exact: true }),
  ).toBeVisible();
  await panel.getByRole("button", { name: "Inspect Prices refresh" }).click();
  const drawer = page.getByRole("dialog", { name: "Prices refresh details" });
  await expect(drawer).toBeVisible();
  await expect(drawer.locator("pre").last()).toContainText(
    '"maximum_subjects": 30',
  );
  await page.screenshot({
    path: testInfo.outputPath("preflight-evidence-after.png"),
    scale: "css",
  });
  await page.keyboard.press("Escape");
  expect(writes).toEqual([]);
});

for (const state of ["STALE", "REFRESHING", "UNAVAILABLE"] as const) {
  test(`Market ${state.toLowerCase()} state stays explicit`, async ({
    page,
  }) => {
    const operations = operationsFixture();
    operations.market_data.state = state;
    operations.market_data.runs = [];
    if (state === "UNAVAILABLE")
      operations.market_data.last_successful_update = null;
    const { writes } = await installRoutes(page, operations);
    await page.goto("/operations#market-data-refresh");
    const panel = page.getByRole("region", {
      name: "Market data refresh",
      exact: true,
    });
    await expect(panel.getByText(state, { exact: true })).toBeVisible();
    await expect(
      panel.getByText("Detailed refresh runs are unavailable."),
    ).toBeVisible();
    if (state === "UNAVAILABLE") {
      await expect(
        panel.getByText("No successful update recorded"),
      ).toBeVisible();
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(writes).toEqual([]);
  });
}

for (const [state, description] of [
  ["EXHAUSTED", "Attempt limit reached. Operator review required."],
  ["ELIGIBLE", "Eligible for the next authorized cloud cycle."],
] as const) {
  test(`Market ${state.toLowerCase()} retries remain read-only`, async ({
    page,
  }) => {
    const operations = operationsFixture();
    const fx = operations.market_data.runs![1];
    fx.retry_state = state;
    if (state === "EXHAUSTED") {
      fx.attempt_count = 3;
      fx.retry_eligible_at = null;
    }
    const { writes } = await installRoutes(page, operations);
    await page.goto("/operations#market-data-refresh");
    const panel = page.getByRole("region", {
      name: "Market data refresh",
      exact: true,
    });
    await expect(panel.getByText(description, { exact: false })).toBeVisible();
    expect(writes).toEqual([]);
  });
}
