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
