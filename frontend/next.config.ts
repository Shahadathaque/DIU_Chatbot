import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep the public API settings available to the browser at build time. Vercel
  // supplies these values from the project's environment configuration.
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:8000",
    NEXT_PUBLIC_USE_MOCK_API:
      process.env.NEXT_PUBLIC_USE_MOCK_API?.trim() || "true",
  },
  // Keep Turbopack's project root inside the Vercel project when a parent
  // directory contains an unrelated lockfile.
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
