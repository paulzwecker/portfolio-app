import { validateReleaseApprovalInputs } from "./policy.mjs";

const errors = validateReleaseApprovalInputs({
  migrationRequired: process.env.MIGRATION_REQUIRED,
  runMigrations: process.env.RUN_MIGRATIONS,
  recoveryRequired: process.env.RECOVERY_REQUIRED,
  migrationConfirmation: process.env.MIGRATION_CONFIRMATION ?? "",
  emptyBaselineConfirmation:
    process.env.EMPTY_BASELINE_NO_RECOVERY_CONFIRMATION ?? "",
});

if (errors.length) {
  console.error(`release_plan_invalid:${errors.join(",")}`);
  process.exitCode = 1;
} else {
  console.log("Release inputs match the verified schema and recovery plan.");
}
