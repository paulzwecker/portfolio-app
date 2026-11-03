import { validateHealthResponse } from "./policy.mjs";

function requireValue(name) {
  const value = process.env[name];
  if (!value) throw new Error(`smoke_configuration_missing:${name}`);
  return value;
}

async function get(url, authorization) {
  return fetch(url, {
    headers: { Accept: "application/json", Authorization: authorization },
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(20_000),
  });
}

async function main() {
  const domain = requireValue("VERCEL_PRODUCTION_DOMAIN");
  const username = requireValue("WEB_ACCESS_USERNAME");
  const password = requireValue("WEB_ACCESS_PASSWORD");
  const basic = `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;

  const apiResponse = await fetch(
    "https://portfolio-api-gisk.onrender.com/health/ready",
    {
      headers: { Accept: "application/json" },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(20_000),
    },
  );
  const apiPayload = await apiResponse.json().catch(() => ({}));
  const apiError = validateHealthResponse(apiResponse.status, apiPayload);
  if (apiError) throw new Error(`api_smoke_failed:${apiError}`);

  const base = `https://${domain}`;
  const webHealth = await get(`${base}/api/health`, basic);
  const webPayload = await webHealth.json().catch(() => ({}));
  const webError = validateHealthResponse(webHealth.status, webPayload);
  if (webError) throw new Error(`web_health_smoke_failed:${webError}`);

  const universe = await get(`${base}/api/research/universe`, basic);
  if (universe.status !== 200)
    throw new Error(`authenticated_api_proxy_smoke_failed:${universe.status}`);
  const contentType = universe.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error("authenticated_api_proxy_response_not_json");
  }
  await universe.body?.cancel();

  console.log(
    "Direct API readiness, authenticated web health, and authenticated API proxy smoke checks passed.",
  );
}

main().catch((error) => {
  console.error(
    error instanceof Error ? error.message : "production_smoke_failed:unknown",
  );
  process.exitCode = 1;
});
