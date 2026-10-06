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
beforeEach(() => vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000"));

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
