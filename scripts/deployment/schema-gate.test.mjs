import assert from "node:assert/strict";
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  commandExitCode,
  evaluateSchema,
  historyFingerprint,
  migrationGraph,
} from "./schema-gate.mjs";

const root = fileURLToPath(new URL("../../", import.meta.url));
const marker = JSON.parse(
  readFileSync(new URL("./production-schema.json", import.meta.url), "utf8"),
);
function migration(revision, parents = "None") {
  return {
    name: `${revision}.py`,
    content: `revision: str = "${revision}"\ndown_revision: str | None = ${parents}\ndepends_on = None\n`,
  };
}
const files = [migration("base"), migration("next", '"base"')];
function attestation(revision = "base", source = files) {
  return {
    ...marker,
    revision,
    migration_history_sha256: historyFingerprint(
      migrationGraph(source),
      revision,
    ),
  };
}

test("pending migrations pass PR planning and block production deployment", () => {
  const result = evaluateSchema(files, attestation());
  assert.equal(result.status, "MIGRATION_REQUIRED");
  assert.deepEqual(result.pending_revisions, ["next"]);
  assert.equal(commandExitCode("review", result), 0);
  assert.equal(commandExitCode("deploy", result), 1);
});

test("exact owner attestation permits the matching release", () => {
  const result = evaluateSchema(files, attestation("next"));
  assert.equal(result.status, "SCHEMA_ATTESTATION_MATCHED");
  assert.deepEqual(result.pending_revisions, []);
  assert.equal(commandExitCode("deploy", result), 0);
});

test("missing verification never authorizes review or deployment", () => {
  assert.equal(commandExitCode("review", null), 1);
  assert.equal(commandExitCode("deploy", null), 1);
});

test("changed already-applied migration bytes invalidate both review and deploy", () => {
  const changed = [
    { ...files[0], content: files[0].content + "# changed\n" },
    files[1],
  ];
  assert.throws(
    () => evaluateSchema(changed, attestation()),
    /APPLIED_MIGRATION_HISTORY_CHANGED/,
  );
});

test("fingerprints are independent of checkout line endings and directory ordering", () => {
  const original = historyFingerprint(migrationGraph(files), "next");
  const windows = [...files]
    .reverse()
    .map((file) => ({ ...file, content: file.content.replace(/\n/g, "\r\n") }));
  assert.equal(historyFingerprint(migrationGraph(windows), "next"), original);
});

test("historical Alembic branches and merge revisions retain every ancestor", () => {
  const branched = [
    migration("base"),
    migration("left", '"base"'),
    migration("right", '"base"'),
    migration("merge", '("left", "right")'),
  ];
  const result = evaluateSchema(branched, attestation("base", branched));
  assert.deepEqual(result.pending_revisions, ["left", "right", "merge"]);
});

test("missing, malformed, wrong-target and unknown-revision attestations fail closed", () => {
  for (const invalid of [
    null,
    {},
    { ...attestation(), contract: "v2" },
    { ...attestation(), verified_at: "invalid" },
    { ...attestation(), target: { ...marker.target, branch: "other" } },
    { ...attestation(), revision: "unknown" },
    { ...attestation(), migration_history_sha256: "bad" },
  ]) {
    assert.throws(() => evaluateSchema(files, invalid));
  }
});

test("invalid migration graphs cannot pass planning or production", () => {
  const invalidGraphs = [
    [],
    [files[0], files[0]],
    [files[0], migration("orphan", '"missing"')],
    [files[0], migration("other")],
    [migration("a", '"b"'), migration("b", '"a"')],
    [files[0], migration("a", '"b"'), migration("b", '"a"')],
    [
      files[0],
      {
        ...files[1],
        content: files[1].content.replace('"base"', "get_parent()"),
      },
    ],
    [
      files[0],
      {
        ...files[1],
        content: files[1].content.replace(
          "depends_on = None",
          'depends_on = "base"',
        ),
      },
    ],
    [files[0], migration("next", '("base", "base")')],
  ];
  for (const invalid of invalidGraphs)
    assert.throws(() => migrationGraph(invalid));
});

test("the repository graph and owner marker bind the reviewed pending ledger range", () => {
  const directory = new URL(
    "../../apps/api/migrations/versions/",
    import.meta.url,
  );
  const actual = readdirSync(directory)
    .filter((name) => name.endsWith(".py") && name !== "__init__.py")
    .map((name) => ({
      name,
      content: readFileSync(new URL(name, directory), "utf8"),
    }));
  const result = evaluateSchema(actual, marker);
  // A future owner-reviewed schema promotion may legitimately empty this range.
  assert.ok(
    ["MIGRATION_REQUIRED", "SCHEMA_ATTESTATION_MATCHED"].includes(
      result.status,
    ),
  );
  assert.equal(result.repository_head, "b59f16c8a203");
  if (marker.revision === "9f2a6d4c81b7")
    assert.deepEqual(result.pending_revisions, [
      "a832e94d6f10",
      "b59f16c8a203",
    ]);
});

test("CLI review and deploy use standard exit semantics without cloud access", () => {
  const run = (mode) =>
    spawnSync(process.execPath, ["scripts/deployment/schema-gate.mjs", mode], {
      cwd: root,
      encoding: "utf8",
    });
  const review = run("review");
  assert.equal(review.status, 0);
  const result = JSON.parse(review.stdout);
  assert.equal(run("deploy").status, commandExitCode("deploy", result));
  assert.equal(run("unknown").status, 1);
});

test("documented Vercel shell hook skips production even if Node crashes or the script is missing", (context) => {
  const shell =
    process.platform === "win32"
      ? path.join(
          process.env.ProgramFiles ?? "C:/Program Files",
          "Git/bin/bash.exe",
        )
      : "/bin/sh";
  if (!existsSync(shell))
    return context.skip(
      "POSIX shell unavailable; execute this provider-hook check on Linux",
    );
  const runbook = readFileSync(
    new URL("../../docs/deployment-and-migrations.md", import.meta.url),
    "utf8",
  );
  const command = runbook
    .split(/\r?\n/)
    .find((line) => line.startsWith('if [ "$VERCEL_ENV" = "preview" ]'));
  assert.ok(command, "the exact operator command must remain tested");
  const temporaryRoot = mkdtempSync(
    path.join(os.tmpdir(), "portfolio-schema-gate-"),
  );
  const workingDirectory = path.join(temporaryRoot, "apps/web");
  const script = path.join(temporaryRoot, "scripts/deployment/schema-gate.mjs");
  mkdirSync(workingDirectory, { recursive: true });
  mkdirSync(path.dirname(script), { recursive: true });
  const run = (environment) => {
    const result = spawnSync(shell, ["-c", command], {
      cwd: workingDirectory,
      encoding: "utf8",
      env: { ...process.env, VERCEL_ENV: environment },
    });
    assert.equal(result.error, undefined);
    return result.status;
  };
  try {
    assert.equal(run("production"), 0, "missing script must skip");
    assert.equal(run("preview"), 1, "preview must still build");
    assert.equal(run(""), 0, "unknown environment must skip");
    writeFileSync(script, "process.exit(0);\n");
    assert.equal(run("production"), 1, "matching attestation builds");
    writeFileSync(script, "process.exit(1);\n");
    assert.equal(run("production"), 0, "pending or invalid attestation skips");
    writeFileSync(script, "this is invalid JavaScript;\n");
    assert.equal(run("production"), 0, "syntax failure must skip");
  } finally {
    assert.equal(
      path.dirname(path.resolve(temporaryRoot)),
      path.resolve(os.tmpdir()),
    );
    assert.ok(
      path.basename(temporaryRoot).startsWith("portfolio-schema-gate-"),
    );
    rmSync(temporaryRoot, { recursive: true, force: true });
  }
});
