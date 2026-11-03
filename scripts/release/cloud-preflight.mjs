import { appendFileSync, readFileSync } from "node:fs";

import { validateRenderService, validateVercelProject } from "./policy.mjs";

async function apiGet(url, token, provider) {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok)
    throw new Error(`${provider}_read_failed:${response.status}`);
  return response.json();
}

function requireValue(name) {
  const value = process.env[name];
  if (!value) throw new Error(`release_configuration_missing:${name}`);
  return value;
}

function unwrapService(payload) {
  return payload?.service ?? payload;
}

function unwrapRows(payload, names) {
  if (Array.isArray(payload)) return payload;
  for (const name of names) {
    if (Array.isArray(payload?.[name])) return payload[name];
  }
  throw new Error("provider_response_shape_invalid");
}

function output(name, value) {
  if (process.env.GITHUB_OUTPUT)
    appendFileSync(process.env.GITHUB_OUTPUT, `${name}=${value}\n`);
}

async function main() {
  const renderToken = requireValue("RENDER_READ_TOKEN");
  const vercelToken = requireValue("VERCEL_READ_TOKEN");
  const vercelProjectId = requireValue("VERCEL_PROJECT_ID");
  const vercelOrgId = requireValue("VERCEL_ORG_ID");
  const vercelDomain = requireValue("VERCEL_PRODUCTION_DOMAIN");
  const expectedDatabaseHost = requireValue("NEON_PRIMARY_DATABASE_HOST");
  const renderOrigin = "https://portfolio-api-gisk.onrender.com";

  const serviceId = "srv-dba8q3rncjis73cl7to0";
  const renderRoot = "https://api.render.com/v1";
  const [servicePayload, envPayload] = await Promise.all([
    apiGet(`${renderRoot}/services/${serviceId}`, renderToken, "render"),
    apiGet(
      `${renderRoot}/services/${serviceId}/env-vars`,
      renderToken,
      "render",
    ),
  ]);
  const service = unwrapService(servicePayload);
  const envRows = unwrapRows(envPayload, ["envVars", "env_vars", "items"]);
  const renderErrors = validateRenderService({
    service,
    envRows,
    expectedDatabaseHost,
  });
  if (service?.url !== renderOrigin)
    renderErrors.push("render_service_origin_mismatch");
  if (service?.rootDir !== "apps/api")
    renderErrors.push("render_root_directory_mismatch");
  if (renderErrors.length)
    throw new Error(`render_preflight_failed:${renderErrors.join(",")}`);

  const teamQuery = new URLSearchParams({ teamId: vercelOrgId });
  const vercelRoot = "https://api.vercel.com";
  const [project, domainPayload, envPayloadVercel] = await Promise.all([
    apiGet(
      `${vercelRoot}/v9/projects/${encodeURIComponent(vercelProjectId)}?${teamQuery}`,
      vercelToken,
      "vercel",
    ),
    apiGet(
      `${vercelRoot}/v9/projects/${encodeURIComponent(vercelProjectId)}/domains?${teamQuery}`,
      vercelToken,
      "vercel",
    ),
    apiGet(
      `${vercelRoot}/v10/projects/${encodeURIComponent(vercelProjectId)}/env?${teamQuery}&decrypt=false`,
      vercelToken,
      "vercel",
    ),
  ]);
  const domains = unwrapRows(domainPayload, ["domains", "items"]);
  const vercelEnvRows = unwrapRows(envPayloadVercel, ["envs", "env", "items"]);
  const vercelConfig = JSON.parse(readFileSync("apps/web/vercel.json", "utf8"));
  const vercelErrors = validateVercelProject({
    project,
    domains,
    envRows: vercelEnvRows,
    vercelConfig,
    expectedProjectId: vercelProjectId,
    expectedDomain: vercelDomain,
    expectedRepository: "paulzwecker/portfolio-app",
    productionApiOrigin: renderOrigin,
  });
  if (vercelErrors.length)
    throw new Error(`vercel_preflight_failed:${vercelErrors.join(",")}`);

  output("render_origin", renderOrigin);
  output("vercel_domain", vercelDomain);
  console.log(
    "Read-only Render and Vercel project checks passed; no provider settings were changed.",
  );
}

main().catch((error) => {
  console.error(
    error instanceof Error ? error.message : "cloud_preflight_failed:unknown",
  );
  process.exitCode = 1;
});
