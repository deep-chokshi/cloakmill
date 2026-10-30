import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  typedRoutes: true,
  productionBrowserSourceMaps: false,
  // Protected pages use dynamic rendering and nonce CSP. No shared data cache.
  experimental: { serverActions: { bodySizeLimit: "16kb" } },
};
export default config;
