import { existsSync, rmSync } from "node:fs";
import path from "node:path";

export function productionEnvironmentCachePath(projectRoot) {
  return path.join(projectRoot, ".vercel", ".env.production.local");
}

export function scrubProductionEnvironmentCache(projectRoot) {
  const file = productionEnvironmentCachePath(projectRoot);
  if (existsSync(file)) rmSync(file);
  if (existsSync(file)) throw new Error("vercel_production_env_cache_present");
}

export function assertProductionEnvironmentCacheAbsent(projectRoot) {
  if (existsSync(productionEnvironmentCachePath(projectRoot))) {
    throw new Error("vercel_production_env_cache_present");
  }
}
