import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { root, windows } from "./process.mjs";

function readRoot(name) {
  return readFileSync(path.join(root, name), "utf8").trim();
}

function checkPython(command, expected) {
  const candidates =
    windows && !path.extname(command)
      ? [`${command}.cmd`, `${command}.exe`, command]
      : [command];
  for (const candidate of candidates) {
    const result = spawnSync(
      candidate,
      [
        "-c",
        "import sys; expected = sys.argv[1]; actual = '.'.join(map(str, sys.version_info[:3])); raise SystemExit(0 if actual == expected else 1)",
        expected,
      ],
      { cwd: root, stdio: "inherit", windowsHide: true },
    );
    if (result.status === 0) return expected;
    if (result.error?.code !== "ENOENT") return null;
  }
  return null;
}

function npmVersionFromEnvironment() {
  const userAgent = process.env.npm_config_user_agent;
  if (!userAgent) return null;
  return userAgent.match(/(?:^|\s)npm\/([^\s]+)/)?.[1] ?? null;
}

const packageJson = JSON.parse(readRoot("package.json"));
const expectedNode = readRoot(".node-version");
const expectedPython = readRoot(".python-version");
const expectedNpm = packageJson.packageManager?.replace(/^npm@/, "");
const pythonCommand =
  process.env.PORTFOLIO_PYTHON || (windows ? "python.exe" : "python3");
const pythonVersion = checkPython(pythonCommand, expectedPython);
const npmVersion = npmVersionFromEnvironment();
const checks = [
  ["Node.js", process.versions.node, expectedNode],
  ["npm", npmVersion, expectedNpm],
  ["Python", pythonVersion, expectedPython],
];
const failures = checks.filter(([, actual, expected]) => actual !== expected);

if (failures.length > 0) {
  console.error("Codex Cloud toolchain check failed:");
  for (const [name, actual, expected] of failures) {
    console.error(
      `- ${name}: expected ${expected}, found ${actual ?? "missing"}`,
    );
  }
  process.exit(1);
}

console.log(
  `Toolchain ready: Node.js ${expectedNode}, npm ${expectedNpm}, Python ${expectedPython}.`,
);
