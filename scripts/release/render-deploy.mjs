import { appendFileSync } from "node:fs";

import { validateRenderDeployment, validateHealthResponse } from "./policy.mjs";
import {
  createRenderDeployment,
  findRenderDeploymentForCommit,
  readRenderDeployment,
} from "./provider-api.mjs";

const SERVICE_ID = "srv-dba8q3rncjis73cl7to0";
const API_ORIGIN = "https://portfolio-api-gisk.onrender.com";

async function ensureMainTip(sha) {
  const response = await fetch(
    "https://api.github.com/repos/paulzwecker/portfolio-app/git/ref/heads/main",
    {
      headers: {
        Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      signal: AbortSignal.timeout(20_000),
    },
  );
  if (!response.ok)
    throw new Error(`github_main_recheck_failed:${response.status}`);
  const payload = await response.json();
  if (payload?.object?.sha?.toLowerCase() !== sha.toLowerCase()) {
    throw new Error("release_sha_no_longer_main_tip");
  }
}

function output(key, value) {
  if (process.env.GITHUB_OUTPUT)
    appendFileSync(process.env.GITHUB_OUTPUT, `${key}=${value}\n`);
}

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function main() {
  const token = process.env.RENDER_DEPLOY_TOKEN;
  const sha = process.env.RELEASE_SHA;
  if (!token || !sha || !/^[0-9a-f]{40}$/i.test(sha)) {
    throw new Error("render_deploy_inputs_invalid");
  }
  await ensureMainTip(sha);
  const prior = await findRenderDeploymentForCommit({
    token,
    serviceId: SERVICE_ID,
    releaseSha: sha,
  });
  let deployId = prior.deployment?.id;
  const reused = Boolean(deployId);
  if (reused) {
    console.log(
      "An exact-SHA Render deployment already exists; verifying and reusing it.",
    );
  } else {
    const created = await createRenderDeployment({
      token,
      serviceId: SERVICE_ID,
      releaseSha: sha,
    });
    deployId = created.deployId;
  }

  const deadline = Date.now() + 20 * 60_000;
  let state;
  while (Date.now() < deadline) {
    const payload = await readRenderDeployment({
      token,
      serviceId: SERVICE_ID,
      deployId,
    });
    state = payload?.deploy ?? payload;
    const error = validateRenderDeployment(state, sha);
    if (
      error === "render_deployment_failed" ||
      error === "render_deployment_commit_mismatch"
    ) {
      throw new Error(error);
    }
    if (
      reused &&
      ![
        "created",
        "queued",
        "build_in_progress",
        "pre_deploy_in_progress",
        "update_in_progress",
        "live",
      ].includes(state?.status)
    ) {
      throw new Error("render_existing_deployment_not_reusable");
    }
    if (!error) break;
    await delay(15_000);
  }
  if (state?.status !== "live") throw new Error("render_deployment_timeout");

  let health;
  const healthDeadline = Date.now() + 10 * 60_000;
  while (Date.now() < healthDeadline) {
    const response = await fetch(`${API_ORIGIN}/health/ready`, {
      headers: { Accept: "application/json" },
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    health = validateHealthResponse(response.status, payload);
    if (!health) break;
    await delay(15_000);
  }
  if (health) throw new Error(`render_readiness_failed:${health}`);

  output("render_deploy_id", deployId);
  output("render_deployed_sha", sha);
  output("render_deployment_reused", String(reused));
  console.log(
    `Render deployment ${deployId} is live for the approved release SHA and readiness is current (reused=${reused}).`,
  );
}

main().catch((error) => {
  console.error(
    error instanceof Error ? error.message : "render_deploy_failed:unknown",
  );
  process.exitCode = 1;
});
