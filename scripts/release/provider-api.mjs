const renderApi = "https://api.render.com/v1";
const vercelApi = "https://api.vercel.com";

async function readJson(response, provider) {
  if (!response.ok)
    throw new Error(`${provider}_request_failed:${response.status}`);
  try {
    return await response.json();
  } catch {
    throw new Error(`${provider}_response_invalid_json`);
  }
}

export async function createRenderDeployment({
  fetchImpl = fetch,
  token,
  serviceId,
  releaseSha,
}) {
  if (!token || !serviceId || !/^[0-9a-f]{40}$/i.test(releaseSha ?? "")) {
    throw new Error("render_deploy_inputs_invalid");
  }
  const response = await fetchImpl(
    `${renderApi}/services/${encodeURIComponent(serviceId)}/deploys`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        commitId: releaseSha,
        clearCache: "do_not_clear",
      }),
      signal: AbortSignal.timeout(20_000),
    },
  );
  const payload = await readJson(response, "render");
  const deployment = payload?.deploy ?? payload;
  if (typeof deployment?.id !== "string" || !deployment.id) {
    throw new Error("render_deploy_id_missing");
  }
  if (
    deployment.commit?.id &&
    deployment.commit.id.toLowerCase() !== releaseSha.toLowerCase()
  ) {
    throw new Error("render_deployment_commit_mismatch");
  }
  return { deployId: deployment.id, deployment };
}

export async function findRenderDeploymentForCommit({
  fetchImpl = fetch,
  token,
  serviceId,
  releaseSha,
  maxPages = 5,
}) {
  if (!token || !serviceId || !/^[0-9a-f]{40}$/i.test(releaseSha ?? "")) {
    throw new Error("render_deploy_inputs_invalid");
  }
  let cursor;
  const cursors = new Set();
  for (let page = 0; page < maxPages; page += 1) {
    const query = new URLSearchParams({ limit: "100" });
    if (cursor) query.set("cursor", cursor);
    const response = await fetchImpl(
      `${renderApi}/services/${encodeURIComponent(serviceId)}/deploys?${query}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
        signal: AbortSignal.timeout(20_000),
      },
    );
    const payload = await readJson(response, "render");
    if (!Array.isArray(payload)) {
      throw new Error("render_deploy_list_response_invalid");
    }
    for (const row of payload) {
      const deployment = row?.deploy ?? row;
      if (typeof deployment?.id !== "string" || !deployment.id) {
        throw new Error("render_deploy_list_response_invalid");
      }
      if (deployment?.commit?.id?.toLowerCase() === releaseSha.toLowerCase()) {
        return { deployment };
      }
    }
    const nextCursor = payload.at(-1)?.cursor;
    if (typeof nextCursor !== "string" || !nextCursor) {
      if (payload.length === 100) {
        throw new Error("render_deploy_list_response_truncated");
      }
      return { deployment: null };
    }
    if (cursors.has(nextCursor)) {
      throw new Error("render_deploy_list_cursor_repeated");
    }
    cursors.add(nextCursor);
    cursor = nextCursor;
  }
  throw new Error("render_deploy_duplicate_scan_incomplete");
}

export async function readRenderDeployment({
  fetchImpl = fetch,
  token,
  serviceId,
  deployId,
}) {
  const response = await fetchImpl(
    `${renderApi}/services/${encodeURIComponent(serviceId)}/deploys/${encodeURIComponent(deployId)}`,
    {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      signal: AbortSignal.timeout(20_000),
    },
  );
  return readJson(response, "render");
}

export async function readVercelDeployment({
  fetchImpl = fetch,
  token,
  deploymentUrl,
  teamId,
}) {
  const query = new URLSearchParams({ teamId });
  const endpoint = `${vercelApi}/v13/deployments/${encodeURIComponent(deploymentUrl)}?${query}`;
  const response = await fetchImpl(endpoint, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    signal: AbortSignal.timeout(20_000),
  });
  return readJson(response, "vercel");
}

export async function findVercelDeploymentForCommit({
  fetchImpl = fetch,
  token,
  projectId,
  teamId,
  releaseSha,
  maxPages = 5,
}) {
  if (
    !token ||
    !projectId ||
    !teamId ||
    !/^[0-9a-f]{40}$/i.test(releaseSha ?? "")
  ) {
    throw new Error("vercel_deploy_inputs_invalid");
  }
  let until;
  const timestamps = new Set();
  for (let page = 0; page < maxPages; page += 1) {
    const query = new URLSearchParams({
      projectId,
      target: "production",
      limit: "100",
      teamId,
    });
    if (until) query.set("until", until);
    const response = await fetchImpl(`${vercelApi}/v7/deployments?${query}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      signal: AbortSignal.timeout(20_000),
    });
    const payload = await readJson(response, "vercel");
    if (!Array.isArray(payload?.deployments)) {
      throw new Error("vercel_deploy_list_response_invalid");
    }
    if (
      payload.deployments.some(
        (item) =>
          item?.projectId !== projectId || item?.target !== "production",
      )
    ) {
      throw new Error("vercel_deploy_list_scope_mismatch");
    }
    const deployment = payload.deployments.find(
      (item) =>
        item?.projectId === projectId &&
        item?.target === "production" &&
        item?.meta?.releaseCommitSha?.toLowerCase() ===
          releaseSha.toLowerCase(),
    );
    if (deployment) {
      const idOrUrl = deployment.uid ?? deployment.id ?? deployment.url;
      if (typeof idOrUrl !== "string" || !idOrUrl) {
        throw new Error("vercel_existing_deploy_id_missing");
      }
      return { deployment, idOrUrl };
    }
    const next = payload.pagination?.next;
    if (next === undefined || next === null || next === "") {
      if (payload.deployments.length === 100) {
        throw new Error("vercel_deploy_list_response_truncated");
      }
      return { deployment: null, idOrUrl: null };
    }
    const nextCursor = String(next);
    if (timestamps.has(nextCursor)) {
      throw new Error("vercel_deploy_list_cursor_repeated");
    }
    timestamps.add(nextCursor);
    until = nextCursor;
  }
  throw new Error("vercel_deploy_duplicate_scan_incomplete");
}
