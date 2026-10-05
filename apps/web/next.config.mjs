import nextEnv from "@next/env";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
nextEnv.loadEnvConfig(repositoryRoot);

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Repository instructions live in the root AGENTS.md, not generated files.
  agentRules: false,
  poweredByHeader: false,
  // The build script runs `next typegen` and `tsc --noEmit` first. Skip Next's
  // duplicate process-based checker, which cannot start in restricted Windows
  // environments.
  typescript: { ignoreBuildErrors: true },
  experimental: { workerThreads: true, cpus: 1 },
  turbopack: { root: repositoryRoot },
};

export default nextConfig;
