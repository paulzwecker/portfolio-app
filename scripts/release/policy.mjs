export const RELEASE_ENVIRONMENTS = Object.freeze([
  "production-readonly",
  "production-migration",
  "production-api",
  "production-web",
  "production-smoke",
]);

export const REQUIRED_CI_CHECKS = Object.freeze([
  "Quality, contracts and build",
  "PostgreSQL integration tests",
  "Windows migration command compatibility",
]);

export function validateReleaseIdentity({
  eventRef,
  eventSha,
  requestedSha,
  mainSha,
  checkRuns,
  requiredChecks = REQUIRED_CI_CHECKS,
}) {
  const errors = [];
  const shaPattern = /^[0-9a-f]{40}$/i;

  if (eventRef !== "refs/heads/main")
    errors.push("workflow_dispatch_must_use_main");
  if (!shaPattern.test(requestedSha ?? "")) errors.push("release_sha_invalid");
  if (requestedSha?.toLowerCase() !== eventSha?.toLowerCase()) {
    errors.push("release_sha_must_match_dispatch_commit");
  }
  if (requestedSha?.toLowerCase() !== mainSha?.toLowerCase()) {
    errors.push("release_sha_must_be_current_main_tip");
  }

  const latest = new Map();
  const invalidCheckTimestamps = new Set();
  for (const run of checkRuns ?? []) {
    if (run.head_sha?.toLowerCase() !== requestedSha?.toLowerCase()) continue;
    const startedAt = Date.parse(run.started_at ?? "");
    if (!Number.isFinite(startedAt)) {
      invalidCheckTimestamps.add(run.name);
      continue;
    }
    const current = latest.get(run.name);
    if (!current || startedAt >= Date.parse(current.started_at)) {
      latest.set(run.name, run);
    }
  }
  for (const name of requiredChecks) {
    const run = latest.get(name);
    if (invalidCheckTimestamps.has(name))
      errors.push(`required_check_timestamp_invalid:${name}`);
    else if (!run) errors.push(`required_check_missing:${name}`);
    else if (run.status !== "completed" || run.conclusion !== "success") {
      errors.push(`required_check_not_green:${name}`);
    }
  }
  return errors;
}

export function validateProtectedEnvironment({
  environment,
  branchPolicies,
  reviewerIds,
}) {
  const errors = [];
  const rules = environment?.protection_rules;
  const expected = new Set((reviewerIds ?? []).map(String));
  if (!Array.isArray(rules))
    errors.push("environment_protection_rules_missing");
  if (expected.size === 0 || [...expected].some((id) => !/^\d+$/.test(id))) {
    errors.push("release_reviewer_allowlist_missing");
  }

  const reviewerRule = rules?.find(
    (rule) => rule.type === "required_reviewers",
  );
  const configuredReviewers = reviewerRule?.reviewers ?? [];
  const actualReviewers = new Set(
    configuredReviewers.map((reviewer) =>
      String(reviewer.reviewer?.id ?? reviewer.id),
    ),
  );
  if (
    !reviewerRule ||
    reviewerRule.prevent_self_review !== true ||
    actualReviewers.size === 0 ||
    [...actualReviewers].some((id) => !expected.has(id))
  ) {
    errors.push("required_release_reviewer_not_configured");
  }

  const deploymentPolicy = environment?.deployment_branch_policy;
  if (
    deploymentPolicy?.protected_branches !== false ||
    deploymentPolicy?.custom_branch_policies !== true
  ) {
    errors.push("environment_branch_policy_must_allow_main_only");
  }
  const policies = branchPolicies?.branch_policies;
  if (
    !Array.isArray(policies) ||
    policies.length !== 1 ||
    policies[0]?.type !== "branch" ||
    policies[0]?.name !== "main"
  ) {
    errors.push("environment_branch_policy_must_allow_main_only");
  }
  return errors;
}

function envVarMap(rows) {
  const result = new Map();
  for (const row of rows ?? []) {
    const item = row?.envVar ?? row;
    if (typeof item?.key === "string") result.set(item.key, item.value);
  }
  return result;
}

export function validateRenderService({
  service,
  envRows,
  expectedDatabaseHost,
}) {
  const errors = [];
  const env = envVarMap(envRows);
  if (service?.id !== "srv-dba8q3rncjis73cl7to0")
    errors.push("render_service_identity_mismatch");
  if (service?.name !== "portfolio-api" || service?.type !== "web_service") {
    errors.push("render_service_identity_mismatch");
  }
  if (service?.branch !== "main") errors.push("render_branch_mismatch");
  if (service?.autoDeployTrigger !== "off")
    errors.push("render_auto_deploy_must_be_off");
  if (
    service?.autoDeploy !== undefined &&
    service.autoDeploy !== false &&
    service.autoDeploy !== "no"
  ) {
    errors.push("render_auto_deploy_must_be_off");
  }
  if (service?.healthCheckPath !== "/health/live")
    errors.push("render_health_check_mismatch");
  if (typeof service?.url !== "string" || !service.url.startsWith("https://")) {
    errors.push("render_service_https_url_missing");
  }

  if (env.get("APP_ENV") !== "production")
    errors.push("render_app_env_mismatch");
  const databaseUrl = env.get("DATABASE_URL");
  try {
    const url = new URL(databaseUrl);
    if (url.protocol !== "postgresql:")
      errors.push("render_database_url_invalid");
    if (url.hostname !== expectedDatabaseHost)
      errors.push("render_database_target_mismatch");
    if (url.searchParams.get("sslmode") !== "verify-full") {
      errors.push("render_database_tls_verification_required");
    }
    if (url.hostname.includes("-pooler."))
      errors.push("render_database_pooler_rejected");
    if (url.pathname.replace(/^\//, "") !== "neondb")
      errors.push("render_database_target_mismatch");
  } catch {
    errors.push("render_database_url_unavailable_or_invalid");
  }
  if (
    typeof env.get("API_ACCESS_TOKEN") !== "string" ||
    env.get("API_ACCESS_TOKEN").length < 32
  ) {
    errors.push("render_api_token_missing");
  }
  if (
    typeof env.get("NEON_API_KEY") !== "string" ||
    env.get("NEON_API_KEY").length < 20
  ) {
    errors.push("render_neon_identity_credential_missing");
  }
  for (const [key, expected] of [
    ["DATABASE_TARGET_ENVIRONMENT", "production"],
    ["DATABASE_TARGET_DATABASE", "neondb"],
    ["NEON_PROJECT_ID", "delicate-heart-04560404"],
    ["NEON_BRANCH_ID", "br-morning-truth-b96361yh"],
    ["NEON_ENDPOINT_ID", "ep-snowy-term-b9gr75j6"],
  ]) {
    if (env.get(key) !== expected) {
      errors.push(`render_database_identity_mismatch:${key}`);
    }
  }
  for (const [key, expected] of [
    ["DATABASE_PRODUCTION_WRITES_AUTHORIZED", "false"],
    ["DATABASE_REHEARSAL_WRITES_AUTHORIZED", "false"],
    ["CLOUD_INGESTION_ENABLED", "false"],
    ["RECURRING_OPERATIONS_ENABLED", "false"],
    ["MANUAL_OPERATIONS_ENABLED", "false"],
    ["WORKBOOK_SYNC_ENABLED", "false"],
    ["GOOGLE_SHEETS_POLL_SECONDS", "0"],
    ["FMP_CONSENSUS_INGESTION_ENABLED", "false"],
  ]) {
    const value = env.get(key);
    if (value === undefined) {
      errors.push(`render_required_environment_variable_missing:${key}`);
    } else if (String(value).toLowerCase() !== expected) {
      errors.push(`render_operation_or_write_flag_invalid:${key}`);
    }
  }
  return errors;
}

export function validateVercelProject({
  project,
  domains,
  envRows,
  vercelConfig,
  expectedProjectId,
  expectedDomain,
  expectedRepository,
  productionApiOrigin,
}) {
  const errors = [];
  if (project?.id !== expectedProjectId)
    errors.push("vercel_project_identity_mismatch");
  if (project?.name !== "portfolio-research")
    errors.push("vercel_project_identity_mismatch");
  if (project?.rootDirectory !== "apps/web")
    errors.push("vercel_root_directory_mismatch");
  if (project?.framework !== "nextjs") errors.push("vercel_framework_mismatch");
  const productionBranch =
    project?.link?.productionBranch ??
    project?.productionBranch ??
    project?.git?.productionBranch;
  if (productionBranch !== "main")
    errors.push("vercel_production_branch_mismatch");
  if (!domains?.some((item) => item.name === expectedDomain)) {
    errors.push("vercel_production_domain_missing");
  }
  if (vercelConfig?.git?.deploymentEnabled?.main !== false) {
    errors.push("vercel_main_auto_deploy_must_be_off");
  }
  const gitDeploymentRules = vercelConfig?.git?.deploymentEnabled;
  if (
    !gitDeploymentRules ||
    Object.keys(gitDeploymentRules).length !== 1 ||
    !Object.hasOwn(gitDeploymentRules, "main")
  ) {
    errors.push("vercel_branch_previews_must_remain_enabled");
  }
  const link = project?.link ?? project?.gitRepository ?? project?.git;
  const repo = link?.repo ?? link?.repository;
  const owner = link?.org ?? link?.owner ?? link?.repoOwner ?? link?.orgName;
  const repository =
    typeof repo === "string" && repo.includes("/")
      ? repo
      : typeof repo === "string" && typeof owner === "string"
        ? `${owner}/${repo}`
        : undefined;
  if (
    !expectedRepository ||
    repository?.toLowerCase() !== expectedRepository.toLowerCase()
  ) {
    errors.push("vercel_repository_mismatch");
  }

  const productionKeys = new Set();
  const previewKeys = new Set();
  let previewApiBaseUrl;
  for (const row of envRows ?? []) {
    if (row.target === "production") productionKeys.add(row.key);
    if (Array.isArray(row.target) && row.target.includes("production"))
      productionKeys.add(row.key);
    if (
      row.target === "preview" ||
      (Array.isArray(row.target) && row.target.includes("preview"))
    ) {
      previewKeys.add(row.key);
      if (row.key === "API_BASE_URL" && typeof row.value === "string") {
        previewApiBaseUrl = row.value;
      }
    }
  }
  for (const key of [
    "API_BASE_URL",
    "API_ACCESS_TOKEN",
    "WEB_ACCESS_USERNAME",
    "WEB_ACCESS_PASSWORD",
  ]) {
    if (!productionKeys.has(key))
      errors.push(`vercel_production_environment_variable_missing:${key}`);
  }
  for (const key of [
    "API_BASE_URL",
    "API_ACCESS_TOKEN",
    "WEB_ACCESS_USERNAME",
    "WEB_ACCESS_PASSWORD",
  ]) {
    if (!previewKeys.has(key))
      errors.push(`vercel_preview_environment_variable_missing:${key}`);
  }
  try {
    const previewUrl = new URL(previewApiBaseUrl);
    const productionUrl = new URL(productionApiOrigin);
    if (
      previewUrl.protocol !== "https:" ||
      previewUrl.origin === productionUrl.origin
    ) {
      errors.push("vercel_preview_must_target_nonproduction_api");
    }
  } catch {
    errors.push("vercel_preview_api_base_url_invalid");
  }
  return errors;
}

export function validateRenderDeployment(deploy, expectedSha) {
  const value = deploy?.deploy ?? deploy;
  if (value?.commit?.id?.toLowerCase() !== expectedSha.toLowerCase()) {
    return "render_deployment_commit_mismatch";
  }
  if (
    ["build_failed", "update_failed", "canceled", "pre_deploy_failed"].includes(
      value?.status,
    )
  ) {
    return "render_deployment_failed";
  }
  return value?.status === "live" ? null : "render_deployment_not_live";
}

export function validateVercelDeployment(
  payload,
  { projectId, releaseSha, productionDomain },
) {
  const deployment = payload?.deployment ?? payload;
  if (deployment?.projectId !== projectId)
    return "vercel_deployment_project_mismatch";
  if (
    deployment?.readyState !== "READY" ||
    deployment?.target !== "production"
  ) {
    return "vercel_deployment_not_ready_production";
  }
  if (
    deployment?.meta?.releaseCommitSha?.toLowerCase() !==
    releaseSha.toLowerCase()
  ) {
    return "vercel_deployment_commit_mismatch";
  }
  const aliases = deployment?.alias;
  if (!Array.isArray(aliases) || !aliases.includes(productionDomain)) {
    return "vercel_production_domain_not_assigned";
  }
  return null;
}

export function validateHealthResponse(status, payload, expectedHead) {
  if (status !== 200) return "api_readiness_http_failure";
  if (payload?.database !== "connected" || payload?.schema !== "current") {
    return "api_readiness_state_mismatch";
  }
  if (expectedHead && payload?.alembic_head !== expectedHead)
    return "api_readiness_revision_mismatch";
  return null;
}
