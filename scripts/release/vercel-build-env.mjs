import { devNull } from "node:os";

export function buildEnvironment(source) {
  const environment = {};
  for (const key of ["PATH", "HOME", "TMPDIR", "TEMP", "TMP", "CI"]) {
    if (source[key]) environment[key] = source[key];
  }
  environment.NPM_CONFIG_USERCONFIG = devNull;
  environment.VERCEL_TELEMETRY_DISABLED = "1";
  return environment;
}
