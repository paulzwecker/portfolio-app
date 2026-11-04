import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (relativePath) =>
  readFileSync(path.join(root, relativePath), "utf8");

test("Render deploys main only after CI and gates traffic on database readiness", () => {
  const render = read("render.yaml");
  assert.match(render, /name: portfolio-api/);
  assert.match(render, /branch: main/);
  assert.match(render, /autoDeployTrigger: checksPass/);
  assert.match(render, /healthCheckPath: \/health\/ready/);
  assert.doesNotMatch(render, /preDeployCommand:.*(?:db:migrate|alembic)/);
});

test("Vercel retains the monorepo build and native preview/production Git behavior", () => {
  const vercel = JSON.parse(read("apps/web/vercel.json"));
  assert.equal(vercel.framework, "nextjs");
  assert.equal(vercel.installCommand, "npm ci --prefix ../..");
  assert.equal(
    vercel.buildCommand,
    "npm run build --workspace @portfolio/web --prefix ../..",
  );
  assert.equal(vercel.git, undefined);
});

test("GitHub PR and main CI provide the three documented required checks", () => {
  const ci = read(".github/workflows/ci.yml");
  assert.match(ci, /pull_request:\s*\n\s+branches: \[main\]/);
  assert.match(ci, /push:\s*\n\s+branches: \[main\]/);
  for (const jobName of [
    "Quality, contracts and build",
    "PostgreSQL integration tests",
    "Windows migration command compatibility",
  ]) {
    assert.ok(ci.includes(`name: ${jobName}`), `missing CI check ${jobName}`);
  }
  assert.doesNotMatch(
    ci,
    /npm run db:migrate|db:production-preflight|DATABASE_PRODUCTION_WRITES_AUTHORIZED/,
  );
});

test("production migrations stay outside deployment and require a recovery preflight", () => {
  const preflight = read(
    "apps/api/src/portfolio_api/production_migration_preflight.py",
  );
  const runbook = read("docs/deployment-and-migrations.md");
  const packageJson = JSON.parse(read("package.json"));
  assert.match(preflight, /create_database_engine\(settings, read_only=True\)/);
  assert.match(preflight, /_verify_recovery\(settings, current, inventory\)/);
  assert.doesNotMatch(preflight, /alembic_command\.upgrade|command\.upgrade/);
  assert.ok(packageJson.scripts["db:production-preflight"]);
  assert.match(runbook, /DATABASE_PRODUCTION_WRITES_AUTHORIZED=true/);
  assert.match(runbook, /fresh recovery point/i);
  assert.match(runbook, /Never run `npm run db:migrate` from CI/);
  assert.match(runbook, /temporary deployment freezes/i);
  assert.ok(runbook.includes("Auto-Deploy **After CI Checks Pass**"));
  assert.ok(runbook.includes("select **Only build preview**"));
});

test("the bespoke multi-environment release pipeline has been removed", () => {
  assert.equal(
    existsSync(path.join(root, ".github/workflows/production-release.yml")),
    false,
  );
  assert.equal(existsSync(path.join(root, "scripts/release")), false);
  assert.equal(
    existsSync(path.join(root, "docs/production-release-pipeline.md")),
    false,
  );
  assert.equal(
    "test:release" in JSON.parse(read("package.json")).scripts,
    false,
  );
});
