import assert from "node:assert/strict";
import test from "node:test";

import {
  createRenderDeployment,
  findRenderDeploymentForCommit,
  findVercelDeploymentForCommit,
  readRenderDeployment,
  readVercelDeployment,
} from "./provider-api.mjs";

const releaseSha = "9f".repeat(20);

test("Render deploy request pins the exact commit and never clears the build cache", async () => {
  let request;
  const result = await createRenderDeployment({
    token: "private-token",
    serviceId: "service-1",
    releaseSha,
    fetchImpl: async (url, options) => {
      request = { url, options };
      return Response.json({
        id: "deploy-1",
        status: "created",
        commit: { id: releaseSha },
      });
    },
  });
  assert.equal(result.deployId, "deploy-1");
  assert.equal(
    request.url,
    "https://api.render.com/v1/services/service-1/deploys",
  );
  assert.equal(request.options.method, "POST");
  assert.deepEqual(JSON.parse(request.options.body), {
    commitId: releaseSha,
    clearCache: "do_not_clear",
  });
  assert.equal(request.options.headers.Authorization, "Bearer private-token");
});

test("Render create response with an unexpected SHA is rejected", async () => {
  await assert.rejects(
    createRenderDeployment({
      token: "private-token",
      serviceId: "service-1",
      releaseSha,
      fetchImpl: async () =>
        Response.json({ id: "deploy-1", commit: { id: "ab".repeat(20) } }),
    }),
    /render_deployment_commit_mismatch/,
  );
});

test("Render exact-SHA lookup finds a prior deployment before any create call", async () => {
  let request;
  const result = await findRenderDeploymentForCommit({
    token: "render-read-token",
    serviceId: "service-1",
    releaseSha,
    fetchImpl: async (url, options) => {
      request = { url, options };
      return Response.json([
        {
          deploy: {
            id: "deploy-existing",
            status: "live",
            commit: { id: releaseSha },
          },
          cursor: "next-page",
        },
      ]);
    },
  });
  assert.equal(result.deployment.id, "deploy-existing");
  const url = new URL(request.url);
  assert.equal(url.pathname, "/v1/services/service-1/deploys");
  assert.equal(url.searchParams.get("limit"), "100");
  assert.equal(request.options.method, undefined);
});

test("Render exact-SHA lookup uses bounded cursor pages and fails closed when truncated", async () => {
  const requests = [];
  const found = await findRenderDeploymentForCommit({
    token: "render-read-token",
    serviceId: "service-1",
    releaseSha,
    fetchImpl: async (url) => {
      requests.push(new URL(url));
      if (requests.length === 1) {
        return Response.json([
          {
            deploy: {
              id: "deploy-other",
              commit: { id: "ab".repeat(20) },
            },
            cursor: "cursor-2",
          },
        ]);
      }
      return Response.json([
        {
          deploy: { id: "deploy-existing", commit: { id: releaseSha } },
          cursor: "cursor-3",
        },
      ]);
    },
  });
  assert.equal(found.deployment.id, "deploy-existing");
  assert.equal(requests[1].searchParams.get("cursor"), "cursor-2");

  await assert.rejects(
    findRenderDeploymentForCommit({
      token: "render-read-token",
      serviceId: "service-1",
      releaseSha,
      maxPages: 1,
      fetchImpl: async () =>
        Response.json([
          {
            deploy: { id: "deploy-other", commit: { id: "ab".repeat(20) } },
            cursor: "more",
          },
        ]),
    }),
    /render_deploy_duplicate_scan_incomplete/,
  );
});

test("Vercel exact-SHA lookup scopes production history to the configured project", async () => {
  let request;
  const result = await findVercelDeploymentForCommit({
    token: "vercel-read-token",
    projectId: "project-1",
    teamId: "team-1",
    releaseSha,
    fetchImpl: async (url, options) => {
      request = { url, options };
      return Response.json({
        deployments: [
          {
            uid: "deployment-existing",
            projectId: "project-1",
            target: "production",
            meta: { releaseCommitSha: releaseSha },
          },
        ],
        pagination: { next: null },
      });
    },
  });
  assert.equal(result.idOrUrl, "deployment-existing");
  const url = new URL(request.url);
  assert.equal(url.pathname, "/v7/deployments");
  assert.equal(url.searchParams.get("projectId"), "project-1");
  assert.equal(url.searchParams.get("target"), "production");
  assert.equal(url.searchParams.get("teamId"), "team-1");
  assert.equal(request.options.method, undefined);
});

test("Vercel exact-SHA lookup paginates and rejects an incomplete bounded scan", async () => {
  const requests = [];
  const found = await findVercelDeploymentForCommit({
    token: "vercel-read-token",
    projectId: "project-1",
    teamId: "team-1",
    releaseSha,
    fetchImpl: async (url) => {
      requests.push(new URL(url));
      if (requests.length === 1) {
        return Response.json({
          deployments: [],
          pagination: { next: 123456 },
        });
      }
      return Response.json({
        deployments: [
          {
            id: "deployment-existing",
            projectId: "project-1",
            target: "production",
            meta: { releaseCommitSha: releaseSha },
          },
        ],
        pagination: { next: null },
      });
    },
  });
  assert.equal(found.idOrUrl, "deployment-existing");
  assert.equal(requests[1].searchParams.get("until"), "123456");

  await assert.rejects(
    findVercelDeploymentForCommit({
      token: "vercel-read-token",
      projectId: "project-1",
      teamId: "team-1",
      releaseSha,
      maxPages: 1,
      fetchImpl: async () =>
        Response.json({ deployments: [], pagination: { next: 123456 } }),
    }),
    /vercel_deploy_duplicate_scan_incomplete/,
  );
});

test("provider read clients use the narrow selected service and deployment", async () => {
  const requests = [];
  const fetchImpl = async (url, options) => {
    requests.push({ url, options });
    return Response.json({ status: "live" });
  };
  await readRenderDeployment({
    fetchImpl,
    token: "render-read-token",
    serviceId: "service-1",
    deployId: "deploy-2",
  });
  await readVercelDeployment({
    fetchImpl,
    token: "vercel-read-token",
    deploymentUrl: "portfolio-abc.vercel.app",
    teamId: "team-1",
  });
  assert.equal(
    requests[0].url,
    "https://api.render.com/v1/services/service-1/deploys/deploy-2",
  );
  assert.match(
    requests[1].url,
    /^https:\/\/api\.vercel\.com\/v13\/deployments\/portfolio-abc\.vercel\.app\?/,
  );
  assert.equal(new URL(requests[1].url).searchParams.get("teamId"), "team-1");
});

test("provider failures are reduced to status codes and do not echo response bodies", async () => {
  await assert.rejects(
    readVercelDeployment({
      token: "secret-token",
      deploymentUrl: "example.vercel.app",
      teamId: "team-1",
      fetchImpl: async () =>
        new Response("secret response payload", { status: 403 }),
    }),
    (error) => {
      assert.match(error.message, /vercel_request_failed:403/);
      assert.doesNotMatch(error.message, /secret/);
      return true;
    },
  );
});
