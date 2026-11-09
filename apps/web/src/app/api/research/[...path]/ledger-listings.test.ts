import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  ledgerAnchor,
  ledgerPortfolioId,
} from "../../../../../e2e/fixtures/ledger";
import { GET, POST } from "./route";

const path = ["portfolios", ledgerPortfolioId, "ledger", "listings"];
const context = { params: Promise.resolve({ path }) };
const url = `http://localhost/api/research/${path.join("/")}`;
const response = () => ({
  results: [
    {
      ...ledgerAnchor.listings[0],
      security_name: "Synthetic fund",
      share_class: null,
      company_name: null,
      is_demo: true,
    },
  ],
  truncated: false,
  unsupported_results: false,
});
beforeEach(() => {
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("API_ACCESS_TOKEN", "");
  vi.stubEnv("WEB_ACCESS_USERNAME", "");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
it("forwards only the exact ticker and validates the authenticated read-only result", async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json(response()));
  vi.stubGlobal("fetch", fetch);
  const result = await GET(
    new Request(`${url}?ticker=SYNF&password=ignored`),
    context,
  );
  expect(result.status).toBe(200);
  expect(await result.json()).toEqual(response());
  expect(result.headers.get("cache-control")).toBe("no-store");
  expect(fetch.mock.calls[0][0].toString()).toBe(
    `http://127.0.0.1:8000/v1/${path.join("/")}?ticker=SYNF`,
  );
  expect(fetch.mock.calls[0][1].method).toBe("GET");
});
it.each([
  "",
  "?ticker=",
  "?ticker=%20",
  "?ticker=ONE&ticker=TWO",
  "?ticker=A%00B",
  `?ticker=${"A".repeat(41)}`,
])(
  "rejects ambiguous or invalid tickers before forwarding %s",
  async (query) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    expect((await GET(new Request(url + query), context)).status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  },
);
it.each(["malformed", "wrong-ticker", "missing-demo"])(
  "rejects %s lookup results",
  async (mode) => {
    const value = response();
    if (mode === "malformed") value.results[0].currency = "bad";
    if (mode === "wrong-ticker") value.results[0].ticker = "OTHER";
    if (mode === "missing-demo")
      Object.assign(value.results[0], { is_demo: undefined });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(value)));
    expect((await GET(new Request(`${url}?ticker=SYNF`), context)).status).toBe(
      503,
    );
  },
);
it("forbids writes and preserves production authentication and HTTPS", async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json(response()));
  vi.stubGlobal("fetch", fetch);
  expect(
    (await POST(new Request(url, { method: "POST", body: "{}" }), context))
      .status,
  ).toBe(404);
  expect(fetch).not.toHaveBeenCalled();
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("WEB_ACCESS_USERNAME", "synthetic-user");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "synthetic-password");
  vi.stubEnv("API_ACCESS_TOKEN", "synthetic-server-token");
  expect((await GET(new Request(`${url}?ticker=SYNF`), context)).status).toBe(
    401,
  );
  const headers = {
    authorization: `Basic ${Buffer.from("synthetic-user:synthetic-password").toString("base64")}`,
  };
  expect(
    (await GET(new Request(`${url}?ticker=SYNF`, { headers }), context)).status,
  ).toBe(503);
  expect(fetch).not.toHaveBeenCalled();
  vi.stubEnv("API_BASE_URL", "https://synthetic.example");
  expect(
    (await GET(new Request(`${url}?ticker=SYNF`, { headers }), context)).status,
  ).toBe(200);
  expect(fetch.mock.calls[0][1].headers["X-API-Access-Token"]).toBe(
    "synthetic-server-token",
  );
});
