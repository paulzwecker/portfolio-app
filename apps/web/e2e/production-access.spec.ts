import { readFileSync } from "node:fs";
import { request as httpsRequest } from "node:https";
import path from "node:path";
import { expect, test } from "@playwright/test";
import {
  modelId,
  malformedModelId,
  revisionId,
} from "./fixtures/dcf-sensitivity.mjs";

test.skip(
  process.env.E2E_MANAGED_PRODUCTION_SERVER !== "1",
  "Use --managed-production with its isolated HTTPS source.",
);

test("production access rejects absent and incorrect credentials on pages and proxy routes", async ({
  baseURL,
}) => {
  for (const pathname of [
    "/",
    "/api/health",
    `/api/research/financial-models/${modelId}/sensitivity?base_revision_id=${revisionId}`,
  ]) {
    const response = await fetch(new URL(pathname, baseURL));
    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toContain("Basic");
    expect(response.headers.get("cache-control")).toBe("no-store");
  }
  expect(
    (
      await fetch(new URL("/", baseURL), {
        headers: { authorization: "Basic aW52YWxpZDppbnZhbGlk" },
      })
    ).status,
  ).toBe(401);
});

test("production access forwards authenticated read-only sensitivity through verified HTTPS", async ({
  request,
}) => {
  expect((await request.get("/")).status()).toBe(200);
  const endpoint = `/api/research/financial-models/${modelId}/sensitivity`;
  const response = await request.get(
    `${endpoint}?base_revision_id=${revisionId}&password=discarded`,
  );
  expect(response.status()).toBe(200);
  const payload = await response.json();
  expect(payload.model_id).toBe(modelId);
  expect(payload.revision_id).toBe(revisionId);
  expect(payload.cells).toHaveLength(9);
  expect(response.headers()["cache-control"]).toBe("no-store");
  expect((await request.get(endpoint)).status()).toBe(400);
  expect(
    (await request.get(`${endpoint}?base_revision_id=${modelId}`)).status(),
  ).toBe(409);
  expect((await request.post(endpoint, { data: {} })).status()).toBe(404);
  expect(
    (
      await request.get(
        `/api/research/financial-models/${malformedModelId}/sensitivity?base_revision_id=${revisionId}`,
      )
    ).status(),
  ).toBe(503);
  const direct = await request.get(
    `${process.env.API_BASE_URL}/v1/financial-models/${modelId}/sensitivity?base_revision_id=${revisionId}`,
  );
  expect(direct.status()).toBe(401);
});

test("production access retains certificate trust and hostname validation", async () => {
  const url = `${process.env.API_BASE_URL}/health/live`;
  const ca = readFileSync(path.join(process.env.E2E_TLS_DIRECTORY!, "ca.pem"));
  const failure = (options: { ca: Buffer | Buffer[]; servername?: string }) =>
    new Promise<string>((resolve) => {
      const request = httpsRequest(url, options, (response) => {
        response.resume();
        resolve("unexpected-success");
      });
      request.on("error", (error: NodeJS.ErrnoException) =>
        resolve(error.code ?? "unknown"),
      );
      request.end();
    });
  expect(await failure({ ca, servername: "wrong-host.invalid" })).toBe(
    "ERR_TLS_CERT_ALTNAME_INVALID",
  );
  expect([
    "UNABLE_TO_VERIFY_LEAF_SIGNATURE",
    "UNABLE_TO_GET_ISSUER_CERT_LOCALLY",
    "SELF_SIGNED_CERT_IN_CHAIN",
  ]).toContain(await failure({ ca: [] }));
});
