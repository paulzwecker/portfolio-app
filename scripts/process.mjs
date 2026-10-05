import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

export const root = fileURLToPath(new URL("../", import.meta.url));
export const windows = process.platform === "win32";
export const toolPython = path.join(
  root,
  ".tools",
  "venv",
  windows ? "Scripts/python.exe" : "bin/python",
);
export const uv = path.join(
  root,
  ".tools",
  "venv",
  windows ? "Scripts/uv.exe" : "bin/uv",
);

export function loadEnv() {
  const envFile = path.join(root, ".env");
  if (existsSync(envFile)) process.loadEnvFile(envFile);
}

export function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    windowsHide: true,
    ...options,
  });
  if (result.error) {
    console.error(
      `Could not run ${path.basename(command)}: ${result.error.message}`,
    );
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}

export function uvEnv() {
  return {
    ...process.env,
    UV_CACHE_DIR: path.join(root, ".cache", "uv"),
    UV_PYTHON_DOWNLOADS: "never",
    UV_PYTHON: process.env.UV_PYTHON || toolPython,
  };
}
