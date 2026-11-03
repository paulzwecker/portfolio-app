import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { scrubProductionEnvironmentCache } from "./vercel-env-cache.mjs";

function runCli(args) {
  const cli = process.env.VERCEL_CLI_PATH;
  if (!cli) throw new Error("vercel_cli_not_preinstalled");
  const result = spawnSync(cli, [...args, "--cwd", "apps/web"], {
    cwd: process.cwd(),
    encoding: "utf8",
    windowsHide: true,
    env: {
      PATH: process.env.PATH,
      HOME: process.env.HOME,
      CI: "1",
      VERCEL_TOKEN: process.env.VERCEL_TOKEN,
      VERCEL_PROJECT_ID: process.env.VERCEL_PROJECT_ID,
      VERCEL_ORG_ID: process.env.VERCEL_ORG_ID,
      VERCEL_TELEMETRY_DISABLED: "1",
    },
    maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error || result.status !== 0)
    throw new Error("vercel_project_prepare_failed");
}

function main() {
  const token = process.env.VERCEL_TOKEN;
  const project = process.env.VERCEL_PROJECT_ID;
  const org = process.env.VERCEL_ORG_ID;
  if (!token || !project || !org)
    throw new Error("vercel_project_prepare_inputs_invalid");

  runCli(["link", "--yes", "--project", project, "--scope", org]);
  runCli(["pull", "--yes", "--environment=production"]);
  scrubProductionEnvironmentCache(resolve(process.cwd(), "apps/web"));
  console.log(
    "Vercel project settings are prepared; the pulled production env cache was removed before build.",
  );
}

try {
  main();
} catch (error) {
  console.error(
    error instanceof Error ? error.message : "vercel_project_prepare_failed",
  );
  process.exitCode = 1;
}
