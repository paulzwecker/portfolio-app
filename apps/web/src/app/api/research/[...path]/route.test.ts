import { beforeEach, expect, it, vi } from "vitest";
import { GET, POST } from "@/app/api/research/[...path]/route";

const id = "11111111-1111-4111-8111-111111111111";
const company = {
  id,
  name: "Example",
  reporting_currency: null,
  is_demo: true,
  created_at: "2026-10-04T00:00:00Z",
  lifecycle: null,
  lifecycle_event_id: null,
};
const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
beforeEach(() => {
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_ACCESS_TOKEN", "");
  vi.stubEnv("WEB_ACCESS_USERNAME", "");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "");
});

it("forwards only known read operations and query parameters without caching", async () => {
  const mock = vi.fn().mockResolvedValue(Response.json([company]));
  vi.stubGlobal("fetch", mock);
  const result = await GET(
    new Request(
      "http://localhost/api/research/universe?lifecycle=CANDIDATE&password=hidden",
    ),
    context(["universe"]),
  );
  expect(result.status).toBe(200);
  const endpoint = mock.mock.calls[0][0] as URL;
  expect(endpoint.searchParams.get("lifecycle")).toBe("CANDIDATE");
  expect(endpoint.searchParams.has("password")).toBe(false);
  expect(result.headers.get("cache-control")).toBe("no-store");
});

it("keeps the backend token server-side and requires web access credentials in production", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("API_BASE_URL", "https://api.example");
  vi.stubEnv("WEB_ACCESS_USERNAME", "researcher");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "preview-password-long-enough");
  vi.stubEnv("API_ACCESS_TOKEN", "backend-token-not-for-browser");
  const authorization = Buffer.from(
    "researcher:preview-password-long-enough",
    "utf8",
  ).toString("base64");
  const mock = vi.fn().mockResolvedValue(Response.json([company]));
  vi.stubGlobal("fetch", mock);

  const result = await GET(
    new Request("https://app.example/api/research/universe", {
      headers: { authorization: `Basic ${authorization}` },
    }),
    context(["universe"]),
  );

  expect(result.status).toBe(200);
  expect(await result.text()).not.toContain("backend-token-not-for-browser");
  expect(mock.mock.calls[0]![1]!.headers).toEqual({
    "Content-Type": "application/json",
    "X-API-Access-Token": "backend-token-not-for-browser",
  });

  vi.stubEnv("API_ACCESS_TOKEN", "");
  const denied = await GET(
    new Request("https://app.example/api/research/universe", {
      headers: { authorization: `Basic ${authorization}` },
    }),
    context(["universe"]),
  );
  expect(denied.status).toBe(503);
  expect(mock).toHaveBeenCalledTimes(1);
});

it("rejects production writes without same-origin evidence", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("API_BASE_URL", "https://api.example");
  vi.stubEnv("WEB_ACCESS_USERNAME", "researcher");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "preview-password-long-enough");
  vi.stubEnv("API_ACCESS_TOKEN", "backend-token-not-for-browser");
  const authorization = Buffer.from(
    "researcher:preview-password-long-enough",
    "utf8",
  ).toString("base64");
  const mock = vi.fn();
  vi.stubGlobal("fetch", mock);

  const response = await POST(
    new Request("https://app.example/api/research/ranking-runs", {
      method: "POST",
      headers: { authorization: `Basic ${authorization}` },
      body: "{}",
    }),
    context(["ranking-runs"]),
  );

  expect(response.status).toBe(403);
  expect(mock).not.toHaveBeenCalled();
});

it("refuses to send the backend token to an HTTP origin in production", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("WEB_ACCESS_USERNAME", "researcher");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "preview-password-long-enough");
  vi.stubEnv("API_ACCESS_TOKEN", "backend-token-not-for-browser");
  vi.stubEnv("API_BASE_URL", "http://backend.example");
  const authorization = Buffer.from(
    "researcher:preview-password-long-enough",
    "utf8",
  ).toString("base64");
  const mock = vi.fn();
  vi.stubGlobal("fetch", mock);

  const response = await GET(
    new Request("https://app.example/api/research/universe", {
      headers: { authorization: `Basic ${authorization}` },
    }),
    context(["universe"]),
  );

  expect(response.status).toBe(503);
  expect(mock).not.toHaveBeenCalled();
});
it("validates the market refresh status contract", async () => {
  const response = {
    state: "PARTIAL",
    last_attempt_at: "2026-10-16T01:19:12Z",
    last_successful_update: "2026-10-16T01:19:12Z",
    market_run_id: null,
    fx_run_id: null,
    message: "Ten active companies have no reviewed provider listing.",
  };
  const mock = vi.fn().mockResolvedValue(Response.json(response));
  vi.stubGlobal("fetch", mock);
  const result = await GET(
    new Request("http://localhost/api/research/market-data/status"),
    context(["market-data", "status"]),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(response);
  expect((mock.mock.calls[0][0] as URL).pathname).toBe(
    "/v1/market-data/status",
  );
});
it("validates recurring operations status before forwarding it", async () => {
  const response = {
    enabled: true,
    worker_state: "RUNNING",
    worker_started_at: "2026-10-16T01:00:00Z",
    worker_last_seen_at: "2026-10-16T01:05:00Z",
    sec_user_agent_configured: true,
    google_sheets_configured: true,
    google_sheets_credentials_available: true,
    google_sheets_poll_seconds: 3600,
    fmp_consensus_ingestion_enabled: false,
    jobs: [
      {
        job_name: "SEC_FUNDAMENTALS",
        status: "SUCCEEDED",
        cadence_seconds: 86400,
        last_attempt_at: "2026-10-16T01:00:00Z",
        last_successful_at: "2026-10-16T01:00:04Z",
        next_attempt_at: "2026-10-17T01:00:04Z",
        failure_code: null,
        failure_message: null,
        result: { observations: 12 },
      },
    ],
    market_data: {
      state: "AVAILABLE",
      last_attempt_at: "2026-10-16T01:00:00Z",
      last_successful_update: "2026-10-16T01:00:00Z",
      market_run_id: id,
      fx_run_id: null,
      message: null,
    },
  };
  const mock = vi.fn().mockResolvedValue(Response.json(response));
  vi.stubGlobal("fetch", mock);
  const result = await GET(
    new Request("http://localhost/api/research/recurring-operations/status"),
    context(["recurring-operations", "status"]),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(response);
  expect((mock.mock.calls[0][0] as URL).pathname).toBe(
    "/v1/recurring-operations/status",
  );
});

it("allows a manual job request only through the typed operations endpoint", async () => {
  const response = {
    id,
    job_name: "SEC_FILINGS",
    scope_kind: "ACTIVE_UNIVERSE",
    company_id: null,
    company_name: null,
    lifecycle: null,
    requested_by: "LOCAL_USER",
    status: "QUEUED",
    requested_at: "2026-10-16T01:00:00Z",
    started_at: null,
    finished_at: null,
    next_attempt_at: null,
    attempt_count: 0,
    retry_of_id: null,
    affected_domains: ["SOURCE_DOCUMENTS"],
    scope_detail: { scope_kind: "ACTIVE_UNIVERSE" },
    result: { steps: [] },
    error_code: null,
    error_message: null,
    retry_available: false,
    deduplicated: false,
    cooldown_until: "2026-10-16T01:15:00Z",
    attempts: [],
  };
  const mock = vi
    .fn()
    .mockResolvedValue(Response.json(response, { status: 202 }));
  vi.stubGlobal("fetch", mock);
  const path = ["operations", "job-requests"];
  const result = await POST(
    new Request(`http://localhost/api/research/${path.join("/")}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_name: "SEC_FILINGS",
        scope_kind: "ACTIVE_UNIVERSE",
      }),
    }),
    context(path),
  );
  expect(result.status).toBe(202);
  expect(await result.json()).toEqual(response);
  expect((mock.mock.calls[0]![0] as URL).pathname).toBe(
    "/v1/operations/job-requests",
  );

  const unsupported = await POST(
    new Request("http://localhost/api/research/operations/execute", {
      method: "POST",
      body: "{}",
    }),
    context(["operations", "execute"]),
  );
  expect(unsupported.status).toBe(404);
  expect(mock).toHaveBeenCalledTimes(1);
});

it("allows only validated agent event history and forwards its bounded limit", async () => {
  const event = {
    id,
    delivery_id: id,
    agent_role: "DATA_UNIVERSE_STEWARD",
    work_type: "DATA_DOMAIN",
    work_key: "fundamentals:portfolio",
    work_fingerprint: "a".repeat(64),
    channel: "API",
    event_type: "DELIVERY_SUCCEEDED",
    reason: null,
    blocker_code: null,
    external_update_id: null,
    proposal_domain: null,
    proposal_candidate_id: null,
    recorded_at: "2026-10-16T09:00:00Z",
  };
  const mock = vi.fn().mockResolvedValue(Response.json([event]));
  vi.stubGlobal("fetch", mock);
  const result = await GET(
    new Request(
      "http://localhost/api/research/research-agent-operations/events?limit=12&password=hidden",
    ),
    context(["research-agent-operations", "events"]),
  );
  expect(result.status).toBe(200);
  const endpoint = mock.mock.calls[0]![0] as URL;
  expect(endpoint.pathname).toBe("/v1/research-agent-operations/events");
  expect(endpoint.searchParams.get("limit")).toBe("12");
  expect(endpoint.searchParams.has("password")).toBe(false);

  const invalid = vi
    .fn()
    .mockResolvedValue(
      Response.json([{ ...event, event_type: "AUTO_ACCEPTED" }]),
    );
  vi.stubGlobal("fetch", invalid);
  const rejected = await GET(
    new Request(
      "http://localhost/api/research/research-agent-operations/events",
    ),
    context(["research-agent-operations", "events"]),
  );
  expect(rejected.status).toBe(503);
});

it("does not expose unapproved agent-operation routes through the research proxy", async () => {
  const mock = vi.fn();
  vi.stubGlobal("fetch", mock);
  const result = await GET(
    new Request(
      "http://localhost/api/research/research-agent-operations/proposals/MODEL/id",
    ),
    context(["research-agent-operations", "proposals", "MODEL", id]),
  );
  expect(result.status).toBe(404);
  expect(mock).not.toHaveBeenCalled();
});
it("validates and forwards Candidate pipeline reads and append-only revisions", async () => {
  const queue = [
    {
      company: { ...company, lifecycle: "CANDIDATE", lifecycle_event_id: id },
      status: "NOT_STARTED",
      stage: null,
      disposition: null,
      candidate_tier: "HIGH",
      priority_seed: "20.0000",
      priority_recorded_at: "2026-10-15T08:00:00Z",
      research_rank_position: null,
      research_rank_status: "INPUTS_UNAVAILABLE",
      research_rank_reason: "Current Research Rank entry is unavailable.",
      current_revision: null,
    },
  ];
  const readMock = vi.fn().mockResolvedValue(Response.json(queue));
  vi.stubGlobal("fetch", readMock);
  const read = await GET(
    new Request(
      `http://localhost/api/research/candidate-pipeline?search=Example`,
    ),
    context(["candidate-pipeline"]),
  );
  expect(read.status).toBe(200);
  expect(await read.json()).toEqual(queue);
  const readUrl = readMock.mock.calls[0]![0] as URL;
  expect(readUrl.pathname).toBe("/v1/candidate-pipeline");
  expect(readUrl.searchParams.get("search")).toBe("Example");

  const revision = {
    id: "22222222-2222-4222-8222-222222222222",
    company_id: id,
    revision_number: 1,
    base_revision_id: null,
    submission_id: "33333333-3333-4333-8333-333333333333",
    stage: "DISCOVERY",
    disposition: null,
    next_action: "Complete the initial company screen.",
    unresolved_questions: [],
    actor: "LOCAL_USER",
    author_id: "researcher",
    source: "Candidate Pipeline UI",
    rationale: "Initial review started.",
    effective_at: "2026-10-15T08:00:00Z",
    recorded_at: "2026-10-15T08:01:00Z",
    content_fingerprint: "a".repeat(64),
    gates: [
      "DISCOVERY",
      "INITIAL_SCREEN",
      "QUALITY_DURABILITY",
      "FUNDAMENTAL_COMPOUNDING",
      "DEEP_DIVE",
    ].map((gate, index) => ({
      id: `44444444-4444-4444-8444-44444444444${index}`,
      gate,
      outcome: "NOT_ASSESSED",
      rationale: null,
      normalized_per_share_basis_confirmed: false,
      evidence: [],
    })),
  };
  const publication = { result: "RECORDED", revision };
  const writeMock = vi
    .fn()
    .mockResolvedValue(Response.json(publication, { status: 201 }));
  vi.stubGlobal("fetch", writeMock);
  const writePath = ["companies", id, "candidate-pipeline-revisions"];
  const requestBody = { submission_id: revision.submission_id };
  const write = await POST(
    new Request(`http://localhost/api/research/${writePath.join("/")}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(requestBody),
    }),
    context(writePath),
  );
  expect(write.status).toBe(201);
  expect(await write.json()).toEqual(publication);
  const writeUrl = writeMock.mock.calls[0]![0] as URL;
  expect(writeUrl.pathname).toBe(`/v1/${writePath.join("/")}`);
  expect(JSON.parse(writeMock.mock.calls[0]![1]!.body as string)).toEqual(
    requestBody,
  );
});
it("validates attention events and forwards only documented filters", async () => {
  const response = {
    as_of: "2026-10-05T12:00:00Z",
    lookback_days: 30,
    total: 1,
    events: [
      {
        id: "model_output_coverage:missing",
        company_id: id,
        company_name: "Example",
        lifecycle: "PORTFOLIO",
        event_type: "DATA_QUALITY",
        severity: "LOW",
        status: "REVIEW",
        title: "No complete normalized model output",
        explanation: "Missing model values remain unavailable.",
        effective_at: null,
        time_precision: "UNKNOWN",
        recorded_at: null,
        source_domain: "model_output_coverage",
        source_id: "missing",
        source_reference: null,
        href: `/company/${id}`,
        prior_value: null,
        current_value: null,
        unit: null,
      },
    ],
  };
  const mock = vi.fn().mockResolvedValue(Response.json(response));
  vi.stubGlobal("fetch", mock);
  const result = await GET(
    new Request(
      `http://localhost/api/research/attention?company_id=${id}&event_type=DATA_QUALITY&lifecycle=PORTFOLIO&severity=LOW&status=REVIEW&lookback_days=30&password=hidden`,
    ),
    context(["attention"]),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(response);
  const upstream = mock.mock.calls[0][0] as URL;
  expect(upstream.pathname).toBe("/v1/attention");
  expect(upstream.searchParams.get("company_id")).toBe(id);
  expect(upstream.searchParams.get("event_type")).toBe("DATA_QUALITY");
  expect(upstream.searchParams.get("password")).toBeNull();
});

it("validates historical decision evaluation and preserves its explicit missing states", async () => {
  const evaluation = {
    company_id: id,
    outcome_known_at: "2026-10-15T12:00:00Z",
    horizon_days: [365, 1095],
    minimum_cross_section_sample: 5,
    scenario_evaluations: [],
    valuation_scenarios: [],
    signals: [],
    summaries: [],
    portfolio_implementation_status: "NOT_AVAILABLE_NO_TRANSACTION_LEDGER",
    portfolio_implementation_reason:
      "Position snapshots do not contain transaction cash flows.",
    limitations: ["Returns are listing-currency and method-specific."],
  };
  const mock = vi.fn().mockResolvedValue(Response.json(evaluation));
  vi.stubGlobal("fetch", mock);
  const result = await GET(
    new Request(
      `http://localhost/api/research/companies/${id}/decision-evaluation?outcome_known_at=2026-10-15T12%3A00%3A00Z&horizons_days=365&horizons_days=1095&password=hidden`,
    ),
    context(["companies", id, "decision-evaluation"]),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(evaluation);
  const upstream = mock.mock.calls[0]![0] as URL;
  expect(upstream.pathname).toBe(`/v1/companies/${id}/decision-evaluation`);
  expect(upstream.searchParams.getAll("horizons_days")).toEqual([
    "365",
    "1095",
  ]);
  expect(upstream.searchParams.get("password")).toBeNull();
});

it("forwards trigger queries and manual idempotent refresh", async () => {
  const list = {
    as_of: "2026-10-15T09:00:00Z",
    triggers: [],
  };
  const readMock = vi.fn().mockResolvedValue(Response.json(list));
  vi.stubGlobal("fetch", readMock);
  const read = await GET(
    new Request(
      `http://localhost/api/research/research-triggers?company_id=${id}&processing_state=OPEN&limit=20&password=hidden`,
    ),
    context(["research-triggers"]),
  );
  expect(read.status).toBe(200);
  const readUrl = readMock.mock.calls[0]![0] as URL;
  expect(readUrl.pathname).toBe("/v1/research-triggers");
  expect(readUrl.searchParams.get("company_id")).toBe(id);
  expect(readUrl.searchParams.get("processing_state")).toBe("OPEN");
  expect(readUrl.searchParams.has("password")).toBe(false);

  const refreshResult = {
    as_of: "2026-10-15T09:00:00Z",
    lookback_days: 30,
    examined: 1,
    created: 1,
    replayed: 0,
    triggers: [],
  };
  const writeMock = vi.fn().mockResolvedValue(Response.json(refreshResult));
  vi.stubGlobal("fetch", writeMock);
  const write = await POST(
    new Request(
      "http://localhost/api/research/research-triggers/refresh?lookback_days=30",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "{}",
      },
    ),
    context(["research-triggers", "refresh"]),
  );
  expect(write.status).toBe(200);
  expect(await write.json()).toEqual(refreshResult);
  const writeUrl = writeMock.mock.calls[0]![0] as URL;
  expect(writeUrl.pathname).toBe("/v1/research-triggers/refresh");
  expect(writeUrl.searchParams.get("lookback_days")).toBe("30");
});

it("forwards the bounded Thesis Watch publication to its fixed app-owned tab", async () => {
  const publication = {
    status: "PUBLISHED",
    spreadsheet_id: "configured-sheet-id",
    spreadsheet_title: "Portfolio/Watchlist",
    tab: "Application Thesis Watch Feed",
    contract_version: "1.0.0",
    content_fingerprint: `sha256:${"a".repeat(64)}`,
    published_at: "2026-10-15T09:00:00Z",
    row_count: 1,
    added_count: 1,
    trigger_ids: [id],
    read_back_verified: true,
    message: "Published one trigger context row.",
  };
  const mock = vi.fn().mockResolvedValue(Response.json(publication));
  vi.stubGlobal("fetch", mock);
  const path = ["google-sheets-sync", "thesis-watch", "publish"];
  const requestBody = { limit: 50, offset: 100 };
  const result = await POST(
    new Request(`http://localhost/api/research/${path.join("/")}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(requestBody),
    }),
    context(path),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(publication);
  expect((mock.mock.calls[0]![0] as URL).pathname).toBe(
    "/v1/google-sheets-sync/thesis-watch/publish",
  );
  expect(JSON.parse(mock.mock.calls[0]![1]!.body as string)).toEqual(
    requestBody,
  );
});
it("rejects arbitrary upstream paths", async () => {
  const mock = vi.fn();
  vi.stubGlobal("fetch", mock);
  expect(
    (
      await GET(
        new Request("http://localhost/api/research/secrets"),
        context(["secrets"]),
      )
    ).status,
  ).toBe(404);
  expect(mock).not.toHaveBeenCalled();
});

it("forwards point-in-time research reads and validates the versioned publication result", async () => {
  const researchRead = {
    company_id: id,
    as_of: "2026-10-10",
    known_at: "2026-10-10T23:59:00Z",
    streams: [],
  };
  const readMock = vi.fn().mockResolvedValue(Response.json(researchRead));
  vi.stubGlobal("fetch", readMock);
  const readPath = ["companies", id, "research"];
  const read = await GET(
    new Request(
      `http://localhost/api/research/${readPath.join("/")}?as_of=2026-10-10&known_at=2026-10-10T23%3A59%3A00Z&unlisted=ignore`,
    ),
    context(readPath),
  );
  expect(read.status).toBe(200);
  expect(await read.json()).toEqual(researchRead);
  const readUrl = readMock.mock.calls[0]![0] as URL;
  expect(readUrl.searchParams.get("as_of")).toBe("2026-10-10");
  expect(readUrl.searchParams.get("known_at")).toBe("2026-10-10T23:59:00Z");
  expect(readUrl.searchParams.has("unlisted")).toBe(false);

  const revision = {
    id,
    company_id: id,
    security_id: null,
    stream_key: "agent/company-outlook",
    revision_number: 1,
    contract_version: "1.0.0",
    external_revision_id: "agent-r1",
    supersedes_revision_id: null,
    author_id: "Research agent",
    source_id: "Google Sheets",
    source_reference: "https://docs.google.com/spreadsheets/d/example/edit",
    observed_at: "2026-10-10T12:00:00Z",
    recorded_at: "2026-10-10T12:01:00Z",
    status: "PUBLISHED",
    rationale: "Revenue outlook supported by cited issuer evidence.",
    uncertainty: null,
    content_fingerprint: "a".repeat(64),
    forecasts: [
      {
        id: "22222222-2222-4222-8222-222222222222",
        metric: "REVENUE",
        period_type: "ANNUAL",
        fiscal_year: 2027,
        fiscal_period: "FY",
        period_end: null,
        scenario: "POINT",
        value: "0",
        currency: "USD",
        unit: "currency",
        availability_status: "AVAILABLE",
        availability_reason: null,
        confidence: "MEDIUM",
        rationale: "Explicit zero forecast.",
        uncertainty: null,
      },
    ],
    assessments: [],
    evidence: [],
  };
  const publication = { result: "PUBLISHED", revision };
  const writeMock = vi
    .fn()
    .mockResolvedValue(Response.json(publication, { status: 201 }));
  vi.stubGlobal("fetch", writeMock);
  const writePath = ["research-revisions"];
  const write = await POST(
    new Request("http://localhost/api/research/research-revisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_type: "ResearchRevisionContractV1",
        contract_version: "1.0.0",
        company_id: id,
        external_revision_id: "agent-r1",
      }),
    }),
    context(writePath),
  );
  expect(write.status).toBe(201);
  expect(await write.json()).toEqual(publication);
  expect(writeMock.mock.calls[0]![0].toString()).toBe(
    "http://127.0.0.1:8000/v1/research-revisions",
  );
});

it("forwards financial statement period and knowledge controls", async () => {
  const statementRead = {
    company_id: id,
    period_type: "QUARTERLY",
    as_of: "2026-10-10",
    known_at: "2026-10-10T23:59:00Z",
    periods: [],
    rows: [],
    reported_periods: [],
    consensus: {
      company_id: id,
      continuity_status: "NO_MAPPING",
      selected_provider_id: null,
      as_of: "2026-10-10",
      known_at: "2026-10-10T23:59:00Z",
      providers: [],
    },
    research: {
      company_id: id,
      as_of: "2026-10-10",
      known_at: "2026-10-10T23:59:00Z",
      streams: [],
    },
    limitations: [],
    latest_observed_at: null,
  };
  const mock = vi.fn().mockResolvedValue(Response.json(statementRead));
  vi.stubGlobal("fetch", mock);
  const path = ["companies", id, "financial-statements"];
  const response = await GET(
    new Request(
      `http://localhost/api/research/${path.join("/")}?period_type=QUARTERLY&period_limit=16&as_of=2026-10-10&known_at=2026-10-10T23%3A59%3A00Z`,
    ),
    context(path),
  );
  expect(response.status).toBe(200);
  const url = mock.mock.calls[0]![0] as URL;
  expect(url.searchParams.get("period_type")).toBe("QUARTERLY");
  expect(url.searchParams.get("period_limit")).toBe("16");
  expect(url.searchParams.get("as_of")).toBe("2026-10-10");
  expect(url.searchParams.get("known_at")).toBe("2026-10-10T23:59:00Z");
});

it("forwards point-in-time thesis reads and validates the versioned publication result", async () => {
  const revision = {
    id,
    company_id: id,
    security_id: null,
    stream_key: "investment-thesis",
    revision_number: 1,
    contract_version: "1.0.0",
    external_revision_id: "thesis-r1",
    supersedes_revision_id: null,
    author_id: "research-agent",
    source_id: "google-sheets",
    source_reference: "https://docs.google.com/spreadsheets/d/example/edit",
    observed_at: "2026-10-10T12:00:00Z",
    recorded_at: "2026-10-10T12:01:00Z",
    status: "PUBLISHED",
    thesis_statement: "Recurring demand may support durable compounding.",
    confidence: "MEDIUM",
    rationale:
      "Current evidence supports the thesis with material uncertainty.",
    uncertainty: "Customer concentration remains unresolved.",
    content_fingerprint: "a".repeat(64),
    claims: [],
  };
  const thesisRead = {
    company_id: id,
    as_of: "2026-10-10",
    known_at: "2026-10-10T23:59:00Z",
    streams: [
      {
        stream_key: revision.stream_key,
        current_revision: revision,
        history: [revision],
      },
    ],
  };
  const readMock = vi.fn().mockResolvedValue(Response.json(thesisRead));
  vi.stubGlobal("fetch", readMock);
  const readPath = ["companies", id, "thesis"];
  const read = await GET(
    new Request(
      `http://localhost/api/research/${readPath.join("/")}?as_of=2026-10-10&known_at=2026-10-10T23%3A59%3A00Z&unlisted=ignore`,
    ),
    context(readPath),
  );
  expect(read.status).toBe(200);
  expect(await read.json()).toEqual(thesisRead);
  const readUrl = readMock.mock.calls[0]![0] as URL;
  expect(readUrl.searchParams.get("as_of")).toBe("2026-10-10");
  expect(readUrl.searchParams.get("known_at")).toBe("2026-10-10T23:59:00Z");
  expect(readUrl.searchParams.has("unlisted")).toBe(false);

  const publication = { result: "PUBLISHED", revision };
  const writeMock = vi
    .fn()
    .mockResolvedValue(Response.json(publication, { status: 201 }));
  vi.stubGlobal("fetch", writeMock);
  const write = await POST(
    new Request("http://localhost/api/research/investment-thesis-revisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contract_type: "InvestmentThesisContractV1",
        contract_version: "1.0.0",
        company_id: id,
        stream_key: "investment-thesis",
      }),
    }),
    context(["investment-thesis-revisions"]),
  );
  expect(write.status).toBe(201);
  expect(await write.json()).toEqual(publication);
  expect(writeMock.mock.calls[0]![0].toString()).toBe(
    "http://127.0.0.1:8000/v1/investment-thesis-revisions",
  );
});

it("validates Execution Pace reads and forwards a documented append-only run", async () => {
  const run = {
    id,
    portfolio_id: id,
    as_of: "2026-10-05T00:00:00Z",
    recorded_at: "2026-10-05T00:00:00Z",
    methodology_version: "legacy-execution-pace-v1",
    status: "UNAVAILABLE",
    actor: "LOCAL_USER",
    reason: "Review current portfolio pace.",
    source: "web",
    company_count: 1,
    available_count: 0,
    review_count: 1,
    unavailable_count: 0,
    not_applicable_count: 0,
  };
  const paceRead = { company_id: id, current: null, history: [] };
  const mock = vi
    .fn()
    .mockResolvedValueOnce(Response.json(paceRead))
    .mockResolvedValueOnce(Response.json(run, { status: 201 }));
  vi.stubGlobal("fetch", mock);

  const getPath = ["companies", id, "execution-pace"];
  const read = await GET(
    new Request(`http://localhost/api/research/${getPath.join("/")}`),
    context(getPath),
  );
  expect(read.status).toBe(200);
  expect(await read.json()).toEqual(paceRead);

  const runPath = ["execution-pace-runs"];
  const write = await POST(
    new Request(`http://localhost/api/research/${runPath.join("/")}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor: "LOCAL_USER", reason: run.reason }),
    }),
    context(runPath),
  );
  expect(write.status).toBe(201);
  expect(await write.json()).toEqual(run);
  expect(mock.mock.calls[1]![0].toString()).toBe(
    "http://127.0.0.1:8000/v1/execution-pace-runs",
  );
  expect(mock.mock.calls[1]![1]).toMatchObject({ method: "POST" });
});

it("forwards only a validated holdings confirmation to the portfolio snapshot endpoint", async () => {
  const snapshot = {
    id,
    portfolio_id: id,
    completeness: "COMPLETE",
    actor: "LOCAL_USER",
    reason: "Investor confirmed positions and cash.",
    source: "web-holdings-confirmation",
    effective_at: "2026-10-16T10:00:00Z",
    recorded_at: "2026-10-16T10:00:01Z",
    positions: [{ listing_id: id, quantity: "12.5" }],
    cash_positions: [{ currency: "USD", balance: "100.25" }],
  };
  const mock = vi
    .fn()
    .mockResolvedValue(Response.json(snapshot, { status: 201 }));
  vi.stubGlobal("fetch", mock);
  const path = ["portfolios", id, "holding-snapshots"];
  const result = await POST(
    new Request(`http://localhost/api/research/${path.join("/")}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        actor: "LOCAL_USER",
        reason: snapshot.reason,
        source: snapshot.source,
        effective_at: snapshot.effective_at,
        completeness: "COMPLETE",
        positions: snapshot.positions,
        cash_positions: snapshot.cash_positions,
      }),
    }),
    context(path),
  );

  expect(result.status).toBe(201);
  expect(await result.json()).toEqual(snapshot);
  expect(mock.mock.calls[0]![0].toString()).toBe(
    `http://127.0.0.1:8000/v1/portfolios/${id}/holding-snapshots`,
  );
});

it.each([
  {
    endpoint: "current",
    response: {
      company_id: id,
      status: "NO_MODEL",
      history_count: 0,
      models: [],
    },
  },
  { endpoint: "history", response: [] },
])(
  "forwards model-output $endpoint reads through the checked proxy",
  async ({ endpoint, response }) => {
    const mock = vi.fn().mockResolvedValue(Response.json(response));
    vi.stubGlobal("fetch", mock);
    const path = ["companies", id, "model-outputs", endpoint];
    const result = await GET(
      new Request(`http://localhost/api/research/${path.join("/")}`),
      context(path),
    );
    expect(result.status).toBe(200);
    expect(await result.json()).toEqual(response);
    expect(mock.mock.calls[0][0].toString()).toBe(
      `http://127.0.0.1:8000/v1/${path.join("/")}`,
    );
  },
);

it("allows only the research and thesis Sheets queue routes and validates responses", async () => {
  const run = {
    id,
    spreadsheet_id: null,
    spreadsheet_title: null,
    status: "SUCCEEDED",
    started_at: "2026-10-15T10:00:00Z",
    completed_at: "2026-10-15T10:00:01Z",
    candidate_count: 0,
    new_count: 0,
    unchanged_count: 0,
    issue_count: 0,
    error_code: null,
    error_message: null,
  };
  const checkPath = ["google-sheets-research-sync", "check"];
  const mock = vi
    .fn()
    .mockResolvedValue(Response.json({ run, new_candidates: [] }));
  vi.stubGlobal("fetch", mock);
  const check = await POST(
    new Request("http://localhost/api/research", {
      method: "POST",
      body: "{}",
    }),
    context(checkPath),
  );
  expect(check.status).toBe(200);
  expect(await check.json()).toEqual({ run, new_candidates: [] });
  expect(mock.mock.calls[0][0].toString()).toBe(
    "http://127.0.0.1:8000/v1/google-sheets-research-sync/check",
  );

  const listPath = ["google-sheets-research-sync", "candidates"];
  const listMock = vi.fn().mockResolvedValue(Response.json([]));
  vi.stubGlobal("fetch", listMock);
  const list = await GET(
    new Request(
      "http://localhost/api/research/google-sheets-research-sync/candidates?status=READY&limit=10",
    ),
    context(listPath),
  );
  expect(list.status).toBe(200);
  const url = listMock.mock.calls[0][0] as URL;
  expect(url.pathname).toBe("/v1/google-sheets-research-sync/candidates");
  expect(url.searchParams.get("status")).toBe("READY");
  expect(url.searchParams.get("limit")).toBe("10");
});

it("forwards the canonical bulk model-output summary through validation", async () => {
  const mock = vi.fn().mockResolvedValue(Response.json([]));
  vi.stubGlobal("fetch", mock);
  const path = ["universe", "model-output-summary"];
  const result = await GET(
    new Request(`http://localhost/api/research/${path.join("/")}`),
    context(path),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual([]);
  expect(mock.mock.calls[0][0].toString()).toBe(
    "http://127.0.0.1:8000/v1/universe/model-output-summary",
  );
});

it("forwards both cutoffs and horizon for the temporal alignment read", async () => {
  const emptyValue = {
    status: "NOT_REPORTED",
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
  const response = {
    company_id: id,
    metric: "REVENUE",
    fiscal_year: 2027,
    as_of: "2026-10-05",
    forecast_known_at: "2026-10-05T12:00:00Z",
    outcome_known_at: "2028-03-15T16:00:00Z",
    horizon_days: 180,
    fiscal_year_mapping_basis: "NO_EXPLICIT_MODEL_FISCAL_YEAR_ANCHOR",
    comparison_status: "NO_MODEL_FORECAST",
    model_forecasts: [],
    consensus: { ...emptyValue, status: "NO_MAPPING" },
    actual: emptyValue,
  };
  const mock = vi.fn().mockResolvedValue(Response.json(response));
  vi.stubGlobal("fetch", mock);
  const path = ["companies", id, "temporal-alignment"];
  const request = new Request(
    `http://localhost/api/research/${path.join("/")}?fiscal_year=2027&as_of=2026-10-05&known_at=2026-10-05T12%3A00%3A00Z&outcome_known_at=2028-03-15T16%3A00%3A00Z&horizon_days=180`,
  );
  const result = await GET(request, context(path));
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(response);
  const endpoint = mock.mock.calls[0][0] as URL;
  expect(endpoint.pathname).toBe(`/v1/${path.join("/")}`);
  expect(endpoint.searchParams.get("known_at")).toBe("2026-10-05T12:00:00Z");
  expect(endpoint.searchParams.get("outcome_known_at")).toBe(
    "2028-03-15T16:00:00Z",
  );
  expect(endpoint.searchParams.get("horizon_days")).toBe("180");
});

it("forwards Estimate Momentum cutoffs and preserves an explicit missing state", async () => {
  const response = {
    company_id: id,
    methodology_version: "legacy-estimate-momentum-v2-partial-1",
    availability: "NO_MAPPING",
    direction: null,
    raw_score: null,
    confidence_adjusted_score: null,
    confidence: "0",
    confidence_band: "NO_DATA",
    coverage_fraction: "0",
    coverage_count: 0,
    coverage_total: 20,
    freshness: "NO_DATA",
    data_quality: "NO_DATA",
    provider_id: null,
    latest_snapshot_date: null,
    as_of: "2026-10-05",
    known_at: "2026-10-05T12:00:00Z",
    reason: "No consensus source is selected for this as-of date.",
    periods: [],
  };
  const mock = vi.fn().mockResolvedValue(Response.json(response));
  vi.stubGlobal("fetch", mock);
  const path = ["companies", id, "estimate-momentum"];
  const result = await GET(
    new Request(
      `http://localhost/api/research/${path.join("/")}?as_of=2026-10-05&known_at=2026-10-05T12%3A00%3A00Z`,
    ),
    context(path),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(response);
  const endpoint = mock.mock.calls[0][0] as URL;
  expect(endpoint.searchParams.get("as_of")).toBe("2026-10-05");
  expect(endpoint.searchParams.get("known_at")).toBe("2026-10-05T12:00:00Z");
});

it("forwards expected-return history cutoffs and accepts an explicit empty history", async () => {
  const response = {
    company_id: id,
    as_of: "2026-10-05",
    known_at: "2026-10-05T12:00:00Z",
    status: "NO_HISTORY",
    history: [],
  };
  const mock = vi.fn().mockResolvedValue(Response.json(response));
  vi.stubGlobal("fetch", mock);
  const path = ["companies", id, "expected-return-history"];
  const result = await GET(
    new Request(
      `http://localhost/api/research/${path.join("/")}?as_of=2026-10-05&known_at=2026-10-05T12%3A00%3A00Z`,
    ),
    context(path),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(response);
  const endpoint = mock.mock.calls[0][0] as URL;
  expect(endpoint.pathname).toBe(`/v1/${path.join("/")}`);
  expect(endpoint.searchParams.get("as_of")).toBe("2026-10-05");
  expect(endpoint.searchParams.get("known_at")).toBe("2026-10-05T12:00:00Z");
});

it("forwards selected Expected IRR points and their point-in-time cutoffs", async () => {
  const mock = vi
    .fn()
    .mockResolvedValue(
      Response.json({ detail: "Attribution point not found" }, { status: 404 }),
    );
  vi.stubGlobal("fetch", mock);
  const path = ["companies", id, "expected-return-attribution"];
  const result = await GET(
    new Request(
      `http://localhost/api/research/${path.join("/")}?prior_point_id=native%3Arevision-a&current_point_id=native%3Arevision-b&as_of=2026-10-05&known_at=2026-10-05T12%3A00%3A00Z`,
    ),
    context(path),
  );
  expect(result.status).toBe(404);
  const endpoint = mock.mock.calls[0][0] as URL;
  expect(endpoint.pathname).toBe(`/v1/${path.join("/")}`);
  expect(endpoint.searchParams.get("prior_point_id")).toBe("native:revision-a");
  expect(endpoint.searchParams.get("current_point_id")).toBe(
    "native:revision-b",
  );
  expect(endpoint.searchParams.get("as_of")).toBe("2026-10-05");
  expect(endpoint.searchParams.get("known_at")).toBe("2026-10-05T12:00:00Z");
});

it("forwards filtered Universe Estimate Momentum summaries through validation", async () => {
  const summary = {
    company_id: id,
    methodology_version: "legacy-estimate-momentum-v2-partial-1",
    availability: "NO_MAPPING",
    direction: null,
    raw_score: null,
    confidence_adjusted_score: null,
    confidence: "0",
    confidence_band: "NO_DATA",
    coverage_fraction: "0",
    coverage_count: 0,
    coverage_total: 20,
    freshness: "NO_DATA",
    data_quality: "NO_DATA",
    provider_id: null,
    latest_snapshot_date: null,
    as_of: "2026-10-05",
    known_at: null,
    reason: "No consensus source is selected for this as-of date.",
  };
  const response = [{ company, estimate_momentum: summary }];
  const mock = vi.fn().mockResolvedValue(Response.json(response));
  vi.stubGlobal("fetch", mock);
  const path = ["universe", "estimate-momentum-summary"];
  const result = await GET(
    new Request(
      `http://localhost/api/research/${path.join("/")}?lifecycle=PORTFOLIO&search=Example&as_of=2026-10-05`,
    ),
    context(path),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(response);
  const endpoint = mock.mock.calls[0][0] as URL;
  expect(endpoint.pathname).toBe(`/v1/${path.join("/")}`);
  expect(endpoint.searchParams.get("lifecycle")).toBe("PORTFOLIO");
  expect(endpoint.searchParams.get("search")).toBe("Example");
  expect(endpoint.searchParams.get("as_of")).toBe("2026-10-05");
});

it.each([
  { method: "GET", path: ["companies", id, "canonical-financial-models"] },
  {
    method: "POST",
    path: [
      "companies",
      id,
      "canonical-financial-models",
      "owner-cash-flow",
      "preview",
    ],
  },
  {
    method: "POST",
    path: ["canonical-financial-models", id, "residual-income", "revisions"],
  },
  { method: "GET", path: ["canonical-financial-models", id, "contract"] },
  {
    method: "POST",
    path: ["canonical-financial-models", id, "contract", "preview"],
  },
])(
  "forwards canonical archetype operation $method $path",
  async ({ method, path }) => {
    const mock = vi
      .fn()
      .mockResolvedValue(
        Response.json({ detail: "Private validation detail" }, { status: 422 }),
      );
    vi.stubGlobal("fetch", mock);
    const result = await (method === "GET" ? GET : POST)(
      new Request("http://localhost/api/research", {
        method,
        ...(method === "POST" ? { body: "{}" } : {}),
      }),
      context(path),
    );
    expect(result.status).toBe(422);
    expect(await result.text()).not.toContain("Private validation detail");
    expect(mock.mock.calls[0][0].toString()).toBe(
      `http://127.0.0.1:8000/v1/${path.join("/")}`,
    );
  },
);
it("forwards canonical financial-model reads through schema validation", async () => {
  const mock = vi.fn().mockResolvedValue(Response.json([]));
  vi.stubGlobal("fetch", mock);
  const path = ["companies", id, "financial-models"];
  const result = await GET(
    new Request(`http://localhost/api/research/${path.join("/")}`),
    context(path),
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual([]);
  expect(mock.mock.calls[0][0].toString()).toBe(
    `http://127.0.0.1:8000/v1/${path.join("/")}`,
  );
});
it.each([
  Response.json({ detail: "postgresql://secret" }, { status: 500 }),
  Response.json([{ ...company, lifecycle: "FAKE" }]),
])("redacts failure or invalid upstream data", async (response) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  const result = await GET(
    new Request("http://localhost/api/research/universe"),
    context(["universe"]),
  );
  expect(result.status).toBe(503);
  expect(await result.text()).not.toContain("secret");
});
it("blocks a foreign-origin lifecycle write", async () => {
  vi.stubGlobal("fetch", vi.fn());
  const result = await POST(
    new Request("http://localhost/api/research", {
      method: "POST",
      headers: { origin: "https://foreign.example" },
      body: "{}",
    }),
    context(["companies", id, "lifecycle-transitions"]),
  );
  expect(result.status).toBe(403);
});
it("accepts the browser host when Next constructs an internal localhost URL", async () => {
  const event = {
    id,
    company_id: id,
    new_state: "WATCHLIST",
    previous_state: null,
    sequence: 1,
    actor: "LOCAL_USER",
    reason: "Explicit decision",
    source: null,
    effective_at: "2026-10-04T00:00:00Z",
    recorded_at: "2026-10-04T00:00:00Z",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json(event, { status: 201 })),
  );
  const result = await POST(
    new Request("http://localhost:3000/api/research", {
      method: "POST",
      headers: { host: "127.0.0.1:3000", origin: "http://127.0.0.1:3000" },
      body: "{}",
    }),
    context(["companies", id, "lifecycle-transitions"]),
  );
  expect(result.status).toBe(201);
});
it("passes lifecycle conflict as a recoverable sanitized conflict", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        Response.json({ detail: "Internal information" }, { status: 409 }),
      ),
  );
  const result = await POST(
    new Request("http://localhost/api/research", {
      method: "POST",
      body: "{}",
    }),
    context(["companies", id, "lifecycle-transitions"]),
  );
  expect(result.status).toBe(409);
  expect(await result.text()).not.toContain("Internal information");
});
it("permits only the canonical model revision write and sanitizes validation detail", async () => {
  const mock = vi
    .fn()
    .mockResolvedValue(
      Response.json({ detail: "Private schema details" }, { status: 422 }),
    );
  vi.stubGlobal("fetch", mock);
  const path = ["financial-models", id, "revisions"];
  const result = await POST(
    new Request("http://localhost/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }),
    context(path),
  );
  expect(result.status).toBe(422);
  expect(await result.text()).not.toContain("Private schema details");
  expect(mock.mock.calls[0][0].toString()).toBe(
    `http://127.0.0.1:8000/v1/${path.join("/")}`,
  );
});

it("publishes bounded Sheets work only for the three configured agent roles", async () => {
  const publication = {
    status: "PUBLISHED",
    agent_role: "DATA_UNIVERSE_STEWARD",
    spreadsheet_id: "sheet-id",
    spreadsheet_title: "Portfolio/Watchlist",
    tab: "Application Agent Work Feed",
    contract_version: "1.0.0",
    content_fingerprint: "sha256:" + "a".repeat(64),
    published_at: "2026-10-16T09:00:00Z",
    row_count: 1,
    added_count: 1,
    work_item_count: 1,
    read_back_verified: true,
    status_reason: null,
    message: "Published and verified.",
  };
  const mock = vi.fn().mockResolvedValue(Response.json(publication));
  vi.stubGlobal("fetch", mock);
  const path = [
    "google-sheets-agent-operations",
    "DATA_UNIVERSE_STEWARD",
    "work",
    "publish",
  ];
  const result = await POST(
    new Request(`http://localhost/api/research/${path.join("/")}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 10, offset: 0 }),
    }),
    context(path),
  );
  expect(result.status).toBe(200);
  expect(mock.mock.calls[0]![0].toString()).toBe(
    `http://127.0.0.1:8000/v1/${path.join("/")}`,
  );

  const rejected = await POST(
    new Request(
      "http://localhost/api/research/google-sheets-agent-operations/UNKNOWN/work/publish",
      { method: "POST", body: "{}" },
    ),
    context(["google-sheets-agent-operations", "UNKNOWN", "work", "publish"]),
  );
  expect(rejected.status).toBe(404);
  expect(mock).toHaveBeenCalledTimes(1);
});

it("forwards validated canonical portfolio-state publication", async () => {
  const publication = {
    status: "PUBLISHED",
    spreadsheet_id: "sheet-id",
    spreadsheet_title: "Portfolio/Watchlist",
    tab: "Application Portfolio State",
    portfolio_id: id,
    contract_version: "1.0.0",
    content_fingerprint: "sha256:" + "b".repeat(64),
    published_at: "2026-10-16T09:00:00Z",
    valuation_as_of: "2026-10-16T08:59:00Z",
    valuation_status: "INCOMPLETE_PRICE_COVERAGE",
    row_count: 46,
    read_back_verified: true,
    message: "Canonical portfolio state published and verified.",
  };
  const mock = vi.fn().mockResolvedValue(Response.json(publication));
  vi.stubGlobal("fetch", mock);
  const path = ["google-sheets-sync", "portfolio-state", "publish"];
  const result = await POST(
    new Request(`http://localhost/api/research/${path.join("/")}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ portfolio_id: id }),
    }),
    context(path),
  );
  expect(result.status).toBe(200);
  expect(mock.mock.calls[0]![0].toString()).toBe(
    `http://127.0.0.1:8000/v1/${path.join("/")}`,
  );
});

it.each([
  { method: "GET", suffix: ["contract"] },
  { method: "POST", suffix: ["contract", "preview"] },
  { method: "POST", suffix: ["contract", "import"] },
])(
  "forwards the portable model contract $method operation",
  async ({ method, suffix }) => {
    const mock = vi
      .fn()
      .mockResolvedValue(
        Response.json({ detail: "Private validation detail" }, { status: 422 }),
      );
    vi.stubGlobal("fetch", mock);
    const path = ["financial-models", id, ...suffix];
    const result = await (method === "GET" ? GET : POST)(
      new Request("http://localhost/api/research", {
        method,
        ...(method === "POST" ? { body: '{"contract_version":"1.0.0"}' } : {}),
      }),
      context(path),
    );
    expect(result.status).toBe(422);
    expect(await result.text()).not.toContain("Private validation detail");
    expect(mock.mock.calls[0][0].toString()).toBe(
      `http://127.0.0.1:8000/v1/${path.join("/")}`,
    );
  },
);
