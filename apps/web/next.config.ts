import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Revision Prompt 16, task: Dockerfiles + docker-compose + deployment
  // docs — a standalone build bundles only the production dependency
  // subset Next.js's own trace actually needs into `.next/standalone`,
  // instead of shipping the full `node_modules` into the runtime image.
  output: "standalone",
};

export default nextConfig;
