import type { components } from "@portfolio/contracts";

export type HealthResponse = components["schemas"]["HealthResponse"];

/** Validate untrusted JSON before displaying a successful connection. */
export function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) return false;
  const health = value as Record<string, unknown>;
  if (
    (health.status !== "ok" && health.status !== "error") ||
    (health.database !== "connected" && health.database !== "unavailable") ||
    (health.schema !== "current" &&
      health.schema !== "outdated" &&
      health.schema !== "unavailable") ||
    typeof health.checked_at !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(health.checked_at) ||
    !Number.isFinite(Date.parse(health.checked_at))
  ) {
    return false;
  }
  const ready = health.database === "connected" && health.schema === "current";
  return (health.status === "ok") === ready;
}

export async function fetchHealth(
  signal: AbortSignal,
): Promise<HealthResponse> {
  const response = await fetch("/api/health", { cache: "no-store", signal });
  const payload: unknown = await response.json();
  if (
    !isHealthResponse(payload) ||
    (payload.status === "ok"
      ? response.status !== 200
      : response.status !== 503)
  ) {
    throw new Error("Service status is unavailable.");
  }
  return payload;
}
