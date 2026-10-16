import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for a slim Cloud Run image (free-tier Artifact Registry).
  // Enabled only in the container build: on Windows it needs symlink rights (Developer Mode).
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
