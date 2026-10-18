import {
  constants,
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
} from "node:fs";
import path from "node:path";
import { root, run, toolPython, uv, uvEnv, windows } from "./process.mjs";

mkdirSync(path.join(root, ".tools"), { recursive: true });
const expectedPython = readFileSync(
  path.join(root, ".python-version"),
  "utf8",
).trim();
if (!/^3\.\d+\.\d+$/.test(expectedPython)) {
  throw new Error(
    ".python-version must contain an exact Python major.minor.patch version.",
  );
}
const pythonCommand =
  process.env.PORTFOLIO_PYTHON || (windows ? "python" : "python3");
if (!existsSync(toolPython)) {
  run(pythonCommand, ["-m", "venv", path.join(root, ".tools", "venv")]);
}
run(toolPython, [
  "-c",
  "import sys; actual = '.'.join(map(str, sys.version_info[:3])); expected = sys.argv[1]; assert actual == expected, f'{expected} is required, found {actual}; set PORTFOLIO_PYTHON to its executable before setup.'",
  expectedPython,
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
