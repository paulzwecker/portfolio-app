import { loadEnv, run, uv, uvEnv } from "./process.mjs";

loadEnv();
if (!process.env.TEST_DATABASE_URL) {
  console.error(
    "Set TEST_DATABASE_URL in .env to a dedicated PostgreSQL database ending in _test.",
  );
  process.exit(1);
}
run(
  uv,
  [
    "run",
    "--locked",
    "--project",
    "apps/api",
    "pytest",
    "apps/api/tests",
    "-m",
    "integration",
  ],
  { env: uvEnv() },
);
