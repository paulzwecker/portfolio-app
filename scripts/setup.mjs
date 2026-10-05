import { copyFileSync, existsSync, mkdirSync, constants } from "node:fs";
import path from "node:path";
import { root, run, toolPython, uv, uvEnv, windows } from "./process.mjs";

mkdirSync(path.join(root, ".tools"), { recursive: true });
if (!existsSync(toolPython)) {
  run(process.env.PORTFOLIO_PYTHON || (windows ? "python" : "python3"), [
    "-m",
    "venv",
    path.join(root, ".tools", "venv"),
  ]);
}
run(toolPython, [
  "-c",
  "import sys; assert sys.version_info[:2] == (3, 12), 'Python 3.12 is required; set PORTFOLIO_PYTHON to its executable before setup.'",
]);
run(toolPython, [
  "-m",
  "pip",
  "--isolated",
  "install",
  "--disable-pip-version-check",
  "--cache-dir",
  path.join(root, ".cache", "pip"),
  "uv==0.12.23",
]);
run(uv, ["sync", "--locked", "--project", "apps/api"], { env: uvEnv() });
if (!existsSync(path.join(root, ".env"))) {
  copyFileSync(
    path.join(root, ".env.example"),
    path.join(root, ".env"),
    constants.COPYFILE_EXCL,
  );
}
console.log(
  "Dependencies ready. Configure .env, run npm run db:migrate, then npm run dev.",
);
