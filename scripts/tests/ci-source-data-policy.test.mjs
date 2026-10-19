import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  findForbiddenSourcePaths,
  validateWorkflowCheckoutPolicy,
  validateWorkflowWorkbookIsolation,
} from "./ci-source-data-policy.mjs";

const workflowPath = path.resolve(".github/workflows/ci.yml");
const workflow = await import("node:fs").then(({ readFileSync }) =>
  readFileSync(workflowPath, "utf8"),
);

test("all GitHub CI checkouts use the restricted source tree", () => {
  assert.doesNotThrow(() => validateWorkflowCheckoutPolicy(workflow));
});

test("GitHub CI cannot access Google credentials, workbook IDs or source snapshots", () => {
  assert.doesNotThrow(() => validateWorkflowWorkbookIsolation(workflow));
  assert.throws(
    () =>
      validateWorkflowWorkbookIsolation(
        `${workflow}\n  GOOGLE_DRIVE_PORTFOLIO_WORKBOOK_FILE_ID: fake-id`,
      ),
    /must not configure Google workbook credentials/,
  );
  assert.throws(
    () =>
      validateWorkflowWorkbookIsolation(
        `${workflow}\n  GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE: '\${{ secrets.GOOGLE_KEY }}'`,
      ),
    /must not configure Google workbook credentials/,
  );
  assert.throws(
    () =>
      validateWorkflowWorkbookIsolation(
        `${workflow}\n  READER_KEY: '\${{ secrets.DRIVE_SERVICE_ACCOUNT }}'`,
      ),
    /must not reference Google credentials or workbook secrets/,
  );
  assert.throws(
    () =>
      validateWorkflowWorkbookIsolation(
        `${workflow}\n      run: |\n        npm run source:workbook --\n        acquire portfolio`,
      ),
    /must not acquire real workbook snapshots/,
  );
  assert.throws(
    () =>
      validateWorkflowWorkbookIsolation(
        `${workflow}\n      run: node -m portfolio_api.workbook_sources`,
      ),
    /must not acquire real workbook snapshots/,
  );
});

test("the CI source-data guard detects excluded operator input paths", () => {
  const root = mkdtempSync(path.join(os.tmpdir(), "portfolio-ci-policy-"));
  try {
    assert.deepEqual(findForbiddenSourcePaths(root), []);
    mkdirSync(path.join(root, "docs", "empty-subdirectory"), {
      recursive: true,
    });
    assert.deepEqual(findForbiddenSourcePaths(root), []);
    mkdirSync(path.join(root, "reference", "workbook"), { recursive: true });
    writeFileSync(
      path.join(root, "reference", "workbook", "synthetic.xlsx"),
      "fixture",
    );
    assert.deepEqual(findForbiddenSourcePaths(root), ["reference"]);
    rmSync(path.join(root, "reference"), { recursive: true, force: true });
    mkdirSync(path.join(root, "apps/api/tests/fixtures"), { recursive: true });
    writeFileSync(
      path.join(root, "apps/api/tests/fixtures/synthetic.json"),
      "synthetic fixture",
    );
    assert.deepEqual(findForbiddenSourcePaths(root), []);
    writeFileSync(
      path.join(root, "apps/api/tests/fixtures/p_googl_ufcf_dcf_v1.json"),
      "operator source fixture",
    );
    assert.deepEqual(findForbiddenSourcePaths(root), [
      "apps/api/tests/fixtures/p_googl_ufcf_dcf_v1.json",
    ]);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
