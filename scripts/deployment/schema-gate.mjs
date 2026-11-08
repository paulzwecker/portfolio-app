import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const revisionPattern = /^[A-Za-z0-9_]{1,64}$/;
const target = {
  project: "blue-pond-96398788",
  branch: "br-square-butterfly-bacw0rn5",
  endpoint: "ep-floral-cake-bae16liy",
  database: "neondb",
  schema: "public",
};

function requireCondition(condition, code) {
  if (!condition) throw new Error(code);
}

function assignment(source, name) {
  const matches = [
    ...source.matchAll(
      new RegExp(`^${name}(?:\\s*:[^=\\n]+)?\\s*=\\s*(.+)$`, "gm"),
    ),
  ];
  requireCondition(matches.length === 1, "MIGRATION_METADATA_INVALID");
  return matches[0][1].trim();
}

function revisionLiteral(value) {
  const match = value.match(/^(["'])([A-Za-z0-9_]{1,64})\1$/);
  requireCondition(match, "MIGRATION_REVISION_INVALID");
  return match[2];
}

// Read literal Alembic metadata only. Never import or execute migration code.
function parentsLiteral(value) {
  if (value === "None") return [];
  if (/^["']/.test(value)) return [revisionLiteral(value)];
  requireCondition(
    value.startsWith("(") && value.endsWith(")"),
    "MIGRATION_PARENTS_INVALID",
  );
  const parts = value
    .slice(1, -1)
    .split(",")
    .map((part) => part.trim());
  if (parts.at(-1) === "") parts.pop();
  requireCondition(parts.length > 0, "MIGRATION_PARENTS_INVALID");
  return parts.map(revisionLiteral);
}

export function migrationGraph(files) {
  requireCondition(files.length > 0, "MIGRATIONS_MISSING");
  const nodes = new Map();
  for (const file of files) {
    const content = file.content.replace(/\r\n/g, "\n");
    const revision = revisionLiteral(assignment(content, "revision"));
    const parents = parentsLiteral(assignment(content, "down_revision"));
    requireCondition(
      assignment(content, "depends_on") === "None",
      "MIGRATION_DEPENDENCY_UNSUPPORTED",
    );
    requireCondition(!nodes.has(revision), "MIGRATION_REVISION_DUPLICATE");
    requireCondition(
      new Set(parents).size === parents.length,
      "MIGRATION_PARENT_DUPLICATE",
    );
    nodes.set(revision, { ...file, content, revision, parents });
  }
  const referenced = new Set();
  for (const node of nodes.values()) {
    for (const parent of node.parents) {
      requireCondition(nodes.has(parent), "MIGRATION_PARENT_MISSING");
      referenced.add(parent);
    }
  }
  const heads = [...nodes.keys()].filter(
    (revision) => !referenced.has(revision),
  );
  requireCondition(heads.length === 1, "MIGRATION_HEAD_AMBIGUOUS");
  function ancestors(revision, visiting = new Set(), found = new Set()) {
    requireCondition(!visiting.has(revision), "MIGRATION_CYCLE");
    if (found.has(revision)) return found;
    visiting.add(revision);
    for (const parent of nodes.get(revision).parents)
      ancestors(parent, visiting, found);
    visiting.delete(revision);
    found.add(revision);
    return found;
  }
  const all = ancestors(heads[0]);
  requireCondition(all.size === nodes.size, "MIGRATION_GRAPH_DISCONNECTED");
  return { head: heads[0], nodes, ancestors };
}

export function historyFingerprint(graph, revision) {
  requireCondition(graph.nodes.has(revision), "ATTESTED_REVISION_UNKNOWN");
  const records = [...graph.ancestors(revision)]
    .map((id) => graph.nodes.get(id))
    .sort((left, right) =>
      left.name < right.name ? -1 : left.name > right.name ? 1 : 0,
    )
    .map(({ name, content }) => [
      name,
      createHash("sha256").update(content).digest("hex"),
    ]);
  return createHash("sha256").update(JSON.stringify(records)).digest("hex");
}

export function evaluateSchema(files, attestation) {
  const graph = migrationGraph(files);
  requireCondition(
    attestation?.contract === "production-schema-attestation-v1",
    "ATTESTATION_CONTRACT_INVALID",
  );
  requireCondition(
    typeof attestation.revision === "string" &&
      revisionPattern.test(attestation.revision),
    "ATTESTATION_REVISION_INVALID",
  );
  requireCondition(
    typeof attestation.verified_at === "string" &&
      Number.isFinite(Date.parse(attestation.verified_at)),
    "ATTESTATION_TIMESTAMP_INVALID",
  );
  requireCondition(
    Object.entries(target).every(
      ([key, value]) => attestation.target?.[key] === value,
    ),
    "ATTESTATION_TARGET_MISMATCH",
  );
  requireCondition(
    historyFingerprint(graph, attestation.revision) ===
      attestation.migration_history_sha256,
    "APPLIED_MIGRATION_HISTORY_CHANGED",
  );
  const applied = graph.ancestors(attestation.revision);
  return {
    status:
      graph.head === attestation.revision
        ? "SCHEMA_ATTESTATION_MATCHED"
        : "MIGRATION_REQUIRED",
    attested_revision: attestation.revision,
    repository_head: graph.head,
    pending_revisions: [...graph.ancestors(graph.head)].filter(
      (id) => !applied.has(id),
    ),
    repository_history_sha256: historyFingerprint(graph, graph.head),
  };
}

export function commandExitCode(mode, result) {
  if (mode === "review") return result ? 0 : 1;
  if (mode === "deploy")
    return result?.status === "SCHEMA_ATTESTATION_MATCHED" ? 0 : 1;
  return 1;
}

function main() {
  const mode = process.argv[2];
  if (!["review", "deploy"].includes(mode) || process.argv.length !== 3) {
    process.stdout.write("SCHEMA_GATE_ARGUMENT_INVALID\n");
    return 1;
  }
  try {
    const directory = path.join(root, "apps/api/migrations/versions");
    const files = readdirSync(directory)
      .filter((name) => name.endsWith(".py") && name !== "__init__.py")
      .map((name) => ({
        name,
        content: readFileSync(path.join(directory, name), "utf8"),
      }));
    const attestation = JSON.parse(
      readFileSync(
        path.join(root, "scripts/deployment/production-schema.json"),
        "utf8",
      ),
    );
    const result = evaluateSchema(files, attestation);
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return commandExitCode(mode, result);
  } catch {
    // No raw filesystem/JSON errors in provider logs.
    process.stdout.write("SCHEMA_GATE_INVALID\n");
    return commandExitCode(mode, null);
  }
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  process.exitCode = main();
}
