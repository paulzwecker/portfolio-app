import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { buildEnvironment } from "./vercel-build-env.mjs";
import { assertProductionEnvironmentCacheAbsent } from "./vercel-env-cache.mjs";

function main() {
  const cli = process.env.VERCEL_CLI_PATH;
  if (!cli) throw new Error("vercel_cli_not_preinstalled");
  assertProductionEnvironmentCacheAbsent(resolve(process.cwd(), "apps/web"));
  const result = spawnSync(cli, ["build", "--prod", "--cwd", "apps/web"], {
    cwd: process.cwd(),
    encoding: "utf8",
    windowsHide: true,
    env: buildEnvironment(process.env),
    maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error || result.status !== 0)
    throw new Error("vercel_production_build_failed");
  process.stdout.write(result.stdout ?? "");
  console.log(
    "Vercel production artifact built without deployment credentials.",
  );
}

try {
  main();
} catch (error) {
  console.error(
    error instanceof Error ? error.message : "vercel_production_build_failed",
  );
  process.exitCode = 1;
}
