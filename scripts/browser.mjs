import { createRequire } from "node:module";
import path from "node:path";
import { loadEnv, root, run } from "./process.mjs";

loadEnv();
const web = path.join(root, "apps", "web");
const require = createRequire(path.join(web, "package.json"));
run(
  process.execPath,
  [require.resolve("@playwright/test/cli"), ...process.argv.slice(2)],
  {
    cwd: web,
    env: {
      ...process.env,
      PLAYWRIGHT_BROWSERS_PATH: path.join(root, ".cache", "ms-playwright"),
    },
  },
);
