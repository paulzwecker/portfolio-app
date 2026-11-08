// Local prerequisite check only: never opens a database or creates a backup.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function checkRecoveryTools(run, binDirectory = "") {
  const results = {};
  for (const tool of ["pg_dump", "pg_restore"]) {
    const executable = binDirectory ? path.join(binDirectory, tool) : tool;
    let result;
    try {
      result = run(executable, ["--version"]);
    } catch {
      // Never surface local paths or process error messages in diagnostics.
      result = null;
    }
    const match =
      result?.status === 0 && typeof result.stdout === "string"
        ? result.stdout
            .trim()
            .match(new RegExp(`^${tool} \\(PostgreSQL\\) (\\d+)(?:[.\\s]|$)`))
        : null;
    results[tool] = !match
      ? "UNAVAILABLE"
      : match[1] === "18"
        ? "POSTGRESQL_18"
        : "WRONG_MAJOR";
  }
  return {
    status: Object.values(results).every((value) => value === "POSTGRESQL_18")
      ? "TOOLS_AVAILABLE"
      : "TOOLS_BLOCKED",
    tools: results,
    recovery_verified: false,
  };
}

function main() {
  const args = process.argv.slice(2);
  if (
    args.length !== 0 &&
    !(args.length === 2 && args[0] === "--pg-bin" && args[1])
  ) {
    process.stdout.write("RECOVERY_TOOLS_ARGUMENT_INVALID\n");
    return 2;
  }
  const result = checkRecoveryTools(
    (executable, argv) =>
      spawnSync(executable, argv, {
        encoding: "utf8",
        timeout: 10000,
        windowsHide: true,
      }),
    args[1],
  );
  process.stdout.write(`${JSON.stringify(result)}\n`);
  return result.status === "TOOLS_AVAILABLE" ? 0 : 2;
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  process.exitCode = main();
}
