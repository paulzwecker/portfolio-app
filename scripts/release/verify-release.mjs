import { appendFileSync } from "node:fs";

import {
  RELEASE_APPROVAL_ENVIRONMENT,
  RELEASE_SECRET_ENVIRONMENTS,
  REQUIRED_CI_CHECKS,
  validateOwnerApprovalEnvironment,
  validateReleaseIdentity,
  validateSecretEnvironment,
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
    GITHUB_ACTOR_ID,
    INPUT_RELEASE_SHA,
  } = process.env;
  if (
    !GITHUB_TOKEN ||
    !GITHUB_REPOSITORY ||
    !GITHUB_REF ||
    !GITHUB_SHA ||
    !GITHUB_ACTOR_ID ||
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
  const [repositoryInfo, mainRef, checks] = await Promise.all([
    githubGet(`/repos/${repository}`, GITHUB_TOKEN),
    githubGet(`/repos/${repository}/git/ref/heads/main`, GITHUB_TOKEN),
    githubGet(
      `/repos/${repository}/commits/${INPUT_RELEASE_SHA}/check-runs?filter=latest&per_page=100`,
      GITHUB_TOKEN,
    ),
  ]);
  const ownerId = repositoryInfo?.owner?.id;
  const identityErrors = validateReleaseIdentity({
    eventRef: GITHUB_REF,
    eventSha: GITHUB_SHA,
    requestedSha: INPUT_RELEASE_SHA,
    mainSha: mainRef?.object?.sha,
    checkRuns: checks?.check_runs,
    eventActorId: GITHUB_ACTOR_ID,
    ownerId,
    requiredChecks: REQUIRED_CI_CHECKS,
  });
  if (identityErrors.length) fail(identityErrors);

  if (!/^\d+$/.test(String(ownerId ?? ""))) {
    fail(["repository_owner_identity_unavailable"]);
  }

  const approvalName = encodeURIComponent(RELEASE_APPROVAL_ENVIRONMENT);
  const [approvalEnvironment, approvalBranchPolicies] = await Promise.all([
    githubGet(
      `/repos/${repository}/environments/${approvalName}`,
      GITHUB_TOKEN,
    ),
    githubGet(
      `/repos/${repository}/environments/${approvalName}/deployment-branch-policies`,
      GITHUB_TOKEN,
    ),
  ]);
  const approvalErrors = validateOwnerApprovalEnvironment({
    environment: approvalEnvironment,
    branchPolicies: approvalBranchPolicies,
    ownerId,
  });
  if (approvalErrors.length) {
    fail(
      approvalErrors.map((code) => `${RELEASE_APPROVAL_ENVIRONMENT}:${code}`),
    );
  }

  for (const name of RELEASE_SECRET_ENVIRONMENTS) {
    const encodedName = encodeURIComponent(name);
    const [environment, branchPolicies] = await Promise.all([
      githubGet(
        `/repos/${repository}/environments/${encodedName}`,
        GITHUB_TOKEN,
      ),
      githubGet(
        `/repos/${repository}/environments/${encodedName}/deployment-branch-policies`,
        GITHUB_TOKEN,
      ),
    ]);
    const errors = validateSecretEnvironment({ environment, branchPolicies });
    if (errors.length) fail(errors.map((code) => `${name}:${code}`));
  }

  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(
      process.env.GITHUB_OUTPUT,
      `release_sha=${INPUT_RELEASE_SHA.toLowerCase()}\n`,
    );
  }
  console.log(
    `Release identity, owner approval, and ${RELEASE_SECRET_ENVIRONMENTS.length} main-only credential scopes verified for ${INPUT_RELEASE_SHA}.`,
  );
}

main().catch((error) => {
  console.error(
    error instanceof Error ? error.message : "release_preflight_failed:unknown",
  );
  process.exitCode = 1;
});
