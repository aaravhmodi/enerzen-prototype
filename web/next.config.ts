import type { NextConfig } from "next";

// Self-hosted (see compose.yaml), the browser calls the API at /api on this same
// address and the web server forwards it, so any hostname or tunnel that reaches
// the web app reaches the API too, with no cross-origin request to allow.
const apiTarget = process.env.API_PROXY_TARGET;

const nextConfig: NextConfig = {
  experimental: {
    // A zoning lookup after an API restart takes minutes while the City layers load.
    proxyTimeout: 600_000,
  },
  async rewrites() {
    return apiTarget ? [{ source: "/api/:path*", destination: `${apiTarget}/:path*` }] : [];
  },
};

export default nextConfig;
