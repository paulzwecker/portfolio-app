import { randomBytes } from "node:crypto";
import path from "node:path";

function port(value) {
  if (!/^\d{4,5}$/.test(value) || Number(value) < 1024 || Number(value) > 65535)
    throw new Error(
      "Browser fixture ports must be integers between 1024 and 65535.",
    );
  return String(Number(value));
}

export function managedBrowserEnvironment(inherited, directory) {
  const webPort = port(inherited.E2E_WEB_PORT ?? "3108");
  const apiPort = port(inherited.E2E_FIXTURE_API_PORT ?? "3109");
  if (webPort === apiPort)
    throw new Error("Browser fixture ports must differ.");
  const username = `fixture-${randomBytes(12).toString("hex")}`;
  const password = randomBytes(32).toString("hex");
  return {
    ...inherited,
    E2E_MANAGED_PRODUCTION_SERVER: "1",
    E2E_USE_PRODUCTION_SERVER: "1",
    E2E_WEB_PORT: webPort,
    E2E_FIXTURE_API_PORT: apiPort,
    E2E_WEB_ACCESS_USERNAME: username,
    E2E_WEB_ACCESS_PASSWORD: password,
    WEB_ACCESS_USERNAME: username,
    WEB_ACCESS_PASSWORD: password,
    API_ACCESS_TOKEN: randomBytes(32).toString("hex"),
    API_BASE_URL: `https://127.0.0.1:${apiPort}`,
    E2E_API_BASE_URL: `https://127.0.0.1:${apiPort}`,
    E2E_TLS_DIRECTORY: directory,
    NODE_EXTRA_CA_CERTS: path.join(directory, "ca.pem"),
    NODE_TLS_REJECT_UNAUTHORIZED: "1",
    NEXT_TELEMETRY_DISABLED: "1",
    APP_ENV: "development",
    DATABASE_URL:
      "postgresql+psycopg://fixture:fixture@127.0.0.1:1/fixture_test",
    TEST_DATABASE_URL: "",
    DATABASE_TARGET_ENVIRONMENT: "development",
    DATABASE_TARGET_DATABASE: "fixture_test",
    DATABASE_LOCAL_TEST_WRITES_AUTHORIZED: "false",
    DATABASE_LOCAL_WRITES_AUTHORIZED: "false",
    DATABASE_REHEARSAL_WRITES_AUTHORIZED: "false",
    DATABASE_PRODUCTION_WRITES_AUTHORIZED: "false",
    CLOUD_INGESTION_ENABLED: "false",
    RECURRING_OPERATIONS_ENABLED: "false",
    MANUAL_OPERATIONS_ENABLED: "false",
    WORKBOOK_SYNC_ENABLED: "false",
    FMP_CONSENSUS_INGESTION_ENABLED: "false",
    GOOGLE_SHEETS_POLL_SECONDS: "0",
    MODEL_PROPOSAL_AGENT_TOKEN: "",
    MODEL_PROPOSAL_REVIEWER_TOKEN: "",
    E2E_LIVE_API: "0",
    E2E_ALLOW_WRITES: "0",
    E2E_DEMO_SEED: "0",
    E2E_REAL_API: "0",
    E2E_SEC_API: "0",
    E2E_LEDGER_REVIEW_API: "0",
    E2E_LEDGER_OWNERSHIP_API: "0",
    E2E_LEDGER_PUBLICATION_API: "0",
  };
}

export function browserSettings(environment) {
  const managed = environment.E2E_MANAGED_PRODUCTION_SERVER === "1";
  const production = environment.E2E_USE_PRODUCTION_SERVER === "1";
  const webPort = port(environment.E2E_WEB_PORT ?? "3000");
  const apiPort = port(environment.E2E_FIXTURE_API_PORT ?? "3109");
  const baseURL = `http://127.0.0.1:${webPort}`;
  const username = environment.E2E_WEB_ACCESS_USERNAME;
  const password = environment.E2E_WEB_ACCESS_PASSWORD;
  if (Boolean(username) !== Boolean(password))
    throw new Error("Provide both explicit browser test credentials.");
  if (
    managed &&
    (!production ||
      !username ||
      !password ||
      webPort === apiPort ||
      environment.API_BASE_URL !== `https://127.0.0.1:${apiPort}` ||
      environment.NODE_TLS_REJECT_UNAUTHORIZED !== "1" ||
      !environment.E2E_TLS_DIRECTORY)
  )
    throw new Error(
      "Managed browser isolation is incomplete; use --managed-production.",
    );
  return {
    managed,
    production,
    baseURL,
    apiURL: `https://127.0.0.1:${apiPort}`,
    httpCredentials:
      production && username && password
        ? { username, password, origin: baseURL }
        : undefined,
    reuseExistingServer: production && !managed,
  };
}
