import { existsSync, lstatSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const checkoutDirectories = ["apps", "packages", "scripts", "tools", ".github"];
const excludedSourcePaths = [
  "apps/api/tests/test_legacy_import.py",
  "apps/api/tests/test_consensus_source_data.py",
  "apps/api/tests/test_model_input_migration.py",
  "apps/api/tests/test_model_input_parity.py",
  "apps/api/tests/test_model_migration_inventory.py",
  "apps/api/tests/test_research_rank_source_data.py",
  "apps/api/tests/test_yahoo_finance_source_data.py",
  "apps/api/tests/fixtures/p_googl_ufcf_dcf_v1.json",
  "apps/api/tests/fixtures/w_hdfc_residual_income_v1.json",
  "apps/api/tests/fixtures/w_tost_owner_cash_flow_v1.json",
];
const forbiddenPaths = ["docs", "reference", ...excludedSourcePaths];

export function validateWorkflowCheckoutPolicy(workflow) {
  const steps = workflow
    .split(/\n\s*- name:/)
    .filter((step) => step.includes("uses: actions/checkout@v4"));
  if (steps.length !== 3) {
    throw new Error("Every CI job must use the restricted source checkout.");
  }
  for (const step of steps) {
    if (
      !step.includes("filter: blob:none") ||
      !step.includes("sparse-checkout-cone-mode: false") ||
      !step.includes("!/*/")
    ) {
      throw new Error(
        "CI checkout must fetch only allowlisted source directories.",
      );
    }
    for (const directory of checkoutDirectories) {
      if (!step.includes(`/${directory}/`)) {
        throw new Error("CI checkout is missing a required source directory.");
      }
    }
    for (const relativePath of excludedSourcePaths) {
      if (!step.includes(`!/${relativePath}`)) {
        throw new Error(
          "CI checkout must exclude source-bound test and fixture paths.",
        );
      }
    }
  }
}

export function findForbiddenSourcePaths(root) {
  return forbiddenPaths.filter((relativePath) =>
    containsFiles(path.join(root, relativePath)),
  );
}

function containsFiles(directory) {
  if (!existsSync(directory)) return false;
  const details = lstatSync(directory);
  if (details.isSymbolicLink() || !details.isDirectory()) return true;
  return readdirSync(directory, { withFileTypes: true }).some((entry) => {
    if (entry.isFile() || entry.isSymbolicLink()) return true;
    return (
      entry.isDirectory() && containsFiles(path.join(directory, entry.name))
    );
  });
}

export function assertCiSourceDataExcluded(root) {
  const workflowPath = path.join(root, ".github", "workflows", "ci.yml");
  validateWorkflowCheckoutPolicy(readFileSync(workflowPath, "utf8"));
  const present = findForbiddenSourcePaths(root);
  if (present.length > 0) {
    throw new Error("CI checkout contains excluded source data paths.");
  }
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    assertCiSourceDataExcluded(process.cwd());
    console.log("CI source-data checkout boundary verified.");
  } catch (error) {
    console.error(
      error instanceof Error ? error.message : "CI source-data check failed.",
    );
    process.exitCode = 1;
  }
}
