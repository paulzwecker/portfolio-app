import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { buildEnvironment } from "./vercel-build-env.mjs";
import {
  assertProductionEnvironmentCacheAbsent,
  productionEnvironmentCachePath,
  scrubProductionEnvironmentCache,
} from "./vercel-env-cache.mjs";

const workflow = readFileSync(
  new URL("../../.github/workflows/production-release.yml", import.meta.url),
  "utf8",
);

function jobSection(name, nextName) {
  const start = workflow.indexOf(`  ${name}:\n`);
  const end = workflow.indexOf(`  ${nextName}:\n`, start + 1);
  assert.notEqual(start, -1, `missing job ${name}`);
  assert.notEqual(end, -1, `missing next job ${nextName}`);
  return workflow.slice(start, end);
}

function jobEnvironment(job) {
  return job.match(/\n    env:\n((?:      [^\n]*\n)+)/)?.[1] ?? "";
}

function stepBlock(job, name) {
  const start = job.indexOf(`      - name: ${name}\n`);
  assert.notEqual(start, -1, `missing workflow step ${name}`);
  const next = job.indexOf("\n      - name:", start + 1);
  return job.slice(start, next === -1 ? undefined : next);
}

const unsafeEnvironmentKeys = [
  "DATABASE_URL",
  "DATABASE_PRODUCTION_WRITES_AUTHORIZED",
  "GITHUB_TOKEN",
  "NEON_API_KEY",
  "RECOVERY_DATABASE_URL",
  "MIGRATION_CONFIRMATION",
  "EMPTY_BASELINE_NO_RECOVERY_CONFIRMATION",
  "RENDER_DEPLOY_TOKEN",
  "RENDER_READ_TOKEN",
  "VERCEL_TOKEN",
  "VERCEL_READ_TOKEN",
  "WEB_ACCESS_USERNAME",
  "WEB_ACCESS_PASSWORD",
];

test("provider credentials and DB authorization are not job-scoped", () => {
  for (const [name, nextName] of [
    ["cloud_preflight", "owner_approval"],
    ["migration", "schema_gate"],
    ["render_deploy", "vercel_deploy"],
    ["vercel_deploy", "smoke"],
    ["smoke", "release_evidence"],
  ]) {
    const job = jobSection(name, nextName);
    const env = jobEnvironment(job);
    for (const key of unsafeEnvironmentKeys) {
      assert.doesNotMatch(
        env,
        new RegExp(`^      ${key}:`, "m"),
        `${name}.${key}`,
      );
    }
    if (name === "smoke") assert.equal(env, "");
    else assert.match(env, /RELEASE_SHA:/);
  }
});

test("read-only Neon credentials are limited to database verification steps", () => {
  const cloud = jobSection("cloud_preflight", "owner_approval");
  const readStep = stepBlock(
    cloud,
    "Verify Neon identity, schema and current recovery point",
  );
  assert.match(
    readStep,
    /DATABASE_URL: \$\{\{ secrets\.PRODUCTION_READONLY_DATABASE_URL \}\}/,
  );
  assert.match(readStep, /NEON_API_KEY: \$\{\{ secrets\.NEON_API_KEY \}\}/);
  assert.match(
    readStep,
    /RECOVERY_DATABASE_URL: \$\{\{ secrets\.RECOVERY_READONLY_DATABASE_URL \}\}/,
  );

  const providerStep = stepBlock(
    cloud,
    "Verify Render and Vercel projects without changing settings",
  );
  assert.doesNotMatch(
    providerStep,
    /DATABASE_URL:|NEON_API_KEY:|RECOVERY_DATABASE_URL:/,
  );
  const cloudSetup = stepBlock(cloud, "Install locked tooling");
  for (const key of unsafeEnvironmentKeys) {
    assert.doesNotMatch(cloudSetup, new RegExp(`^          ${key}:`, "m"));
  }
  assert.match(readStep, /UV_NO_SYNC: "1"/);
  const schemaCheck = stepBlock(
    cloud,
    "Verify current Alembic metadata when migration is not needed",
  );
  assert.match(schemaCheck, /DATABASE_PRODUCTION_WRITES_AUTHORIZED: "false"/);
  assert.match(
    schemaCheck,
    /DATABASE_URL: \$\{\{ secrets\.PRODUCTION_READONLY_DATABASE_URL \}\}/,
  );
  assert.match(schemaCheck, /migration_required == 'false'/);
  assert.match(schemaCheck, /production_release schema-check/);
});

test("production writer credentials are limited to guarded migration steps", () => {
  const migration = jobSection("migration", "schema_gate");
  const preflightStep = stepBlock(
    migration,
    "Reverify read-only target, reviewed base, recovery point and exact migration confirmation",
  );
  assert.match(preflightStep, /DATABASE_PRODUCTION_WRITES_AUTHORIZED: "false"/);
  assert.match(preflightStep, /UV_NO_SYNC: "1"/);
  assert.match(
    preflightStep,
    /DATABASE_URL: \$\{\{ secrets\.PRODUCTION_READONLY_DATABASE_URL \}\}/,
  );
  assert.doesNotMatch(
    preflightStep,
    /NEON_PRODUCTION_MIGRATION_DATABASE_URL|DATABASE_PRODUCTION_WRITES_AUTHORIZED: "true"/,
  );
  assert.match(preflightStep, /MIGRATION_CONFIRMATION:/);
  assert.match(
    preflightStep,
    /EMPTY_BASELINE_NO_RECOVERY_CONFIRMATION: \$\{\{ inputs\.empty_baseline_no_recovery_confirmation \}\}/,
  );

  const migrationStep = stepBlock(
    migration,
    "Apply only the checked-in Alembic migration chain",
  );
  assert.match(migrationStep, /DATABASE_PRODUCTION_WRITES_AUTHORIZED: "true"/);
  assert.match(
    migrationStep,
    /DATABASE_URL: \$\{\{ secrets\.NEON_PRODUCTION_MIGRATION_DATABASE_URL \}\}/,
  );
  assert.match(migrationStep, /npm run db:migrate/);
  assert.doesNotMatch(migrationStep, /db:check/);
  assert.match(migrationStep, /UV_NO_SYNC: "1"/);

  const metadataStep = stepBlock(
    migration,
    "Verify migrated schema metadata with read-only authority",
  );
  assert.match(metadataStep, /DATABASE_PRODUCTION_WRITES_AUTHORIZED: "false"/);
  assert.match(
    metadataStep,
    /DATABASE_URL: \$\{\{ secrets\.PRODUCTION_READONLY_DATABASE_URL \}\}/,
  );
  assert.doesNotMatch(metadataStep, /NEON_PRODUCTION_MIGRATION_DATABASE_URL/);
  assert.match(metadataStep, /production_release schema-check/);
  assert.match(metadataStep, /UV_NO_SYNC: "1"/);

  const setupStep = stepBlock(migration, "Install locked tooling");
  const mainCheckStep = stepBlock(migration, "Confirm main has not advanced");
  for (const key of unsafeEnvironmentKeys) {
    assert.doesNotMatch(setupStep, new RegExp(`^          ${key}:`, "m"));
    if (key !== "GITHUB_TOKEN") {
      assert.doesNotMatch(mainCheckStep, new RegExp(`^          ${key}:`, "m"));
    }
  }
  assert.match(mainCheckStep, /GITHUB_TOKEN: \$\{\{ github\.token \}\}/);

  const finalRead = stepBlock(
    migration,
    "Reverify exact production head in a read-only transaction",
  );
  assert.match(finalRead, /DATABASE_PRODUCTION_WRITES_AUTHORIZED: "false"/);
  assert.match(
    finalRead,
    /DATABASE_URL: \$\{\{ secrets\.PRODUCTION_READONLY_DATABASE_URL \}\}/,
  );
  assert.match(finalRead, /UV_NO_SYNC: "1"/);
});

test("provider deploy and web smoke credentials are step-scoped", () => {
  const render = jobSection("render_deploy", "vercel_deploy");
  const renderStep = stepBlock(
    render,
    "Deploy the exact SHA and require live API readiness",
  );
  assert.match(
    renderStep,
    /RENDER_DEPLOY_TOKEN: \$\{\{ secrets\.RENDER_DEPLOY_TOKEN \}\}/,
  );
  assert.match(renderStep, /GITHUB_TOKEN: \$\{\{ github\.token \}\}/);
  assert.doesNotMatch(
    stepBlock(render, "Set up Node.js"),
    /RENDER_DEPLOY_TOKEN|GITHUB_TOKEN/,
  );

  const vercel = jobSection("vercel_deploy", "smoke");
  const installStep = stepBlock(
    vercel,
    "Install pinned Vercel CLI without credentials",
  );
  assert.doesNotMatch(
    installStep,
    /GITHUB_TOKEN:|VERCEL_TOKEN:|VERCEL_DEPLOY_TOKEN/,
  );
  assert.match(installStep, /vercel@24\.14\.0/);
  const prepareStep = stepBlock(
    vercel,
    "Link the Vercel project and pull production build settings",
  );
  assert.match(
    prepareStep,
    /VERCEL_TOKEN: \$\{\{ secrets\.VERCEL_DEPLOY_TOKEN \}\}/,
  );
  assert.doesNotMatch(prepareStep, /GITHUB_TOKEN:/);
  const buildStep = stepBlock(
    vercel,
    "Build production web artifact without deployment credentials",
  );
  assert.doesNotMatch(
    buildStep,
    /GITHUB_TOKEN:|VERCEL_TOKEN:|VERCEL_DEPLOY_TOKEN/,
  );
  assert.match(buildStep, /scripts\/release\/vercel-build\.mjs/);
  assert.match(buildStep, /VERCEL_CLI_PATH:/);
  const deployStep = stepBlock(
    vercel,
    "Deploy and verify the exact web commit",
  );
  assert.match(
    deployStep,
    /VERCEL_TOKEN: \$\{\{ secrets\.VERCEL_DEPLOY_TOKEN \}\}/,
  );
  assert.match(deployStep, /GITHUB_TOKEN: \$\{\{ github\.token \}\}/);
  assert.doesNotMatch(
    stepBlock(vercel, "Set up Node.js"),
    /VERCEL_TOKEN|GITHUB_TOKEN/,
  );

  const smoke = jobSection("smoke", "release_evidence");
  const smokeStep = stepBlock(
    smoke,
    "Verify API readiness and authenticated web-to-API reads",
  );
  assert.match(
    smokeStep,
    /WEB_ACCESS_USERNAME: \$\{\{ secrets\.WEB_ACCESS_USERNAME \}\}/,
  );
  assert.match(
    smokeStep,
    /WEB_ACCESS_PASSWORD: \$\{\{ secrets\.WEB_ACCESS_PASSWORD \}\}/,
  );
});

test("one credential-free owner approval gates migration and all deployments", () => {
  const validation = jobSection("validate_release", "cloud_preflight");
  assert.match(validation, /GITHUB_ACTOR_ID: \$\{\{ github\.actor_id \}\}/);

  const plan = jobSection("release_plan", "owner_approval");
  assert.match(plan, /needs: \[validate_release, cloud_preflight\]/);
  assert.match(plan, /MIGRATION_REQUIRED:/);
  assert.match(plan, /RECOVERY_REQUIRED:/);
  assert.doesNotMatch(
    plan,
    /secrets\.|NEON_API_KEY|DATABASE_URL|RENDER_READ_TOKEN|VERCEL_READ_TOKEN/,
  );

  const approval = jobSection("owner_approval", "migration");
  assert.match(
    approval,
    /needs: \[validate_release, cloud_preflight, release_plan\]/,
  );
  assert.match(approval, /environment: production-release-approval/);
  assert.match(approval, /permissions: \{\}/);
  assert.doesNotMatch(
    approval,
    /secrets\.|GITHUB_TOKEN|RENDER_|VERCEL_|DATABASE_URL/,
  );
  assert.doesNotMatch(workflow, /RELEASE_REVIEWER_IDS/);

  for (const [name, nextName] of [
    ["migration", "schema_gate"],
    ["schema_gate", "render_deploy"],
    ["render_deploy", "vercel_deploy"],
    ["vercel_deploy", "smoke"],
    ["smoke", "release_evidence"],
  ]) {
    const job = jobSection(name, nextName);
    assert.match(job, /owner_approval/);
  }
});

test("Vercel application build receives only a narrow environment allowlist", () => {
  const environment = buildEnvironment({
    PATH: "runner-path",
    HOME: "runner-home",
    CI: "true",
    GITHUB_TOKEN: "must-not-propagate",
    VERCEL_TOKEN: "must-not-propagate",
    WEB_ACCESS_PASSWORD: "must-not-propagate",
    DATABASE_URL: "must-not-propagate",
    NPM_CONFIG_USERCONFIG: "must-not-propagate",
  });
  assert.deepEqual(Object.keys(environment).sort(), [
    "CI",
    "HOME",
    "NPM_CONFIG_USERCONFIG",
    "PATH",
    "VERCEL_TELEMETRY_DISABLED",
  ]);
  for (const key of [
    "GITHUB_TOKEN",
    "VERCEL_TOKEN",
    "WEB_ACCESS_PASSWORD",
    "DATABASE_URL",
  ]) {
    assert.equal(environment[key], undefined);
  }
});

test("Vercel production environment cache is removed and blocked before build", () => {
  const prepare = readFileSync(
    new URL("./vercel-prepare.mjs", import.meta.url),
    "utf8",
  );
  const build = readFileSync(
    new URL("./vercel-build.mjs", import.meta.url),
    "utf8",
  );
  assert.ok(
    prepare.indexOf('runCli(["pull"') <
      prepare.lastIndexOf("scrubProductionEnvironmentCache"),
  );
  assert.ok(
    build.indexOf("assertProductionEnvironmentCacheAbsent(resolve") <
      build.indexOf("spawnSync("),
  );

  const root = mkdtempSync(path.join(tmpdir(), "vercel-cache-"));
  try {
    const file = productionEnvironmentCachePath(root);
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(
      file,
      "API_ACCESS_TOKEN=private\nWEB_ACCESS_PASSWORD=private\n",
    );
    scrubProductionEnvironmentCache(root);
    assert.equal(existsSync(file), false);
    assert.doesNotThrow(() => assertProductionEnvironmentCacheAbsent(root));

    writeFileSync(file, "API_ACCESS_TOKEN=must-not-reach-build\n");
    assert.throws(
      () => assertProductionEnvironmentCacheAbsent(root),
      /vercel_production_env_cache_present/,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
