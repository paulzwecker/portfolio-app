import { appendFileSync } from "node:fs";

import {
  RELEASE_ENVIRONMENTS,
  REQUIRED_CI_CHECKS,
  validateProtectedEnvironment,
  validateReleaseIdentity,
} from "./policy.mjs";

const apiRoot = "https://api.github.com";

async function githubGet(path, token) {
  const response = await fetch(`${apiRoot}${path}`, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
    },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error(`github_read_failed:${response.status}`);
  return response.json();
}

function fail(errors) {
  throw new Error(`release_preflight_failed:${errors.join(",")}`);
}

async function main() {
  const {
    GITHUB_TOKEN,
    GITHUB_REPOSITORY,
    GITHUB_REF,
    GITHUB_SHA,
    INPUT_RELEASE_SHA,
  } = process.env;
  const reviewerIds = (process.env.RELEASE_REVIEWER_IDS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (
    !GITHUB_TOKEN ||
    !GITHUB_REPOSITORY ||
    !GITHUB_REF ||
    !GITHUB_SHA ||
    !INPUT_RELEASE_SHA
  ) {
    fail(["release_context_or_repository_variables_missing"]);
  }
  if (GITHUB_REPOSITORY.toLowerCase() !== "paulzwecker/portfolio-app") {
    fail(["release_repository_identity_mismatch"]);
  }
  const [owner, name] = GITHUB_REPOSITORY.split("/");
  if (!owner || !name || GITHUB_REPOSITORY.split("/").length !== 2) {
    fail(["github_repository_context_invalid"]);
  }
  const repository = `${encodeURIComponent(owner)}/${encodeURIComponent(name)}`;
  const mainRef = await githubGet(
    `/repos/${repository}/git/ref/heads/main`,
    GITHUB_TOKEN,
  );
  const checks = await githubGet(
    `/repos/${repository}/commits/${INPUT_RELEASE_SHA}/check-runs?filter=latest&per_page=100`,
    GITHUB_TOKEN,
  );
  const identityErrors = validateReleaseIdentity({
    eventRef: GITHUB_REF,
    eventSha: GITHUB_SHA,
    requestedSha: INPUT_RELEASE_SHA,
    mainSha: mainRef?.object?.sha,
    checkRuns: checks?.check_runs,
    requiredChecks: REQUIRED_CI_CHECKS,
  });
  if (identityErrors.length) fail(identityErrors);

  for (const name of RELEASE_ENVIRONMENTS) {
    const encodedName = encodeURIComponent(name);
    const environment = await githubGet(
      `/repos/${repository}/environments/${encodedName}`,
      GITHUB_TOKEN,
    );
    const branchPolicies = await githubGet(
      `/repos/${repository}/environments/${encodedName}/deployment-branch-policies`,
      GITHUB_TOKEN,
    );
    const errors = validateProtectedEnvironment({
      environment,
      branchPolicies,
      reviewerIds,
    });
    if (errors.length) fail(errors.map((code) => `${name}:${code}`));
  }

  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(
      process.env.GITHUB_OUTPUT,
      `release_sha=${INPUT_RELEASE_SHA.toLowerCase()}\n`,
    );
  }
  console.log(
    `Release identity and ${RELEASE_ENVIRONMENTS.length} protected environments verified for ${INPUT_RELEASE_SHA}.`,
  );
}

main().catch((error) => {
  console.error(
    error instanceof Error ? error.message : "release_preflight_failed:unknown",
  );
  process.exitCode = 1;
});
