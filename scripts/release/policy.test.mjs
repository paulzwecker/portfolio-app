import assert from "node:assert/strict";
import test from "node:test";

import {
  EMPTY_BASELINE_NO_RECOVERY_CONFIRMATION,
  INITIAL_MIGRATION_CONFIRMATION,
  REQUIRED_CI_CHECKS,
  validateHealthResponse,
  validateOwnerApprovalEnvironment,
  validateReleaseApprovalInputs,
  validateReleaseIdentity,
  validateRenderDeployment,
  validateRenderService,
  validateSecretEnvironment,
  validateVercelDeployment,
  validateVercelProject,
} from "./policy.mjs";

const sha = "9f".repeat(20);
const greenRuns = REQUIRED_CI_CHECKS.map((name) => ({
  name,
  head_sha: sha,
  status: "completed",
  conclusion: "success",
  started_at: "2026-11-03T09:00:00Z",
}));

test("release identity requires the current main tip and green CI on that exact SHA", () => {
  assert.deepEqual(
    validateReleaseIdentity({
      eventRef: "refs/heads/main",
      eventSha: sha,
      requestedSha: sha,
      mainSha: sha,
      checkRuns: greenRuns,
      eventActorId: "123",
      ownerId: 123,
    }),
    [],
  );
  assert.ok(
    validateReleaseIdentity({
      eventRef: "refs/heads/feature",
      eventSha: sha,
      requestedSha: sha,
      mainSha: sha,
      checkRuns: greenRuns,
      eventActorId: "123",
      ownerId: 123,
    }).includes("workflow_dispatch_must_use_main"),
  );
  assert.ok(
    validateReleaseIdentity({
      eventRef: "refs/heads/main",
      eventSha: sha,
      requestedSha: sha,
      mainSha: "ab".repeat(20),
      checkRuns: greenRuns,
      eventActorId: "123",
      ownerId: 123,
    }).includes("release_sha_must_be_current_main_tip"),
  );
  assert.ok(
    validateReleaseIdentity({
      eventRef: "refs/heads/main",
      eventSha: sha,
      requestedSha: sha,
      mainSha: sha,
      checkRuns: [
        ...greenRuns,
        {
          ...greenRuns[0],
          conclusion: "failure",
          started_at: "2026-11-03T10:00:00Z",
        },
      ],
      eventActorId: "123",
      ownerId: 123,
    }).includes(`required_check_not_green:${REQUIRED_CI_CHECKS[0]}`),
  );
  assert.ok(
    validateReleaseIdentity({
      eventRef: "refs/heads/main",
      eventSha: sha,
      requestedSha: sha,
      mainSha: sha,
      checkRuns: [...greenRuns, { ...greenRuns[0], started_at: "invalid" }],
      eventActorId: "123",
      ownerId: 123,
    }).includes(`required_check_timestamp_invalid:${REQUIRED_CI_CHECKS[0]}`),
  );
  assert.ok(
    validateReleaseIdentity({
      eventRef: "refs/heads/main",
      eventSha: sha,
      requestedSha: sha,
      mainSha: sha,
      checkRuns: greenRuns,
      eventActorId: "456",
      ownerId: 123,
    }).includes("workflow_dispatch_must_be_started_by_repository_owner"),
  );
});

test("single-owner approval requires the repository owner and permits owner self-approval", () => {
  const environment = {
    protection_rules: [
      { type: "branch_policy" },
      {
        type: "required_reviewers",
        prevent_self_review: false,
        reviewers: [{ type: "User", reviewer: { id: 123 } }],
      },
    ],
    deployment_branch_policy: {
      protected_branches: false,
      custom_branch_policies: true,
    },
  };
  const policies = { branch_policies: [{ type: "branch", name: "main" }] };
  assert.deepEqual(
    validateOwnerApprovalEnvironment({
      environment,
      branchPolicies: policies,
      ownerId: 123,
    }),
    [],
  );
  assert.ok(
    validateOwnerApprovalEnvironment({
      environment,
      branchPolicies: policies,
      ownerId: 456,
    }).includes("single_owner_approval_rule_mismatch"),
  );
  assert.ok(
    validateOwnerApprovalEnvironment({
      environment: {
        ...environment,
        protection_rules: [
          { type: "branch_policy" },
          { ...environment.protection_rules[1], prevent_self_review: true },
        ],
      },
      branchPolicies: policies,
      ownerId: 123,
    }).includes("single_owner_approval_rule_mismatch"),
  );
  assert.ok(
    validateOwnerApprovalEnvironment({
      environment: {
        ...environment,
        protection_rules: [
          { type: "branch_policy" },
          {
            ...environment.protection_rules[1],
            reviewers: [
              ...environment.protection_rules[1].reviewers,
              { type: "User", reviewer: { id: 456 } },
            ],
          },
        ],
      },
      branchPolicies: policies,
      ownerId: 123,
    }).includes("single_owner_approval_rule_mismatch"),
  );
  assert.ok(
    validateOwnerApprovalEnvironment({
      environment,
      branchPolicies: { branch_policies: [{ type: "branch", name: "*" }] },
      ownerId: 123,
    }).includes("environment_branch_policy_must_allow_main_only"),
  );
});

test("credential environments are main-only and add no second reviewer gate", () => {
  const environment = {
    protection_rules: [{ type: "branch_policy" }],
    deployment_branch_policy: {
      protected_branches: false,
      custom_branch_policies: true,
    },
  };
  const branchPolicies = {
    branch_policies: [{ type: "branch", name: "main" }],
  };
  assert.deepEqual(
    validateSecretEnvironment({ environment, branchPolicies }),
    [],
  );
  assert.ok(
    validateSecretEnvironment({
      environment: {
        ...environment,
        protection_rules: [
          { type: "branch_policy" },
          {
            type: "required_reviewers",
            prevent_self_review: false,
            reviewers: [{ type: "User", reviewer: { id: 123 } }],
          },
        ],
      },
      branchPolicies,
    }).includes("secret_environment_must_not_add_approval_gate"),
  );
  assert.ok(
    validateSecretEnvironment({
      environment,
      branchPolicies: { branch_policies: [{ type: "branch", name: "*" }] },
    }).includes("environment_branch_policy_must_allow_main_only"),
  );
});

test("release approval inputs must match the read-only migration and recovery plan", () => {
  assert.deepEqual(
    validateReleaseApprovalInputs({
      migrationRequired: "true",
      runMigrations: "true",
      recoveryRequired: "false",
      migrationConfirmation: INITIAL_MIGRATION_CONFIRMATION,
      emptyBaselineConfirmation: EMPTY_BASELINE_NO_RECOVERY_CONFIRMATION,
    }),
    [],
  );
  assert.deepEqual(
    validateReleaseApprovalInputs({
      migrationRequired: "true",
      runMigrations: "true",
      recoveryRequired: "true",
      migrationConfirmation: INITIAL_MIGRATION_CONFIRMATION,
      emptyBaselineConfirmation: "",
    }),
    [],
  );
  assert.deepEqual(
    validateReleaseApprovalInputs({
      migrationRequired: "false",
      runMigrations: "false",
      recoveryRequired: "false",
      migrationConfirmation: "",
      emptyBaselineConfirmation: "",
    }),
    [],
  );
  assert.ok(
    validateReleaseApprovalInputs({
      migrationRequired: "true",
      runMigrations: "false",
      recoveryRequired: "false",
      migrationConfirmation: INITIAL_MIGRATION_CONFIRMATION,
      emptyBaselineConfirmation: EMPTY_BASELINE_NO_RECOVERY_CONFIRMATION,
    }).includes("migration_checkbox_must_match_verified_schema"),
  );
  assert.ok(
    validateReleaseApprovalInputs({
      migrationRequired: "true",
      runMigrations: "true",
      recoveryRequired: "false",
      migrationConfirmation: INITIAL_MIGRATION_CONFIRMATION,
      emptyBaselineConfirmation: "",
    }).includes("empty_baseline_recovery_confirmation_required"),
  );
  assert.ok(
    validateReleaseApprovalInputs({
      migrationRequired: "true",
      runMigrations: "true",
      recoveryRequired: "true",
      migrationConfirmation: INITIAL_MIGRATION_CONFIRMATION,
      emptyBaselineConfirmation: EMPTY_BASELINE_NO_RECOVERY_CONFIRMATION,
    }).includes(
      "empty_baseline_confirmation_not_allowed_when_recovery_required",
    ),
  );
  assert.ok(
    validateReleaseApprovalInputs({
      migrationRequired: "unknown",
      runMigrations: "true",
      recoveryRequired: "false",
      migrationConfirmation: INITIAL_MIGRATION_CONFIRMATION,
      emptyBaselineConfirmation: EMPTY_BASELINE_NO_RECOVERY_CONFIRMATION,
    }).includes("migration_requirement_unavailable"),
  );
});

test("Render preflight rejects autodeploy, incorrect target TLS, and enabled ingestion", () => {
  const service = {
    id: "srv-dba8q3rncjis73cl7to0",
    name: "portfolio-api",
    type: "web_service",
    branch: "main",
    autoDeployTrigger: "off",
    autoDeploy: false,
    healthCheckPath: "/health/live",
    url: "https://portfolio-api.example.onrender.com",
  };
  const envRows = [
    { key: "APP_ENV", value: "production" },
    {
      key: "DATABASE_URL",
      value:
        "postgresql://user:test-password@db.example/neondb?sslmode=verify-full",
    },
    { key: "API_ACCESS_TOKEN", value: "x".repeat(40) },
    { key: "NEON_API_KEY", value: "x".repeat(40) },
    { key: "DATABASE_TARGET_ENVIRONMENT", value: "production" },
    { key: "DATABASE_TARGET_DATABASE", value: "neondb" },
    { key: "NEON_PROJECT_ID", value: "delicate-heart-04560404" },
    { key: "NEON_BRANCH_ID", value: "br-morning-truth-b96361yh" },
    { key: "NEON_ENDPOINT_ID", value: "ep-snowy-term-b9gr75j6" },
    { key: "DATABASE_PRODUCTION_WRITES_AUTHORIZED", value: "false" },
    { key: "DATABASE_REHEARSAL_WRITES_AUTHORIZED", value: "false" },
    { key: "CLOUD_INGESTION_ENABLED", value: "false" },
    { key: "RECURRING_OPERATIONS_ENABLED", value: "false" },
    { key: "MANUAL_OPERATIONS_ENABLED", value: "false" },
    { key: "WORKBOOK_SYNC_ENABLED", value: "false" },
    { key: "GOOGLE_SHEETS_POLL_SECONDS", value: "0" },
    { key: "FMP_CONSENSUS_INGESTION_ENABLED", value: "false" },
  ];
  assert.deepEqual(
    validateRenderService({
      service,
      envRows,
      expectedDatabaseHost: "db.example",
    }),
    [],
  );
  const errors = validateRenderService({
    service: { ...service, autoDeployTrigger: "commit" },
    envRows: envRows.map((row) =>
      row.key === "DATABASE_URL"
        ? {
            ...row,
            value:
              "postgresql://user:test-password@other.example/neondb?sslmode=require",
          }
        : row.key === "CLOUD_INGESTION_ENABLED"
          ? { ...row, value: "true" }
          : row,
    ),
    expectedDatabaseHost: "db.example",
  });
  assert.ok(errors.includes("render_auto_deploy_must_be_off"));
  assert.ok(errors.includes("render_database_target_mismatch"));
  assert.ok(errors.includes("render_database_tls_verification_required"));
  assert.ok(
    errors.includes(
      "render_operation_or_write_flag_invalid:CLOUD_INGESTION_ENABLED",
    ),
  );
  assert.ok(!JSON.stringify(errors).includes("test-password"));
  assert.ok(
    validateRenderService({
      service,
      envRows: envRows.filter((row) => row.key !== "MANUAL_OPERATIONS_ENABLED"),
      expectedDatabaseHost: "db.example",
    }).includes(
      "render_required_environment_variable_missing:MANUAL_OPERATIONS_ENABLED",
    ),
  );
  assert.ok(
    validateRenderService({
      service,
      envRows: envRows.map((row) =>
        row.key === "DATABASE_PRODUCTION_WRITES_AUTHORIZED"
          ? { ...row, value: "true" }
          : row,
      ),
      expectedDatabaseHost: "db.example",
    }).includes(
      "render_operation_or_write_flag_invalid:DATABASE_PRODUCTION_WRITES_AUTHORIZED",
    ),
  );
});

test("Vercel preflight protects main while preserving branch previews and production identity", () => {
  const project = {
    id: "prj_expected",
    name: "portfolio-research",
    rootDirectory: "apps/web",
    framework: "nextjs",
    link: {
      productionBranch: "main",
      repo: "portfolio-app",
      org: "paulzwecker",
    },
  };
  const envRows = [
    ...[
      "API_BASE_URL",
      "API_ACCESS_TOKEN",
      "WEB_ACCESS_USERNAME",
      "WEB_ACCESS_PASSWORD",
    ].map((key) => ({ key, target: ["production"] })),
    ...[
      "API_BASE_URL",
      "API_ACCESS_TOKEN",
      "WEB_ACCESS_USERNAME",
      "WEB_ACCESS_PASSWORD",
    ].map((key) => ({
      key,
      target: ["preview"],
      ...(key === "API_BASE_URL"
        ? { value: "https://portfolio-api-preview.onrender.com" }
        : {}),
    })),
  ];
  const valid = {
    project,
    domains: [{ name: "portfolio-research.example" }],
    envRows,
    expectedProjectId: "prj_expected",
    expectedDomain: "portfolio-research.example",
    expectedRepository: "paulzwecker/portfolio-app",
    productionApiOrigin: "https://portfolio-api.onrender.com",
    vercelConfig: { git: { deploymentEnabled: { main: false } } },
  };
  assert.deepEqual(validateVercelProject(valid), []);
  assert.ok(
    validateVercelProject({
      ...valid,
      vercelConfig: { git: { deploymentEnabled: { main: true } } },
      envRows: envRows.map((row) =>
        row.target.includes("preview") && row.key === "API_BASE_URL"
          ? { ...row, value: "https://portfolio-api.onrender.com" }
          : row,
      ),
    }).includes("vercel_preview_must_target_nonproduction_api"),
  );
  assert.ok(
    validateVercelProject({
      ...valid,
      project: { ...project, link: { ...project.link, org: "another-owner" } },
    }).includes("vercel_repository_mismatch"),
  );
  assert.ok(
    validateVercelProject({
      ...valid,
      vercelConfig: {
        git: { deploymentEnabled: { main: false, "*": false } },
      },
    }).includes("vercel_branch_previews_must_remain_enabled"),
  );
});

test("release deployment and health checks bind to the exact schema-ready release", () => {
  assert.equal(
    validateRenderDeployment({ status: "live", commit: { id: sha } }, sha),
    null,
  );
  assert.equal(
    validateRenderDeployment(
      { status: "live", commit: { id: "ab".repeat(20) } },
      sha,
    ),
    "render_deployment_commit_mismatch",
  );
  assert.equal(
    validateHealthResponse(
      200,
      { database: "connected", schema: "current", alembic_head: sha },
      sha,
    ),
    null,
  );
  assert.equal(
    validateHealthResponse(503, {}, sha),
    "api_readiness_http_failure",
  );
  assert.equal(
    validateRenderDeployment(
      { status: "build_failed", commit: { id: sha } },
      sha,
    ),
    "render_deployment_failed",
  );
  assert.equal(
    validateVercelDeployment(
      {
        projectId: "project",
        readyState: "READY",
        target: "production",
        meta: { releaseCommitSha: sha },
        alias: ["portfolio.example"],
      },
      {
        projectId: "project",
        releaseSha: sha,
        productionDomain: "portfolio.example",
      },
    ),
    null,
  );
  assert.equal(
    validateVercelDeployment(
      {
        projectId: "other",
        readyState: "READY",
        target: "production",
        meta: { releaseCommitSha: sha },
        alias: ["portfolio.example"],
      },
      {
        projectId: "project",
        releaseSha: sha,
        productionDomain: "portfolio.example",
      },
    ),
    "vercel_deployment_project_mismatch",
  );
  assert.equal(
    validateVercelDeployment(
      {
        projectId: "project",
        readyState: "ERROR",
        target: "production",
        meta: { releaseCommitSha: sha },
        alias: ["portfolio.example"],
      },
      {
        projectId: "project",
        releaseSha: sha,
        productionDomain: "portfolio.example",
      },
    ),
    "vercel_deployment_not_ready_production",
  );
});
