import assert from "node:assert/strict";
import path from "node:path";
import { mkdtempSync, readdirSync, rmdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import test from "node:test";
import {
  browserSettings,
  managedBrowserEnvironment,
} from "../browser-environment.mjs";

test("managed browser execution replaces inherited targets and credentials without mutating them", () => {
  const original = {
    API_BASE_URL: "https://production.invalid",
    API_ACCESS_TOKEN: "owner-token",
    WEB_ACCESS_USERNAME: "owner",
    WEB_ACCESS_PASSWORD: "owner-password",
    DATABASE_URL: "private-database",
    TEST_DATABASE_URL: "private-test",
    E2E_LIVE_API: "1",
    E2E_ALLOW_WRITES: "1",
    DATABASE_PRODUCTION_WRITES_AUTHORIZED: "true",
    DATABASE_LOCAL_TEST_WRITES_AUTHORIZED: "true",
    DATABASE_LOCAL_WRITES_AUTHORIZED: "true",
    DATABASE_REHEARSAL_WRITES_AUTHORIZED: "true",
    CLOUD_INGESTION_ENABLED: "true",
    RECURRING_OPERATIONS_ENABLED: "true",
    MANUAL_OPERATIONS_ENABLED: "true",
    NODE_TLS_REJECT_UNAUTHORIZED: "0",
  };
  const saved = { ...original };
  const first = managedBrowserEnvironment(original, "fixture-directory");
  const second = managedBrowserEnvironment(original, "fixture-directory");
  assert.deepEqual(original, saved);
  assert.equal(first.API_BASE_URL, "https://127.0.0.1:3109");
  assert.equal(first.E2E_API_BASE_URL, first.API_BASE_URL);
  assert.notEqual(first.API_ACCESS_TOKEN, original.API_ACCESS_TOKEN);
  assert.notEqual(first.API_ACCESS_TOKEN, second.API_ACCESS_TOKEN);
  assert.notEqual(first.WEB_ACCESS_PASSWORD, second.WEB_ACCESS_PASSWORD);
  assert.equal(first.WEB_ACCESS_USERNAME, first.E2E_WEB_ACCESS_USERNAME);
  assert.equal(first.WEB_ACCESS_PASSWORD, first.E2E_WEB_ACCESS_PASSWORD);
  assert.equal(first.TEST_DATABASE_URL, "");
  assert.match(first.DATABASE_URL, /@127\.0\.0\.1:1\/fixture_test$/);
  assert.equal(first.NODE_TLS_REJECT_UNAUTHORIZED, "1");
  assert.equal(
    first.NODE_EXTRA_CA_CERTS,
    path.join("fixture-directory", "ca.pem"),
  );
  for (const name of [
    "DATABASE_PRODUCTION_WRITES_AUTHORIZED",
    "DATABASE_LOCAL_TEST_WRITES_AUTHORIZED",
    "DATABASE_LOCAL_WRITES_AUTHORIZED",
    "DATABASE_REHEARSAL_WRITES_AUTHORIZED",
    "CLOUD_INGESTION_ENABLED",
    "RECURRING_OPERATIONS_ENABLED",
    "MANUAL_OPERATIONS_ENABLED",
    "WORKBOOK_SYNC_ENABLED",
    "FMP_CONSENSUS_INGESTION_ENABLED",
  ])
    assert.equal(first[name], "false");
  for (const name of [
    "E2E_LIVE_API",
    "E2E_ALLOW_WRITES",
    "E2E_DEMO_SEED",
    "GOOGLE_SHEETS_POLL_SECONDS",
  ])
    assert.equal(first[name], "0");
  const settings = browserSettings(first);
  assert.equal(settings.reuseExistingServer, false);
  assert.equal(settings.httpCredentials.origin, "http://127.0.0.1:3108");
  assert.equal(settings.managed, true);
});

test("rejects remote-like, ambiguous, privileged and colliding fixture ports", () => {
  for (const port of [
    "443",
    "65536",
    "3108@remote.invalid",
    "3108/path",
    "1e4",
    "0",
    "",
    "-3000",
  ])
    assert.throws(
      () =>
        managedBrowserEnvironment({ E2E_WEB_PORT: port }, "fixture-directory"),
      /ports must be integers/,
    );
  assert.throws(
    () =>
      managedBrowserEnvironment(
        { E2E_WEB_PORT: "3108", E2E_FIXTURE_API_PORT: "3108" },
        "fixture-directory",
      ),
    /must differ/,
  );
});

test("rejects incomplete managed isolation before starting any server", () => {
  const environment = managedBrowserEnvironment({}, "fixture-directory");
  for (const change of [
    { E2E_USE_PRODUCTION_SERVER: "0" },
    { E2E_WEB_ACCESS_PASSWORD: "" },
    { API_BASE_URL: "https://production.invalid" },
    { NODE_TLS_REJECT_UNAUTHORIZED: "0" },
    { E2E_TLS_DIRECTORY: "" },
  ])
    assert.throws(() => browserSettings({ ...environment, ...change }));
});

test("keeps the documented development and explicit operator-server modes", () => {
  const development = browserSettings({});
  assert.equal(development.production, false);
  assert.equal(development.httpCredentials, undefined);
  assert.equal(development.reuseExistingServer, false);
  const production = browserSettings({
    E2E_USE_PRODUCTION_SERVER: "1",
    E2E_WEB_ACCESS_USERNAME: "synthetic-user",
    E2E_WEB_ACCESS_PASSWORD: "synthetic-password",
  });
  assert.equal(production.reuseExistingServer, true);
  assert.equal(production.httpCredentials.origin, "http://127.0.0.1:3000");
  assert.throws(
    () => browserSettings({ E2E_WEB_ACCESS_USERNAME: "partial" }),
    /both explicit/,
  );
});

test("failed validation cleans its empty private temporary directory", () => {
  const directory = mkdtempSync(
    path.join(tmpdir(), "portfolio-browser-policy-"),
  );
  try {
    const result = spawnSync(
      process.execPath,
      ["scripts/browser.mjs", "test", "--managed-production", "--list"],
      {
        env: {
          ...process.env,
          TEMP: directory,
          TMP: directory,
          TMPDIR: directory,
          E2E_WEB_PORT: "invalid",
        },
        encoding: "utf8",
        windowsHide: true,
      },
    );
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /ports must be integers/);
    assert.deepEqual(readdirSync(directory), []);
  } finally {
    for (const name of readdirSync(directory)) {
      assert.ok(name.startsWith("portfolio-browser-"));
      rmdirSync(path.join(directory, name));
    }
    rmdirSync(directory);
  }
});
