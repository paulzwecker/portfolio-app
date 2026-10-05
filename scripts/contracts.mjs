import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import openapiTS, { astToString } from "openapi-typescript";
import { loadEnv, root, run, uv, uvEnv } from "./process.mjs";

loadEnv();
const check = process.argv.includes("--check");
run(
  uv,
  [
    "run",
    "--locked",
    "--project",
    "apps/api",
    "python",
    "apps/api/scripts/export_openapi.py",
    ...(check ? ["--check"] : []),
  ],
  { env: uvEnv() },
);
const schema = new URL("../packages/contracts/openapi.json", import.meta.url);
const content = astToString(await openapiTS(schema));
const destination = path.join(root, "packages", "contracts", "schema.d.ts");
if (check) {
  if (readFileSync(destination, "utf8") !== content) {
    console.error(
      "TypeScript contract is stale. Run npm run contracts:generate.",
    );
    process.exit(1);
  }
  console.log("OpenAPI and TypeScript contracts are current.");
} else {
  writeFileSync(destination, content);
}
