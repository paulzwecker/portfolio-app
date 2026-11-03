import { appendFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { validateVercelDeployment } from "./policy.mjs";
import {
  findVercelDeploymentForCommit,
  readVercelDeployment,
} from "./provider-api.mjs";

function runCli(args, cwd) {
  const cli = process.env.VERCEL_CLI_PATH;
  if (!cli) throw new Error("vercel_cli_not_preinstalled");
  const result = spawnSync(cli, [...args, "--cwd", cwd], {
    cwd: process.cwd(),
    encoding: "utf8",
    windowsHide: true,
    env: {
      PATH: process.env.PATH,
      HOME: process.env.HOME,
      CI: "1",
      VERCEL_TOKEN: process.env.VERCEL_TOKEN,
      VERCEL_PROJECT_ID: process.env.VERCEL_PROJECT_ID,
      VERCEL_ORG_ID: process.env.VERCEL_ORG_ID,
      VERCEL_TELEMETRY_DISABLED: "1",
    },
    maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error || result.status !== 0)
    throw new Error("vercel_cli_step_failed");
  return result.stdout;
}

function setOutput(name, value) {
  if (process.env.GITHUB_OUTPUT)
    appendFileSync(process.env.GITHUB_OUTPUT, `${name}=${value}\n`);
}

async function main() {
  const token = process.env.VERCEL_TOKEN;
  const project = process.env.VERCEL_PROJECT_ID;
  const org = process.env.VERCEL_ORG_ID;
  const domain = process.env.VERCEL_PRODUCTION_DOMAIN;
  const sha = process.env.RELEASE_SHA;
  if (
    !token ||
    !project ||
    !org ||
    !domain ||
    !/^[0-9a-f]{40}$/i.test(sha ?? "")
  ) {
    throw new Error("vercel_deploy_inputs_invalid");
  }
  await ensureMainTip(sha);

  let prior = await findVercelDeploymentForCommit({
    token,
    projectId: project,
    teamId: org,
    releaseSha: sha,
  });
  let idOrUrl = prior.idOrUrl;
  const reused = Boolean(idOrUrl);
  if (!reused) {
    await ensureMainTip(sha);
    const cliOutput = runCli(
      [
        "deploy",
        "--prebuilt",
        "--prod",
        "--yes",
        "--meta",
        `releaseCommitSha=${sha}`,
      ],
      "apps/web",
    );
    const deploymentUrl = cliOutput.match(
      /https:\/\/[a-zA-Z0-9.-]+\.vercel\.app/,
    )?.[0];
    if (!deploymentUrl) throw new Error("vercel_deployment_url_missing");
    idOrUrl = deploymentUrl.replace(/^https:\/\//, "");
  } else {
    console.log(
      "An exact-SHA Vercel production deployment already exists; verifying and reusing it.",
    );
  }

  const deadline = Date.now() + 20 * 60_000;
  let deployment;
  while (Date.now() < deadline) {
    deployment = await readVercelDeployment({
      deploymentUrl: idOrUrl,
      token,
      teamId: org,
    });
    const error = validateVercelDeployment(deployment, {
      projectId: project,
      releaseSha: sha,
      productionDomain: domain,
    });
    if (
      error === "vercel_deployment_project_mismatch" ||
      error === "vercel_deployment_commit_mismatch"
    ) {
      throw new Error(error);
    }
    if (deployment?.readyState === "READY" && error) {
      if (reused) throw new Error("vercel_existing_deployment_not_current");
      if (error !== "vercel_production_domain_not_assigned") {
        throw new Error(error);
      }
    }
    if (["ERROR", "CANCELED", "BLOCKED"].includes(deployment?.readyState)) {
      throw new Error("vercel_deployment_failed");
    }
    if (!error) break;
    await new Promise((resolve) => setTimeout(resolve, 15_000));
  }
  const error = validateVercelDeployment(deployment, {
    projectId: project,
    releaseSha: sha,
    productionDomain: domain,
  });
  if (error) throw new Error("vercel_deployment_timeout_or_invalid");

  setOutput("vercel_deployment_id", deployment.id);
  setOutput("vercel_deployed_sha", sha);
  setOutput("vercel_deployment_reused", String(reused));
  console.log(
    `Vercel deployment ${deployment.id} is READY for the exact release SHA and production domain (reused=${reused}).`,
  );
}

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

main().catch((error) => {
  console.error(
    error instanceof Error ? error.message : "vercel_deploy_failed:unknown",
  );
  process.exitCode = 1;
});
