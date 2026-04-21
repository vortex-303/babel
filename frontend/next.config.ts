import type { NextConfig } from "next";

const backendOrigin =
  process.env.NEXT_PUBLIC_BABEL_BACKEND ?? "http://127.0.0.1:8765";

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  experimental: {
    proxyClientMaxBodySize: "500mb",
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;
