import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The backend allows both http://localhost:3000 and http://127.0.0.1:3000 (CORS), so let the dev server serve both.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Next 16 can write an AGENTS.md into the project root; this project documents itself in README.md instead.
  agentRules: false,
  // Pin the workspace root so Next never walks up into sibling projects (scholarpath-frontend / -backend / -data).
  turbopack: { root: projectRoot },
};

export default nextConfig;
