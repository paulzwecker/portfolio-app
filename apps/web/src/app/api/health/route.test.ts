// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/health/route";

const healthy = {
  status: "ok",
  database: "connected",
  schema: "current",
  checked_at: "2026-10-04T10:00:00Z",
};

beforeEach(() => vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000"));

describe("health proxy", () => {
  it("forwards a validated response without caching and bounds the request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(healthy));
    vi.stubGlobal("fetch", fetchMock);
    const response = await GET();
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual(healthy);
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://127.0.0.1:8000/health/ready"),
      expect.objectContaining({
        cache: "no-store",
        signal: expect.any(AbortSignal),
        redirect: "error",
      }),
    );
  });

  it("preserves a failed schema check from a reachable API", async () => {
    const health = { ...healthy, status: "error", schema: "outdated" };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json(health, { status: 503 })),
    );
    const response = await GET();
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual(health);
  });

  it("forwards only the public health contract fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ ...healthy, debug: "private configuration" }),
        ),
    );
    expect(await (await GET()).json()).toEqual(healthy);
  });

  it.each([
    Response.json({ password: "secret-from-upstream" }),
    Response.json(healthy, { status: 500 }),
    Response.json({ ...healthy, schema: "outdated" }),
    new Response("upstream stack trace", { status: 500 }),
  ])("redacts unexpected upstream responses", async (upstream) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(upstream));
    const response = await GET();
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      detail:
        "The API is unavailable. Check the development services and retry.",
    });
  });

  it.each([
    new Error("password=secret"),
    new DOMException("Timed out", "TimeoutError"),
  ])("redacts transport and timeout failures", async (error) => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(error));
    const response = await GET();
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("secret");
  });

  it("returns unavailable when server configuration is absent", async () => {
    vi.stubEnv("API_BASE_URL", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect((await GET()).status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
