import { existsSync } from "node:fs";
import { loadEnv, run, uv, uvEnv } from "./process.mjs";

if (!existsSync(uv)) {
  console.error("Python tooling is missing. Run npm run setup first.");
  process.exit(1);
}
loadEnv();
run(uv, process.argv.slice(2), { env: uvEnv() });
