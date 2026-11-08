import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { checkRecoveryTools } from "./recovery-tools.mjs";

test("recovery prerequisite check only invokes version probes and never certifies recovery", () => {
  const calls = [];
  const result = checkRecoveryTools((exe, args) => {
    calls.push([exe, args]);
    return { status: 0, stdout: `${exe} (PostgreSQL) 18.1\n` };
  });
  assert.deepEqual(calls, [
    ["pg_dump", ["--version"]],
    ["pg_restore", ["--version"]],
  ]);
  assert.equal(result.status, "TOOLS_AVAILABLE");
  assert.equal(result.recovery_verified, false);
});

test("missing, failed, malformed and mismatched clients fail closed", () => {
  for (const response of [
    { status: null, error: new Error("private path") },
    { status: 1, stdout: "pg_dump (PostgreSQL) 18.0" },
    { status: 0, stdout: "unknown" },
    { status: 0, stdout: "pg_dump (PostgreSQL) 17.2" },
  ]) {
    const result = checkRecoveryTools(() => response);
    assert.equal(result.status, "TOOLS_BLOCKED");
    assert.equal(result.recovery_verified, false);
    assert.ok(!JSON.stringify(result).includes("private path"));
  }
  const mixed = checkRecoveryTools((exe) => ({
    status: 0,
    stdout: `${exe} (PostgreSQL) ${exe === "pg_dump" ? "18" : "17"}.1`,
  }));
  assert.equal(mixed.status, "TOOLS_BLOCKED");
  assert.equal(
    checkRecoveryTools(() => {
      throw new Error("private path");
    }).status,
    "TOOLS_BLOCKED",
  );
  assert.equal(
    checkRecoveryTools(() => ({
      status: 0,
      stdout: "pg_dump (PostgreSQL) 18.1",
    })).status,
    "TOOLS_BLOCKED",
  );
});

test("explicit client directory changes only executable selection", () => {
  const calls = [];
  const result = checkRecoveryTools(
    (exe, args) => {
      calls.push([exe, args]);
      return { status: 0, stdout: `${path.basename(exe)} (PostgreSQL) 18.1` };
    },
    path.join("private", "pg18"),
  );
  assert.equal(result.status, "TOOLS_AVAILABLE");
  assert.deepEqual(
    calls.map(([exe, args]) => [path.basename(exe), args]),
    [
      ["pg_dump", ["--version"]],
      ["pg_restore", ["--version"]],
    ],
  );
  assert.ok(!JSON.stringify(result).includes("private"));
});
