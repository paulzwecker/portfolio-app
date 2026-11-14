import { beforeEach, expect, it, vi } from "vitest";
import { returnHurdleFixture } from "../../../../../e2e/fixtures/return-hurdle";
import { GET, POST } from "./route";

const baseline = returnHurdleFixture();
const path = ["financial-models", baseline.model_id, "return-hurdle"];
const context = { params: Promise.resolve({ path }) };
const url = `http://localhost/api/research/${path.join("/")}`;
const query = `?base_revision_id=${baseline.revision_id}&required_return=0.1200`;

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("API_ACCESS_TOKEN", "");
});

it("forwards only bounded read inputs and matches equivalent decimal echoes", async () => {
  const payload = returnHurdleFixture();
  payload.hypothetical_entry_price = "20.000000000000000000";
  payload.hypothetical_expected_irr = "0.11";
  payload.hypothetical_status = "AVAILABLE";
  const fetch = vi.fn().mockResolvedValue(Response.json(payload));
  vi.stubGlobal("fetch", fetch);
  const response = await GET(
    new Request(`${url}${query}&entry_price=20.00&secret=not-forwarded`),
    context,
  );
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual(payload);
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(fetch.mock.calls[0][0].toString()).toBe(
    `http://127.0.0.1:8000/v1/${path.join("/")}${query}&entry_price=20.00`,
  );
  expect(fetch.mock.calls[0][1].method).toBe("GET");
});

it.each([
  "",
  `?base_revision_id=${baseline.revision_id}`,
  "?base_revision_id=bad&required_return=0.12",
  `${query}&required_return=0.12`,
  `${query}&base_revision_id=${baseline.revision_id}`,
  `${query}&entry_price=0`,
  `${query}&entry_price=-1`,
  `${query}&entry_price=Infinity`,
  `${query}&entry_price=1&entry_price=2`,
  `?base_revision_id=${baseline.revision_id}&required_return=1`,
  `?base_revision_id=${baseline.revision_id}&required_return=-0.1`,
])(
  "rejects invalid or ambiguous inputs before calling the API: %s",
  async (params) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    expect((await GET(new Request(url + params), context)).status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  },
);

it.each(["model", "revision", "return", "entry", "currency", "shape"])(
  "rejects a mismatched %s response",
  async (mode) => {
    const payload = returnHurdleFixture();
    if (mode === "model") payload.model_id = baseline.revision_id;
    if (mode === "revision") payload.revision_id = baseline.model_id;
    if (mode === "return") payload.required_return = "0.13";
    if (mode === "entry") payload.hypothetical_entry_price = "10";
    if (mode === "currency") payload.model_currency = "invalid";
    if (mode === "shape") payload.cash_flows.pop();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(payload)));
    expect((await GET(new Request(url + query), context)).status).toBe(503);
  },
);

it("preserves stale-revision conflicts and rejects writes", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      Response.json({ detail: "Private context" }, { status: 409 }),
    );
  vi.stubGlobal("fetch", fetch);
  const response = await GET(new Request(url + query), context);
  expect(response.status).toBe(409);
  expect(await response.text()).not.toContain("Private context");
  fetch.mockClear();
  expect(
    (await POST(new Request(url, { method: "POST", body: "{}" }), context))
      .status,
  ).toBe(404);
  expect(fetch).not.toHaveBeenCalled();
});

it("keeps production authentication, HTTPS and the server-only token", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("WEB_ACCESS_USERNAME", "synthetic-user");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "synthetic-password");
  vi.stubEnv("API_ACCESS_TOKEN", "synthetic-server-token");
  const fetch = vi.fn().mockResolvedValue(Response.json(returnHurdleFixture()));
  vi.stubGlobal("fetch", fetch);
  expect((await GET(new Request(url + query), context)).status).toBe(401);
  const headers = {
    authorization: `Basic ${Buffer.from("synthetic-user:synthetic-password").toString("base64")}`,
  };
  expect(
    (await GET(new Request(url + query, { headers }), context)).status,
  ).toBe(503);
  expect(fetch).not.toHaveBeenCalled();
  vi.stubEnv("API_BASE_URL", "https://synthetic.example");
  expect(
    (await GET(new Request(url + query, { headers }), context)).status,
  ).toBe(200);
  expect(fetch.mock.calls[0][1].headers["X-API-Access-Token"]).toBe(
    "synthetic-server-token",
  );
});
