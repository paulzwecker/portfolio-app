import { expect, test } from "@playwright/test";

const healthy = {
  status: "ok",
  database: "connected",
  schema: "current",
  checked_at: "2026-10-04T10:00:00Z",
};

test("empty workspace is usable without horizontal overflow", async ({
  page,
}, testInfo) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: healthy }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true, level: 1 }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("All services connected");
  await expect(page.getByText("Research foundation")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("workspace.png"),
    fullPage: true,
  });
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
});

test("loading, unavailable and retry states are explicit", async ({ page }) => {
  let release: () => void = () => undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  // Development mode may mount effects twice. All initial requests must keep
  // the same state until the test explicitly starts recovery.
  let recovered = false;
  await page.route("**/api/health", async (route) => {
    await pending;
    if (!recovered) {
      await route.fulfill({ status: 503, json: { detail: "API unavailable" } });
    } else {
      await route.fulfill({ json: healthy });
    }
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Checking connection");
  await expect(page.getByRole("button", { name: "Checking" })).toBeDisabled();
  release();
  await expect(page.getByRole("status")).toHaveText(
    "Connection needs attention",
  );
  recovered = true;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("status")).toHaveText("All services connected");
});

test("Sheets research proposals require preview and explicit review acceptance", async ({
  page,
}) => {
  const companyId = "11111111-1111-4111-8111-111111111111";
  const candidateId = "22222222-2222-4222-8222-222222222222";
  const researchCandidate = {
    id: candidateId,
    domain: "RESEARCH",
    company_id: companyId,
    security_id: null,
    stream_key: "agent/revenue-outlook",
    external_revision_id: "sheets-research-r1",
    base_revision_id: null,
    contract_version: "1.0.0",
    content_fingerprint: "a".repeat(64),
    source_url:
      "https://docs.google.com/spreadsheets/d/example/edit#gid=43&range=A2:E2",
    sheet_title: "Application Research Inbox",
    source_row_number: 2,
    author_id: "research-agent",
    source_id: "google-sheets",
    source_reference:
      "https://docs.google.com/spreadsheets/d/example/edit#gid=43",
    observed_at: "2026-10-15T09:00:00Z",
    rationale:
      "A primary source supports a moderate increase in the revenue outlook.",
    item_count: 1,
    evidence_count: 1,
    status: "PENDING",
    issue: null,
    preview_data: null,
    reviewer: null,
    reviewer_note: null,
    accepted_research_revision_id: null,
    accepted_thesis_revision_id: null,
    first_observed_at: "2026-10-15T09:05:00Z",
    last_observed_at: "2026-10-15T09:05:00Z",
    accepted_at: null,
    rejected_at: null,
  };
  const ready = {
    ...researchCandidate,
    status: "READY",
    preview_data: {
      status: "READY",
      contract_type: "ResearchRevisionContractV1",
      base_revision_id: null,
      current_revision_id: null,
      current_revision_number: null,
      candidate_revision_number: 1,
      observed_at: "2026-10-15T09:00:00+00:00",
      forecast_count: 1,
      assessment_count: 0,
      evidence_count: 1,
      company_id: companyId,
      security_id: null,
      forecasts: [
        {
          metric: "REVENUE",
          fiscal_year: 2027,
          fiscal_period: "FY",
          scenario: "POINT",
          value: "125.0",
          currency: "USD",
          unit: "currency",
          availability_status: "AVAILABLE",
        },
      ],
      assessments: [],
      evidence: [
        {
          source_name: "Issuer earnings release",
          external_identifier: "earnings-release-2026-q3",
          source_url: "https://issuer.example.test/earnings-q3",
          published_at: "2026-10-10",
          excerpt: "Orders improved during the quarter.",
          note: "Primary-source evidence linked to the forecast.",
        },
      ],
    },
  };
  const accepted = {
    ...ready,
    status: "ACCEPTED",
    accepted_research_revision_id: "33333333-3333-4333-8333-333333333333",
    reviewer: "Reviewer One",
    reviewer_note: "Reviewed primary source and period alignment.",
    accepted_at: "2026-10-15T10:00:00Z",
  };
  let publishedCandidate: Record<string, unknown> = researchCandidate;
  let acceptCallCount = 0;
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: healthy }),
  );
  await page.route("**/api/research/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/research/", "");
    if (route.request().method() === "POST") {
      if (path.endsWith("/preview")) {
        publishedCandidate = ready;
        return route.fulfill({ json: ready });
      }
      if (path.endsWith("/accept")) {
        acceptCallCount += 1;
        publishedCandidate = accepted;
        return route.fulfill({ json: accepted });
      }
      if (path.endsWith("/reject"))
        return route.fulfill({
          json: { ...researchCandidate, status: "REJECTED" },
        });
      if (path.endsWith("/connection-test"))
        return route.fulfill({
          json: {
            connected: true,
            spreadsheet_id: "s".repeat(24),
            spreadsheet_title: "Private Research Workbook",
            research_inbox_exists: true,
            thesis_inbox_exists: true,
            checked_at: "2026-10-15T10:00:00Z",
            message: "Workbook access is ready.",
          },
        });
      if (path.endsWith("/check"))
        return route.fulfill({
          json: {
            run: {
              id: candidateId,
              spreadsheet_id: "s".repeat(24),
              spreadsheet_title: "Private Research Workbook",
              status: "SUCCEEDED",
              started_at: "2026-10-15T10:00:00Z",
              completed_at: "2026-10-15T10:00:01Z",
              candidate_count: 1,
              new_count: 1,
              unchanged_count: 0,
              issue_count: 0,
              error_code: null,
              error_message: null,
            },
            new_candidates: [researchCandidate],
          },
        });
    }
    if (path === "candidate-pipeline") return route.fulfill({ json: [] });
    if (path === "research-queue")
      return route.fulfill({
        json: {
          as_of: "2026-10-15T10:00:00Z",
          tasks: [],
          counts: {
            open: 0,
            complete: 0,
            portfolio: 0,
            watchlist: 0,
            candidate: 0,
          },
        },
      });
    if (path === "research-triggers")
      return route.fulfill({
        json: { as_of: "2026-10-15T10:00:00Z", triggers: [] },
      });
    if (path === "universe")
      return route.fulfill({
        json: [
          {
            id: companyId,
            name: "Research Example",
            reporting_currency: "USD",
            created_at: "2026-10-01T10:00:00Z",
            is_demo: false,
            lifecycle: "WATCHLIST",
            lifecycle_event_id: "11111111-1111-4111-8111-111111111112",
          },
        ],
      });
    if (path === "google-sheets-research-sync/status")
      return route.fulfill({
        json: {
          configured: true,
          credentials_available: true,
          spreadsheet_id: "s".repeat(24),
          spreadsheet_url:
            "https://docs.google.com/spreadsheets/d/example/edit",
          research_inbox_tab: "Application Research Inbox",
          thesis_inbox_tab: "Application Thesis Inbox",
          last_run: null,
        },
      });
    if (path === "google-sheets-research-sync/candidates")
      return route.fulfill({ json: [publishedCandidate] });
    if (path === "google-sheets-research-sync/runs")
      return route.fulfill({ json: [] });
    if (path === "google-sheets-sync/status")
      return route.fulfill({
        json: {
          configured: true,
          credentials_available: true,
          spreadsheet_id: "s".repeat(24),
          spreadsheet_url:
            "https://docs.google.com/spreadsheets/d/example/edit",
          sync_tab: "Application Model Sync Inbox",
          polling_interval_seconds: 0,
          last_run: null,
        },
      });
    if (
      path === "google-sheets-sync/candidates" ||
      path === "google-sheets-sync/runs" ||
      path === "portfolios"
    )
      return route.fulfill({ json: [] });
    if (path === "google-sheets-risk-sync/status")
      return route.fulfill({
        json: {
          configured: true,
          credentials_available: true,
          spreadsheet_id: "s".repeat(24),
          spreadsheet_url:
            "https://docs.google.com/spreadsheets/d/example/edit",
          inbox_tab: "Application Risk Assessment Inbox",
          last_run: null,
        },
      });
    if (
      path === "google-sheets-risk-sync/candidates" ||
      path === "google-sheets-risk-sync/runs"
    )
      return route.fulfill({ json: [] });
    return route.fulfill({
      status: 404,
      json: { detail: `Unexpected route ${path}` },
    });
  });

  await page.goto("/research?view=reviews");
  await expect(
    page.getByRole("heading", { name: "Agent proposal review" }),
  ).toBeVisible();
  await expect(
    page.getByText("sheets-research-r1", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Accept proposal" }),
  ).toBeDisabled();
  await page.getByLabel("Reviewer", { exact: true }).fill("Reviewer One");
  await page
    .getByLabel("Review rationale", { exact: true })
    .fill("Reviewed primary source and period alignment.");
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(page.getByText("READY", { exact: true }).last()).toBeVisible();
  await expect(
    page.getByText(/125\.0 USD · currency · AVAILABLE/),
  ).toBeVisible();
  await expect(
    page.getByText("Orders improved during the quarter.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Accept proposal" }).click();
  await expect(
    page.getByRole("button", { name: "Confirm acceptance" }),
  ).toBeVisible();
  expect(acceptCallCount).toBe(0);
  await page.getByRole("button", { name: "Confirm acceptance" }).click();
  await expect(
    page.getByText("Accepted into canonical history."),
  ).toBeVisible();
  expect(acceptCallCount).toBe(1);
  await page.getByRole("button", { name: "Review history" }).click();
  await expect(
    page.getByText("33333333-3333-4333-8333-333333333333"),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("reachable database with outdated schema is not reported ready", async ({
  page,
}) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({
      status: 503,
      json: { ...healthy, status: "error", schema: "outdated" },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText(
    "Connection needs attention",
  );
  await expect(page.getByText("Migration required")).toBeVisible();
});

test("recurring operations status explains partial provider work and fits mobile", async ({
  page,
}, testInfo) => {
  const observedAt = "2026-10-16T08:47:00Z";
  const nonReadOperations: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/research/") && request.method() !== "GET")
      nonReadOperations.push(`${request.method()} ${request.url()}`);
  });
  const jobs = [
    "SEC_FUNDAMENTALS",
    "SEC_FILINGS",
    "FMP_CONSENSUS",
    "SHEETS_DISCOVERY",
    "RESEARCH_TRIGGER_SCAN",
    "AGENT_WORK_FEED",
    "DECISION_RECOMPUTE",
  ].map((job_name) => ({
    job_name,
    status: job_name === "SEC_FUNDAMENTALS" ? "PARTIAL" : "SUCCEEDED",
    cadence_seconds: job_name.startsWith("SEC_") ? 86400 : 3600,
    last_attempt_at: observedAt,
    last_successful_at: observedAt,
    next_attempt_at: null,
    failure_code: null,
    failure_message: null,
    result:
      job_name === "SEC_FUNDAMENTALS"
        ? {
            report: {
              domains: [
                {
                  domain: "REPORTED_FUNDAMENTALS",
                  status: "PARTIAL",
                  failure_code: "PARTIAL_COVERAGE",
                  report: {
                    normalized_source_fact_count: 4200,
                    data_check_fact_count: 2,
                  },
                },
              ],
            },
          }
        : {},
  }));
  await page.route("**/api/research/recurring-operations/status", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        worker_state: "RUNNING",
        worker_started_at: observedAt,
        worker_last_seen_at: observedAt,
        sec_user_agent_configured: true,
        google_sheets_configured: true,
        google_sheets_credentials_available: true,
        google_sheets_poll_seconds: 3600,
        fmp_consensus_ingestion_enabled: false,
        jobs,
        market_data: {
          state: "AVAILABLE",
          last_attempt_at: observedAt,
          last_successful_update: observedAt,
          market_run_id: null,
          fx_run_id: null,
          message: null,
        },
      },
    }),
  );
  const workbookBase = {
    configured: true,
    credentials_available: true,
    spreadsheet_id: "test-workbook",
    spreadsheet_url:
      "https://docs.google.com/spreadsheets/d/test-workbook/edit",
  };
  await page.route("**/api/research/google-sheets-sync/status", (route) =>
    route.fulfill({
      json: {
        ...workbookBase,
        sync_tab: "Application Model Sync Inbox",
        polling_interval_seconds: 3600,
        last_run: null,
      },
    }),
  );
  await page.route(
    "**/api/research/google-sheets-research-sync/status",
    (route) =>
      route.fulfill({
        json: {
          ...workbookBase,
          research_inbox_tab: "Application Research Inbox",
          thesis_inbox_tab: "Application Thesis Inbox",
          last_run: null,
        },
      }),
  );
  await page.route("**/api/research/google-sheets-risk-sync/status", (route) =>
    route.fulfill({
      json: {
        ...workbookBase,
        inbox_tab: "Application Risk Assessment Inbox",
        last_run: null,
      },
    }),
  );
  await page.route("**/api/research/google-sheets-sync/candidates*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(
    "**/api/research/google-sheets-research-sync/candidates*",
    (route) => route.fulfill({ json: [] }),
  );
  await page.route(
    "**/api/research/google-sheets-risk-sync/candidates*",
    (route) => route.fulfill({ json: [] }),
  );
  await page.route(
    "**/api/research/research-agent-operations/events*",
    (route) => route.fulfill({ json: [] }),
  );
  const requestId = "77777777-7777-4777-8777-777777777777";
  let queuedRefresh: Record<string, unknown> | null = null;
  await page.route(
    "**/api/research/operations/job-requests*",
    async (route) => {
      if (route.request().method() === "POST") {
        queuedRefresh = {
          id: requestId,
          job_name: "MARKET_AND_FX",
          scope_kind: "ACTIVE_UNIVERSE",
          company_id: null,
          company_name: null,
          lifecycle: null,
          requested_by: "LOCAL_USER",
          status: "QUEUED",
          requested_at: observedAt,
          started_at: null,
          finished_at: null,
          next_attempt_at: null,
          attempt_count: 0,
          retry_of_id: null,
          affected_domains: ["MARKET_DATA", "CORPORATE_ACTIONS", "FX"],
          scope_detail: { scope_kind: "ACTIVE_UNIVERSE" },
          result: { steps: [] },
          error_code: null,
          error_message: null,
          retry_available: false,
          deduplicated: false,
          cooldown_until: "2026-10-16T08:52:00Z",
          attempts: [],
        };
        return route.fulfill({ status: 202, json: queuedRefresh });
      }
      return route.fulfill({ json: queuedRefresh ? [queuedRefresh] : [] });
    },
  );

  await page.goto("/operations");
  await expect(
    page.getByRole("heading", {
      name: "Data and integration status",
    }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Operational summary" })
      .getByText("RUNNING", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Workbook synchronization and proposal intake",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("No synchronization run has been recorded.").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "No agent receipts recorded" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open research reviews" }).first(),
  ).toHaveAttribute("href", "/research?view=reviews");
  const jobView =
    testInfo.project.name === "mobile"
      ? page.locator(
          '[aria-label="Recurring data and research jobs, mobile view"]',
        )
      : page.locator("table");
  await page.getByRole("button", { name: "Refresh status" }).click();
  await expect(jobView.getByText("SEC reported fundamentals")).toBeVisible();
  await page.getByRole("button", { name: "Market prices and FX" }).click();
  await expect(
    page.getByText(
      "Refresh request queued for the background operations worker.",
    ),
  ).toBeVisible();
  await expect(page.getByText("QUEUED", { exact: true }).first()).toBeVisible();
  expect(nonReadOperations).toHaveLength(1);
  expect(nonReadOperations[0]).toContain("POST ");
  expect(nonReadOperations[0]).toContain(
    "/api/research/operations/job-requests",
  );

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("heading", { name: "Data and integration status" }),
  ).toBeVisible();
});

test("former model-sync URL opens the unified Research review workspace", async ({
  page,
}) => {
  await page.route("**/api/research/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/research/", "");
    if (path === "candidate-pipeline" || path === "universe")
      return route.fulfill({ json: [] });
    if (path === "research-queue")
      return route.fulfill({
        json: {
          as_of: "2026-10-16T09:00:00Z",
          tasks: [],
          counts: {
            open: 0,
            complete: 0,
            portfolio: 0,
            watchlist: 0,
            candidate: 0,
          },
        },
      });
    if (path === "research-triggers")
      return route.fulfill({
        json: { as_of: "2026-10-16T09:00:00Z", triggers: [] },
      });
    return route.fulfill({ json: [] });
  });
  await page.goto("/model-sync");
  await expect(page).toHaveURL(/\/research\?view=reviews$/);
  await expect(
    page.getByRole("heading", { name: "Research & Review" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Agent proposal review" }),
  ).toBeVisible();
});

test("real frontend to API to PostgreSQL connectivity", async ({ page }) => {
  test.skip(
    process.env.E2E_LIVE_API !== "1",
    "Requires the explicitly enabled running API and migrated PostgreSQL database.",
  );
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("All services connected");
  await expect(page.getByText("Current", { exact: true })).toBeVisible();
});

test("imported workbook data appears in the live portfolio and universe flows", async ({
  page,
}) => {
  test.skip(
    process.env.E2E_LIVE_API !== "1",
    "Requires the explicitly enabled running API and imported local PostgreSQL data.",
  );
  await page.goto("/portfolio");
  await expect(page.getByText("Imported Legacy Portfolio")).toBeVisible();
  await expect(page.getByText("Current portfolio value")).toBeVisible();
  await expect(page.getByText("Published Expected IRR").first()).toBeVisible();
  await expect(page.getByText("VALUED", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText(/Holdings confirmation is 6 days old/),
  ).toBeVisible();
  await expect(page.getByText(/FX 0\.8924 as of/)).toBeVisible();
  await expect(page.getByText("Needs attention")).toBeVisible();
  await expect(page.getByText(/items in the current view/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Standalone securities" }),
  ).toBeVisible();
  await expect(page.getByText(/SPYY · ETR · EUR/)).toBeVisible();
  await page.goto("/universe");
  await expect(page.getByRole("status")).toContainText("219 businesses shown");
  await expect(
    page.getByText("Published valuation and return outputs").first(),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "AAON, Inc." })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("listing-specific market facts keep ordinary shares and ADR quotes distinct responsively", async ({
  page,
}) => {
  test.skip(
    process.env.E2E_LIVE_API !== "1",
    "Requires the read-only imported market-data snapshot in local PostgreSQL.",
  );
  const response = await page.request.get(
    "/api/research/universe/market-summary",
  );
  expect(response.ok()).toBe(true);
  const rows: unknown = await response.json();
  expect(Array.isArray(rows)).toBe(true);
  const tsm = (
    rows as Array<{
      company: { id: string; name: string };
      market_data: Array<{
        listing: { ticker: string; venue: string; currency?: string | null };
        latest: { split_adjusted_close: string | null } | null;
        freshness: string;
      }>;
    }>
  ).find((row) => row.company.name.includes("Taiwan Semiconductor"));
  expect(tsm).toBeDefined();
  const ordinary = tsm!.market_data.find(
    (item) => item.listing.venue === "TPE" && item.listing.ticker === "2330",
  );
  const adr = tsm!.market_data.find(
    (item) => item.listing.venue === "NYSE" && item.listing.ticker === "TSM",
  );
  expect(ordinary?.latest?.split_adjusted_close).not.toBeNull();
  expect(["FRESH", "STALE"]).toContain(ordinary?.freshness);
  expect(adr?.latest?.split_adjusted_close).not.toBeNull();
  expect(["FRESH", "STALE"]).toContain(adr?.freshness);

  await page.goto(`/company/${tsm!.company.id}`);
  await expect(
    page.getByRole("heading", { name: "Market facts" }),
  ).toBeVisible();
  const marketFacts = page.locator("#market-facts");
  await expect(marketFacts.getByText(/2330.*TPE.*TWD/)).toBeVisible();
  await expect(marketFacts.getByText(/TSM.*NYSE.*USD/)).toBeVisible();
  await expect(marketFacts.getByText("Market refresh")).toBeVisible();
  await expect(marketFacts).toContainText("PARTIAL");
  await marketFacts
    .getByText("Price history and regime measures (90 sessions)")
    .first()
    .click();
  await expect(marketFacts.getByText("200-day average").first()).toBeVisible();
  await expect(
    marketFacts
      .getByRole("img", {
        name: "Recent split-adjusted daily closing prices",
      })
      .first(),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
