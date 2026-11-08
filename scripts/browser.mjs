import { createRequire } from "node:module";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { mkdtempSync, unlinkSync, rmdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { managedBrowserEnvironment } from "./browser-environment.mjs";
import { loadEnv, root, run, uv, uvEnv, windows } from "./process.mjs";

loadEnv();
const web = path.join(root, "apps", "web");
const require = createRequire(path.join(web, "package.json"));
const args = process.argv.slice(2);
const managed = args.includes("--managed-production");
if (managed) {
  if (args[0] !== "test")
    throw new Error("Managed production is a browser test mode.");
  const directory = mkdtempSync(path.join(tmpdir(), "portfolio-browser-"));
  let status = 0;
  try {
    const env = {
      ...managedBrowserEnvironment(process.env, directory),
      PLAYWRIGHT_BROWSERS_PATH: path.join(root, ".cache", "ms-playwright"),
    };
    const commands = [
      {
        command: uv,
        args: [
          "run",
          "--locked",
          "--project",
          "apps/api",
          "python",
          "apps/api/tests/browser_tls.py",
          directory,
        ],
        cwd: root,
        env: { ...uvEnv(), ...env },
      },
      {
        command: windows ? "cmd.exe" : "npm",
        args: windows ? ["/d", "/s", "/c", "npm run build"] : ["run", "build"],
        cwd: root,
        env,
      },
      {
        command: process.execPath,
        args: [
          require.resolve("@playwright/test/cli"),
          ...args.filter((arg) => arg !== "--managed-production"),
        ],
        cwd: web,
        env,
      },
    ];
    for (const step of commands) {
      const result = spawnSync(step.command, step.args, {
        cwd: step.cwd,
        env: step.env,
        stdio: "inherit",
        windowsHide: true,
      });
      if (result.error)
        console.error(
          "Managed browser command could not start (" +
            (result.error.code ?? "unknown") +
            ").",
        );
      status = result.status ?? 1;
      if (status !== 0) break;
    }
  } finally {
    for (const name of ["ca.pem", "server.pem", "server.key"]) {
      try {
        unlinkSync(path.join(directory, name));
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
    }
    rmdirSync(directory);
  }
  process.exit(status);
}
run(process.execPath, [require.resolve("@playwright/test/cli"), ...args], {
  cwd: web,
  env: {
    ...process.env,
    PLAYWRIGHT_BROWSERS_PATH: path.join(root, ".cache", "ms-playwright"),
  },
});
