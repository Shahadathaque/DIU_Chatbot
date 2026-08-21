import type { NextConfig } from "next";
import { resolvePublicFrontendConfig } from "./config/public-env";

const publicConfig = resolvePublicFrontendConfig(process.env);

const nextConfig: NextConfig = {
  // Keep the public API settings available to the browser at build time. Vercel
  // supplies these values from the project's environment configuration.
  env: {
    NEXT_PUBLIC_API_URL:
      publicConfig.apiUrl,
    NEXT_PUBLIC_USE_MOCK_API: publicConfig.useMockApi,
  },
  // Keep Turbopack's project root inside the Vercel project when a parent
  // directory contains an unrelated lockfile.
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
