import { createRequire } from "node:module";
import path from "node:path";
import { loadEnv, root, run } from "./process.mjs";

loadEnv();
const web = path.join(root, "apps", "web");
const require = createRequire(path.join(web, "package.json"));
const action = process.argv[2];
const port = process.env.E2E_WEB_PORT ?? "3000";
if (!["dev", "build", "start"].includes(action))
  throw new Error("Expected dev, build, or start.");
const args = [require.resolve("next/dist/bin/next"), action];
if (action !== "build") args.push("--hostname", "127.0.0.1", "--port", port);
run(process.execPath, args, { cwd: web });
