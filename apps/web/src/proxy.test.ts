// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { proxy } from "./proxy";

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("WEB_ACCESS_USERNAME", "researcher");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "a-long-preview-password");
});

afterEach(() => vi.unstubAllEnvs());

describe("deployment access boundary", () => {
  it("challenges requests without valid credentials", () => {
    const response = proxy(new NextRequest("https://research.example/"));

    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toContain("Basic");
  });

  it("allows correctly authenticated requests", () => {
    const token = Buffer.from(
      "researcher:a-long-preview-password",
      "utf8",
    ).toString("base64");
    const request = new NextRequest("https://research.example/", {
      headers: { authorization: `Basic ${token}` },
    });
    const response = proxy(request);

    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("fails closed when deployment credentials are missing", () => {
    vi.stubEnv("WEB_ACCESS_PASSWORD", "");
    const response = proxy(new NextRequest("https://research.example/"));

    expect(response.status).toBe(503);
  });

  it("leaves local development unchallenged", () => {
    vi.stubEnv("NODE_ENV", "development");
    const response = proxy(new NextRequest("http://localhost:3000/"));

    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});
