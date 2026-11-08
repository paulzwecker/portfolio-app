import { beforeEach, expect, it, vi } from "vitest";
import { GET, POST } from "./route";
import {
  modelId,
  revisionId,
  sensitivityFixture,
} from "../../../../../e2e/fixtures/dcf-sensitivity.mjs";

const path = ["financial-models", modelId, "sensitivity"];
const context = { params: Promise.resolve({ path }) };
const url = `http://localhost/api/research/${path.join("/")}`;

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("API_ACCESS_TOKEN", "");
});

it("forwards the pinned read-only sensitivity query and verifies its payload", async () => {
  const payload = sensitivityFixture();
  const fetch = vi.fn().mockResolvedValue(Response.json(payload));
  vi.stubGlobal("fetch", fetch);
  const response = await GET(
    new Request(
      `${url}?base_revision_id=${revisionId}&password=hidden&company_id=${modelId}`,
    ),
    context,
  );
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual(payload);
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(fetch.mock.calls[0][0].toString()).toBe(
    `http://127.0.0.1:8000/v1/${path.join("/")}?base_revision_id=${revisionId}`,
  );
  expect(fetch.mock.calls[0][1].method).toBe("GET");
});

it.each([
  "",
  "?base_revision_id=bad",
  `?base_revision_id=${revisionId}&base_revision_id=${revisionId}`,
])(
  "rejects an ambiguous or absent revision before the upstream request %s",
  async (query) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    expect((await GET(new Request(url + query), context)).status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  },
);

it.each(["malformed", "wrong-model", "wrong-revision"])(
  "rejects %s upstream sensitivity",
  async (mode) => {
    const payload = sensitivityFixture();
    if (mode === "malformed") payload.cells.pop();
    if (mode === "wrong-model") payload.model_id = revisionId;
    if (mode === "wrong-revision") payload.revision_id = modelId;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(payload)));
    expect(
      (await GET(new Request(`${url}?base_revision_id=${revisionId}`), context))
        .status,
    ).toBe(503);
  },
);

it("preserves conflicts and forbids sensitivity writes", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      Response.json({ detail: "Private reason" }, { status: 409 }),
    );
  vi.stubGlobal("fetch", fetch);
  const response = await GET(
    new Request(`${url}?base_revision_id=${revisionId}`),
    context,
  );
  expect(response.status).toBe(409);
  expect(await response.text()).not.toContain("Private reason");
  fetch.mockClear();
  expect(
    (await POST(new Request(url, { method: "POST", body: "{}" }), context))
      .status,
  ).toBe(404);
  expect(fetch).not.toHaveBeenCalled();
});

it("retains production authentication, HTTPS and a separate server token", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("WEB_ACCESS_USERNAME", "synthetic-user");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "synthetic-password");
  vi.stubEnv("API_ACCESS_TOKEN", "synthetic-server-token");
  const fetch = vi.fn().mockResolvedValue(Response.json(sensitivityFixture()));
  vi.stubGlobal("fetch", fetch);
  const target = `${url}?base_revision_id=${revisionId}`;
  expect((await GET(new Request(target), context)).status).toBe(401);
  const headers = {
    authorization: `Basic ${Buffer.from("synthetic-user:synthetic-password").toString("base64")}`,
  };
  expect((await GET(new Request(target, { headers }), context)).status).toBe(
    503,
  );
  expect(fetch).not.toHaveBeenCalled();
  vi.stubEnv("API_BASE_URL", "https://synthetic.example");
  expect((await GET(new Request(target, { headers }), context)).status).toBe(
    200,
  );
  expect(fetch.mock.calls[0][1].headers["X-API-Access-Token"]).toBe(
    "synthetic-server-token",
  );
});
