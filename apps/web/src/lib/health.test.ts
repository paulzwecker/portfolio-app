import { describe, expect, it, vi } from "vitest";

import { fetchHealth, isHealthResponse } from "@/lib/health";

const healthy = {
  status: "ok",
  database: "connected",
  schema: "current",
  checked_at: "2026-10-04T10:00:00Z",
};

describe("health contract validation", () => {
  it("accepts a timestamped healthy result and explicit database failure", () => {
    expect(isHealthResponse(healthy)).toBe(true);
    expect(
      isHealthResponse({
        ...healthy,
        status: "error",
        database: "unavailable",
        schema: "unavailable",
      }),
    ).toBe(true);
  });

  it.each([
    null,
    {},
    { ...healthy, database: null },
    { ...healthy, schema: "unknown" },
    { ...healthy, status: "error", schema: ["outdated"] },
    { ...healthy, checked_at: "yesterday" },
    { ...healthy, checked_at: "2026-10-04T10:00:00" },
    { ...healthy, database: "unavailable" },
    { ...healthy, schema: "outdated" },
    { ...healthy, status: "error" },
  ])("rejects malformed or inconsistent payload %j", (payload) => {
    expect(isHealthResponse(payload)).toBe(false);
  });
});

describe("health client", () => {
  it("uses a cancellable same-origin request with caching disabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(healthy));
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    expect(await fetchHealth(signal)).toEqual(healthy);
    expect(fetchMock).toHaveBeenCalledWith("/api/health", {
      cache: "no-store",
      signal,
    });
  });

  it("retains an explicit migration failure returned with 503", async () => {
    const outdated = { ...healthy, status: "error", schema: "outdated" };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json(outdated, { status: 503 })),
    );
    expect(await fetchHealth(new AbortController().signal)).toEqual(outdated);
  });

  it.each([
    Response.json({ detail: "API unavailable" }, { status: 503 }),
    Response.json(healthy, { status: 503 }),
    new Response("not json", { status: 502 }),
  ])(
    "does not interpret transport failure as a successful connection",
    async (response) => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
      await expect(fetchHealth(new AbortController().signal)).rejects.toThrow();
    },
  );
});
